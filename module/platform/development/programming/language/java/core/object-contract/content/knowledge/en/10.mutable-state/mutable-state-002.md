# Why a Key Can Become Unfindable After Modification

## 1. Symptom: the entry is still in the Map, yet `get` returns null

Consider an object used as a **key** in a `HashMap` or as an **element** in a `HashSet`. If the fields used to compute `equals(Object)` and `hashCode()` are modified **after the object has been added to the hash structure**, calling `get(key)`, `containsKey(key)`, `remove(key)`, or `contains(element)` may fail to find the stored entry, even when you pass in **the exact same old object reference**.

This can be surprising: `map.size()` may still be `1`, iterating over `entrySet()` still shows the entry, yet `map.get(key)` returns `null`. Nothing automatically deletes the data; the problem lies in **the storage location having been determined from the old hash code**, whereas the subsequent lookup uses the **new hash code**.

This is a consequence of the relationship between mutable state, the `equals`/`hashCode` contract, and how a hash table locates elements. `HashMap` does not watch for changes to automatically move an entry to another bucket whenever a field in the key object is modified.

> Takeaway: changing a field unrelated to `equals` and `hashCode` does not affect lookup. The risk specifically arises when modifying **state involved in determining equality or the hash code**.

## 2. Step-by-step mechanism

Suppose class `Key` has a field `id`; two keys with the same `id` are equal, and `hashCode()` returns the hash of `id`.

1. When `map.put(key, value)` is executed while `id == 1`, `HashMap` computes the current hash of the key, uses that hash to determine the bucket, and stores the entry in its internal structure. The JDK's `HashMap` implementation also stores the hash code computed at insertion time in the internal entry.
2. Afterward, application code modifies `key.id = 2`. **The key object has changed**, but the entry inside the hash table does not automatically relocate to match the new state.
3. When `map.get(key)` is called, `HashMap` recomputes the hash from `id == 2`. This hash may direct the lookup to a different bucket from where the entry was inserted, or fail to match the hash stored in the old entry.
4. Because no matching entry is found via the lookup algorithm, `get` returns `null` and `containsKey` returns `false`, even though the data can still be traversed via `entrySet`.

Conceptual illustration:

~~~text
Before modification:
key.id = 1  -> hash = 1 -> bucket of hash 1 -> [key -> "data"]

After modifying key.id = 2:
key.id = 2  -> hash = 2 -> search by hash 2 -> stored entry not found
                                               (old entry is still in previous bucket)
~~~

This is a **logical diagram**, not a description of fixed bucket addresses across all table capacities. Actual bucket positions depend on the hash mixing algorithm, table size, and structural resize history. The core point remains: **mutating the key object itself is not equivalent to removing the old entry and reinserting it**.

A hash code is also not a unique storage slot. Multiple objects can share the same hash; when handling collisions, `HashMap` performs additional key checks, including `equals`. Therefore:

- If two objects are **equal**, they must have the same hash code.
- If two hash codes are the same, the two objects are **not necessarily equal**.
- If a stored key changes fields participating in equality, the key's state inside the hash structure is no longer stable; searching by either the new key or the old key may fail to produce the expected result.
- `get` returning `null` by itself can also happen because the value associated with the key is genuinely `null`. Use `containsKey` and inspect entries in `entrySet` to distinguish these when debugging.

## 3. Runnable Java 17 program

The following example has `MutableKey` with a mutable `id` field and a `StableKey` class using a `record` with an `int` component that cannot change after creation. The `equals` and `hashCode` methods of `MutableKey` are **correct while `id` is fixed**; the bug comes from changing `id` while the object is inside a collection.

Save the following code to **`MutableHashKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class MutableHashKeyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void changeId(int newId) {
            id = newId;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof MutableKey that && id == that.id);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    record StableKey(int id) { }

    public static void main(String[] args) {
        Map<MutableKey, String> broken = new HashMap<>();
        MutableKey key = new MutableKey(1);
        broken.put(key, "data");

        System.out.println("before: " + broken.get(key));

        key.changeId(2);
        System.out.println("after: " + broken.get(key));
        System.out.println("contains mutated: " + broken.containsKey(key));
        System.out.println("entries: " + broken.size());
        System.out.println("entry still value: "
                + broken.entrySet().iterator().next().getValue());
        System.out.println("same object reference: "
                + (broken.entrySet().iterator().next().getKey() == key));
        System.out.println("search old id: "
                + broken.get(new MutableKey(1)));
        System.out.println("search new id: "
                + broken.get(new MutableKey(2)));

        Set<MutableKey> set = new HashSet<>();
        MutableKey member = new MutableKey(5);
        set.add(member);
        member.changeId(6);
        System.out.println("set contains after: " + set.contains(member));
        System.out.println("set size: " + set.size());

        Map<MutableKey, String> safe = new HashMap<>();
        MutableKey editable = new MutableKey(100);
        safe.put(editable, "safe");
        String savedValue = safe.remove(editable); // While hash is still 100
        editable.changeId(101);
        safe.put(editable, savedValue);
        System.out.println("safe lookup: " + safe.get(editable));

        Map<StableKey, String> stable = new HashMap<>();
        StableKey original = new StableKey(8);
        stable.put(original, "stable");
        StableKey replacement = new StableKey(9);
        System.out.println("stable original: "
                + stable.get(new StableKey(8)));
        System.out.println("stable replacement: "
                + stable.get(replacement));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac MutableHashKeyDemo.java
java MutableHashKeyDemo
~~~

Output:

~~~text
before: data
after: null
contains mutated: false
entries: 1
entry still value: data
same object reference: true
search old id: null
search new id: null
set contains after: false
set size: 1
safe lookup: safe
stable original: stable
stable replacement: null
~~~

### Reading the output properly

- **`before: data`:** immediately after insertion, `key.id == 1`; the hash at lookup time still matches the hash at insertion time.
- **`after: null` and `contains mutated: false`:** `id` changed to `2`, so the new hash no longer leads to the entry with the old hash in this example. Both lookup calls fail to find the entry.
- **`entries: 1` and `entry still value: data`:** the element was not automatically deleted, so it still exists in the `HashMap`.
- **`same object reference: true`:** the key in the stored entry is the exact `key` object that was mutated. Thus, failing to find it does not mean Java replaced the key with a copy.
- **`search old id: null`:** looking up with a new key where `id == 1` reaches the location holding the old entry, but the stored key now has `id == 2`, so `equals` no longer matches.
- **`search new id: null`:** looking up with a new key where `id == 2` uses the new hash, which does not match the location/hash stored when the old key was inserted. In this example with the default table size and these small integer values, the two hashes lead to two different buckets.
- **`set contains after: false` and `set size: 1`:** `HashSet` suffers from the exact same issue because it uses a hash structure underneath.
- **`safe lookup: safe`:** removing while the key still had `id == 100`, then changing to `101` and reinserting created an entry in the proper position for the new hash.
- **`stable original: stable`:** the record key holds a fixed `int`, so lookup with an equivalent key value continues to work. `replacement` is a new key with a different value and does not automatically replace the old key.

Do not conclude that **every** mutation always makes `get` fail. The result depends on the modified field, the `equals`/`hashCode` implementation, the hash values, and the specific operations. However, modifying data that determines hash/equality while a key is already in a hash structure is an unsafe design.

## 4. Why can the entry still be seen via `entrySet`?

`HashMap.entrySet()` allows iterating over the entries currently stored in the table. Iterating over the table does not require finding an entry based on **a freshly recomputed hash from an input key** like `get(key)` does.

In the program, an internal loop over the entry set still sees the key and value. Meanwhile, `get(key)` must repeat the location-finding process from the new hash. Because these two paths differ, the observation "iteration sees the entry, but lookup does not" is not contradictory.

For the same reason, you cannot assume you can fix the bug by calling `map.remove(key)` **after the key has already changed**: `remove` also needs to locate the key by its current hash and may fail. Repeatedly calling `put(key, value)` after the key has changed can even cause the same key reference to appear in different entries if the old entry is not found. That should not be treated as a way to "repair" a collection in an invalid state.

## 5. Diagnosing and preventing without losing entries

When encountering `size() > 0` yet `get(key) == null`, first distinguish **key not found** from **key mapped to a null value** using `containsKey`. Next, assuming no concurrent writers, inspect existing entries to verify whether the key object was modified compared to insertion time. Being able to iterate over the entry does not prove the hash structure can still find it using the current key.

**Rule to prevent the bug from the start:** use keys whose `equals/hashCode` data is stable; a `record` containing immutable types such as `String` or primitives is suitable. A record with an array or mutable collection component is only shallowly immutable: you must also protect component references and nested data.

If **you genuinely need to change an identifier**, validate the new key and check for collisions, **remove the old key while it is still intact**, and only then modify the attribute or create a new key and reinsert. For a `Map` that allows null values, check existence before relying on the return value of `remove`. A `remove → mutate → put` sequence is not an atomic transaction when other writer threads exist.

If **a key has already been mutated while stored**, do not repeatedly call `remove(mutatedKey)` or `put(mutatedKey, value)` to fix it: that lookup path itself may be wrong or create extra entries. You need exclusive control over the collection, iterate to identify the entry, remove via a valid iterator when appropriate or rebuild from trusted data, and check the duplicate policy. Key-transition steps with collision handling, rollback, and concurrency are taught specifically in the lesson *Removing and Re-adding Data When Business Logic Truly Requires Changing a Key*.

With a mutable object used as a **value** in a `Map`, modifying only display fields of the value does not cause a hash bug for the **key**. For objects used as keys, separating immutable identity from mutable display state avoids relying on old buckets. The lesson *Prefer Immutable Keys* goes deeper into choosing types and defending component objects.

## 6. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "The Map keeps a copy of the key, so editing the key outside has no effect" | `HashMap` normally stores a reference to the key object; it does not automatically copy custom keys |
| "The object is still in the map, so `get` is guaranteed to find it" | The entry still exists, but looking up by the current hash may not lead to the old entry |
| "Having a correct `equals` is enough" | For hash collections, `hashCode` must be consistent with `equals`, and fields determining equality must remain stable while used as a key |
| "If `hashCode` does not change, any mutation is safe" | Changing data used in `equals` still alters comparison semantics against other keys; keys must be designed to be stable |
| "Calling `remove` after changing the id will fix it immediately" | `remove` also looks up using the current hash and may fail to find the stored entry |
| "Using a `record` makes every field deeply immutable" | Reference-type components can hold mutable objects |
| "Changing an old key by mutating itself is equivalent to reinserting" | The table does not watch setters; you must remove first and re-add, or create a new key |

## 7. Design checks and testing

When designing a class to serve as a key, answer:

- Which fields are used in `equals` and `hashCode`? Do both methods use corresponding data to ensure equal keys share the same hash?
- Is there any update path that changes these fields **after the key has been placed into** a `HashMap`/`HashSet`?
- Does any other code hold a reference and possibly mutate the key?
- If an identifier must change, does the application remove the old entry and add the new key in an explicit order?
- Are there mutable component values inside an object that looks immutable?
- In a multithreaded environment, are key reads/writes and collection updates coordinated consistently?

A useful behavioral test is to insert a key, verify a successful lookup, attempt to modify permitted fields, and then check `get`/`containsKey` or `contains` again. If changing an identifier field is intentional business logic, tests should verify the **remove old key then add new key** workflow and entry count integrity. At the same time, verify `equals`/`hashCode` results when relevant data fields do not change.

**Takeaway:** Hash keys must have **stable equality state and hash codes for as long as they remain stored**. When you modify a field participating in `hashCode`, `HashMap` does not automatically move the entry to a new location; therefore the entry may still exist yet no longer be findable with `get`. Prefer immutable keys; if changing a key is unavoidable, update the collection through controlled removal and reinsertion.