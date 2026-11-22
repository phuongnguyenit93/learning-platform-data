# keySet, values, entrySet, and Write-Through Operations to Map

## 1. A View Is a Way to Access Existing Data

A map stores roles by username:

~~~text
ada -> READER
lin -> EDITOR
sam -> READER
~~~

One feature only needs the names; one feature aggregates role counts; another feature needs both names and roles. Java provides three views of the same map:

~~~java
Set<K> keySet();
Collection<V> values();
Set<Map.Entry<K, V>> entrySet();
~~~

These are API signature shapes for reading the contract, not a standalone Java program.

**A view is not a copy by default.** For a modifiable map such as `LinkedHashMap`, the view objects are backed by the source map: changes to the source are reflected through the view, and supported write operations on the view propagate back to the source. Therefore, returning `keySet` to another method can grant the ability to remove mappings, not just hand out a list of names.

`Map` specifies these three collection views; iteration order depends on the map implementation. [Java 17: Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

This lesson explains the write-through paths, the operations that are rejected, how to iterate and modify according to the contract, and the differences between a view, a read-only wrapper, and a copy. The complete program uses APIs compatible with **Java 17 and later**.

## 2. The Three Views Differ in Element Unit

Given the source:

~~~text
map                 {ada=READER, lin=EDITOR, sam=READER}

keySet              [ada, lin, sam]
values              [READER, EDITOR, READER]
entrySet            [ada=READER, lin=EDITOR, sam=READER]
~~~

The square brackets here represent the printed sequence of an example using a linked map, not that all three objects are `List`s.

| View | Return type | Element represented | Can contain duplicates in the usual sense? |
| --- | --- | --- | --- |
| `keySet()` | `Set<K>` | Key | No |
| `values()` | `Collection<V>` | Value of each mapping | Yes |
| `entrySet()` | `Set<Map.Entry<K,V>>` | Key-value pair | Each mapping is one entry |

### 2.1. Why Isn't values a Set?

Two keys, `ada` and `sam`, both have the value `READER`. The map still has three mappings, so the values view also has three elements: two occurrences of `READER` and one `EDITOR`.

If you used a set of values to represent that view, you would lose the per-mapping occurrence count. When you want to count how many people have each role, do not deduplicate before counting.

### 2.2. An Entry Considers Both Key and Value

A `Map.Entry` describes a pair. The entry `ada=READER` differs from `ada=EDITOR` because the value differs. This matters for `entrySet.contains` or `entrySet.remove`: matching by entry is not just a longer way to write a key.

Standard entry equality checks both the key and the value; whether an entry remains connected to the map also depends on how you obtained it. [Java 17: Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

### 2.3. Not All Views Have the Same equals Contract

`keySet` and `entrySet` are sets, so they follow set membership equality semantics. `values` is only declared as `Collection`, not a positional list or a deduplicating set.

Do not use `map.values().equals(expectedList)` as a general way to verify value contents or order. If you need to check sequence order, build a list in the appropriate iteration order. If order does not matter but occurrence counts do, compare frequencies instead of converting directly to a set.

`Collection` does not impose the same `equals` contract as `List` or `Set`. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## 3. Bidirectional Link Between Source and View

You can hold onto a view and then modify the map:

~~~java
Map<String, String> users = new LinkedHashMap<>();
users.put("ada", "READER");
Set<String> names = users.keySet();

users.put("lin", "EDITOR");
System.out.println(names);
~~~

This is an illustrative snippet placed inside a method with the corresponding imports. The result read through `names` is `[ada, lin]`. You do not need to call `keySet` again for the view to "reload new data".

Conversely:

~~~java
names.remove("ada");
~~~

If the source supports removal, the mapping for `ada` disappears from `users`. It is not merely removed from a separate collection of names.

Mental model:

~~~text
                 same source map
                       |
         +-------------+-------------+
         |             |             |
       keySet        values       entrySet
         |             |             |
    remove key    remove value  remove matching pair
         +-------------+-------------+
                       |
              remove source mapping
~~~

"Write-through" means an operation performed via a view modifies the source data. It does not refer to writing to a file, database, or network; this lesson only discusses in-memory Java objects.

### 3.1. A Live View Differs from an Active Iterator

A view can continue reflecting the source across new queries. An iterator is a specific traversal process with its own rules when the source is modified.

You cannot create an iterator, add a key with `map.put`, and then argue "this is a live view" to keep iterating arbitrarily. You must obey the iterator contract and the map's concurrency policy.

### 3.2. Reading Views Does Not Create an Atomic Snapshot

If another thread modifies the map between the moments you check its size, print keys, and then print values, the three observations may not belong to the same state. Being backed by the source does not mean there is an implicit lock covering the whole sequence of operations.

The program in this lesson runs single-threaded to make behavior clear. In real usage, ownership and synchronization policies must be designed where the source is managed.

## 4. Removal Operations That Write Through to the Map

### 4.1. keySet.remove(k): Only Needs to Match the Key

Given `{ada=READER, lin=EDITOR, sam=READER}`:

~~~text
keySet.remove("lin")       true
map after                  {ada=READER, sam=READER}
~~~

The value for `lin` does not need to be passed. On a modifiable view, a return value of `true` means the key element was removed, so that mapping was also removed.

This is useful when values can be `null`. `map.remove(k)` returns the previous value and can return `null` both when the mapping is absent and when it previously mapped to `null`. `keySet.remove(k)` returns a boolean indicating whether the key was removed, helping distinguish those cases when used appropriately.

Both remain optional operations and must follow the source's type/`null` policies.

### 4.2. values.remove(v): Removes One Occurrence

If two people have the role `READER`, `values().remove("READER")` removes **one mapping** with a matching value, not both people.

On the program's `LinkedHashMap`, iteration follows insertion order, so the example yields a deterministic result. In code accepting an arbitrary `Map`, do not use this operation as a way to target a specific person's identity. If the goal is to remove `sam`, remove by the key `sam`.

`Collection.remove` removes a single matching occurrence if present; `removeAll` has different semantics. [Java 17: Collection.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)).

Do not assume that removing via the values view only drops a value while keeping a "valueless" key. A map entry always associates a key and a value; removing an element from this view removes the corresponding mapping.

### 4.3. entrySet.remove(entry): Must Match the Pair

Given a source containing `maya=REVIEWER`:

~~~java
entries.remove(Map.entry("maya", "WRONG"));     // false
entries.remove(Map.entry("maya", "REVIEWER"));  // true
~~~

This snippet assumes non-`null` keys/values and a modifiable entry view. The first call leaves the source untouched because the pair does not match. The second call removes the existing mapping.

If you want to remove a key only when it currently maps to an expected value, `map.remove(key, expectedValue)` also expresses that intent clearly. Do not assume a `contains` followed by `remove` on a view is atomic in a concurrent environment.

### 4.4. clear: Removes All Mappings

On views that support removal:

~~~java
map.keySet().clear();
map.values().clear();
map.entrySet().clear();
~~~

Each line on its own is a path that clears the entire map. If the first line runs first, the next two lines simply operate on an already empty source; they do not target three separate datasets.

This is a key reason not to return a source view to a caller when you only intend to provide read access. A returned collection can carry broader mutation power than the method name suggests.

### 4.5. removeAll, retainAll, and removeIf

Filtering operations on views can be very convenient:

| Intent | Usage on a source that supports removal |
| --- | --- |
| Remove keys in a blocklist | `map.keySet().removeAll(blockedKeys)` |
| Keep only allowed keys | `map.keySet().retainAll(allowedKeys)` |
| Remove all mappings whose value is in a group | `map.values().removeAll(rejectedValues)` |
| Remove by a predicate on both key and value | `map.entrySet().removeIf(predicate)` |

`retainAll` means removing elements that are not retained; it does not merely "mark selected elements". If the allowed set is empty, retaining against an empty set can empty the map.

`removeIf` removes elements matching the predicate; the default implementation relies on an iterator and the iterator's remove operation. If the predicate throws an exception after some removals, do not assume earlier removals were rolled back.

The predicate should focus on deciding whether to remove, without simultaneously modifying the map's structure through another path. For example, `entry -> entry.getValue().equals("REVIEWER")` is suitable when the domain forbids `null`; if `null` is allowed, compare safely according to that policy.

## 5. Why Adding to Views Is Usually Rejected

`keySet` and `values` lack sufficient information to create a new mapping in the map's sense:

- adding a key does not specify what the value should be;
- adding a value does not specify which key owns it.

Even though `entrySet` has full pairs, the view contract does not provide `add` or `addAll` as an alternative to `Map.put`. These standard views do not support those addition operations.

On the modifiable source in the example:

~~~java
map.keySet().add("new-user");
map.values().add("READER");
map.entrySet().add(Map.entry("new-user", "READER"));
~~~

Each statement is tested individually and throws `UnsupportedOperationException`. To add or update mappings, use the appropriate map API.

Do not test an unsupported operation with duplicate or empty data and conclude "it works in this case". Optional operations can be rejected even when you think they would produce no change.

There is also no `set(index, value)` on `values` because its return type is `Collection`, not a list. To change the value for a key, use the map API or an entry iterator that supports updates.

## 6. entry.setValue: Direct Value Update Path

When iterating over the `entrySet` of a modifiable `LinkedHashMap`, the entry returned by the iterator can be used to update the mapping's value:

~~~java
for (Map.Entry<String, String> entry : users.entrySet()) {
    if (entry.getValue().equals("EDITOR")) {
        entry.setValue("REVIEWER");
    }
}
~~~

This snippet replaces `EDITOR` with `REVIEWER` while keeping the keys and the number of mappings intact. It does not "change a local entry variable"; the call writes into the source mapping's value if supported.

### 6.1. Reassigning a Local Value Variable Differs from Updating the Map Value

The following snippet does not change any mapping:

~~~java
for (String role : users.values()) {
    role = "REVIEWER";
}
~~~

It only reassigns the loop variable to another string. The variable `role` is not a reference slot that can replace the value stored by the map.

Conversely, if the value is a mutable object such as a `List`, calling a mutating method on that object itself can change the state visible through the map. That mutates the element's state, which is different from changing the mapping to point to a new object.

### 6.2. setValue Is Optional and Has a Lifecycle

Not every `Map.Entry` allows `setValue`. An entry from `Map.entry` is an independent unmodifiable entry; an entry obtained through a read-only map/view does not grant update access either.

With an entry iterator, the connection to the source is tied to the iteration. Do not keep that entry as a long-lived handle, remove or structurally modify the source through another path, and continue relying on it. If you need to store a pair at the current point in time, create an appropriate independent entry.

You cannot modify an entry's key through this API; only `setValue` exists. Key identity and its equality/hashing rules remain part of the map contract.

### 6.3. Values May Be Restricted

A map may forbid `null` values or enforce other constraints. Updating through an entry does not bypass the source's constraints. Do not use `setValue(null)` as a way to remove a mapping: if allowed, it assigns the value `null` while the key remains present.

To remove the mapping currently being visited, use the contract-compliant removal operation.

## 7. Iterating and Removing: Use the Traversal's Own Iterator

The clear way to do this is:

~~~java
var it = users.entrySet().iterator();
while (it.hasNext()) {
    var entry = it.next();
    if (shouldDelete(entry)) {
        it.remove();
    }
}
~~~

This snippet requires an application-provided decision method `shouldDelete`; it is not yet a standalone program.

`Iterator.remove` removes the element last returned by `next`; for an entry view, that is the corresponding mapping. It may only be called in the valid state and at most once per call to `next` according to the iterator contract. [Java 17: Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()).

Do not write a `for-each` loop over `keySet` and call `map.remove(key)` inside it on ordinary maps and expect traversal to always remain valid. The removal condition may be right, but the mutation path is outside the active iterator.

### 7.1. Fail-Fast Is Not a Synchronization Mechanism

`HashMap` does not guarantee iteration order and is not synchronized; a fail-fast iterator exists to detect certain unauthorized structural modifications, not to guarantee that every race condition is caught. [Java 17: HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Not seeing `ConcurrentModificationException` does not prove that code modifying a map inside a loop is correct. Nor should you treat a test asserting "must throw an exception on this exact line" as a business specification for contract-violating code.

### 7.2. LinkedHashMap Is Used to Verify Ordered stdout

The full example chooses a default insertion-order `LinkedHashMap` so that printed lines are predictable. That does not impose the same ordering on every `Map`.

If you use an access-order `LinkedHashMap`, some `get` calls can change the iteration order. Therefore, when you already need both key and value, iterating over entries is usually clearer than iterating over keys and repeatedly calling `get`. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

### 7.3. Concurrent Maps Have Different Policies, but Do Not Automatically Form Transactions

A source such as `ConcurrentHashMap` has weakly consistent iterators and separately specified concurrent operations. It forbids `null` keys and values; observations while the source is changing should not be interpreted as an atomic snapshot of the entire map. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

When adapting an algorithm to a concurrent map, read the contracts of the source, the update operations, and the view in use. Do not carry over all `HashMap` fail-fast assumptions, and do not assume a multi-item filtering pass is automatically a single transaction.

## 8. null and Entry Matching

In a map that allows `null`, a key can exist even when its value is `null`:

~~~java
Map<String, String> state = new LinkedHashMap<>();
state.put("pending", null);
boolean removed = state.keySet().remove("pending");
~~~

`removed` is `true` because the key existed and was removed. This case does not require inferring anything from an old `null` value.

To construct a matching entry with a `null` value, do not use `Map.entry("pending", null)` because that factory rejects `null`. You can use:

~~~java
Map.Entry<String, String> expected =
        new AbstractMap.SimpleImmutableEntry<>("pending", null);
boolean removed = state.entrySet().remove(expected);
~~~

This snippet assumes the source already contains a matching mapping. `SimpleImmutableEntry` creates an independent pair and does not allow changing the value via `setValue`. [Java 17: AbstractMap.SimpleImmutableEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html).

Checks and removals on sources that forbid `null` may have their own contract-defined behavior. Do not generalize a single test on `HashMap` to every map.

## 9. Views, Collection Copies, and Entry Copies Are Three Different Levels

### 9.1. Copying Keys or Values

If you want a structurally independent list of names:

~~~java
List<String> savedNames = new ArrayList<>(users.keySet());
~~~

Adding or removing keys in `users` afterward does not automatically add or remove elements in `savedNames`. The new list receives elements in the source's iteration order at copy time. `ArrayList` creates a separate list structure and allows list operations according to its class contract. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Similarly, `new ArrayList<>(users.values())` stores the value references at copy time. If values are mutable objects, copying the collection does not deep-copy them.

### 9.2. Copying Only the Entry Collection Does Not Prove Pairs Are Independent

This snippet creates a new list:

~~~java
List<Map.Entry<String, String>> saved =
        new ArrayList<>(users.entrySet());
~~~

However, the elements placed into it are still the entry objects supplied by the source. Do not rely on the new list to assume every entry is detached from the source or retains valid update rights outside iteration.

To keep independent pairs, copy each entry during iteration:

~~~java
List<Map.Entry<String, String>> saved = new ArrayList<>();
for (Map.Entry<String, String> entry : users.entrySet()) {
    saved.add(new AbstractMap.SimpleImmutableEntry<>(entry));
}
~~~

The new entries are no longer the source view's entry objects. This is still a shallow copy of the key/value references.

Java 17 also provides `Map.Entry.copyOf` to create an independent entry, but it does not accept `null` keys or values. Choose the tool based on the data domain, not only on statement brevity.

### 9.3. Copying the Map

`new LinkedHashMap<>(users)` creates a new map with copied mappings, preserving input iteration order in this constructor. Afterward, changing a key's value in the original map does not automatically change the copy's mapping.

However, if both maps hold the same `List` as a value, mutating that `List` is visible through both. A structural map copy and a deep data copy are two different levels of guarantee.

A copy created while multiple threads are modifying the source is also not automatically promoted to an atomic business snapshot. Appropriate access control is needed throughout the copy.

## 10. Read-Only Wrappers Must Protect the Right Layer

### 10.1. Collections.unmodifiableMap Protects Mutation Paths Through the Map and Views

`Collections.unmodifiableMap(source)` returns a view that blocks modifying mappings through the map and through the collection views it returns. Reads still see the underlying source, so the source can still change through another reference. [Java 17: Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).

This is useful when you want to keep a live source without granting the caller permission to add, remove, or replace mapping values.

It does not make value objects deeply immutable. If the source holds an `ArrayList`, the caller can obtain the list reference via `get` and mutate that list directly, unless the data model also protects the element layer.

### 10.2. Wrapping Only entrySet with unmodifiableSet Can Leak setValue

Consider the intent "return an entry set that prevents the caller from modifying the map":

~~~java
Set<Map.Entry<String, Integer>> result =
        Collections.unmodifiableSet(scores.entrySet());
~~~

The wrapper blocks adding/removing set elements and removing through its iterator. However, it does not automatically replace each entry with a read-only entry. When the source's entries still allow updates during iteration, `entry.setValue` can still write through.

The full program demonstrates this on a `LinkedHashMap`: iterating over the wrapped set changes the score for `math` from `80` to `90`. Wrapping `scores` with `unmodifiableMap` and then taking its `entrySet` is what blocks that entry update path.

The API design lesson is to check **permissions on the element objects**, not only on the outer collection. Similarly, an unmodifiable `List` can still contain mutable elements.

### 10.3. When to Choose an Unmodifiable Copy?

If the caller needs state at a point in time, you can copy the appropriate structure and wrap the copy. If deep immutability is required, you must copy or use immutable types for the keys/values involved.

`Map.copyOf` creates an unmodifiable map that does not reflect subsequent mapping changes in the source, but it forbids `null` keys/values and does not guarantee the same desired iteration order. Do not use it as an unconditional all-purpose copy.

Your choice should be based on four separate requirements: whether the source stays live, whether structural modification is allowed, whether elements are mutable, and whether order matters.

## 11. Complete Program

Save all the code below into **`MapWriteThroughDemo.java`**. The program runs single-threaded, uses `LinkedHashMap` for deterministic stdout ordering, and does not use APIs introduced after Java 17.

Role strings are sample data illustrating collection behavior; the example does not implement an authorization system.

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class MapWriteThroughDemo {
    static String unsupported(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        Map<String, String> users = new LinkedHashMap<>();
        users.put("ada", "READER");
        users.put("lin", "EDITOR");
        users.put("sam", "READER");
        Set<String> keys = users.keySet();
        Collection<String> roles = users.values();
        Set<Map.Entry<String, String>> entries = users.entrySet();

        users.put("maya", "REVIEWER");
        users.put("lin", "ADMIN");
        System.out.println("live keys: " + keys);
        System.out.println("live values: " + roles);
        System.out.println("live entries: " + entries);

        boolean changed = roles.remove("READER");
        System.out.println("remove one value: " + changed + ", map=" + users);
        changed = keys.remove("lin");
        System.out.println("remove key: " + changed + ", map=" + users);
        changed = entries.remove(Map.entry("maya", "WRONG"));
        System.out.println("remove wrong pair: " + changed + ", map=" + users);
        changed = entries.remove(Map.entry("maya", "REVIEWER"));
        System.out.println("remove matching pair: " + changed + ", map=" + users);

        users.put("nora", "READER");
        users.put("oli", "EDITOR");
        users.put("pia", "READER");
        changed = roles.removeAll(Set.of("READER"));
        System.out.println("remove all reader values: " + changed + ", map=" + users);
        users.put("uma", "VIEWER");
        users.put("vic", "ADMIN");
        users.put("wen", "EDITOR");
        keys.retainAll(Set.of("oli", "uma", "vic"));
        System.out.println("retain allowed keys: " + users);

        Iterator<Map.Entry<String, String>> it = entries.iterator();
        while (it.hasNext()) {
            Map.Entry<String, String> entry = it.next();
            if (entry.getValue().equals("VIEWER")) {
                it.remove();
            } else if (entry.getValue().equals("EDITOR")) {
                entry.setValue("REVIEWER");
            }
        }
        System.out.println("iterator remove and setValue: " + users);
        entries.removeIf(entry -> entry.getValue().equals("REVIEWER"));
        System.out.println("entry predicate removal: " + users);

        List<String> savedKeys = new ArrayList<>(keys);
        List<String> savedValues = new ArrayList<>(roles);
        List<Map.Entry<String, String>> savedEntries = new ArrayList<>();
        for (Map.Entry<String, String> entry : entries) {
            savedEntries.add(new AbstractMap.SimpleImmutableEntry<>(entry));
        }
        Map<String, String> savedMap = new LinkedHashMap<>(users);
        users.put("vic", "OWNER");
        users.put("zoe", "EDITOR");
        System.out.println("live map after changes: " + users);
        System.out.println("saved keys: " + savedKeys);
        System.out.println("saved values: " + savedValues);
        System.out.println("saved entries: " + savedEntries);
        System.out.println("saved map: " + savedMap);

        roles.clear();
        System.out.println("clear values, map: " + users);
        System.out.println("other views after clear: keys=" + keys + ", entries=" + entries);
        System.out.println("key add: " + unsupported(() -> keys.add("new-user")));
        System.out.println("value add: " + unsupported(() -> roles.add("READER")));
        System.out.println("entry add: "
                + unsupported(() -> entries.add(Map.entry("new-user", "READER"))));

        Map<String, String> nullable = new LinkedHashMap<>();
        nullable.put("pending", null);
        System.out.println("null mapping key remove: "
                + nullable.keySet().remove("pending") + ", empty=" + nullable.isEmpty());
        nullable.put("pending", null);
        Map.Entry<String, String> nullPair =
                new AbstractMap.SimpleImmutableEntry<>("pending", null);
        System.out.println("null pair remove: " + nullable.entrySet().remove(nullPair));

        users.put("r1", "VIEWER");
        Map<String, String> readOnly = Collections.unmodifiableMap(users);
        System.out.println("read-only key remove: "
                + unsupported(() -> readOnly.keySet().remove("r1")));
        System.out.println("read-only entry setValue: " + unsupported(() -> {
            for (Map.Entry<String, String> entry : readOnly.entrySet()) {
                entry.setValue("OTHER");
            }
        }));
        users.put("r2", "EDITOR");
        System.out.println("read-only view sees source: " + readOnly);

        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("math", 80);
        Set<Map.Entry<String, Integer>> setOnly =
                Collections.unmodifiableSet(scores.entrySet());
        for (Map.Entry<String, Integer> entry : setOnly) {
            entry.setValue(90);
        }
        System.out.println("set wrapper entry still writes: " + scores);
        Map<String, Integer> protectedMap = Collections.unmodifiableMap(scores);
        System.out.println("map wrapper blocks entry write: " + unsupported(() -> {
            for (Map.Entry<String, Integer> entry : protectedMap.entrySet()) {
                entry.setValue(99);
            }
        }));

        Map<String, List<String>> groups = new LinkedHashMap<>();
        groups.put("team", new ArrayList<>(List.of("a")));
        Map<String, List<String>> groupCopy = new LinkedHashMap<>(groups);
        Map<String, List<String>> groupView = Collections.unmodifiableMap(groups);
        groupView.get("team").add("b");
        System.out.println("nested value changes source: " + groups);
        System.out.println("shallow copy shares value: "
                + (groups.get("team") == groupCopy.get("team")));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 MapWriteThroughDemo.java
java MapWriteThroughDemo
~~~

You can use JDK 17 or later to compile at release level 17 and a Java 17 or later runtime to execute it. The example was compiled at release level 17 and ran successfully using OpenJDK 24.0.2.

Exact stdout:

~~~text
live keys: [ada, lin, sam, maya]
live values: [READER, ADMIN, READER, REVIEWER]
live entries: [ada=READER, lin=ADMIN, sam=READER, maya=REVIEWER]
remove one value: true, map={lin=ADMIN, sam=READER, maya=REVIEWER}
remove key: true, map={sam=READER, maya=REVIEWER}
remove wrong pair: false, map={sam=READER, maya=REVIEWER}
remove matching pair: true, map={sam=READER}
remove all reader values: true, map={oli=EDITOR}
retain allowed keys: {oli=EDITOR, uma=VIEWER, vic=ADMIN}
iterator remove and setValue: {oli=REVIEWER, vic=ADMIN}
entry predicate removal: {vic=ADMIN}
live map after changes: {vic=OWNER, zoe=EDITOR}
saved keys: [vic]
saved values: [ADMIN]
saved entries: [vic=ADMIN]
saved map: {vic=ADMIN}
clear values, map: {}
other views after clear: keys=[], entries=[]
key add: UnsupportedOperationException
value add: UnsupportedOperationException
entry add: UnsupportedOperationException
null mapping key remove: true, empty=true
null pair remove: true
read-only key remove: UnsupportedOperationException
read-only entry setValue: UnsupportedOperationException
read-only view sees source: {r1=VIEWER, r2=EDITOR}
set wrapper entry still writes: {math=90}
map wrapper blocks entry write: UnsupportedOperationException
nested value changes source: {team=[a, b]}
shallow copy shares value: true
~~~

### 11.1. Views Obtained Before the Source Changed

The three views were created when the source only had three people. After adding `maya` and changing `lin`'s value, printing the views showed the updated state. This proves that views are not copies created at the time they were obtained.

### 11.2. Removals Target Different Things

Removing one `READER` value removes only a single mapping. Removing the key `lin` does not require passing a role. Removing the entry `maya=WRONG` does not match, so it leaves the source unchanged, whereas the matching pair is removed.

`removeAll` on the values view removes all mappings with the selected roles; `retainAll` on the keys view removes keys outside the allowed set.

### 11.3. Iterator Coordinating Removal and Update

In the iterator loop, `uma` is removed via `it.remove`. `oli`'s value is updated through the current entry. The loop does not add or remove via `users.put` or `users.remove` outside the iterator.

Afterward, `entrySet.removeIf` removes entries matching the predicate. Each phase finishes its traversal before the next step makes structural changes.

### 11.4. Copies and Wrappers

The four saved snapshots capture the data when the source only had `vic=ADMIN`. Updating `vic` and adding `zoe` on the source do not change the saved structures or independent entries.

`roles.clear` empties the source, and the other two views become empty as well. Attempts to add to the views are rejected.

At the end of the program, two wrapper examples demonstrate layer-specific limits: wrapping the set does not wrap the entries, and wrapping the map does not make a value `List` immutable.

## 12. Designing Methods That Return Map Data

Before returning a view, decide what the caller is allowed to do:

| Caller's need | Potentially suitable choice | What must be made explicit |
| --- | --- | --- |
| Track the source and allow removing mappings by key | Direct `keySet` | This grants permission to mutate the source |
| Read-only access to the live source | Map/view wrapped read-only at the right layer | The source can still change via another path |
| Hold a list of names at a point in time | Copy of keys into a suitable collection | Not automatically an atomic snapshot if the source changes concurrently |
| Hold structurally independent pairs | Copy each entry or copy the map | Must still decide on deep copy depth |
| Filter data for display without mutating the source | Build a separate filtered result | Do not call remove on a live view |
| Update values while iterating a supporting source | Entry iterator and `setValue` | Respect lifecycle, types, and mutability |

A method named `getUserNames` that directly returns `users.keySet()` can make sense if the contract intentionally grants that permission. If the goal is a read-only boundary, the method name alone does not protect the data.

Also, do not catch every `UnsupportedOperationException` and ignore it just to make a method "work with any map". When a feature requires removal or updates, an unsupported source is a contract difference that should be handled or reported clearly.

## 13. Common Mistakes

| Misconception | Problem | Intent-based fix |
| --- | --- | --- |
| `keySet` is a copy of the key list | Removing through it can delete from the source | Choose a view or a copy intentionally |
| `values.remove` only hides one displayed value | The corresponding mapping is deleted | Use a separate display result |
| `values` is a set | Loses value occurrence counts | Preserve collection semantics allowing duplicates |
| `entrySet.remove` only needs a matching key | A pair with a mismatched value is not removed | Remove by key or match the full pair |
| Add through a view to update the map | Operation is unsupported | Use the map API |
| Reassign the value variable in a for-each loop | Does not update the mapping | Use `put`, `replace`, or a modifiable entry |
| Remove from the source directly in a for-each loop | Breaks standard traversal rules | Use `iterator.remove` or `removeIf` appropriately |
| Wrapping `entrySet` with `unmodifiableSet` is enough | Entries may still allow `setValue` | Wrap the map properly or copy entries as needed |
| Copying an entry list is a deep copy | Entries/elements may still be tied to the source or share references | Separate each level of copying |
| Not seeing an exception means thread-safe | No such guarantee exists | Design access around the source and business unit |

## 14. Practice with Answers

### Exercise 1 — View or Copy?

Create `Set<String> names = map.keySet()` and then add a key via `map.put`. Does `names` see the new key? What happens to the source if you remove a key through `names`?

**Answer:** A view backed by the source sees updates across subsequent queries. On a source/view that supports removal, removing through `names` removes the corresponding mapping from the map. Any iterator created before the change must still obey its own traversal contract.

### Exercise 2 — Duplicate Values

The source has `{A=OPEN, B=OPEN, C=DONE}`. Compare the intent of `values().remove("OPEN")` and `values().removeAll(Set.of("OPEN"))`.

**Answer:** The first removes one mapping with a matching value; do not rely on it to deterministically target key `A` across all maps. The second removes all mappings whose values belong to the group, so neither `OPEN` value remains after successful completion on a supporting source. To remove one specific key, remove by that key.

### Exercise 3 — Matching the Full Entry

The source has `{item=7}`. What does `entrySet().remove(Map.entry("item", 8))` return, and does it empty the map?

**Answer:** On a standard modifiable source, it returns `false` because the value does not match, and the source remains `{item=7}`. Removing by entry matches both key and value; removing by key is a different intent.

### Exercise 4 — Reassigning a Loop Variable

Why does `for (String v : map.values()) { v = "NEW"; }` not change every value in the map? What is a correct way to update them?

**Answer:** `v` is a local variable holding a reference; reassigning it does not modify the mapping. You can use an entry iterator and `setValue` on a supporting source, or an appropriate map update API such as `replaceAll` with a clear mutability contract. Do not simultaneously modify structure outside traversal rules.

### Exercise 5 — A Wrapper Missing One Layer

An API returns `Collections.unmodifiableSet(map.entrySet())` of a modifiable map and claims the caller cannot update values. Is that claim well-founded?

**Answer:** No. The set wrapper blocks changing set membership, but it does not automatically block mutating methods on individual entries. If the source entries support `setValue` during iteration, the caller can still write through. Wrap the map appropriately and take its view, or return independent unmodifiable entries depending on the data goal.

### Exercise 6 — Copying Entries

A method needs to save the current pairs for use after the map continues changing. Does `new ArrayList<>(map.entrySet())` alone prove the entries are independent?

**Answer:** Not yet. The new collection still receives entry objects from the source; do not rely on an entry iterator's lifecycle as a guarantee for long-lived data. Copy each entry during iteration, such as `new SimpleImmutableEntry<>(entry)`. This is still a shallow copy of keys/values; if you want to use `Map.Entry.copyOf`, you must handle the non-`null` requirement.

### Exercise 7 — null and the Removal Flag

A map allows `null` and contains `pending=null`. What does `keySet().remove("pending")` return? Why is it different from inferring from `map.remove("pending")` returning `null`?

**Answer:** Removing the key through the view returns `true` when the key existed and was removed. The previous value returned by `map.remove` can be `null` both when the mapping was absent and when it previously had a `null` value. Choose the return type that matches what you need to know and obey the source's policy.

### Exercise 8 — Unmodifiable Map, Mutable Value

A read-only map holds `ArrayList` values. Can calling `readOnly.get("team").add("new")` change the data visible through the source?

**Answer:** Yes, if you receive the exact same mutable list held by the source. Blocking additions, removals, and replacements of mappings does not automatically make value objects deeply immutable. You must decide whether to copy or wrap data at the element layer, while considering lifecycles and shared references.

When extending the example yourself, try each operation on a modifiable source, a read-only wrapper, and an independent copy. After each step, inspect both the map and any views obtained earlier. Distinguishing where data actually changes is essential for using collection views without losing ownership boundaries.
