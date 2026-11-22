# TreeMap: firstKey, lastKey, firstEntry, and lastEntry

Once data is organized by key, applications often need to inspect both ends of the order: the earliest and latest timestamps, the smallest and largest IDs, or the first and last records according to a comparator.

`TreeMap` provides four methods for inspecting those endpoints. `firstKey` and `lastKey` return only the key; `firstEntry` and `lastEntry` return a key–value pair. Common sources of confusion involve empty maps, what "first/last" means when the order is reversed, and how the returned entry relates to the underlying map data.

This article uses Java 17. The goal is to choose the right method for reading, handle missing results explicitly, and understand the limits of a mapping snapshot.

## 1. What do the four methods return?

| Method | Result on a non-empty map | When the map is empty | Removes the mapping? |
|---|---|---|---|
| firstKey() | First key in the map's order | Throws NoSuchElementException | No |
| lastKey() | Last key in the map's order | Throws NoSuchElementException | No |
| firstEntry() | First key–value pair | Returns null | No |
| lastEntry() | Last key–value pair | Returns null | No |

`firstKey` and `lastKey` belong to the `SortedMap` contract; the methods that return entries at both ends were added by `NavigableMap`. `TreeMap` implements `NavigableMap`, so it provides all four methods. [Java 17: SortedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedMap.html), [Java 17: NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html)

None of these four methods means "remove from the map." If the intent is to retrieve and remove, that is the `pollFirstEntry` or `pollLastEntry` family. Do not use `poll` just to inspect data and accidentally discard a mapping.

### 1.1. Simple scenario

Suppose a `TreeMap` uses the natural order of `Integer` and contains:

~~~text
10 -> ten
20 -> twenty
30 -> thirty
~~~

Then:

~~~text
firstKey()   -> 10
lastKey()    -> 30
firstEntry() -> pair 10=ten
lastEntry()  -> pair 30=thirty
~~~

The lines `10=ten` and `30=thirty` are just a textual representation of pairs in the example, not a string format you should parse by splitting on the equals sign. In code, retrieve the key with `entry.getKey()` and the value with `entry.getValue()`.

### 1.2. When there is only one mapping

The first key and last key are the same key. Both entries represent the same data pair.

You should not assume that two calls return the exact same entry object instance in memory. What the application cares about is the key and value defined by the contract, not the object identity created to carry the result.

If you need to compare pair contents, use an appropriate content comparison; do not use `==` to require two entry results to be the same object.

## 2. "First" and "last" according to the map's order

### 2.1. Not the first and last insertion

`TreeMap` sorts by the keys' natural order or by the chosen comparator. Inserting `30, 10, 20` in that order does not make `firstKey` equal to `30`. With ascending numeric order, the first key is `10` and the last is `30`.

Insertion order is a different requirement. If the business question is "which record was added first?", do not use a `TreeMap` and interpret `firstEntry` as insertion history.

Similarly, `firstEntry` does not find the smallest value. It returns the mapping with the first key in the map's order. If a priority, price, or timestamp lives inside the value object, a comparator on the keys does not automatically inspect those values.

### 2.2. A reversed comparator swaps both ends

With a descending comparator and keys `10, 20, 30`:

~~~text
map order: 30 -> 20 -> 10
firstKey: 30
lastKey:  10
~~~

The phrase "lowest key" in the ordering contract must be read according to the map's comparator. It does not always mean the smallest number in the usual ascending numeric sense.

This is why you should name results after the domain concept—for example, `earliestByTime` only when the comparator actually orders time from earliest to latest. If the comparator puts higher scores first, `firstEntry` is the top of that ranking rule.

### 2.3. Multi-criteria comparators

Suppose keys have a score and an identifier. If the comparator orders by score descending and then by identifier ascending, the first element has the highest score; when scores are tied, the smaller identifier comes first.

To understand `firstEntry` in this situation, you must read the entire comparator. Do not look only at the key type or method name.

The comparator must also distinguish keys as intended by the data model. If two keys compare as `0`, `TreeMap` treats them as occupying the same key position; there are not two separate mappings for `first` and `last` to choose between. Keeping the fields used for comparison stable is essential so the tree order continues to reflect the data accurately. [Java 17: TreeMap and key ordering rules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

## 3. Return only the key or the whole entry?

### 3.1. When you only need the key

If you already have a non-empty `SortedMap` and only need the first or last boundary key, `firstKey`/`lastKey` expresses that intent directly.

Partial illustration:

~~~java
SortedMap<Integer, String> labels = new TreeMap<>();
labels.put(20, "middle");
labels.put(10, "start");

Integer earliestKey = labels.firstKey();
~~~

The example knows for certain that `labels` has data because the preceding lines just populated it in the same thread. This is different from assuming a shared map "probably still has data" after a separate check.

There is no need to copy the entire `keySet` into a `List` just to grab index `0` or the last element. These methods already express the operation directly on a sorted map.

### 3.2. When you need both key and value

Use `firstEntry`/`lastEntry` to obtain the pair:

~~~java
NavigableMap<Integer, String> orderedLabels = new TreeMap<>();
orderedLabels.put(10, "start");
Map.Entry<Integer, String> first = orderedLabels.firstEntry();
if (first != null) {
    System.out.println(first.getKey() + ": " + first.getValue());
}
~~~

The snippet declares `orderedLabels` as `NavigableMap` so that `firstEntry` is available. If the variable is declared only as `SortedMap` in Java 17, you cannot call `firstEntry` directly through that type.

Variable type declarations are part of the design. A method that needs endpoint entry operations should accept `NavigableMap` as appropriate, rather than accepting `Map` and performing a blind cast.

### 3.3. Avoid fetching the key and then looking up the value when you need a pair

The following pattern performs two separate operations:

~~~java
Integer key = map.firstKey();
String value = map.get(key);
~~~

On a stable, single-threaded map, this may produce the expected result. However, if you need both the key and the value, `firstEntry` expresses the intent more clearly and avoids a separate key lookup.

If another modification happens between the two calls, `key` and `value` may no longer reflect the same data state. A conceptual timeline:

~~~text
T1: read firstKey, receive 10
T2: another operation removes key 10
T3: get(10), no matching mapping remains
~~~

Using a single pair-returning method eliminates the need to manually assemble the pair from two reads. It does not by itself make `TreeMap` thread-safe; concurrent access still requires its own policy.

## 4. Empty maps: exceptions and null are two different contracts

### 4.1. firstKey and lastKey do not use null to signal emptiness

On an empty map, the two key-returning methods throw `NoSuchElementException`. Do not write checks like this:

~~~java
Integer first = map.firstKey();
if (first == null) {
    // Not the right way to check for an empty map with firstKey.
}
~~~

This illustrates a wrong assumption. If the map is empty, execution never reaches the comparison because the exception is already thrown.

If a business invariant requires the map to be non-empty, the exception can help expose violations of that condition. If being empty is a normal state, design an explicit empty-handling branch instead of treating it as an unexpected error.

### 4.2. firstEntry and lastEntry treat empty as a normal outcome

Pattern for reading an endpoint and handling absence:

~~~java
Map.Entry<Integer, String> first = map.firstEntry();
if (first == null) {
    System.out.println("No mappings");
} else {
    System.out.println(first.getKey() + "=" + first.getValue());
}
~~~

Do not call `getKey` or `getValue` before handling the case where `entry` is `null`.

If the application layer uses `Optional` to represent an absent result, wrap the entry itself. Do not wrap only the value and conflate a "null value" with "no mapping."

### 4.3. isEmpty followed by firstKey is not atomic

On a single thread with no intervening modifications, checking `isEmpty` and then calling `firstKey` works. Still, two calls remain two steps.

If the map is shared and another thread can remove elements, it may become empty after the check. Do not use `isEmpty` as a substitute for synchronization.

Likewise, calling `firstEntry` and then `lastEntry` does not automatically produce a consistent snapshot of both ends. If you need both under a single protected state, coordinate the reads under the same data-protection policy.

## 5. A TreeMap entry result is a snapshot of the mapping pair

### 5.1. It does not track subsequent value changes

With a `TreeMap`:

~~~text
initially:       10 -> ten
captured = firstEntry()

update map:      10 -> TEN
captured still:  10 -> ten
new firstEntry:  10 -> TEN
~~~

The entry returned by `TreeMap`'s `firstEntry`/`lastEntry` represents the mapping at the moment the result was created. Replacing a value in the map does not turn the old entry into a pair carrying the new value.

If the key is removed from the map, the captured pair still holds the old result data; it does not automatically become `null`. If a preceding key is inserted, the captured entry does not automatically become the new first entry either.

Therefore, naming the variable `capturedFirst` or `firstAtReadTime` can communicate the semantics better than a name that suggests a live link to the current head.

### 5.2. Do not use setValue to write back

These navigable entries returned by `TreeMap` do not support `setValue`. Calling it throws `UnsupportedOperationException`.

If you want to update the current mapping, use an appropriate map operation—such as `put` with the chosen key—while accounting for the fact that the state may have changed before the update.

Do not generalize this to "every `Map.Entry` is immutable." Entries obtained from an `entrySet` iterator have their own contract. The topic here is specifically the entries returned directly by `TreeMap`'s `firstEntry`/`lastEntry`.

### 5.3. A pair snapshot is not a deep copy

Suppose the value is an `ArrayList`:

~~~text
map:   1 -> List object L
entry: 1 -> same List object L
~~~

If you mutate the contents of `L`, both references see the modified contents. The entry does not allow reassigning the value field via `setValue`, but that does not make the `List` object itself immutable.

If you replace the mapping in the map to point to a new `List`, the old entry still points to the old `List`. Distinguish two actions:

- Replacing the value referenced by the mapping.
- Mutating the internal contents of the value object itself.

The unmodifiable-pair concept of `SimpleImmutableEntry` also distinguishes not supporting value replacement from whether the referenced objects themselves are immutable. You do not need to rely on the concrete class name of `TreeMap`'s entry to use this contract. [Java 17: AbstractMap.SimpleImmutableEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html)

If reporting data must be completely isolated from later mutations, choose an appropriate copying strategy or immutable data type for the value object, rather than merely holding onto the entry.

## 6. Null in three positions means three different things

| Position of null | Meaning to consider |
|---|---|
| The entry variable is null | For `TreeMap`'s `firstEntry`/`lastEntry`, there is no mapping because the map or view is empty |
| `entry.getValue()` is null | May be an existing mapping whose value is `null` |
| The returned key is null | May be a valid `null` key if the comparator allows it |

### 6.1. A null value does not make the entry disappear

A `TreeMap` containing `1 -> null` still has a non-null `firstEntry`. Getting `null` from `entry.getValue()` does not prove the map is empty.

The right check pattern is to test the entry object first, then handle the value according to your data policy.

### 6.2. A null key can be valid with a custom comparator

A `TreeMap` using natural ordering does not allow `null` keys. A comparator that explicitly handles `null`, such as `Comparator.nullsFirst(...)`, can allow them.

When such a map contains a `null` key, `firstKey` can return `null` while the map is non-empty. This does not contradict the empty contract: an empty map still throws an exception; a `null` result in this case is a valid key.

Therefore, do not use `firstKey() == null` as an emptiness check. If you auto-unbox a potentially null `Integer` key to `int`, also account for the unboxing failure on `null`; that is distinct from a missing-element error.

### 6.3. Do not parse printed strings to guess state

A line like `null=unknown` could be the printed form of an entry with a `null` key, not an absent entry. Use the entry object and its accessor methods to determine state, not log string prefixes.

A thorough program checks both `null` values and `null` keys so neither case is conflated with a `null` entry.

## 7. Views have their own endpoint bounds

### 7.1. A range view only considers keys within its region

If the parent map has `10, 20, 30` and the view is `[15, 30)`, the view contains only `20`. Both `firstKey` and `lastKey` of the view are `20`, even though the parent's endpoints are `10` and `30`.

"First" and "last" are always evaluated on the map or view object on which the call is made. Do not take the parent's endpoints and assume they are the endpoints of every `subMap`.

### 7.2. A view can be empty even when the parent is not

The view `[11, 19]` on the data above has no mappings. The view's `firstEntry`/`lastEntry` return `null`, while the view's `firstKey`/`lastKey` throw `NoSuchElementException`.

This matters when querying a time window with no events: the overall map may be huge, yet the queried window is empty. Checking the parent's `size` is no substitute for handling an empty view result.

A view shares backing data. When underlying entries within the range change, subsequent endpoint reads reflect the current range. An entry captured from an earlier read remains the old result.

### 7.3. A descending view swaps the two ends

On `descendingMap` of the same ascending data:

~~~text
original:       10, 20, 30
reversed view:  30, 20, 10

firstEntry of reversed view: 30=thirty
lastEntry of reversed view:  10=ten
~~~

Those are the endpoints under the view's reversed comparator. There is no need to copy and re-sort just to observe the reverse direction.

## 8. Using endpoints in a business decision

### 8.1. Choose the method from the result you need

| Need | Suitable choice |
|---|---|
| Only the first key; data must be non-empty | `firstKey` |
| Only the last key; data must be non-empty | `lastKey` |
| First pair; empty is a normal outcome | `firstEntry` with `null` handling |
| Last pair; empty is a normal outcome | `lastEntry` with `null` handling |
| Retrieve and remove atomically | Consider the corresponding `poll` method |
| Element near a threshold | Use `floor`/`ceiling`/`lower`/`higher`, not the map's global endpoints |

Do not use `lastEntry` to ask for the "newest record" if the key and comparator do not actually represent recency. For example, a map sorted by product code does not make the largest code the most recently updated product.

### 8.2. Control the boundary between reading and acting

An entry may be enough to print a report of the state as read. However, if the next action is to modify or delete that same mapping, evaluate the state at the time of the action.

In a multithreaded system, reading `firstEntry` and then updating by key does not automatically form an atomic operation. A snapshot entry carries the read data; it does not grant exclusive ownership of the mapping.

`TreeMap` is not synchronized by itself. When using a synchronized wrapper, all accesses must follow the same locking mechanism. If you need to read both endpoints under one protected state, hold the lock across both reads.

Partial illustration, with appropriate imports:

~~~java
NavigableMap<Integer, String> shared =
        Collections.synchronizedNavigableMap(new TreeMap<>());

Map.Entry<Integer, String> first;
Map.Entry<Integer, String> last;
synchronized (shared) {
    first = shared.firstEntry();
    last = shared.lastEntry();
}
~~~

This requires that all other accesses also go through the wrapper and follow the same protection rule, without bypassing it via an unsynchronized backing reference. Finishing the read does not keep the map immutable afterward. If values are internally mutable, those objects also need their own policy. [Java 17: Collections.synchronizedNavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedNavigableMap(java.util.NavigableMap))

## 9. Complete Java program

Save the following code to `TreeMapEndpointsDemo.java`. The program uses separate maps to isolate each question: natural order, empty map, single mapping, reversed comparator, pair snapshot, mutable values, `null`s, and views.

Assertions verify the facts the explanation relies on. There are no timing measurements or assumptions about entry object identity.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NoSuchElementException;
import java.util.TreeMap;
import java.util.function.Supplier;

public class TreeMapEndpointsDemo {
    private static TreeMap<Integer, String> sample() {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(30, "thirty");
        map.put(10, "ten");
        map.put(20, "twenty");
        return map;
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected result");
        }
    }

    private static String emptyKeyResult(Supplier<?> operation) {
        try {
            operation.get();
            return "returned";
        } catch (NoSuchElementException exception) {
            return exception.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> natural = sample();
        require(natural.firstKey() == 10 && natural.lastKey() == 30);
        System.out.println("natural/firstKey=" + natural.firstKey()
                + ", lastKey=" + natural.lastKey());
        System.out.println("natural/firstEntry=" + natural.firstEntry()
                + ", lastEntry=" + natural.lastEntry());
        System.out.println("natural/afterReads=" + natural);

        TreeMap<Integer, String> empty = new TreeMap<>();
        System.out.println("empty/firstKey=" + emptyKeyResult(empty::firstKey));
        System.out.println("empty/lastKey=" + emptyKeyResult(empty::lastKey));
        System.out.println("empty/firstEntry=" + empty.firstEntry()
                + ", lastEntry=" + empty.lastEntry());

        TreeMap<Integer, String> single = new TreeMap<>();
        single.put(7, "only");
        require(single.firstKey().equals(single.lastKey()));
        System.out.println("single/firstEntry=" + single.firstEntry()
                + ", lastEntry=" + single.lastEntry());

        TreeMap<Integer, String> reversed =
                new TreeMap<>(Comparator.reverseOrder());
        reversed.putAll(sample());
        require(reversed.firstKey() == 30 && reversed.lastKey() == 10);
        System.out.println("reverse/firstKey=" + reversed.firstKey()
                + ", lastKey=" + reversed.lastKey());
        System.out.println("reverse/firstEntry=" + reversed.firstEntry()
                + ", lastEntry=" + reversed.lastEntry());

        TreeMap<Integer, String> changing = sample();
        Map.Entry<Integer, String> captured = changing.firstEntry();
        changing.put(10, "TEN");
        require(captured.getValue().equals("ten"));
        System.out.println("snapshot/captured=" + captured
                + ", current=" + changing.firstEntry());
        changing.remove(10);
        require(captured.getKey() == 10 && changing.firstKey() == 20);
        System.out.println("snapshot/afterRemove=" + captured
                + ", newFirst=" + changing.firstEntry());
        boolean rejected = false;
        try {
            captured.setValue("forbidden");
        } catch (UnsupportedOperationException exception) {
            rejected = true;
        }
        require(rejected);
        System.out.println("snapshot/setValueRejected=" + rejected);

        TreeMap<Integer, List<String>> mutable = new TreeMap<>();
        mutable.put(1, new ArrayList<>(List.of("draft")));
        Map.Entry<Integer, List<String>> shallow = mutable.firstEntry();
        mutable.get(1).add("reviewed");
        require(shallow.getValue().equals(List.of("draft", "reviewed")));
        System.out.println("shallow/afterObjectMutation=" + shallow.getValue());
        mutable.put(1, new ArrayList<>(List.of("replacement")));
        System.out.println("shallow/oldValue=" + shallow.getValue()
                + ", currentValue=" + mutable.firstEntry().getValue());

        TreeMap<Integer, String> nullValue = new TreeMap<>();
        nullValue.put(1, null);
        Map.Entry<Integer, String> present = nullValue.firstEntry();
        require(present != null && present.getValue() == null);
        System.out.println("nullValue/entryPresent=" + (present != null)
                + ", key=" + present.getKey() + ", value=" + present.getValue());

        TreeMap<String, String> nullKey =
                new TreeMap<>(Comparator.nullsFirst(
                        Comparator.<String>naturalOrder()));
        nullKey.put("A", "alpha");
        nullKey.put(null, "unknown");
        require(!nullKey.isEmpty() && nullKey.firstKey() == null);
        System.out.println("nullKey/empty=" + nullKey.isEmpty()
                + ", firstKey=" + nullKey.firstKey());
        System.out.println("nullKey/firstEntry=" + nullKey.firstEntry());

        TreeMap<Integer, String> parent = sample();
        NavigableMap<Integer, String> window =
                parent.subMap(15, true, 30, false);
        require(window.firstKey() == 20 && window.lastKey() == 20);
        System.out.println("view/firstKey=" + window.firstKey()
                + ", lastKey=" + window.lastKey());
        NavigableMap<Integer, String> emptyWindow =
                parent.subMap(11, true, 19, true);
        require(parent.size() == 3 && emptyWindow.isEmpty());
        System.out.println("view/parentSize=" + parent.size()
                + ", emptyWindowFirst=" + emptyWindow.firstEntry());
        System.out.println("view/emptyWindowFirstKey="
                + emptyKeyResult(emptyWindow::firstKey));

        NavigableMap<Integer, String> backward = parent.descendingMap();
        require(backward.firstKey().equals(parent.lastKey()));
        System.out.println("descending/firstEntry=" + backward.firstEntry()
                + ", lastEntry=" + backward.lastEntry());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 TreeMapEndpointsDemo.java
java TreeMapEndpointsDemo
~~~

Stdout from the verification run:

~~~text
natural/firstKey=10, lastKey=30
natural/firstEntry=10=ten, lastEntry=30=thirty
natural/afterReads={10=ten, 20=twenty, 30=thirty}
empty/firstKey=NoSuchElementException
empty/lastKey=NoSuchElementException
empty/firstEntry=null, lastEntry=null
single/firstEntry=7=only, lastEntry=7=only
reverse/firstKey=30, lastKey=10
reverse/firstEntry=30=thirty, lastEntry=10=ten
snapshot/captured=10=ten, current=10=TEN
snapshot/afterRemove=10=ten, newFirst=20=twenty
snapshot/setValueRejected=true
shallow/afterObjectMutation=[draft, reviewed]
shallow/oldValue=[draft, reviewed], currentValue=[replacement]
nullValue/entryPresent=true, key=1, value=null
nullKey/empty=false, firstKey=null
nullKey/firstEntry=null=unknown
view/firstKey=20, lastKey=20
view/parentSize=3, emptyWindowFirst=null
view/emptyWindowFirstKey=NoSuchElementException
descending/firstEntry=30=thirty, lastEntry=10=ten
~~~

The code compiled with `--release 17` and ran successfully. The release option specifies the API level and compatible target bytecode; it does not assert that the executing JVM is specifically JDK 17.

## 10. Explaining the output groups

### 10.1. Natural, empty, and single

The three `natural` lines show that endpoint reads do not remove data. The map still contains `10, 20, 30` after the calls.

The `empty` lines contrast the two ways of signaling emptiness: key-returning methods throw `NoSuchElementException`, while entry-returning methods return `null`.

In `single`, both first and last represent `7=only`. The program does not compare the two entries with `==` because there is no guarantee that they are the same object instance.

### 10.2. Reverse and descending

A map created with a descending comparator has `firstKey` equal to `30` and `lastKey` equal to `10`. The `descending` view of an ascending map has the corresponding endpoints.

The word `first` stays the same, yet the result depends on the ordering rule. This is the first thing to check when a "top of list" report appears inverted relative to expectations.

### 10.3. Snapshot

The `captured` pair remains `10=ten` after the map becomes `10=TEN`. After removing `10`, the old pair can still be read as captured result data, while the map's current head is `20=twenty`.

`setValue` is rejected. This illustrates that a navigable entry is not a handle for directly mutating the current head of the tree.

### 10.4. Shallow

After adding `"reviewed"` to the same `List`, the old entry sees `[draft, reviewed]`. After the map is assigned a new `List`, the old entry still holds the old `List`, while the new entry yields `[replacement]`.

Thus, a pair snapshot isolates mapping reference replacements, but does not automatically copy the contents of the `List`.

### 10.5. Null and view

An entry in a map with a `null` value still exists. A map that allows `null` keys is not empty even though `firstKey` returns `null`. Checks inspect the entry object and `isEmpty` explicitly, rather than inferring state from printed output.

A single-key view returns the same key at both ends. An empty view returns a `null` `firstEntry` even though the parent has three mappings. The emptiness belongs to the queried range.

## 11. Common pitfalls

| Pitfall | Correction in mental model |
|---|---|
| `first` is the element inserted first | `first` follows the current key order |
| `last` is the largest value | `last` is chosen by key and comparator |
| `firstKey` returns `null` on an empty map | An empty map throws `NoSuchElementException` |
| `entry.getValue()` being `null` means there is no entry | Check the entry itself first |
| `firstKey` being `null` means the map is empty | A comparator may allow `null` keys |
| The returned entry stays updated with the map | `TreeMap` navigable entries are pair snapshots |
| Calling `setValue` on `firstEntry` updates the head of the tree | The operation is unsupported |
| An entry snapshot is a deep copy | Keys and values may still be shared references |
| Because the parent map is non-empty, every view has endpoints | Each view has its own range and can be empty |
| Reading both ends in two calls snapshots the whole map | Needs a protection policy if concurrent writes occur |
| The four read methods remove elements | They do not remove mappings |
| Changing the variable type to `Map` discards the order | A `TreeMap` object's order does not change with the reference type |

## 12. Exercises and solutions

### Exercise 1. Identifying the right endpoints

A natural-order `TreeMap` receives keys `80, 10, 50` in that insertion order. What are `firstKey` and `lastKey`? What if a descending comparator is used?

**Solution:** Natural order gives `10` and `80`. Descending order gives `80` and `10`. Insertion order does not determine the endpoints; the comparator or natural order does.

### Exercise 2. Choosing the empty contract

A screen may initially have no records and needs to display the last pair if one exists. Should you choose `lastKey` followed by `get`, or `lastEntry`? What must you handle before reading the value?

**Solution:** `lastEntry` directly expresses fetching the pair and returns `null` when empty. You must check that the entry is non-null before calling `getKey`/`getValue`. The value inside the entry may also be `null` depending on the data policy.

### Exercise 3. Captured pair

A map has `1=old` and `2=other`. You call `firstEntry`, then `put(1, "new")`, and then remove `1`. Does the previously captured entry automatically become `2=other`?

**Solution:** No. A navigable entry is a snapshot of the pair `1=old`. A new `firstEntry` read after the removal yields `2=other`. The old result does not automatically track the map's current head.

### Exercise 4. Cannot edit the entry, yet the List still changes

The value of `firstEntry` is an `ArrayList`. `setValue` is unsupported, yet adding an element through `entry.getValue()` can still modify the `List`. Is this a contradiction?

**Solution:** No. Not supporting replacement of the pair's value field does not make the `List` object immutable. The entry holds a reference to the `List`; operations on the `List` itself still depend on the `List` contract and your data policy.

### Exercise 5. Empty view

The parent contains `10, 20, 30`. The view is `subMap(11, true, 19, true)`. How do `firstEntry` and `firstKey` behave on the view?

**Solution:** The view has no mappings. `firstEntry` returns `null`; `firstKey` throws `NoSuchElementException`. A non-empty parent does not alter the view's empty contract.

### Exercise 6. Null key

A `TreeMap` uses a `nullsFirst` comparator and contains a `null` key along with key `"A"`. `firstKey` returns `null`. Can you use that result to report that the map is empty?

**Solution:** No. That is a valid `null` key under the chosen order. You can read `firstEntry` and inspect the entry object, or check `isEmpty` in a valid access context. Calling `firstKey` on an empty map would throw an exception.

### Exercise 7. Two-step read with an intervening change

Code reads `firstKey` and then calls `get` with that key on a shared map. Between the two steps, the mapping is removed. Why can a `null` result from `get` not simply be interpreted as "the map had no data initially"?

**Solution:** The two steps observed different points in time. The key existed at the first read but may be gone by the second; furthermore, a `null` value can also be valid data. If you need a pair, use an entry-returning method; if you need concurrent consistency or a follow-up action, design a protection policy covering the entire required scope.

## 13. Before choosing one of the four methods

Determine which ordering is in use, whether you need only the key or the whole pair, whether emptiness is a normal state, and whether the result will be used purely as read data or as the basis for a subsequent mutation.

All four methods inspect the two ends. Differences in return type and empty-state signaling help applications express their intent accurately; understanding pair snapshots prevents mistaking a read result for a live link to current data.
