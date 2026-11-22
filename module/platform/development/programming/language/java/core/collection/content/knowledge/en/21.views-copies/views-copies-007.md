# Source-Backed vs. Standalone Map.Entry

## 1. Same Entry Type, Different Ownership Semantics

`Map.Entry<K,V>` represents a key–value pair. Looking at that signature, you know you can call `getKey()` and `getValue()`, while `setValue(v)` is an optional operation.

However, the interface type does not tell you whether the pair is **still connected to a map** or **just standalone data**. This distinction is decisive when you want to update a map, keep a result for later use, return data across an API boundary, or take a snapshot.

Consider two scenarios:

~~~text
Scenario A:
entry currently returned by a map iterator
        |
        +--- setValue supported by source ---> value in the map changes

Scenario B:
entry created with new SimpleEntry(...)
        |
        +--- setValue ---> only the standalone pair changes
~~~

The `Map.Entry` documentation clearly distinguishes between modifiable and unmodifiable entries, and between standalone entries and entries that represent a mapping in a map view. For an iterator entry, the connection to the source has a validity scope tied to the iteration. [Java 17: Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

This article helps you answer three separate questions: where the entry came from, whether modifying it writes to any map, and whether the underlying data is still shared. The full program uses **Java 17 or later**, including `Map.Entry.copyOf` introduced in Java 17.

## 2. Three Axes That Must Not Be Conflated

An entry should be evaluated along three axes:

| Axis | Two Common Possibilities | Practical Question |
| --- | --- | --- |
| Source connection | Backed by a map or standalone | Can modifying the entry affect a map? |
| Replacing the pair's value | `setValue` supported or rejected | Can the entry's value reference be changed? |
| Key/value state | Immutable or mutable objects | Even if the pair's reference does not change, can the internal data change? |

A standalone entry can be **modifiable**, such as `SimpleEntry`. An unmodifiable entry can hold a **mutable value**, such as an `ArrayList`. An entry being iterated over a read-only map is not a backdoor for updating the source.

Therefore, terms like "copy", "immutable", or "view" must be tied to the exact data layer being discussed. Do not use a single word to infer all permissions and lifecycles.

## 3. Entries Obtained from an entrySet Iterator

### 3.1. Value updates within the supported iteration scope

Example with a modifiable `LinkedHashMap`:

~~~java
for (Map.Entry<String, Integer> entry : stock.entrySet()) {
    if (entry.getKey().equals("sku-A")) {
        Integer oldValue = entry.setValue(11);
    }
}
~~~

This is an illustrative snippet placed inside a method with the appropriate imports and `stock` source.

Calling `setValue(11)` replaces the value of the current mapping in the map, if the source supports that operation. It returns the previous value—not a `boolean` flag and not a new entry.

The key is not changed by `setValue`. If the source previously had `sku-A=10`, after the update it has `sku-A=11`. The number of mappings remains the same.

`Map.entrySet` allows `setValue` on entries returned by its iterator to the extent supported by the source, alongside removal via the iterator. [Java 17: Map.entrySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entrySet()).

### 3.2. Reassigning the entry variable does not update the source

The following snippet only reassigns a local variable:

~~~java
entry = new AbstractMap.SimpleEntry<>(entry.getKey(), 11);
~~~

It does not call a map update method. The `entry` variable now points to a new pair, but the original mapping does not automatically receive that value.

Similarly, assigning `value = 11` to a previously read value variable does not turn that variable into a reference slot inside the map.

Updating the source must go through an API with a write-through contract, such as a valid `setValue` call on a connected entry or a map update method.

### 3.3. Lifecycle: do not keep an iterator entry as a long-lived handle

The connection guarantee of an iterator entry is not a promise that "this entry will track that key forever." The Java 17 contract limits entry usage to the iteration; if the map is modified after the entry is returned by the iterator—other than through `setValue` itself as specified—you must not continue relying on the old entry's behavior as a stable API.

In particular, do not grab an entry, finish the loop, remove the key from the map, and then call `setValue` on that entry expecting it to re-insert the key or reliably throw a specific exception.

A single test on one implementation might still observe stale data or an internal node. That does not elevate it to an interface guarantee. If you need to use it later, create a standalone pair while the entry is still being validly read.

### 3.4. setValue is not a substitute for removal

If the source permits `null`, `entry.setValue(null)` sets the value to `null`; the key still exists. If the source forbids `null`, the operation may be rejected according to its constraints.

To remove the current mapping during iteration, use `Iterator.remove` following iterator rules or choose an appropriate filtering operation. To change a key, you must design a different operation; an entry has no `setKey`.

## 4. Ways to Create a Standalone Entry

### 4.1. SimpleEntry: a standalone pair whose value can be replaced

~~~java
Map.Entry<String, Integer> local =
        new AbstractMap.SimpleEntry<>("sku-A", 50);
Integer oldValue = local.setValue(60);
~~~

The `local` pair becomes `sku-A=60`; `oldValue` is `50`. No map is automatically updated just because another map in the program also contains the key `sku-A`.

`SimpleEntry` holds its own key and value, supports `setValue`, and does not belong to any map's entry-set view. It has a constructor taking two components or taking an existing entry to copy the pair. [Java 17: AbstractMap.SimpleEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleEntry.html).

If you want to put this pair's data into a map, you must do so explicitly:

~~~java
stock.put(local.getKey(), local.getValue());
~~~

Modifying `local` again afterward does not automatically modify the map. Calling `put` takes the key and value; it does not establish a live link to this standalone entry object.

### 4.2. SimpleImmutableEntry: standalone, does not support replacing the pair's value

~~~java
Map.Entry<String, Integer> saved =
        new AbstractMap.SimpleImmutableEntry<>("sku-A", 50);
~~~

This standalone pair does not allow changing the value via `setValue`; that operation throws `UnsupportedOperationException` on this concrete class. The key/value references are retained, but the objects they point to may still be mutable.

The class documentation explicitly notes that the unmodifiability of the pair does not imply deep immutability of the key and value. [Java 17: AbstractMap.SimpleImmutableEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html).

If you use the constructor that takes an entry, you copy the entry's components at the time of a valid read. You do not retain the source object's entry-set connection.

### 4.3. Map.entry(k, v): concise factory for an unmodifiable pair

~~~java
Map.Entry<String, Integer> pair = Map.entry("sku-A", 50);
~~~

The created pair is standalone, forbids `setValue`, and does not accept a `null` key or value. Creating the entry alone does not insert it into any map.

Entries returned by this factory are value-based objects; do not rely on reference identity `==` or use them as synchronization locks. They are not guaranteed to be newly allocated distinct objects on every call. [Java 17: Map.entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entry(K,V)).

If you need long-term storage or to pass data across application layers, a clearly named domain type can express intent better than a generic pair. Still, `Map.entry` is a useful choice when you genuinely need the `Map.Entry` contract and the data domain has no `null` values.

### 4.4. Map.Entry.copyOf(existing): detaching a pair from its source since Java 17

~~~java
Map.Entry<String, Integer> snapshot = Map.Entry.copyOf(entry);
~~~

The result is not backed by any map, does not support `setValue`, and has the same component characteristics as `Map.entry`. The entry argument, its key, and its value must all be non-`null`.

Do not verify "detachment" by asserting `snapshot != entry`. If the input is already a suitable standalone entry, the factory may reuse the object. What you should verify is the data contract and the absence of a write-through path to the source map through that pair, not an unpromised identity condition.

### 4.5. Quick comparison table

| How obtained / created | Source-backed? | Replace value via setValue? | Null components |
| --- | --- | --- | --- |
| Iterator entry of a modifiable source, during iteration | Connected per contract | Depends on source; e.g., LinkedHashMap supports it | Per source |
| `new SimpleEntry(k, v)` | No | Yes on this class | Can hold `null` |
| `new SimpleImmutableEntry(k, v)` | No | No on this class | Can hold `null` |
| `Map.entry(k, v)` | No | No | Rejected |
| `Map.Entry.copyOf(e)` | No | No | Rejected |
| Entry from an unmodifiable map view | No permission to update source | Blocked through this path | Per source / wrapper |

"Can hold `null`" for the two standalone entry classes applies to the pair itself. When inserting its components into a map that forbids `null`, that map still rejects them.

## 5. Creating Entry Snapshots at the Right Layer

### 5.1. Copying the collection does not copy each entry

The following snippet creates a new list:

~~~java
List<Map.Entry<String, Integer>> saved =
        new ArrayList<>(stock.entrySet());
~~~

However, the list elements are still the entry objects obtained from the source. You cannot simply look at `new ArrayList` and conclude that the pairs have been detached into standalone entries.

Even `List.copyOf(stock.entrySet())` only addresses the contract of the outer list; it does not turn each element into a `Map.Entry.copyOf`.

### 5.2. Copying each pair during valid iteration

For domains without `null` keys or values:

~~~java
List<Map.Entry<String, Integer>> snapshots = new ArrayList<>();
for (Map.Entry<String, Integer> entry : stock.entrySet()) {
    snapshots.add(Map.Entry.copyOf(entry));
}
~~~

Each entry is read and copied inside the loop. Afterward, you can retain the standalone pairs even if the map continues to add, remove, or replace mappings.

If you need standalone pairs that can be modified locally, create `new SimpleEntry<>(entry)`. If `null` is present and you want pairs that forbid replacing the value, you can create `new SimpleImmutableEntry<>(entry)` according to your data policy.

The outer list here is an `ArrayList`, so elements can still be added to or removed from the list. Forbidding `setValue` on the pairs does not automatically make the list unmodifiable. If you want both layers restricted, you need an additional choice for the list layer.

### 5.3. Streams also require an entry transformation step

In Java 17, you can write:

~~~java
List<Map.Entry<String, Integer>> snapshots =
        stock.entrySet().stream()
                .map(Map.Entry::copyOf)
                .toList();
~~~

The crucial step is `map(Map.Entry::copyOf)`. Plain `entrySet().stream().toList()` does not detach each pair from the source.

`Stream.toList` in this usage produces an unmodifiable list, while the entry permissions are determined by the entry creation step. The `Map.Entry` documentation itself recommends copying each pair to obtain source-independent data; `null` rules still apply.

## 6. An Unmodifiable Entry Can Still Share Mutable State

Example:

~~~java
List<String> tags = new ArrayList<>(List.of("a"));
Map.Entry<String, List<String>> pair = Map.entry("tags", tags);
Map.Entry<String, List<String>> snapshot = Map.Entry.copyOf(pair);
tags.add("b");
~~~

`snapshot.getValue()` sees `[a, b]` because the pair holds a reference to the same `tags` list. You did not change the entry's value reference; you mutated the value object itself.

Model:

~~~text
pair.value --------+
                   +----> mutable List tags
snapshot.value ----+
~~~

This is a **shallow copy**. Independence from the source map describes the pair's relationship to the mapping; it does not imply that every object behind a reference has been cloned.

### 6.1. When the nested data is a list of strings

You can create a separate, unmodifiable list value:

~~~java
Map.Entry<String, List<String>> safe =
        Map.entry("tags", List.copyOf(tags));
~~~

Adding elements to the original `tags` list afterward does not grow `safe`'s list. With immutable string elements, this provides the level of independence needed for the example.

`List.copyOf` does not accept `null` and does not deep-copy each element object. If the list elements are mutable objects, you still need to determine the appropriate copy depth. [Java 17: List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Do not call every pair containing an unmodifiable collection "deeply immutable" when the elements inside can still change.

### 6.2. Keys can also be mutable objects

Not having `setKey` does not mean the key object is immutable. An entry can hold a reference to a custom key with mutable fields.

If that same object is being used as a key in a map or a member of a hash set, mutating fields that affect equality/hashing can break lookup assumptions. Choose key types that are stable for their intended use; a standalone unmodifiable entry does not make a key stable.

## 7. Entries from Navigation APIs Are Usually Snapshots

`NavigableMap` provides `firstEntry`, `lastEntry`, `floorEntry`, `ceilingEntry`, and polling methods such as `pollFirstEntry`. They return a pair representing a mapping at the time of the call, which is different from iterating over an entry set.

The `NavigableMap` documentation describes navigation entries as snapshots and notes that they generally do not support `setValue`. The demo program uses `TreeMap.firstEntry` to verify this concretely. [Java 17: NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html).

Example with source `{1=one, 2=two}`:

~~~text
before = firstEntry()             before is 1=one
source put(1, ONE)                source is {1=ONE, 2=two}
before                            still describes 1=one
before.setValue(X)                rejected on this snapshot entry
~~~

To update the map, use the appropriate map API. To find the first mapping and update it in a multithreaded environment as a unified operation, you need a dedicated concurrency contract; obtaining a snapshot does not reserve the key or mapping.

### 7.1. Poll returns an entry for the already-removed mapping

`pollFirstEntry` both removes the first mapping and returns information about that mapping, or returns `null` if none exists. The resulting entry is not an implicit way to put the mapping back into the source via `setValue`.

If you want to restore or insert data into the map, you must call an explicit map operation, accounting for whether the key has already been re-inserted by another operation.

### 7.2. Connection to SequencedMap since Java 21

Since Java 21, `SequencedMap` specifies that `firstEntry`, `lastEntry`, `pollFirstEntry`, and `pollLastEntry` return snapshots that do not support modifying the source via `setValue`.

This interface also emphasizes that an entry obtained in another way—such as `sequencedEntrySet().getFirst()`—does not share the same general guarantees regarding connection or modifiability. Do not infer solely from the `Map.Entry` type and the word "first" that both retrieval methods have the same contract. [Java 21: SequencedMap, entry lifecycle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

This note refers to the Java 21 API. The main program does not use `SequencedMap` so that it still compiles targeting Java 17.

## 8. Read-Only Wrappers and Returning Entries Across APIs

`Collections.unmodifiableMap(source)` blocks modifying the map through the wrapper's map methods and collection views, including the `setValue` path through entries it provides.

It is still a view of the source, not a fixed-state copy. Changes to the original map through another reference can be observed through the wrapper. [Java 17: Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).

Two goals should be separated:

- **not granting map update permission:** use an appropriate wrapper or return a standalone pair;
- **preserving data at a point in time:** copy to the required depth under consistent read conditions.

Wrapping only the outer collection, such as `Collections.unmodifiableSet(source.entrySet())`, does not automatically strip `setValue` permission from the entry objects inside. Protecting one layer does not automatically protect the element layer.

If a function finds the "best item" and returns an entry for later processing, a standalone pair usually expresses the result data more clearly than an iterator entry with a stretched lifecycle. If the function genuinely needs to grant a controlled update command, an update API keyed by business key and condition is usually clearer than returning an entry handle.

## 9. equals and hashCode Do Not Tell Whether an Entry Is Source-Backed

Standard entries compare both key and value. A `SimpleEntry("item", 1)` and `Map.entry("item", 1)` can be `equals` to each other even though their modifiability and origin differ.

After `simple.setValue(2)`, that pair is no longer equal to `item=1`. Because equality and hash codes depend on the components, changing the value can change the entry's `hashCode`.

Therefore:

- being `equals` does not prove identical update permissions;
- being `equals` does not prove a shared source;
- `==` is not a valid check for value-based factories;
- you should not place an entry with mutable contents as a hash key or hash-set member and then mutate components affecting equality/hashing while it resides in that structure.

`Set` warns about elements whose state changes in a way that affects equality while still in the set. [Java 17: Set, mutable elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

If you need a long-lived identifier for a mapping, use a key with an appropriate contract; if you need to record a pair, use a value-based data pair that is stable to the degree required by the recording.

## 10. Complete Program

Save the entire code below to **`EntryOwnershipDemo.java`**. The program does not retain or use iterator entries after iteration ends. Any pairs that need to be kept are created as standalone entries right inside the loop.

The primary source is a `LinkedHashMap` in default insertion order so stdout is predictable. It does not make all other maps share the same order. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class EntryOwnershipDemo {
    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException | NullPointerException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("sku-A", 10);
        stock.put("sku-B", 20);
        List<Map.Entry<String, Integer>> snapshots = new ArrayList<>();
        List<AbstractMap.SimpleEntry<String, Integer>> localCopies = new ArrayList<>();

        for (Map.Entry<String, Integer> entry : stock.entrySet()) {
            if (entry.getKey().equals("sku-A")) {
                int previous = entry.setValue(11);
                System.out.println("connected setValue previous: " + previous);
            }
            snapshots.add(Map.Entry.copyOf(entry));
            localCopies.add(new AbstractMap.SimpleEntry<>(entry));
        }
        System.out.println("source after iteration: " + stock);
        System.out.println("captured snapshots: " + snapshots);

        stock.put("sku-A", 15);
        stock.remove("sku-B");
        stock.put("sku-C", 30);
        System.out.println("source changed later: " + stock);
        System.out.println("snapshots stay: " + snapshots);
        System.out.println("mutable copies stay: " + localCopies);

        AbstractMap.SimpleEntry<String, Integer> local = localCopies.get(0);
        int previous = local.setValue(99);
        System.out.println("local setValue previous: " + previous + ", local=" + local);
        System.out.println("source unaffected by local edit: " + stock);
        stock.put(local.getKey(), local.getValue());
        local.setValue(100);
        System.out.println("explicit put then local edit: local=" + local + ", source=" + stock);

        Map.Entry<String, Integer> frozen = Map.Entry.copyOf(local);
        local.setValue(101);
        System.out.println("copyOf detached pair: " + frozen + ", local now=" + local);
        System.out.println("copyOf setValue: " + failure(() -> frozen.setValue(500)));

        Map.Entry<String, Integer> literal = Map.entry("fixed", 7);
        Map.Entry<String, Integer> immutable =
                new AbstractMap.SimpleImmutableEntry<>("fixed", 7);
        System.out.println("Map.entry setValue: " + failure(() -> literal.setValue(8)));
        System.out.println("SimpleImmutableEntry setValue: "
                + failure(() -> immutable.setValue(8)));
        System.out.println("independent pair auto-inserted: " + stock.containsKey("fixed"));

        AbstractMap.SimpleEntry<String, Integer> nullLocal =
                new AbstractMap.SimpleEntry<>(null, null);
        Map.Entry<String, Integer> nullFrozen =
                new AbstractMap.SimpleImmutableEntry<>(null, null);
        System.out.println("independent null pair: " + nullFrozen);
        System.out.println("null local old value: " + nullLocal.setValue(10)
                + ", now=" + nullLocal);
        System.out.println("Map.entry null value: "
                + failure(() -> Map.entry("N", null)));
        System.out.println("copyOf null components: "
                + failure(() -> Map.Entry.copyOf(nullFrozen)));

        NavigableMap<Integer, String> sorted = new TreeMap<>();
        sorted.put(1, "one");
        sorted.put(2, "two");
        Map.Entry<Integer, String> first = sorted.firstEntry();
        sorted.put(1, "ONE");
        System.out.println("navigation snapshot: " + first + ", current=" + sorted);
        System.out.println("navigation setValue: " + failure(() -> first.setValue("X")));
        Map.Entry<Integer, String> removed = sorted.pollFirstEntry();
        System.out.println("polled snapshot: " + removed + ", source=" + sorted);

        Map<String, Integer> readOnly = Collections.unmodifiableMap(stock);
        System.out.println("read-only iterator entry: " + failure(() -> {
            for (Map.Entry<String, Integer> entry : readOnly.entrySet()) {
                entry.setValue(0);
            }
        }));

        List<String> tags = new ArrayList<>(List.of("a"));
        Map.Entry<String, List<String>> pair = Map.entry("tags", tags);
        Map.Entry<String, List<String>> shallow = Map.Entry.copyOf(pair);
        tags.add("b");
        System.out.println("unmodifiable pair shares payload: " + shallow);
        Map.Entry<String, List<String>> protectedPayload =
                Map.entry("tags", List.copyOf(tags));
        tags.add("c");
        System.out.println("shallow after another edit: " + shallow);
        System.out.println("copied string-list payload: " + protectedPayload);
        System.out.println("protected payload add: "
                + failure(() -> protectedPayload.getValue().add("d")));

        AbstractMap.SimpleEntry<String, Integer> left =
                new AbstractMap.SimpleEntry<>("item", 1);
        Map.Entry<String, Integer> right = Map.entry("item", 1);
        System.out.println("equal across entry implementations: " + left.equals(right));
        left.setValue(2);
        System.out.println("equal after value replacement: " + left.equals(right));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 EntryOwnershipDemo.java
java EntryOwnershipDemo
~~~

Use JDK 17 or later to compile at release level 17 and a Java 17 or later runtime to run. The example was compiled with release 17 and run successfully on OpenJDK 24.0.2.

Exact stdout:

~~~text
connected setValue previous: 10
source after iteration: {sku-A=11, sku-B=20}
captured snapshots: [sku-A=11, sku-B=20]
source changed later: {sku-A=15, sku-C=30}
snapshots stay: [sku-A=11, sku-B=20]
mutable copies stay: [sku-A=11, sku-B=20]
local setValue previous: 11, local=sku-A=99
source unaffected by local edit: {sku-A=15, sku-C=30}
explicit put then local edit: local=sku-A=100, source={sku-A=99, sku-C=30}
copyOf detached pair: sku-A=100, local now=sku-A=101
copyOf setValue: UnsupportedOperationException
Map.entry setValue: UnsupportedOperationException
SimpleImmutableEntry setValue: UnsupportedOperationException
independent pair auto-inserted: false
independent null pair: null=null
null local old value: null, now=null=10
Map.entry null value: NullPointerException
copyOf null components: NullPointerException
navigation snapshot: 1=one, current={1=ONE, 2=two}
navigation setValue: UnsupportedOperationException
polled snapshot: 1=ONE, source={2=two}
read-only iterator entry: UnsupportedOperationException
unmodifiable pair shares payload: tags=[a, b]
shallow after another edit: tags=[a, b, c]
copied string-list payload: tags=[a, b]
protected payload add: UnsupportedOperationException
equal across entry implementations: true
equal after value replacement: false
~~~

### 10.1. Write-through inside the loop, copy before leaving the loop

The iterated `sku-A` entry updates the source from `10` to `11` and returns the previous value `10`. Both the unmodifiable snapshot and the modifiable pair copy are created after that update step, so both record `sku-A=11`.

After the loop, the source changes to `{sku-A=15, sku-C=30}`. The copied pairs still hold `sku-A=11` and `sku-B=20`. Removing `sku-B` from the source does not cause the standalone pairs to lose data.

### 10.2. Editing a local pair and applying data to the map are two separate actions

`local.setValue(99)` only changes the local pair. The subsequent `stock.put(local.getKey(), local.getValue())` call is what updates the map to `sku-A=99`.

Changing `local` again to `100` does not cause the map to receive `100`. `copyOf(local)` captures a standalone `sku-A=100` pair; changing `local` to `101` does not change that snapshot either.

### 10.3. null, navigation, and wrappers

The two standalone entry classes can hold `null` components, whereas the two factories `Map.entry` and `Map.Entry.copyOf` tested in the example reject `null` components.

The first entry of `TreeMap` retains its value from before the map was updated and rejects `setValue`. The entry from `pollFirstEntry` describes the mapping that was already removed. Entries obtained through the read-only map also reject updates.

### 10.4. Pair immutability differs from nested data immutability

The `tags` pair does not change its reference, yet the shared value list still grows from `[a]` to `[a, b]` and then `[a, b, c]`.

The version holding `List.copyOf(tags)` was created before `c` was added, so it stays `[a, b]` and rejects adding `d`. This suffices for a list of strings; it is not automatically a deep-copy solution for every value type.

## 11. Storing and Passing Entries in Production Code

### 11.1. Returning data for later processing

When receiving an entry from a source, determine whether the receiver will use it within the same iteration or afterward. If it outlives the iteration scope, copy the pair or convert it into an appropriate domain type right at the time of a valid read.

For history or events, you also need to check whether nested values can change. An event meaning "recorded value at time T" fails its purpose if it merely holds a reference to a list that is mutated later.

### 11.2. A single-pair snapshot is not an atomic whole-map snapshot

Copying each entry guarantees that the new pair is no longer a write-through path into the source mapping. It does not automatically guarantee that all pairs in a snapshot list were read at the exact same instant if the source is changing concurrently.

Even concurrent sources like `ConcurrentHashMap` have their own aggregate observation semantics; iterators can reflect states from different points in time during traversal. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

If the requirement is a consistent report across multiple mappings, you must use an appropriate state-reading or publishing mechanism at the owning layer. Do not use the word "snapshot" on individual pairs to implicitly promise a transaction over the entire dataset.

### 11.3. Do not use a snapshot as an unconditional update license

Suppose you copy `product=10`, and then another task changes the source to `product=12`. Later taking the value from the old snapshot to `put` back can overwrite the newer data.

Standalone entries help manage data lifecycle, but they do not resolve update conflicts. If updates must be conditioned on an expected value, choose a conditional API and concurrency mechanism suited to the source.

### 11.4. Testing against committed behavior

A good test suite can verify that:

- a valid `setValue` inside a loop on a supporting source updates the right map;
- a standalone pair edited locally does not automatically write to the source;
- snapshots retain their pairs after subsequent source updates;
- unsupported operations throw the expected exception for the chosen class/factory;
- nested data is shared or copied to the designed depth.

Do not write tests that use an out-of-scope iterator entry and assert that it "should" still be linked or "should" be detached. Avoid turning out-of-contract behavior into a requirement that must be maintained.

## 12. Common Pitfalls

| Misconception | What Is Missed | How to Handle |
| --- | --- | --- |
| Every Map.Entry is a live slot in a map | An entry may be standalone or a snapshot | Identify where it was created/obtained |
| Every setValue modifies the source | SimpleEntry only modifies its own pair | Use the update API matching your intent |
| An iterator entry can be kept forever | The connection is scoped to the iteration | Copy when you need to retain it |
| new ArrayList(entrySet) detaches all pairs | Only the outer collection is new | Copy each entry individually |
| Map.entry inserts data automatically | The factory only creates a pair | Call map.put if you want to add it |
| copyOf must return a != object | The factory may reuse an instance | Verify the value-based contract |
| The word Immutable makes nested data immutable | References can point to mutable objects | Copy/wrap at each layer |
| Navigation entries always allow source writes | Many APIs return unmodifiable snapshots | Use the appropriate map API |
| Equal pairs have the same edit permissions | Equality only checks key and value | Separate operation permissions from data |
| Copying pairs resolves all contention | Stale data and concurrent edits still occur | Design consistency and update conditions |

## 13. Practice Exercises with Answers

### Exercise 1 — Origin determines effect

You have an entry `e` returned by an iterator of a modifiable `LinkedHashMap` inside a loop, and `p = new SimpleEntry<>(e)`. You call `e.setValue(8)` and then `p.setValue(9)` under valid conditions. Which call updates the source?

**Answer:** `e.setValue(8)` updates the source mapping if supported. `p` is a standalone pair; `p.setValue(9)` only changes that pair. The moment `p` is created determines the initial value it records, but creates no live connection afterward.

### Exercise 2 — Keeping an entry for later

A function iterates over a map and directly returns a matching iterator entry for the caller to modify the next day. Can you rely on the general contract for this?

**Answer:** No. An iterator entry is not a long-lived update handle guaranteed by the interface. If you need data for later use, create a standalone pair during a valid read. If you need updates, design an API based on keys/conditions and an appropriate ownership policy.

### Exercise 3 — Is a new List enough?

Does `new ArrayList<>(map.entrySet())` guarantee that each entry is a standalone snapshot? What extra step is needed when the data has no nulls?

**Answer:** No. It only creates a new outer list. You can copy each entry with `Map.Entry.copyOf` during iteration, or use the corresponding transformation in a stream. If `null` must be retained, choose a suitable pair constructor such as `SimpleImmutableEntry` according to your data policy.

### Exercise 4 — Factories and null

Compare `new SimpleImmutableEntry<>("K", null)` with `Map.entry("K", null)` and `Map.Entry.copyOf` on the first pair.

**Answer:** The first concrete entry class can hold a `null` value and does not support `setValue`. `Map.entry` rejects `null` components; `copyOf` also rejects a pair with a `null` key or value. A source map allowing `null` does not make other factories accept `null`.

### Exercise 5 — Immutable pair, mutable List

A pair is created with `Map.entry("items", mutableList)` and copied with `copyOf`. Afterward, an element is added to `mutableList`. Can the snapshot see it?

**Answer:** Yes, because both pairs hold a reference to the same list. Not changing the value reference does not mean the list cannot change state. For a list of strings, you can copy the list with `List.copyOf` as needed; for mutable elements, you must further determine the copy depth.

### Exercise 6 — Entry from firstEntry

A `TreeMap` currently holds `1=one`. You call `before = firstEntry()` and then update the map to `1=ONE`. Can `before.setValue` be used to update it further in this case?

**Answer:** No; this source's navigation entry is a snapshot that does not support `setValue`. It recorded `1=one` at the time it was obtained. Use a map API to update, while accounting for conflicts if multiple tasks modify concurrently.

### Exercise 7 — Equality and edit permissions

`new SimpleEntry<>("K", 1)` equals `Map.entry("K", 1)`. Can you infer that both allow `setValue`?

**Answer:** No. Equality checks matching key and value, not edit permissions or origin. The first pair can be edited locally; the factory pair forbids changing the value. Do not use `equals` or `==` to infer operation permissions.

### Exercise 8 — Snapshots and conditional updates

You hold a standalone pair `K=10`. The source later changes to `K=12`. A task uses the old pair to `put(K, 11)`. Has copying the entry prevented overwriting newer data?

**Answer:** No. Copying detaches the live relationship and preserves the data that was read; it does not hold a lock or resolve update conflicts. You need an expected-value policy, versioning, or a concurrent update mechanism suited to the requirement.

When practicing further, explicitly note which category each entry in your program belongs to before calling a method: active source iteration, modifiable standalone pair, or unmodifiable standalone pair. Then separately check whether the key/value holds any mutable objects. These two steps help you use key–value pairs with the right lifecycle and ownership semantics.
