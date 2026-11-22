# Reproducing the Bug of Mutating a Key After Putting It into a HashMap

## 1. Practice Objective

When an object is used as a **key** in a `HashMap`, the values participating in `equals()` and `hashCode()` must remain stable for the entire time the object resides in the map. If you mutate a field used to compute the key after calling `put()`, the map may **fail to find the entry**, even though the entry is still there and even when using the exact original reference variable.

In this practice, we will:

1. Create a key class with a mutable `id` field.
2. Override `equals()` and `hashCode()` based on `id`, obeying both methods' contracts at every state.
3. Put the key into a `HashMap`, mutate `id`, and observe `get()`, `containsKey()`, `remove()`, and `size()`.
4. Explain why the map loses the ability to look up an entry that still exists.
5. Try calling `put()` again to observe an even more anomalous state.
6. Fix the design with an immutable key and verify the result.

**Conclusion to prove:** still holding a reference to the key and seeing `map.size()` greater than 0 **does not mean** `map.get(key)` can still find the value. `HashMap` uses the hash code to determine the lookup slot; it does not scan every entry to match that reference.

## 2. Reviewing HashMap's Key Contract

`HashMap<K,V>` implements `Map<K,V>` using a hash table. Two methods on the key play primary roles:

- `hashCode()`: produces an integer used to select the storage/lookup region, after `HashMap` processes bits and computes the bucket index.
- `equals(Object)`: decides whether two keys are considered logically the same key once HashMap has checked the relevant hash conditions.

Core contract between the two methods:

- If `a.equals(b)` returns `true`, `a.hashCode()` and `b.hashCode()` must be equal.
- If `a.hashCode() == b.hashCode()`, you cannot yet deduce `a.equals(b)`.
- For an object whose information used in `equals()` does not change, `hashCode()` must remain stable during the corresponding execution.
- When `equals()` returns `false`, two keys may share a hash; HashMap can still store them as two separate entries.

**Using a key in a map also requires a practical condition:** do not mutate a key's state in a way that affects equality comparisons while the key is in the map. Java's `Map` documentation states that behavior is not specified if an object used as a map key is mutated in a manner that affects `equals` comparisons while it is in the map.

This does not mean a mutable key class always immediately violates the `equals/hashCode` contract itself. The class can still compute both methods consistently at any single instant, yet **the map indexed the entry under the old state** and is not notified to re-index when the key field changes.

## 3. Runnable Example: A Key Changes Hash After Put

Create the file `MutableHashMapKeyDemo.java` (Java 17+):

~~~java
import java.util.HashMap;
import java.util.Map;

public class MutableHashMapKeyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void setId(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            return obj instanceof MutableKey other && id == other.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    public static void main(String[] args) {
        Map<MutableKey, String> map = new HashMap<>();
        MutableKey key = new MutableKey(1);

        map.put(key, "An");
        System.out.println("hash before: " + key.hashCode());
        System.out.println("get before: " + map.get(key));
        System.out.println("size before: " + map.size());

        key.setId(2); // Design bug: mutating a field participating in equals/hashCode

        System.out.println("hash after: " + key.hashCode());
        System.out.println("get after: " + map.get(key));
        System.out.println("containsKey after: " + map.containsKey(key));
        System.out.println("remove after: " + map.remove(key));
        System.out.println("size after remove: " + map.size());
        System.out.println("containsValue An: " + map.containsValue("An"));

        for (Map.Entry<MutableKey, String> entry : map.entrySet()) {
            System.out.println("remaining entry: id="
                    + entry.getKey().id + ", value=" + entry.getValue());
            System.out.println("same key reference: "
                    + (entry.getKey() == key));
        }
    }
}
~~~

Compile and run:

~~~bash
javac MutableHashMapKeyDemo.java
java MutableHashMapKeyDemo
~~~

Output with JDK 17's `HashMap` implementation:

~~~text
hash before: 1
get before: An
size before: 1
hash after: 2
get after: null
containsKey after: false
remove after: null
size after remove: 1
containsValue An: true
remaining entry: id=2, value=An
same key reference: true
~~~

### Explaining Each Output Line

1. On `put(key, "An")`, `hashCode()` returns `1` and `HashMap` stores the entry under the hash at insertion time.
2. `map.get(key)` before mutation returns `"An"` because the object's state matches the indexed information.
3. After `key.setId(2)`, that same `key` object changes its `hashCode()` from `1` to `2`. The previously stored entry **does not move automatically**.
4. `map.get(key)` looks up using the new hash. It does not find the entry located at the old position/hash, so it returns `null`.
5. `containsKey(key)` is `false` and `remove(key)` returns `null` because they also depend on looking up the key by its new hash code.
6. `size()` still returns `1` because `remove` could not delete the entry; `containsValue("An")` remains `true` because that operation checks values across existing entries.
7. Iterating `entrySet()` proves the map still holds **the exact original key object** (comparison via `==` is `true`), which now has `id == 2`.

A `null` result from `get` does not by itself prove no entry exists if the map permits `null` values. In this example, we already know the inserted value was `"An"` and additionally verify with `containsKey`, `size`, and `entrySet`.

## 4. Looking Deeper at the Cause: Hash Is Recorded at Insertion

To visualize the bug, consider a simplified model corresponding to the example above (JDK `HashMap` typically initializes a 16-bucket table on first insertion). For small hashes like `1` and `2`, the hash mixing in common implementations preserves the value, leading to different buckets.

~~~text
At put time:
key.id = 1  ---> hashCode() = 1
                    |
                    v
           bucket 1: [stored hash = 1, key -> "An"]

After key.setId(2):
key.id = 2  ---> hashCode() = 2
                    |
                    v
           search in bucket 2: no entry found

Meanwhile bucket 1 still holds:
           [stored hash = 1, key (now id=2) -> "An"]
~~~

This is a model explaining the phenomenon in JDK 17, **not an API guarantee** regarding bucket counts, bucket formulas, or internal structures across all Java versions.

In OpenJDK's `HashMap` implementation, each entry/node stores the hash computed at insertion time. During lookup, the map computes the hash from the key object at call time and uses that hash when identifying matching entries. Mutating the key does not trigger `put`/rehash for an existing entry.

A common misconception is: "`key.equals(key)` surely returns `true`, so `get(key)` must succeed." In reality, **`equals` comparison cannot rescue the entry if the hash lookup step already led to a different location**. Reusing the exact same reference (`==`) does not help either.

Another misconception is "if the new hash happens to fall into the same bucket, lookup will stay safe." In common HashMap implementations, matching conditions also inspect the entry's **stored hash**, so landing in the same bucket provides no guarantee when the hash code changes. Moreover, mutating a field that participates only in `equals()` without changing `hashCode()` can also break lookup semantics with other equivalent key objects. The design rule remains **keep both the fields affecting `equals()` and `hashCode()` stable**.

## 5. Extended Experiment: Putting the Same Key Variable Again

**Perform this only to observe the bug; never use it to "fix" a map in an application.**

Insert the following lines after the `for` loop in `main` of the section 3 example:

~~~java
map.put(key, "Binh");
System.out.println("size after re-put: " + map.size());
System.out.println("get after re-put: " + map.get(key));

for (Map.Entry<MutableKey, String> entry : map.entrySet()) {
    System.out.println("entry value: " + entry.getValue()
            + ", same reference: " + (entry.getKey() == key));
}
~~~

Given the map state after the main example, the output of this added snippet in JDK 17 is:

~~~text
size after re-put: 2
get after re-put: Binh
entry value: An, same reference: true
entry value: Binh, same reference: true
~~~

Here, the hash table can contain **two entries holding the exact same key reference**: the old entry still sits under hash `1`, and the new entry is inserted under hash `2`. `size()` becomes `2` even though both keys are the same object.

This happens because `HashMap` cannot find the old entry using the key's current hash and treats `put` as inserting a new entry. It illustrates the anomalous state created when violating key stability assumptions. This practice chose small hash codes `1`/`2` so bucket behavior in JDK 17 is clear; **never rely on this specific buggy behavior as a feature guaranteed by the `Map` API**.

Do not issue further `put`, `remove`, or `compute` calls assuming the state has recovered; a map whose keys were mutated while stored can become unpredictable, especially when multiple keys and equality relationships change.

## 6. Fixing with an Immutable Key

The most reliable fix is **using a key whose identifying state is immutable**. With Java 17, a `record` containing only immutable components such as `int`, `long`, and `String` is a concise choice.

Create the file `StableHashMapKeyDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class StableHashMapKeyDemo {
    record UserKey(int id) {}

    public static void main(String[] args) {
        Map<UserKey, String> map = new HashMap<>();

        UserKey oldKey = new UserKey(1);
        map.put(oldKey, "An");

        System.out.println("get by equivalent key: "
                + map.get(new UserKey(1)));

        UserKey newKey = new UserKey(2);
        System.out.println("get with new id: " + map.get(newKey));
        System.out.println("get with old id: " + map.get(oldKey));

        String oldValue = map.remove(oldKey);
        map.put(newKey, oldValue);

        System.out.println("get after key migration: " + map.get(newKey));
        System.out.println("size: " + map.size());
        System.out.println("contains old key: " + map.containsKey(oldKey));
    }
}
~~~

Compile and run:

~~~bash
javac StableHashMapKeyDemo.java
java StableHashMapKeyDemo
~~~

Output:

~~~text
get by equivalent key: An
get with new id: null
get with old id: An
get after key migration: An
size: 1
contains old key: false
~~~

**The key difference:** `UserKey(1)` is not mutated into `UserKey(2)`. When business logic needs to change an identifier, the application **removes the entry with the old key first**, then inserts with **a new key object**. The hash table state and lookup rules remain intact.

In the general case, `remove(oldKey)` can return `null` either because the key did not exist *or* because the key was mapped to a `null` value. If the map allows `null` values, check `containsKey(oldKey)` before migrating the key to distinguish the two cases. Also clarify the policy when `newKey` already exists, as `put(newKey, value)` can overwrite existing data. The example above uses simple data so neither issue arises.

### 6.1. Record Does Not Automatically Provide Deep Immutability

Do not infer that every `record` is a safe key. For example:

~~~java
record ArrayKey(int[] values) {}
~~~

Arrays are still mutable. Furthermore, the auto-generated `equals/hashCode` for an array component uses the comparison/hash of the array reference itself, **not the array contents**. If business logic needs element-wise comparison, you must define the equality relation explicitly and protect the state behind that relation. Reference fields like collections or mutable beans inside a `record` also require examining aliasing and how `equals/hashCode` are computed.

For a simple identifier, `record UserKey(int id)` is a good example because `int` has no nested mutable objects inside.

### 6.2. Values Can Be Mutable; Keys Should Be Stable

Another design pattern is storing the mutable business object as the **value**, and using an immutable ID as the **key**:

~~~java
// Illustrative snippet inside a method; account is a business object.
Map<Long, Account> byId = new HashMap<>();
byId.put(account.getId(), account);
account.setDisplayName("New name"); // Does not change the Long key
~~~

`Account` here is merely an illustrative business class name, not a JDK class or standalone runnable program. If the ID itself ever needs to change, you must define how to migrate the entry in the map using the old and new keys. Never mutate a stored key object in a way that affects `equals/hashCode`.

## 7. What If You Must Use a Key Class with Mutable Fields?

There are classes with setters that can still be used as keys if **only fields that do not affect `equals/hashCode` are allowed to change while serving as a key**. For example, a `User` with a `final long id` used in `equals/hashCode` and a mutable `displayName` *not participating* in those two methods: changing the name does not itself break lookup by ID.

However, all of the following must hold simultaneously:

- The `equals` and `hashCode` rules use the exact same identification criteria and stay stable throughout the key's lifecycle.
- No setter, external alias, or nested reference exists that can silently alter those identifying details.
- Fields used in comparison do not depend on mutable external state outside the object, such as configuration, current time, or mutable collections.
- Objects considered equal always yield the same hash. Avoid using changing data or unstable rules when computing the hash.

**Caution:** using `final` on a variable holding a key, such as `final MutableKey key = ...`, only prevents reassigning the variable to another object; `key.setId(2)` is still valid. Using `final` on a reference field also does not make the referenced object immutable. For arrays or collections participating in identification, defensive copying and/or truly immutable structures are required.

### When a HashMap Has Already Been Corrupted

There is no `Map`-guaranteed "refresh hashes for all mutated keys" method that handles every corrupted state. You can:

1. If you know the exact old identifying state and no anomalous duplicate entries have appeared, restore the key to its old state **only as a controlled incident recovery measure**, remove the entry under the old state, and switch to a new immutable key.
2. If a reliable source of truth remains (database, list of objects with stable IDs, snapshot), **build a new map** using immutable keys constructed from that source. Define a policy if multiple entries map to the same logical key.
3. If you must iterate `entrySet()` of the corrupted map to salvage data, check for duplicate keys, conflicting values, and aliases; this is not an automatic recovery guaranteed to be lossless.

Even `new HashMap<>(damagedMap)` is **not** a design patch: it does not make keys immutable and may merge keys currently seen as equal or preserve the risk of future mutation.

## 8. Debugging Workflow in Real Projects

When `get(key)` unexpectedly returns `null`, inspect in order:

1. **Check the exact map instance:** does the variable being read point to the map where `put` was previously called? Did anything call `clear` or `remove`?
2. **Distinguish missing key from null value:** use `containsKey(key)` and check whether the map permits storing null values.
3. **Log identifying attributes before and after:** if possible, log the ID, fields participating in `equals/hashCode`, and hash at both points in time; do not log only `toString()`.
4. **Inspect setters and aliases:** was the key object mutated from somewhere else after `put`? Is there a nested collection/array participating in comparison?
5. **Iterate `entrySet()` for diagnosis:** check whether the entry still exists and what the key's current identity looks like. Finding the object in iteration does not prove `get(key)` ought to find it.
6. **Check `equals/hashCode` implementations:** two objects considered equal must share the same hash; check symmetry, transitivity, stability, and `null` handling per contract.
7. **Fix the design and re-test:** use an immutable key or separate key/value. Do not patch by re-inserting the same mutable key to mask the symptom.

This bug is not solved merely by switching to `ConcurrentHashMap` or synchronization locks: concurrent collections handle multi-threaded access, yet **they do not make a mutable key object's identifying state immutable**. If a key can change while in use, the design flaw remains.

## 9. Self-Check Exercises

### Question 1: Does having the same object reference guarantee `get` succeeds?

**No.** The example in section 3 uses the exact same `key` variable for both `put` and `get`. HashMap does not rely on scanning all elements and comparing identity to locate an entry.

### Question 2: What if a field that does not participate in `equals/hashCode` is mutated?

If that field truly has no direct or indirect effect on the hash and equality relation, that change alone does not break key indexing. However, the program must still properly address other requirements such as thread safety.

### Question 3: Should `System.identityHashCode(key)` be used for keys?

Do not treat this as a general fix. Identity hash is tied only to object identity and does not reflect value equality. Choose `equals/hashCode` according to the key identification contract. If the problem genuinely requires identity comparison, consider `IdentityHashMap` with a clear understanding of `==` semantics and its differences from `HashMap`; it is not suitable as a mechanical replacement.

### Question 4: Why can `HashSet` suffer from the same bug?

In standard Java implementations, `HashSet` is backed by a hash structure. If you add an object and then mutate state affecting `hashCode/equals`, `contains` or `remove` can fail even while the element remains visible during iteration. This is the same class of bug: **mutating identifying state while stored in a hash-based collection**.

### Question 5: Must every object used as a key be strictly immutable?

The `Map` contract does not strictly require key types to be declared `final` or completely immutable. The essential requirement is that **information affecting equality and hash codes must remain stable** while the key is in the map. In practice, immutable design is the clearest and easiest way to guarantee this during code review.

## 10. Quick Memory Checklist

- Before `put`: know which fields participate in `equals/hashCode`.
- While the key is in the map: **do not mutate** those fields or any mutable data they depend on.
- When needing to change a "key ID": use a **new key**, remove using the **intact old key**, and re-insert according to your conflict policy.
- When `get` returns `null`: cross-check `containsKey`, `size`, `entrySet`, and key state; do not immediately conclude the data vanished.
- In new designs: prefer primitive/`String`/immutable IDs or a `record` containing only immutable identifying components.

**Remember:** `HashMap` does not watch setters to automatically re-index entries. A key can still sit inside the map yet get "lost" during lookup because **the state used to determine hash/equals changed after insertion**.
