# Consequences of Mutating Fields Used in `equals()` and `hashCode()`

## 1. The Problem: The Object Is Still in the Collection, Yet May Not Be Found

In Java, `HashMap` and `HashSet` use **hash codes and equality comparisons** to organize, look up, and detect duplicate keys/elements. If a field that affects `equals(Object)` or `hashCode()` is changed **while the object is a key in a `HashMap` or an element in a `HashSet`**, the structure that stored the object based on its old state will **not automatically relocate or reindex it** just because a setter ran.

The consequences can be:

- `contains` or `get` fails to find an object even though an iterator still traverses it.
- `remove` using the current key does not succeed.
- Two distinct objects that were not equal at insertion time become equal after mutation yet remain in the same Set.
- A Map can contain entries whose current keys carry the same logical identity.
- Cache misses, duplicate creation operations, inconsistent index data, and hard-to-reproduce tests.

**This is a bug caused by changing the information that determines equality/hash throughout the time the key is stored, not a Java syntax error.**

Example of a commonly encountered class:

~~~java
class MutableKey {
    private String code;

    MutableKey(String code) {
        this.code = java.util.Objects.requireNonNull(code);
    }

    void rename(String next) {
        code = java.util.Objects.requireNonNull(next);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey key
                && code.equals(key.code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
~~~

This is an **illustrative class**, without a `main` yet. When `code = "A"`, the hash is the hash of A; changing it to B changes the hash. If the key was added to a hash collection while it was A, the collection is not invoked to update the entry when the object changes its own field.

> **Principle:** Information affecting a key's `equals/hashCode` must remain stable throughout the time the key is stored in a hash-based collection, or must be replaced by a controlled remove, update, and re-add protocol.

This Java 17+ Knowledge README explains the `Object.equals/hashCode` contract, hash lookup mechanics, symptoms and guaranteed boundaries, mutable fields and aliases, records, entity identity, HashMap/HashSet/TreeSet, how to design immutable keys, safe updates, concurrency, and tests. There are four standalone Java programs accompanied by run commands and output results.

## 2. Precisely Identifying the Condition That Causes *key instability*

Before seeing how HashMap fails, we only need to keep two rules: `equals` is equality according to the class's contract (defaulting to Object identity); and **if two keys are equal, their hash codes must be equal**. The `equals` contract retains reflexivity/symmetry/transitivity/consistency when equality-related state does not change; collisions between unequal keys remain valid.

**The risk to investigate in this article is the timeline**, not that an implementation is always wrong:

~~~text
T0: key.code = "A"  → hash/equality based on state A
T1: map.put(key, value)  → entry is placed while key is still in state A
T2: key.rename("B")  → same object, but the comparison/hash field has changed
T3: map.get(key)  → lookup uses state B; the entry is not automatically relocated
~~~

Even if the `equals` and `hashCode` implementations **still match each other at T3**, changing equality-relevant information while acting as a key causes the application to lose membership/lookup guarantees under the collections' conditions. **Do not claim that every JDK always returns the same result**; hash collisions and the current structure may coincidentally make the lookup succeed.

The following sections explain the mechanics, present a HashSet program whose expected stdout relies only on deterministic facts, and then provide solutions using **immutable key**, **stable identity**, or controlled **remove–modify–reinsert**.

## 3. How Does HashMap Use Keys?

Conceptually:

**When writing `put(key, value)`:**

1. The Map obtains `hashCode` from the key to determine the appropriate storage path.
2. It uses key comparison according to the contract to detect an equivalent key.
3. It stores the entry associated with the key and value.

**When reading `get(lookupKey)`:**

1. The Map computes the hash of lookupKey at **read time**.
2. It searches for candidates matching the storage structure.
3. It checks logical equality to select the entry.

~~~text
At put time:
  key.code = "A"
  key.hashCode() = hash("A")
  entry is organized according to the key's state at that time

After the key.rename("B") call:
  key.code = "B"
  key.hashCode() = hash("B")
  entry is not automatically relocated just because of the rename call

At get time:
  lookup relies on hash("B")
  the state no longer matches the structure built for "A"
~~~

**HashMap does not deep-copy keys**, does not register listeners to automatically track setters on the key, and cannot know on its own when your code changes a field.

### 3.1. Post-Mutation Behavior Has No Standardized Fixed Outcome

The Java Collections specification clearly states that **the behavior is not fully specified** if an object's value is changed in a way that affects equality while it is in a Set/used as a key of a Map.

Therefore, do not claim that every JVM/implementation always returns `false` for `contains` after mutation. Symptoms depend on hash, collisions, capacity, implementation, and circumstances. **A test still returning true today does not mean a mutable key design is guaranteed to be correct**.

We can state more definitively:

- The Java object has changed its field.
- The key's current hash/equality may differ from the time of insertion.
- The collection does not automatically reindex a key merely because a field changed.
- The application can no longer rely on lookup/membership behavior as when the key is stable.

### 3.2. Iterator and Lookup Are Two Different Paths

An iterator can traverse an entry already stored in the Set, whereas `contains` performs a lookup using the current hash/equality. Therefore, seeing the object inside a `for` loop **does not prove** that `set.contains(object)` will succeed after an invalid mutation.

Similarly, `map.size() > 0` only indicates that entries exist structurally; it does not prove that the current key will be looked up properly.

## 4. Runnable Example 1 — Hash Changes, Object Remains in the Set

Create the file **`MutableKeyObservationDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MutableKeyObservationDemo {
    static final class MutableKey {
        private String code;

        MutableKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        void rename(String next) {
            code = Objects.requireNonNull(next);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }

        @Override
        public String toString() {
            return "Key(" + code + ")";
        }
    }

    public static void main(String[] args) {
        MutableKey key = new MutableKey("A");
        Set<MutableKey> keys = new HashSet<>();
        int before = key.hashCode();

        keys.add(key);
        System.out.println("Original hash = " + before);
        System.out.println("Original size = " + keys.size());

        key.rename("B");
        int after = key.hashCode();

        System.out.println("New hash = " + after);
        System.out.println("Hash changed = " + (before != after));
        System.out.println("Stored object = " + keys.iterator().next());
        System.out.println("Same reference = "
                + (keys.iterator().next() == key));
        System.out.println("Size after rename = " + keys.size());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 MutableKeyObservationDemo.java
java MutableKeyObservationDemo
~~~

**Exact stdout:**

~~~text
Original hash = 65
Original size = 1
New hash = 66
Hash changed = true
Stored object = Key(B)
Same reference = true
Size after rename = 1
~~~

**Explanation:**

- The hash of `"A"` is 65 and `"B"` is 66 according to the `String.hashCode` formula.
- The collection holds a reference to the **key object itself**; the iterator recognizes that the object already has the new code.
- Renaming is neither `remove` nor `add`, so the Set size does not change automatically.
- The object's hash changed from 65 to 66 while the element remained stored.
- The program intentionally **does not print `contains(key)` with a fixed expected boolean**, because after a mutation affecting equality/hash, the collection API does not guarantee a specific result.

You can try `keys.contains(key)` and `keys.remove(key)` on the last line. On common implementations, both may fail to find the key even though the iterator still sees it. Treat that as a **symptom**, not a specification that every implementation must produce the same result.

## 5. Real-World Consequences

### 5.1. Failed Lookups

`HashMap.get`, `containsKey`, or `HashSet.contains` may fail to find the object. Code treats the result as "does not exist", recreates data, or misses business logic.

### 5.2. Failed Removals

`map.remove(key)` or `set.remove(key)` may search according to the new hash state, while the entry is organized according to the old state. Attempting to delete after mutation may fail. **To change a key according to the protocol, it usually must be removed before modifying it.**

### 5.3. Duplicate Logical Keys

Two keys that were not equal at insertion time can become equal after one key changes. The Set/Map is not automatically notified to scan all entries and merge keys that have become equal.

~~~text
At write time:
  A.code = "A"
  B.code = "B"
  A.equals(B) = false

After changing A:
  A.code = "B"
  B.code = "B"
  A.equals(B) = true
  The collection may still contain both stored references
~~~

This can happen even when hashCode suffers a collision or every key returns the same fixed hash: **changing the equality relationship is already an independent risk**.

### 5.4. Cache Misses and Stale Indexes

If a cache uses a mutable entity as a key, a rename/email/status change can cause a lookup miss. Subsequently, the code creates a new entry, leading to duplicate cached values or inconsistent logic.

It is also necessary to distinguish a **stale secondary index**: if a Map uses an **immutable String email** as its key, yet `User.email` changes and the application forgets to update the index, that is still a bug even though the String key did not mutate. The old email mapping must be removed and the new email added within the business transaction.

### 5.5. Do Not Use `hashCode` as a Unique Identifier

Even if a key does not change, `hashCode` is still not guaranteed to be unique. Do not use it as a database primary key, authorization token, or security data. Mutability and uniqueness are two separate issues.

## 6. Why Does Changing `hashCode()` to Return a Constant Not Solve the Problem Completely?

Some suggest:

~~~java
@Override
public int hashCode() {
    return 1;
}
~~~

A constant hash does not in itself violate the rule "equal objects have equal hashes", but:

- Entries can collide heavily, degrading performance.
- `equals` still changes when the mutable field changes.
- The collection does not automatically scan and merge keys that newly become equal.
- There is still no contract guaranteeing correct semantics when a key is mutated in a way that affects equality.

**Do not use a constant hash as a cure-all for mutable keys.** If the object has a stable identity, design equality/hash around that identity. If not, use an immutable value key or manage key changes explicitly.

### 6.1. Is Caching the Hash in a Field Safer?

A class might store a cachedHash computed at construction time. However, if `equals` subsequently depends on mutable fields, the cached hash may not match the new equality. If x and y become equal while their cached hashes differ, the equal-hash contract is violated.

Only cache the hash when you have **solid assurance that the data determining equality does not change** (an immutable value object, or an equivalent contract). Do not cache to mask the improper use of mutable fields.

## 7. HashMap Keys and Map Values Have Different Roles

~~~java
Map<CustomerId, Customer> customers = new HashMap<>();
~~~

If `CustomerId` is immutable and `Customer` has mutable `displayName`/`status`, changing the Customer name **does not affect looking up the Map by CustomerId**.

Conversely:

~~~java
Map<Customer, String> auditByCustomer = new HashMap<>();
~~~

if `Customer.equals/hashCode` relies on mutable displayName or status, using the Customer object directly as a key is prone to risk.

The distinction: **a Map selects an entry based on the key**, not on whether the Java value object changes its fields. However, mutable values have their own issues regarding concurrency/aliasing/domain invariants.

## 8. Strategy 1 — Immutable Key + Mutable Domain Object

A straightforward solution is to **separate stable identity from mutable state**. Use a Java 17 record with immutable components to represent the key:

~~~java
record CustomerId(long number, String tenant) {
    CustomerId {
        if (number <= 0) {
            throw new IllegalArgumentException("ID không dương");
        }
        java.util.Objects.requireNonNull(tenant);
    }
}
~~~

If tenant can change, a different key type must be chosen. A safe key must be **truly stable according to the domain**, not merely have the final modifier.

### 8.1. Runnable Example 2 — Changing displayName Does Not Affect Lookup

File **`ImmutableMapKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ImmutableMapKeyDemo {
    record CustomerId(long value, String tenant) {
        CustomerId {
            if (value <= 0) {
                throw new IllegalArgumentException("ID không dương");
            }
            Objects.requireNonNull(tenant, "tenant");
            if (tenant.isBlank()) {
                throw new IllegalArgumentException("Tenant rỗng");
            }
        }
    }

    static final class Customer {
        private final CustomerId id;
        private String displayName;

        Customer(CustomerId id, String name) {
            this.id = Objects.requireNonNull(id);
            displayName = Objects.requireNonNull(name);
        }

        CustomerId id() {
            return id;
        }

        void rename(String next) {
            if (next == null || next.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }
            displayName = next;
        }

        String displayName() {
            return displayName;
        }
    }

    public static void main(String[] args) {
        CustomerId id = new CustomerId(7, "shop");
        Customer customer = new Customer(id, "Lan");

        Map<CustomerId, Customer> customers = new HashMap<>();
        customers.put(customer.id(), customer);

        System.out.println("Before = "
                + customers.get(new CustomerId(7, "shop"))
                        .displayName());

        customer.rename("Linh");

        System.out.println("After = "
                + customers.get(new CustomerId(7, "shop"))
                        .displayName());
        System.out.println("Key equal = "
                + id.equals(new CustomerId(7, "shop")));
        System.out.println("Key hash equal = "
                + (id.hashCode()
                        == new CustomerId(7, "shop").hashCode()));
        System.out.println("Map size = " + customers.size());
        System.out.println("Stable id = " + customer.id());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ImmutableMapKeyDemo.java
java ImmutableMapKeyDemo
~~~

**Exact stdout:**

~~~text
Before = Lan
After = Linh
Key equal = true
Key hash equal = true
Map size = 1
Stable id = CustomerId[value=7, tenant=shop]
~~~

- `CustomerId` is an immutable record in this example because its components are primitive long and immutable String.
- Customer holds a final id but is allowed to change displayName.
- The Map looks up by ID, so renaming does not change the key's hash/equality.
- Two different CustomerId instances remain equal according to their record components and are used to look up the same entry.
- Map size remains 1, and the record's toString has the format printed above in Java 17.

**Condition:** `tenant` and `value` must be the stable identity of the customer in the real system. If the business allows changing tenant, a formal key transition must be defined.

## 9. Strategy 2 — equals/hash Based Only on a Stable Field

A class with mutable fields can still be a hash key if the information **participating in equality/hash** does not change during the storage period.

~~~java
final class User {
    private final long id;
    private String nickname;

    User(long id, String nickname) {
        this.id = id;
        this.nickname = nickname;
    }

    void rename(String next) {
        nickname = next;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof User user && id == user.id;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(id);
    }
}
~~~

This is an illustrative class; production code must also validate id/name and consider ID namespace/uniqueness.

`nickname` is allowed to change; because `equals/hashCode` depends only on the final `id`, changing nickname **does not cause the hash key mechanism to change in the failure pattern we are studying**.

### 9.1. When Not Overriding equals/hash Can Also Be Correct

If the business logic genuinely wants **reference identity**, the inherited `Object.equals/hashCode` can be appropriate: changing business state does not turn the object into a different reference.

Do not override equality across all fields merely because the IDE suggests it or because you think every OOP class must override it. Answer this question: **when are two objects with different references truly considered the same logical entity/value?**

### 9.2. The ORM Generated ID Pitfall

An entity has its database ID assigned **after** persistence. If equals/hashCode relies on the ID and the entity was put into a hash collection **before the ID existed**, transitioning the ID from null to a number can change its identity/hash while stored.

With JPA/ORM there are also proxy subclasses, transient/persisted lifecycles, and multi-tenant identity. **There is no single copy-paste formula that is correct for every ORM.** You must follow the framework contract and domain identity. A simple approach is to avoid using an entity without a stable identity as a hash key; use an immutable application-assigned key if appropriate.

## 10. Strategy 3 — Remove First, Modify, Re-add

If the business requires changing a mutable key object, a conditional protocol is:

~~~text
remove(key) while equality/hash is still in the old state
        ↓
verify that removal succeeded
        ↓
mutate the key's state
        ↓
add/put(key) with the new state
~~~

You must **remove before mutating**; removing after code has changed may fail to locate the stored entry.

### 10.1. Runnable Example 3 — remove/mutate/reinsert

File **`RemoveMutateReinsertDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class RemoveMutateReinsertDemo {
    static final class Key {
        private String code;

        Key(String code) {
            this.code = Objects.requireNonNull(code);
        }

        void change(String next) {
            code = Objects.requireNonNull(next);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Key key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    public static void main(String[] args) {
        Set<Key> set = new HashSet<>();
        Key one = new Key("A");

        set.add(one);
        boolean removed = set.remove(one); // While key is still at A
        one.change("B");
        boolean added = set.add(one);

        System.out.println("Set removed = " + removed);
        System.out.println("Set readded = " + added);
        System.out.println("Set contains B = "
                + set.contains(new Key("B")));
        System.out.println("Set contains A = "
                + set.contains(new Key("A")));
        System.out.println("Set size = " + set.size());

        Map<Key, String> map = new HashMap<>();
        Key key = new Key("old");
        map.put(key, "payload");

        String payload = map.remove(key);
        key.change("new");
        map.put(key, payload);

        System.out.println("Map new = "
                + map.get(new Key("new")));
        System.out.println("Map old = "
                + map.containsKey(new Key("old")));
        System.out.println("Map size = " + map.size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 RemoveMutateReinsertDemo.java
java RemoveMutateReinsertDemo
~~~

**Exact stdout:**

~~~text
Set removed = true
Set readded = true
Set contains B = true
Set contains A = false
Set size = 1
Map new = payload
Map old = false
Map size = 1
~~~

### 10.2. Limitations of This Protocol

This is a **sequential example where each key is managed by a single collection**. Production code additionally needs:

- No other object mutates the key via an alias during the operation.
- Only proceed with the change after removal succeeds.
- Check for a **new key conflict** and decide to reject/merge.
- Roll back if the mutation or insertion fails.
- Update **every collection/index** holding the key, not just a single Set.
- If there are concurrent readers/writers, the lock/transaction must cover the **entire sequence**.
- Do not assume that hash-based collection iteration order is preserved after remove/reinsert.

If possible, using a **new immutable key** instead of mutating the old key is usually easier to audit/test.

## 11. Immutable Replacement Instead of Modifying the Key Object

An identity-changing operation can be described as:

~~~java
record Key(String code) {
    Key {
        java.util.Objects.requireNonNull(code);
    }
}
~~~

In a method using a Map:

~~~java
Map<Key, String> values = new HashMap<>();
Key oldKey = new Key("A");
Key newKey = new Key("B");

values.put(oldKey, "payload");
String payload = values.remove(oldKey);
values.put(newKey, payload);
~~~

This is a **fragment**; it requires appropriate imports and method scope. No key object is mutated. The operation clearly expresses transferring the mapping.

**Note:** remove+put are still **two operations**. With multiple threads or persisted data, an atomicity/transaction protocol is needed if no gap or intermediate state is permitted. `ConcurrentHashMap` does not automatically make every multi-step sequence atomic.

## 12. `final` Fields and Records Do Not Mean Deep Immutability

A hash key with:

~~~java
private final List<String> tags;
~~~

only keeps the **reference to the List** fixed; it does not forbid `tags.add(...)` when the underlying List is mutable. If the key's equals/hashCode relies on the List content, mutable tags cause the same kind of bug.

### 12.1. Input Aliasing

~~~java
List<String> source = new ArrayList<>(List.of("A"));
Key key = new Key(source);
source.add("B");
~~~

If the Key constructor only writes `this.tags = source`, the caller still holds an alias to the List and can alter its contents after the key is added to a Map/Set.

### 12.2. Getters Exposing Mutable State

If a getter returns the internal mutable List itself, callers can modify it even though the field is private/final:

~~~java
List<String> tags() {
    return tags; // Dangerous if tags is mutable
}
~~~

Defensive copying must consider **both incoming arguments and outgoing return values**.

### 12.3. `List.copyOf` and Shallow Copying

`List.copyOf(source)` creates an appropriate unmodifiable List, avoiding structural mutation from an alias of source. However, it **does not deep-copy mutable elements**. With immutable Strings, it is useful; with a List containing MutableItem, elements can still be modified through another alias.

`Collections.unmodifiableList(source)` typically creates a **view** that prevents modification through the view, yet reflects mutations happening on source. A view and a snapshot are **not equivalent**.

## 13. Runnable Example 4 — A Record with a Mutable Component Still Changes Hash

File **`MutableRecordComponentDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableRecordComponentDemo {
    record UnsafeKey(List<String> tags) {
    }

    record SafeKey(List<String> tags) {
        SafeKey {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        UnsafeKey unsafe = new UnsafeKey(source);
        SafeKey safe = new SafeKey(source);

        int beforeUnsafe = unsafe.hashCode();
        int beforeSafe = safe.hashCode();

        source.add("B");

        System.out.println("Unsafe = " + unsafe.tags());
        System.out.println("Safe = " + safe.tags());
        System.out.println("Unsafe shares source = "
                + (unsafe.tags() == source));
        System.out.println("Unsafe hash changed = "
                + (beforeUnsafe != unsafe.hashCode()));
        System.out.println("Safe hash unchanged = "
                + (beforeSafe == safe.hashCode()));
        System.out.println("Safe equal = "
                + safe.equals(new SafeKey(List.of("A"))));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MutableRecordComponentDemo.java
java MutableRecordComponentDemo
~~~

**Exact stdout:**

~~~text
Unsafe = [A, B]
Safe = [A]
Unsafe shares source = true
Unsafe hash changed = true
Safe hash unchanged = true
Safe equal = true
~~~

### 13.1. Analysis

Record component fields generated by Java are private final. However, `UnsafeKey.tags` points to the caller's mutable List. The generated record `hashCode` uses the List component, while `List.hashCode` reflects its contents. After `source.add("B")`, the hash of UnsafeKey changes.

`SafeKey` uses a compact constructor to copy the List before assigning the component field. Because the elements are **immutable Strings**, the snapshot is stable for this scenario. If tags contains mutable objects, a deep copy or an immutable element model is still required.

**Point to remember:** "a record is final" and "record components are final" do not mean that all nested state is immutable.

## 14. Why Is Changing Equality Still a Problem Even When the Hash Does Not Change?

Suppose a Set stores two objects A and B when they are not equal. Later, a mutation makes A.equals(B) true while their hashCodes **happen not to change** due to a collision.

The collection is not notified to rescan and remove logical duplicates. Therefore, you should not narrow the rule down to **"just keep hashCode constant"**. The right rule is: **information affecting logical equality/hash must remain stable while stored**.

An implementation of `hashCode() { return 1; }` does not prevent this problem. Even though the equal-hash relation is still satisfied, the relationship of **which object equals which** has changed compared to insertion time.

### 14.1. Why Does Set.size Not Update Automatically?

`size` reflects the number of entries managed via collection operations. Changing an object's field outside the collection API does not trigger it to recheck the entire set of keys, even when some pairs have become equal.

## 15. Mutable Graph: A Key Pointing to Another Object Also Carries Risk

A key does not even need a public setter of its own. If `hashCode` relies on a nested object with mutable state, the result can still change:

~~~java
final class Group {
    private final List<Member> members;

    @Override
    public int hashCode() {
        return members.hashCode();
    }
}
~~~

This is a fragment with type `Member` and a corresponding List; if Member changes a field participating in Member.hashCode, List.hashCode can change accordingly. The same applies to:

- Arrays with mutable elements.
- Lists/Maps containing mutable objects.
- Mutable Date.
- Records with a mutable component.
- Nested value objects that are only **shallowly immutable**.
- State obtained from collaborators invoked by equality/hash.

You need to inspect the **entire dependency path of equality/hash**, not just the `final` modifier on the outer layer.

### 15.1. Do Not Call an External Mutable Provider from hashCode

A hashCode based on `configuration.currentRegion()` or `clock.instant()` can change over time even if fields inside the key are never reassigned. This is a very hard-to-defend design when the object serves as a key.

Equality/hash should rely on **state representing identity/value within that object**, not an external mutable time/configuration source invoked on each call.

## 16. When the Same Object Is in Multiple Collections

Suppose a mutable `UserKey` is currently used in:

- `HashSet<UserKey> activeUsers`.
- `HashMap<UserKey, Session> sessions`.
- `HashMap<UserKey, Roles> roleCache`.

Calling `activeUsers.remove(key)` before renaming **is not sufficient** if the two maps still hold the same key object. They must also be updated following the protocol, or better yet, all of them should use an **immutable UserId**.

The lesson about **ownership**: who has permission to call setters affecting key semantics, who manages the indexes, and who ensures the operation updates the entire system? If multiple callers hold unrestricted references, it is very hard to guarantee.

### 16.1. A Secondary Index Differs from a Mutable-Key Bug

A map with an immutable String key `email` also needs updating when the domain object changes its email. This is a **stale index** bug rather than the String key mutating itself:

~~~text
emailIndex["old@domain"] = user
user.email = "new@domain"
emailIndex has not been updated yet
~~~

Both problems demand a lifecycle protocol, but one is **the intrinsic key object changing its hash**, while the other is **the mapping missing an update operation**. Do not use the solution for one case to misexplain the other.

## 17. `TreeSet` and `TreeMap`: Same Risk, Not Hash-Based

`TreeSet`/`TreeMap` use `Comparable` or `Comparator` to organize and look up by **ordering**, not HashMap's bucket system.

If a Person stored in a TreeSet ordered by `age` later has its age changed, the ordering used at insertion time may no longer hold; lookup/range operations may become incorrect. Therefore, **fields participating in compareTo/comparator also need to remain stable throughout the time the object serves as a key/member**.

Do not infer that TreeSet is safe just because it does not rely on Object.hashCode.

A Comparator that is inconsistent with equals can also cause TreeSet's notion of "duplicate" to differ from how `equals` defines logical equality; you must understand the SortedSet/Map contract.

## 18. Concurrency Does Not Automatically Rescue a Mutable Key

When multiple threads concurrently mutate a key and perform lookups, two independent problems can arise:

1. **Data races/visibility** because the mutable field lacks synchronization.
2. **Hash collection invariant broken** because the stored key's equality/hash changed outside the collection API.

Declaring:

~~~java
private volatile String code;
~~~

can assist with visibility for the code field, yet **does not notify HashMap to reindex**.

Using `ConcurrentHashMap` likewise does not make keys track field changes automatically. It guarantees the concurrent operations specified by its API, not that mutating a mutable key becomes safe.

### 18.1. Remove–Mutate–Reinsert May Require a Transaction

If the business genuinely permits identity changes, a lock/transaction must cover the entire sequence and ensure all readers/writers follow the same protocol. When operations are separated, a reader may observe the entry temporarily missing.

Immutable key replacement usually significantly reduces the synchronization states that must be handled.

## 19. Generated IDs, ORM, and Proxies

Considerations when using JPA/ORM or frameworks that work with entities:

- An ID generated after persistence can change from null to non-null.
- New entities and persisted entities may require different equality semantics.
- Proxy subclasses require careful thought regarding `getClass()` and `instanceof` in equals.
- You should not include every mutable entity field in generated equals/hashCode.
- A HashMap/HashSet may outlive a single persistence transaction.

There is no single equals/hashCode recipe that is right for every version/framework/domain. Check the specific framework contract and the system's identity model. If possible, use a **stable immutable key** separate from the mutable entity.

### 19.1. Avoid Overusing Code Generation Tools

An IDE or Lombok can generate equals/hashCode from selected fields. If you include `status`, `updatedAt`, `displayName`, or a mutable List merely because they are present in the class, you can accidentally change logical equality when state updates.

**Generated code does not know business identity on its own.** Review the participating fields and write tests for the actual lifecycle.

## 20. Practical Debugging

If `map.get(key) == null` while the map still has entries, check:

1. Do the key used at put time and the key used at get time have the same semantic identity?
2. Does the class override `equals/hashCode` with the correct `equals(Object)` signature?
3. Which fields participate in those two methods?
4. Is there a setter, ORM hydration, JSON mapper, external alias, or listener changing those fields?
5. Is there a mutable nested List/Map/array/child object?
6. Do the hashes before put and after modification differ?
7. Does an iterator still traverse the key in question?
8. Are multiple maps/indexes holding the same key?
9. Are there concurrent mutations and data races?
10. Are you relying on collision/implementation-specific behavior?
11. Are you using a key with an unstable ID lifecycle?
12. Can this be fixed with an immutable ID/value key?

**Do not** modify HashMap's internal buckets via reflection or assume that triggering a resize/rehash at some arbitrary point will properly restore all business semantics. That is an implementation detail, not an API contract.

### 20.1. When Data Semantics Are Already Corrupted

A controlled recovery approach:

- Halt/synchronize related updates.
- Retrieve data from a sufficiently reliable source, possibly via iteration or persistence.
- Determine current equality/identity and resolve logical duplicates according to domain policy.
- Rebuild the index/collection with immutable keys.
- Publish the new state using safe synchronization/transactions.
- Verify lookup, duplicates, size, and recovery/rollback.

`new HashSet<>(oldSet)` may drop some entries that are now equal to each other; you should not do that without a policy for choosing which record to keep.

## 21. What Does Testing Require Beyond a Single `contains` Call?

| Test Case | What to Confirm |
| --- | --- |
| Reflexivity/symmetry/transitivity | `equals` complies with the contract |
| Equal-hash rule | Equal instances have equal hashes |
| Null handling | `equals(null)` returns false, does not throw arbitrary exceptions |
| Hash key stability | Equality-relevant state does not change throughout the key lifecycle |
| Mutable non-key fields | Changing a field not participating in equality does not break lookup |
| HashMap lookup | A new equal immutable key can access the value |
| HashSet membership | An equal immutable instance is recognized appropriately |
| Aliasing | Input/getter does not allow mutating nested equality components |
| Generated ID lifecycle | Does not unintentionally alter identity/hash of a stored key |
| Safe replacement | Removing old key/adding new key covers all indexes |
| Concurrent access | Clear atomicity/visibility and ownership |
| Comparator ordering | TreeSet/TreeMap have stable comparator keys |

A `contains(mutatedKey)` test that happens to return true on the current JVM **does not prove stability**. Verify the design rule and lifecycle rather than just observing a lucky outcome.

### 21.1. Do Not Forget `@Override`

If you write `boolean equals(MyType other)`, that is an **overload**, not an override replacing `Object.equals(Object)`. When collections invoke through Object-based contracts, the result differs from expectations.

Use:

~~~java
@Override
public boolean equals(Object other) {
    // ...
}
~~~

and the corresponding hashCode. The Java compiler will detect that the signature does not actually override if the annotation is misplaced.

## 22. Common Mistakes

1. Using mutable email/username as hash identity and then changing them.
2. Generating equals/hashCode across all fields, including status and updatedAt.
3. Overriding equals but forgetting hashCode.
4. Using different fields in hash code than in logical equality, leading to a violation of the equal-hash rule.
5. Choosing a constant hash to mask the equality mutation problem.
6. Caching the old hash while equals continues to change.
7. Thinking `final List` makes its elements unmodifiable.
8. Thinking a record is automatically deeply immutable.
9. Thinking `Collections.unmodifiableList(source)` always prevents source from changing.
10. Attempting to remove **after** the key has mutated.
11. Removing a key from one Set while forgetting other Maps/indexes.
12. Seeing the object in an iterator and concluding `contains` must be true.
13. Treating `size()` as the current count of logical equivalence classes after mutation.
14. Claiming every JVM returns a fixed contains value after breaking the contract.
15. Assuming `ConcurrentHashMap` automatically tracks key setters.
16. Using volatile to fix a stale hash bucket bug.
17. Using a mutable comparator field in a TreeSet.
18. Using an unstable generated ORM ID inside a hash collection.
19. Using `==` for String content when value equality is needed.
20. Using hashCode as a collision-free ID or security token.
21. Having a public setter for a field participating in equality without an owner managing it.
22. Using a mutable object graph in a record/hash key without defensive copying.
23. Rebuilding a Set after an incident without resolving duplicate identities.
24. Modifying collection internals via reflection instead of fixing the domain protocol.

## 23. Self-Check Exercises with Answers

**Question 1.** What can happen when changing a field participating in `equals/hashCode` while the object is in a HashSet?

**Answer:** Lookup/remove/membership are no longer guaranteed; the object may still be traversed by an iterator, yet `contains` fails to find it. The Set does not automatically reindex by field.

**Question 2.** If a key's hash changes, must `set.contains(key)` always return false?

**Answer:** No. The behavior is not fully specified in scenarios where mutation affects equality; the outcome may depend on conditions/implementation.

**Question 3.** If two objects are equal, what must be true of their hash codes?

**Answer:** They must be equal. Conversely, having the same hash is not sufficient to conclude they are equal.

**Question 4.** If a field changes without participating in equality/hash, does the same bug occur?

**Answer:** Not due to this mechanism, provided all state affecting equality/hash remains stable and other contracts are satisfied.

**Question 5.** Does `final List<String> tags` automatically create an immutable list?

**Answer:** No. Final prevents reassigning the field, not modifying the List's contents.

**Question 6.** Can `record R(List<String> items)` change its hashCode?

**Answer:** Yes, when the mutable List component is modified and the record's hash uses that List component.

**Question 7.** Does `List.copyOf` deep-copy mutable elements?

**Answer:** No. It protects the List structure, but does not automatically deep-copy each mutable child object.

**Question 8.** Why is using an immutable CustomerId as a HashMap key better than using a Customer with a mutable displayName?

**Answer:** Changing displayName does not alter the stable ID's equality/hash, so lookup by ID retains consistent meaning.

**Question 9.** Can we make hashCode always return 1 to fix mutation?

**Answer:** No: it degrades performance due to collisions and does not stabilize the equality relationship among stored keys.

**Question 10.** If mutating a key is unavoidable, what should the order of operations usually be?

**Answer:** Remove using the old state → mutate → reinsert with the new state, while managing all owners/indexes and concurrency.

**Question 11.** If the same key appears in three maps, is removing it from one Map sufficient?

**Answer:** No. The remaining maps still hold the key reference that may mutate; all of them must be updated, or an immutable identifier should be used.

**Question 12.** Is there still risk if a key's hash does not change but equals changes?

**Answer:** Logical duplicates and the membership state of the Set/Map may no longer reflect current equality; the Set does not automatically scan/merge.

**Question 13.** Is TreeSet safe against changes to fields used in its Comparator?

**Answer:** No. It relies on the ordering used at insertion time; changing comparison-relevant state can also break lookup/ordering.

**Question 14.** Does `volatile String code` cause HashMap to automatically update its entry when code changes?

**Answer:** No. Volatile addresses memory visibility/ordering, not rehashing.

**Question 15.** Does `ConcurrentHashMap` make mutable keys safe?

**Answer:** No. It supports concurrent map operations; it does not automatically track internal mutable key state.

**Question 16.** Why can a database-generated ID create a mutable hash key?

**Answer:** The ID transitions from unassigned → assigned, which can cause equals/hash to change if based on the ID, especially when the object is already in a Set/Map.

**Question 17.** Does HashMap.get returning null always mean the key does not exist?

**Answer:** No: HashMap allows null values. For a valid map, containsKey can be used to distinguish; with a mutated key, the lookup contract itself is unreliable.

**Question 18.** Should a mutable status field be used for an entity's logical identity?

**Answer:** Usually not if status is allowed to change while the entity remains the same entity. Choose a stable ID/domain contract.

**Question 19.** Is it possible to modify an immutable email String key via a setter?

**Answer:** String has no setter that changes its contents. However, when User.email changes, the secondary index Map<String,User> still needs to remove the old key and add the new key; this is a stale index, not a mutable String key.

**Question 20.** Why can't we assume the map will automatically reindex when a key setter runs?

**Answer:** A map holds references and performs operations via its API; it does not observe/subscribe to individual mutations on arbitrary key objects.

**Question 21.** When rebuilding a collection that already has duplicates under current equality, what is important?

**Answer:** Having a policy for selecting/merging records, transaction/synchronization, and re-verifying indexes. Creating a new Set can drop data unexpectedly if not reviewed.

**Question 22.** If an object does not override equals/hashCode, does changing displayName alter reference identity?

**Answer:** No. Inherited Object.equals is identity-based; mutating a business field does not turn an object into a different reference.

**Question 23.** Is `hashCode()` a unique ID across objects?

**Answer:** No. Collisions are valid and there is no guarantee of stability across runs.

**Question 24.** Is having an IDE auto-generate equals/hashCode from all fields safe?

**Answer:** Only when the field selection matches the logical equality contract and lifecycle. Mutable fields usually need review.

**Question 25.** When can a mutable object be used as a Map key?

**Answer:** When the information determining equals/hashCode is **truly stable throughout the storage duration** and ownership/API guarantees this; it is better to use an immutable key.

## 24. Checklist for Applying to Real Java Code

1. Have you clearly defined **business identity** or value equality?
2. Does `equals` have the exact signature `equals(Object)` and `@Override`?
3. Is `hashCode` compatible across all cases where equals is true?
4. Do the fields participating in equality/hash change across the lifecycle?
5. Is there a generated ID not yet assigned when the object is inserted into a Set/Map?
6. Are nested objects/Lists/Maps/arrays mutable?
7. Does the input constructor defensively copy the parts that must remain stable?
8. Does any getter expose an equality-relevant mutable representation?
9. Is there a more suitable immutable record/value key?
10. Can the stable ID be separated from displayName/status/updatedAt?
11. If changing the key is unavoidable, can it be removed under the old state first?
12. Have you checked for conflicts with an existing new key?
13. Is there rollback handling if reinsertion or mutation fails?
14. Do other indexes/collections hold the same key reference?
15. Do concurrent readers/writers follow the same transaction/lock?
16. Are you misusing `volatile`/`ConcurrentHashMap` in place of an update protocol?
17. Are there mutable comparator fields in TreeSet/TreeMap?
18. Have tests verified the equal-hash rule and key stability?
19. Is it understood that a `contains` result after an invalid mutation is not a contract?
20. Are you using hashCode as a security ID or database key? If so, redesign it.

## Conclusion

**`equals()` determines when two objects are considered equal; `hashCode()` provides a hash consistent with logical equality.** When an object is stored as a key/member of a `HashMap` or `HashSet`, the collection requires that information to remain **stable** for lookup, removal, and duplicate detection. If you change a relevant field without going through the collection's update API, the object may remain inside the structure while lookups become unreliable. The two methods may still be self-consistent with each other **at any single point in time**, yet the key was altered during its storage interval.

A sustainable design approach is to **prefer immutable keys**, use record/value types with genuinely immutable components, separate stable identity from mutable business state, and protect nested data with appropriate defensive copying. When a key change is unavoidable, **remove under the old state → modify → re-add**, while safeguarding all collections, indexes, error handling, and concurrency.

This principle does not mean forbidding all mutable fields: **simply do not change the information determining equality/hash while the object is serving as a key**. Mastering that boundary prevents a subtle yet high-impact category of Java collections bugs in real-world software.
