# Risks of Modifying Fields Participating in equals or hashCode After Insertion

A key can remain inside a `HashMap` while calling `get` with that very same reference fails to find it. A `HashSet` can hold two objects that were initially distinct upon insertion, and after a field modification makes those two objects equal, `size()` still returns `2`. Both phenomena can stem from changing the data used to identify a key or element after it has been inserted into a collection.

Within the **Java core - collection** topic, under **Equality and Hashing**, this article explains why such modifications are dangerous and how to design your code to avoid them. The goal is not to memorize a specific failure output of `HashMap`. The goal is to keep a key's meaning stable for the entire duration it serves as a key.

## 1. Prerequisite mental model: the object changes, the collection does not automatically re-index

Imagine a catalog organized by file code. When a file with code `A` is placed into the catalog, the system chooses a lookup location based on code `A`. If someone later picks up the physical file directly and changes the code written on the paper to `B`, modifying the paper does not mean the system has performed a catalog transfer from `A` to `B`.

Similarly, `HashMap` organizes its entries based on information obtained from the key at the time of insertion. Calling a method such as `key.setId(2)` only mutates the key object. It is not a key-renaming call on the `Map`, nor does it notify the hash table to rebuild its lookup structure.

Three concepts must be clearly separated:

| Concept | Question it answers |
|---|---|
| Reference identity, `a == b` | Do both variables point to the exact same object? |
| Value equality, `a.equals(b)` | Do the two objects represent the same key or value under the chosen model? |
| Hash code, `a.hashCode()` | What numeric value is used to organize storage and narrow down lookups? |

An unchanged reference does not imply an unchanged object state. And a changed state can alter the results of `equals` or `hashCode`.

**Practical rule:** while an object is serving as a key in a `HashMap` or an element in a `HashSet`, keep the data that determines its equality and hash code stable.

Both the `Map` and `Set` documentation warn against mutating an object while it is stored in a manner that affects equality comparisons. When that condition is violated, the behavior of the collection is not specified. Therefore, the failure symptoms shown in this article serve to illustrate the underlying mechanism and prevent poor designs; they are not guaranteed outcomes that every implementation must produce. [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

## 2. Why this is a temporal problem, not just writing the two methods properly

A class is typically checked against these rules:

- `equals` must be reflexive, symmetric, transitive, and consistent while the data participating in comparisons remains unchanged.
- Two equal objects must have the same hash code.
- Two unequal objects may still share the same hash code.
- Repeated calls to `hashCode` must remain consistent while the data used in `equals` is not modified.

The last rule is conditional: provided the relevant data is not modified. It does not state that every object's hash code must be immutable from creation until garbage collection. [Object.equals and Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)

For example, a class that uses `id` for both `equals` and `hashCode` might behave as follows:

- At time 1: `id = 1`; both equality and the hash code are based on `1`.
- At time 2: `id = 2`; both shift to being based on `2`.

The two methods can still be completely consistent with each other at each individual point in time. However, if between those two points in time the object is stored as a key inside a hash table, using that key is still problematic. The storage structure was built around the earlier state.

We need to distinguish between two categories of errors:

| Error category | Example | Resolution approach |
|---|---|---|
| Broken contract between `equals` and `hashCode` | Two objects are equal but return different hash codes even in the exact same state | Fix the design and implementation of the two methods |
| Mutating key-identifying data while the key is stored | Initially `id = 1`, inserted into a map, then mutated to `id = 2` | Keep the key stable or perform a controlled rekeying workflow |

Implementing the two methods properly does not automatically solve the second category of error. Safe usage in a hash table requires an additional design decision regarding the **key lifecycle**.

## 3. Mechanism: information at insertion differs from information at lookup

Suppose a key has a `hashCode()` method that directly returns `id`. A simplified model of the insertion operation is:

1. Obtain the hash code from the current key.
2. Use the hash code to determine the search bucket/region.
3. Inspect candidate keys to see whether an equal key already exists.
4. Store a new entry if none is found.

During a lookup, the map starts from the hash code of the lookup object at the time of the query. It is not required to scan every element in the table and compare references against the target object.

In OpenJDK 17's `HashMap` implementation, each storage node caches the hash value computed when the node was created. The lookup path checks the hash value before testing reference identity or `equals` on a candidate node. Consequently, changing the object's hash code does not automatically update the cached hash inside the node. This is an explanation of a specific implementation, not a universal definition applicable to every `Map` type. [OpenJDK 17 HashMap source code](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java)

Timeline example:

| Time | Key state | Operation | What to understand |
|---|---|---|---|
| T0 | `id = 1` | `map.put(key, "payload")` | The map organizes the entry using the initial information |
| T1 | `id = 2` | `key.setId(2)` | Only the object mutates; no rekeying operation occurs on the map |
| T2 | `id = 2` | `map.get(key)` | The lookup path uses the key's current information |
| T3 | `id = 2` | Iterate `entrySet` or `keySet` | The entry and the mutated reference may still be visible |

**Failing to find an entry during lookup does not mean the entry was removed.** The entry may still occupy space, still be counted in `size`, and still appear during iteration.

Nor should you assume that keeping the same bucket index is safe enough. A hash table may verify the stored hash value itself, not just the selected bucket. Similarly, do not rely on inserting enough elements to trigger a table resize as a repair mechanism: that is not an API-guaranteed rekeying operation.

## 4. Three types of modifications to recognize

### 4.1. Hash code changes

A field used to compute `hashCode` is modified after insertion:

```java
// Illustrates a dangerous operation; the MutableKey class is in the full program.
MutableKey key = new MutableKey(1);
map.put(key, "payload");
key.setId(2);
```

Possible symptoms include:

- `containsKey(key)` returns `false` even though iterating over the map still reveals the key.
- `get(key)` returns `null` even though the stored value is non-`null`.
- `remove(key)` fails to remove the entry the programmer intended to delete.
- A subsequent `put` does not produce the state the programmer expects as "updating the old entry".

You should never write business logic assuming a specific symptom is guaranteed to occur. Once a key has been mutated in an unsupported way, the API guarantees no automatic recovery path.

Note also that `get` returning `null` carries another meaning in `HashMap`: either there is no mapping for the key, or the key is explicitly mapped to a `null` value. When diagnosing a valid map that permits `null` values, you must check `containsKey` as well. In the runnable example below, the initial value is the string `"payload"` to eliminate this ambiguity. [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

### 4.2. Equality relationship changes, even though the hash code stays the same

Suppose every instance of a class returns a constant hash code of `7`. While this hurts performance, having multiple objects share the same hash code does not by itself violate the rule that "equal objects must have equal hash codes".

Consider two objects:

- `left.code = "A"`.
- `right.code = "B"`.

Initially they are unequal, so they are inserted as two distinct elements in a set. If `right.code` is subsequently changed to `"A"`, the two stored objects become equal.

The hash code is still `7`, but the equality relationship has changed. The set does not automatically re-run the insertion logic across all elements to deduplicate the newly equal element.

Key takeaway: **keeping the hash code constant is not enough; the equality meaning must also remain stable.**

An analogous situation in a map is even harder to resolve because two keys that have now become equal may be associated with two different values. If you rebuild the map, you must decide which value to keep or whether to report a collision. You cannot treat it merely as "rehashing to fix the index".

### 4.3. Non-identifying fields change

Not every mutation on an object breaks its usage in a map.

For example:

- `id` is a stable identifier.
- `displayName` is a mutable display name.
- `equals` and `hashCode` depend strictly on `id`.

Changing `displayName` does not alter the data used for equality or hashing. From a key-lookup perspective, that modification can be safe.

Nevertheless, you must verify the domain semantics. If `id` is actually unique only within each `tenant`, then a key containing only `id` was missing identifying data from the start. The decision to exclude a field from `equals` must come from a sound definition of identity, not as a workaround to dodge an observed bug.

## 5. Complete runnable program for Java 17 or later

The following program places these scenarios side by side:

1. Modifying a field that changes a key's hash code.
2. Modifying the equality relationship of a set element while its hash code stays constant.
3. Changing a field that does not participate in identity.
4. Observing the risk of a `record` holding a mutable list.
5. Using a defensive copy for the list and using immutable keys for rekeying.

Save the entire source into `MutableCollectionKeyDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class MutableCollectionKeyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void setId(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof MutableKey other && id == other.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    static final class SameHashKey {
        private String code;

        SameHashKey(String code) {
            this.code = Objects.requireNonNull(code, "code");
        }

        void setCode(String code) {
            this.code = Objects.requireNonNull(code, "code");
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof SameHashKey other
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return 7;
        }
    }

    static final class StableId {
        private final int id;
        private String displayName;

        StableId(int id, String displayName) {
            this.id = id;
            this.displayName = displayName;
        }

        void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        String displayName() {
            return displayName;
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof StableId other && id == other.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    record UnsafeTagsKey(String tenant, List<String> tags) {}

    record SafeTagsKey(String tenant, List<String> tags) {
        SafeTagsKey {
            tenant = Objects.requireNonNull(tenant, "tenant");
            tags = List.copyOf(tags);
        }
    }

    record UserKey(String tenant, int id) {
        UserKey {
            Objects.requireNonNull(tenant, "tenant");
        }
    }

    public static void main(String[] args) {
        MutableKey key = new MutableKey(1);
        Map<MutableKey, String> map = new HashMap<>();
        map.put(key, "payload");
        System.out.println("Before change: "
                + map.get(new MutableKey(1)));

        key.setId(2);
        System.out.println("Same object still stored: "
                + (map.keySet().iterator().next() == key));
        System.out.println("Map size after change: " + map.size());
        System.out.println("Lookup same changed object: " + map.get(key));
        System.out.println("Lookup old logical key: "
                + map.get(new MutableKey(1)));
        System.out.println("Lookup new logical key: "
                + map.get(new MutableKey(2)));

        SameHashKey left = new SameHashKey("A");
        SameHashKey right = new SameHashKey("B");
        Set<SameHashKey> set = new HashSet<>();
        set.add(left);
        set.add(right);
        right.setCode("A");
        System.out.println("Elements now equal: " + left.equals(right));
        System.out.println("Set size after equality change: " + set.size());
        System.out.println("Distinct references still stored: "
                + (set.stream().filter(value -> value == left).count() == 1
                && set.stream().filter(value -> value == right).count() == 1));

        StableId stable = new StableId(7, "Old name");
        Map<StableId, String> stableMap = new HashMap<>();
        stableMap.put(stable, "account");
        stable.setDisplayName("New name");
        System.out.println("Changed non-key field: " + stable.displayName());
        System.out.println("Stable identity lookup: "
                + stableMap.get(new StableId(7, "Another name")));

        List<String> mutableTags = new ArrayList<>(List.of("reader"));
        UnsafeTagsKey unsafe = new UnsafeTagsKey("t", mutableTags);
        UnsafeTagsKey oldSnapshot =
                new UnsafeTagsKey("t", List.of("reader"));
        mutableTags.add("writer");
        System.out.println("Unsafe record changed equality: "
                + !unsafe.equals(oldSnapshot));

        List<String> input = new ArrayList<>(List.of("reader"));
        SafeTagsKey safe = new SafeTagsKey("t", input);
        int oldHash = safe.hashCode();
        input.add("writer");
        System.out.println("Safe record tags: " + safe.tags());
        System.out.println("Safe record hash stable: "
                + (oldHash == safe.hashCode()));
        Map<SafeTagsKey, String> safeMap = new HashMap<>();
        safeMap.put(safe, "allowed");
        System.out.println("Safe record lookup: "
                + safeMap.get(new SafeTagsKey("t", List.of("reader"))));

        UserKey oldKey = new UserKey("t", 1);
        UserKey newKey = new UserKey("t", 2);
        Map<UserKey, String> accounts = new HashMap<>();
        accounts.put(oldKey, "value");
        if (!accounts.containsKey(oldKey)
                || accounts.containsKey(newKey)) {
            throw new IllegalStateException("cannot change key");
        }
        String value = accounts.remove(oldKey);
        accounts.put(newKey, value);
        System.out.println("Rekey old present: "
                + accounts.containsKey(oldKey));
        System.out.println("Rekey new value: " + accounts.get(newKey));
        System.out.println("Rekey size: " + accounts.size());
    }
}

```

Compile and run in the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked MutableCollectionKeyDemo.java
java MutableCollectionKeyDemo
```

The code uses only language features and APIs available in Java 17 or earlier. The commands above were verified with `javac` and Java 24.0.2 using `--release 17` at compile time; no external libraries are required.

Observed output from the verified run:

```text
Before change: payload
Same object still stored: true
Map size after change: 1
Lookup same changed object: null
Lookup old logical key: null
Lookup new logical key: null
Elements now equal: true
Set size after equality change: 2
Distinct references still stored: true
Changed non-key field: New name
Stable identity lookup: account
Unsafe record changed equality: true
Safe record tags: [reader]
Safe record hash stable: true
Safe record lookup: allowed
Rekey old present: false
Rekey new value: value
Rekey size: 1
```

**Scope of the results:** the lines belonging to the two scenarios that deliberately mutate a stored key/element describe the observed behavior of `HashMap` and `HashSet` in this specific run. Behavior after such mutation is not a portable guarantee of the `Map` or `Set` contract. The sections at the end using stable keys represent the design patterns you should apply.

### 5.1. Reading the MutableKey results

`Before change: payload` proves that an independent lookup key with `id = 1` finds the value prior to the modification.

After `key.setId(2)`:

- `Same object still stored: true` is verified via `==` while iterating `keySet`: the original reference still resides inside the map.
- `Map size after change: 1` shows that mutating a field is not an entry-removal operation.
- Looking up using the mutated object itself, a new key with `id = 1`, or a new key with `id = 2` all return `null` in this run.

A new key with `id = 1` is no longer equal to the stored object because the stored object now has `id = 2`. Meanwhile, a new key with `id = 2` starts its search using the new hash information, whereas the entry was organized under the old information. "Reusing the exact same object reference" does not bypass the initial candidate-selection process.

### 5.2. Reading the SameHashKey results

Two elements are added while their `code` values differ. After changing `right` to `"A"`:

- `Elements now equal: true` confirms the new equality relationship.
- `Set size after equality change: 2` shows that the collection does not automatically remove a duplicate entry.
- `Distinct references still stored: true` proves that both original references are still yielded during iteration.

Counting with `==` here is used strictly to observe the two physical objects. It does not replace the set's equality definition.

### 5.3. Reading the StableId results

The `StableId` key uses `id` for both `equals` and `hashCode`; `displayName` does not participate. Because `id` never changes, another instance with `id = 7` still locates `"account"` after the display name is modified.

This is an example of an object with mutable state that nonetheless maintains a stable key-identifying core. In larger designs, separating the key into its own dedicated type is usually easier to test and reason about.

### 5.4. Reading the record and list results

`UnsafeTagsKey` directly retains the list reference passed into it. After `mutableTags.add("writer")`, the `tags` component inside the record sees the mutated list as well, so the record is no longer equal to a snapshot containing only `"reader"`.

`SafeTagsKey` calls `List.copyOf(tags)` inside its compact constructor. Since the elements in this example are immutable `String` instances, modifying the input list afterward does not alter the list held inside the key. The key can still look up its value using an independent key initialized with the same data.

### 5.5. Reading the rekeying results

`UserKey` provides separate immutable key instances for the old identity and the new identity. The program verifies that the old key exists and the new key is absent, then removes the value under the old key and inserts it under the new key.

Afterward:

- The old key no longer exists.
- The new key resolves to the same value.
- The map size remains `1`.

This snippet executes on a single thread with immutable keys, with no concurrent actors mutating the map and no simulated failure between the two steps. It is not a universal atomic rekeying operation for every environment.

## 6. final and record do not automatically mean deep immutability

### 6.1. final locks the reference, not the entire object graph

Consider the declaration:

```java
final List<String> tags = new ArrayList<>();
tags.add("reader");
```

`final` forbids reassigning `tags` to point to a different reference after initialization. It does not forbid calling `add` on the referenced `ArrayList` instance.

If a key computes `equals` or `hashCode` from the contents of that list, mutating the list through any reference can alter the key's identifying data. A key class does not need an explicit `setTags` method on itself to be vulnerable.

Common indirect mutation paths include:

- The caller retains a reference to the input list and continues mutating it after constructing the key.
- An accessor method returns the internal list reference directly.
- The list itself forbids adding/removing elements, but the elements inside the list remain mutable.
- A nested object inside the key changes its own `equals` or `hashCode` result.

You must inspect both incoming data and outgoing data, as well as any nested objects upon which equality comparisons depend.

### 6.2. record generates component-based methods, not deep defensive copies

A `record` declares its component fields as `private final` and generates accessors, `equals`, `hashCode`, and `toString` based on those components. However, if a component references a mutable list, that list itself can still change. A record does not automatically turn an input list into an immutable copy. [Records in Java 17](https://docs.oracle.com/en/java/javase/17/language/records.html)

Therefore:

```java
record UserKey(String tenant, int id) {}
```

is a straightforward, stable key choice: `String` is immutable, `int` is a primitive value, and neither component can be reassigned after construction.

Conversely:

```java
record TagsKey(List<String> tags) {}
```

requires an explicit list-ownership policy. The `record` keyword alone does not supply that policy.

There are three important points to understand about the `List.copyOf` pattern used in the full program:

1. The resulting list does not allow structural modification through the `List` API.
2. Adding or removing elements on the original input list after copying is not reflected in the resulting list.
3. It does not perform a deep copy of each individual element.

`List.copyOf` rejects a `null` source collection as well as `null` elements. For `List<String>`, the string elements themselves are immutable, so the risk of mutating an element's internal state does not arise. If the component were `List<MutableTag>`, you would still have to guarantee the stability of each `MutableTag` element. [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

Furthermore, when a list forms part of an identity, element order matters according to `List.equals`. The two lists `["reader", "writer"]` and `["writer", "reader"]` do not automatically become the same key. If business rules require ignoring order or normalizing letter case, you must define and normalize the data at key-construction time, before inserting the key into a map.

## 7. Design choices: stable identity as the key, mutable data on the value side

A maintainable design typically looks like this:

```text
Immutable key: tenant + userId
                 ↓
Mutable value: display name, account status, current permissions...
```

Example key type declaration:

```java
record AccountKey(String tenant, long userId) {}
```

If `tenant` and `userId` define the account's identity and remain unchanged while stored, this key is much easier to work with than using a large `Account` object containing numerous mutable fields.

Decision table:

| Requirement | Option to consider | What to verify |
|---|---|---|
| Identified by a single stable code | Use an immutable code as the key | Is the code truly unique within the required scope? |
| Identified by multiple fields | Create a dedicated key class/record | Are all components stable and normalized consistently? |
| Updating only name, status, or display data | Mutate or replace the map's value | Is this data truly excluded from the key's identity? |
| Business identity genuinely changes | Execute a controlled rekeying workflow | Are there collisions with the new key, mid-flight failures, or concurrent access? |
| Using a key with nested collections | Make defensive copies and keep elements stable | Is the copy deep enough for the equality definition? |

Do not exclude a field from `equals` merely because it changes frequently if omitting it causes two distinct domain entities to collapse into the same key. First answer the question: "Which two objects are allowed to represent the exact same entry in this map?" Only then decide on the key structure.

A map's value object can mutate without affecting the key index of that map itself. For example, modifying `Account.displayName` in a map keyed by `AccountKey` does not mutate the key. However, if you subsequently use the entire map—or an object containing that map—as a key somewhere else, you must re-evaluate the `equals` and `hashCode` dependency chain in that outer context.

## 8. When identifying data must change

### 8.1. Preferred approach: replace with a new immutable key

For a map owned by a single thread, the workflow can be:

1. Represent the old key and the new key as stable values.
2. Verify that the old key exists.
3. Check the policy when the new key already exists: reject, merge, or overwrite.
4. Retrieve the value and remove the mapping under the old key.
5. Insert the mapping under the new key.
6. Verify that the resulting state satisfies the chosen policy.

The runnable program above chooses a rejection policy if the new key already exists. That is one specific policy; not every application must use the exact same policy.

If a map permits `null` values, merely checking whether `remove` returned `null` is insufficient to distinguish "key was absent" from "key was present with a `null` value". That is why the example checks `containsKey(oldKey)` first.

A check-then-remove-then-put sequence can be interleaved when multiple threads or external actors mutate the map. It may also require rollback logic if the system performs additional operations that can fail mid-way. Synchronization, transaction management, or coordination must cover the entire rekeying requirement, not just an individual method call.

### 8.2. If you still use a mutable key object

Within a strictly controlled scope, the mandatory order of operations is:

```text
Key is still in its old state and the map is still valid
    → remove the key from all structures currently indexing it
    → mutate the identifying data
    → re-insert under the new data and handle any collisions
```

The decisive point is **removing before mutating**, while lookup using the old state is still valid. Mutating first and calling `remove(key)` afterward may already be too late.

At the same time, you must know every place where that object is currently stored. A single key instance might appear in multiple maps or simultaneously reside in a set. Removing it from only one map does not make mutating it safe for the remaining data structures.

This approach demands strict ownership and coordination. If you cannot prove those conditions hold, creating separate immutable key instances is a far less risky choice.

### 8.3. If an object was already mutated while stored inside a hash table

Do not repeatedly call `put`, `remove`, or force map resizing in the hope that the table will heal itself.

A controlled recovery approach is:

1. Stop further mutations and concurrent access to the affected structure.
2. Inspect the existing entries to capture the keys, values, and any collision evidence needed.
3. Migrate the data onto new, stable keys.
4. Detect keys that have now become equal and apply an explicit collision-resolution policy.
5. Replace the old structure only after the new result has been validated.

This is a data-recovery procedure, not a guarantee that every operation on a misused map has specified behavior. If the incident affects critical data, you should cross-check against an authoritative data source or a trusted snapshot.

Never blindly copy entries into a new map and assume every value was preserved: keys that have mutated into becoming equal can cause one value to silently overwrite another. Re-indexing must always be paired with a business decision on how to handle collisions.

## 9. Changes that look like fixes but do not solve the root cause

### 9.1. Reusing the exact same reference

`get(key)` is not a request to perform a full linear scan for a matching object address. A hash-based structure typically navigates to candidate nodes via the hash before checking reference identity. Therefore, "I still hold the original `key` variable" does not guarantee the key can still be found.

### 9.2. Switching to ConcurrentHashMap

`ConcurrentHashMap` provides thread-safety guarantees for concurrent access. It does not make internal key fields immutable, nor does it automatically track field mutations on stored keys. [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Operations such as `compute` or `putIfAbsent` also do not automatically turn "remove old key and insert new key" into an atomic rename across two distinct keys. Dedicated coordination is required if business rules demand atomicity across the whole sequence.

### 9.3. Wrapping the map in unmodifiableMap or calling Map.copyOf

A map that forbids structural modification through its own API can still hold references to keys or values with mutable internal state. Blocking `put` and `remove` does not block an external reference from calling `key.setId(...)`.

`Collections.unmodifiableMap` creates an unmodifiable view over the map; it does not freeze the key objects themselves. Likewise, with `Map.copyOf`, you must not assume that key objects have been deeply copied. [Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)), [Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map))

### 9.4. Changing hashCode to a constant

If the `equals` relationship changes, a constant hash code does not protect element uniqueness. The `SameHashKey` example demonstrated this directly. A constant hash code also degrades hash distribution, so it is never a valid fix for key design.

### 9.5. Switching to TreeMap or TreeSet

Sorted structures rely on comparison rules to locate elements. If you mutate a field used by `Comparator` or `compareTo` while an element is stored, its ordering relationship can change without the tree rebalancing or reorganizing itself. Switching data structures only helps when the identification criteria and mutation patterns genuinely match the new structure's contract. [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

### 9.6. Using IdentityHashMap to bypass equals and hashCode

`IdentityHashMap` identifies keys by reference identity (`==`). That is a fundamentally different key model, suitable for specific problems that track individual object instances in memory. Two distinct object instances carrying the same business code will not automatically be treated as the same key. Therefore, it is appropriate only when the problem domain explicitly requires reference-identity semantics. [IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

### 9.7. Waiting for ConcurrentModificationException

Mutating a field on a stored object is not a structural addition or removal through the collection's API. There is no guarantee that such a field mutation will trigger a `ConcurrentModificationException`.

The fail-fast mechanism that detects structural modifications during iteration is not a validator for key-identity stability. A program that throws no exception can still be holding a corrupted lookup structure whose queries are no longer reliable.

## 10. How to review a key type before putting it into production

### 10.1. Verify the identity definition

Write down a single clear sentence, for example:

> In this map, two keys are equal when they share the same tenant and the same account ID.

Then cross-check:

- Does `equals` use strictly those two components?
- Is `hashCode` computed from the corresponding components?
- Can any of those components change while the key is stored?
- Does input data require normalization?
- Was any field omitted that could cause two distinct identities to collapse into one?

An IDE-generated method can be syntactically consistent while still encoding the wrong domain identity.

### 10.2. Check indirect mutation paths

Look for setter methods, accessor methods, and shared references. For keys containing nested data, inspect the inner objects as well.

Practical questions to ask:

- After creating the key, does mutating the caller's input list alter the key?
- Does retrieving a list from the key and mutating it alter the key?
- Can elements inside the list mutate state that participates in equality?
- Is a `final` field holding a reference to a mutable object?
- Could a subclass override relevant methods and alter how identity is evaluated?

### 10.3. Test valid behavior, do not lock in an unguaranteed failure symptom

Tests should protect your design invariants:

| Invariant / Commitment | Meaningful way to test |
|---|---|
| Independent key with the same identity can look up the entry | Create two separate key instances with identical data; use the second key to retrieve the value inserted with the first |
| Non-identity fields are allowed to change | Change the display name; verify that an independent key with the same identity still looks up the entry properly |
| Input data is defensively copied | Mutate the input list after construction; verify that the key's data, equality, and hash code remain unchanged |
| Key does not expose mutable internal structures | Verify that returned collection accessors enforce immutability in line with the design |
| Rekeying follows the defined policy | Test when the new key is free, when the new key already exists, when the old key is absent, and when the mapped value is `null` (if supported) |
| Collisions do not silently lose data | Construct a scenario where multiple entries map to the same new key and verify the collision-handling policy |

Do not treat an assertion like `map.get(mutatedKey) == null` as a portable contract that your application must preserve across every JVM. That only tests one symptom of violating the storage preconditions. A far more valuable test ensures that identifying data cannot be mutated while a key is stored.

## 11. Practice exercises

### Exercise 1: changing an account name

A map uses `record AccountKey(String tenant, long id)` as its key and an `Account` object as its value. Is changing `Account.displayName` considered mutating the key?

**Answer:** no, provided `Account` is strictly the value and changing the display name does not alter the components of `AccountKey`. You still need to handle concurrency and any value-specific constraints if applicable, but that is separate from key stability.

### Exercise 2: a record containing a list

A key is defined as `record GroupKey(List<String> members)`. The caller constructs the key using an `ArrayList` and then continues adding members to that `ArrayList`. Can we conclude this is safe because a record has no setter methods?

**Answer:** no. The record holds a reference to the passed-in list. The list's contents directly affect the component's equality and hash code. You need to re-evaluate the group identity definition and apply a defensive-copying policy; if group membership changes frequently, using a stable group ID as the key is usually a better design.

### Exercise 3: hashCode always equals 7

A set contains two elements whose hash code is always `7`. They are unequal when inserted, and later one element is mutated so that it becomes equal to the other. Is an unchanged hash code sufficient to guarantee the set remains valid?

**Answer:** no. The equality relationship changed while the elements were stored. The hash code is only one part of the invariant that must remain stable.

### Exercise 4: order of mutation and removal

A developer calls `key.setId(newId)` and then `map.remove(key)` before re-inserting the key. Why is this order dangerous?

**Answer:** the removal operation starts searching using the new state, whereas the entry was indexed under the old state. If you must use a mutable key within a controlled scope, you have to remove it while it still holds its old state. A much more maintainable approach is to use two distinct immutable key instances and an explicit re-mapping workflow.

### Exercise 5: two concurrent operations rekeying

A `ConcurrentHashMap` workflow checks that a new key is absent, removes the old key, and inserts the new key. Does `ConcurrentHashMap` automatically guarantee that no other thread can interleave between those steps?

**Answer:** no. Having thread-safe individual operations does not turn a multi-step sequence across two keys into an atomic transaction. You must establish synchronization or transactional boundaries at the level of the rekeying operation.

## 12. Key takeaways

- Keep both the equality relationship and the hash code stable for the entire duration a key or element is stored in a hash table.
- A class can implement `equals` and `hashCode` consistently at each individual point in time yet still be misused if its identifying data changes while stored.
- Keeping the same reference, returning a constant hash code, or using `final`, `record`, or an unmodifiable map wrapper does not automatically close every mutation path on identifying data.
- Prefer small, immutable keys that accurately model domain identity; place frequently changing information in the mapped value.
- When a domain identity genuinely needs to change, handle it through an explicit rekeying workflow with clear collision and concurrency policies.
- Use failure demonstrations to understand the risks; use design invariants to test for correct code.

## References

- [Object — equals and hashCode contracts](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).
- [Map — key usage requirements and mapping operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
- [Set — element usage requirements and uniqueness](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).
- [HashMap — API behavior and implementation characteristics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).
- [Records in Java 17](https://docs.oracle.com/en/java/javase/17/language/records.html).
- [List.copyOf — unmodifiable copy and copying boundaries](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [OpenJDK 17 HashMap source code — concrete mechanism reference](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java).
