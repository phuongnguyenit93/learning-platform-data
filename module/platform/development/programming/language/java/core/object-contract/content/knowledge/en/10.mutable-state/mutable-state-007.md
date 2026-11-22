# Removing and Re-adding Data When Business Logic Truly Requires Changing a Key

A Java object is sometimes used as an **element of a `HashSet`** or a **key of a `HashMap`**. If `equals()` and `hashCode()` rely on a business attribute such as `customerId`, modifying this attribute **while the object is still inside the collection** can break lookup, removal, or duplicate prevention.

When business requirements genuinely call for changing a key, the safe sequence at the collection level is:

1. Identify and verify the **old key** while the collection is still operating normally.
2. Validate the new key and ensure it does not collide with any existing key.
3. **Remove the element or entry using the old key**, before modifying data that affects `equals()`/`hashCode()`.
4. Change the key on the detached object, or create a new key object.
5. **Re-add** using the new key and confirm that lookup by the new key works.

This is a conditional approach when **a key truly has to change**. In ordinary design, prefer a stable, immutable identifier; if business logic only changes a display name or status, there is no need to—and you should not—touch the key used for `equals()`/`hashCode()`.

## 1. Why shouldn't you modify the key directly inside the collection?

For `HashSet` and `HashMap`, Java relies on `hashCode()` to determine the storage/lookup region, then uses `equals()` to recognize two equal elements or keys. Suppose:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return customerId.equals(other.customerId);
}

@Override
public int hashCode() {
    return customerId.hashCode();
}
~~~

This is a **code snippet inside a `Customer` class**, not a standalone program. Both methods rely on `customerId`.

When adding a `Customer("C-01")` to a `HashSet`, the structure uses the hash corresponding to `"C-01"`. If that same object is subsequently changed to `"C-02"` while still in the set, the hash computed during lookup may differ from the hash used at insertion time. The collection does not automatically relocate the element whenever an object's field changes. Consequently, `contains` or `remove` may fail to find the element, and uniqueness rules may be broken.

Example of **wrong operation order**:

~~~java
// Illustrative snippet; assumes customer is already in customers.
customer.changeId("C-02"); // WRONG: mutating the key while still in the HashSet.
customers.remove(customer); // May not be found under the new hash.
~~~

Calling `remove` after mutation is not guaranteed to fix this situation. Even if a particular pair of values happens to succeed in lookup, the code still depends on unguaranteed collection behavior.

**Correct order:**

~~~java
// Illustrative snippet; in practice, check preconditions beforehand.
boolean removed = customers.remove(customer); // While ID is still "C-01".
if (!removed) {
    throw new IllegalStateException("Old key not found");
}
customer.changeId("C-02");                     // Now change the key.
customers.add(customer);                       // Re-hash under the new key.
~~~

With `HashSet`, `remove` must happen **before** modifying a field that affects the equality relation. With `HashMap`, we use `remove(oldKey)` followed by `put(newKey, value)`. These two operations do not automatically form an atomic transaction; handling contention and mid-way errors is discussed later.

## 2. Distinguishing a key change from normal attribute edits

Not every state change on an object is dangerous.

| Data modified | Participates in `equals()`/`hashCode()`? | Impact while object is in a collection |
| --- | --- | --- |
| `customerId` as the equality key | Yes | Must perform a safe key transition or design an immutable key |
| `displayName` for display only | No | Can be modified without removing from hash collections because hash and equality do not change |
| `status` excluded from equality | No | Can be updated like normal data; consider synchronization if multithreaded |
| Contents of an array field or nested object used in hash code | Yes | Also constitutes a logical key change even though the field reference does not change |
| `hashCode()` relies on a field ignored by `equals()` | Broken design | Fix the `equals()`/`hashCode()` contract first; remove/add cannot cure this inconsistency |

A property declared `final` is **still not enough** to guarantee deep immutability if it points to a mutable object (such as an array or collection). What matters is that **values participating in equality and hashing do not change** during the period the object serves as a key.

If a key is derived from a normalized value (for example, an uppercase code normalized before storage), identify which **normalized value** changes; do not rely on superficial changes that do not affect the key.

## 3. Complete Java 17 example: safe key transition in `HashSet` and `HashMap`

Create the file **`KeyChangeDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class KeyChangeDemo {

    // Example intentionally allows editing ID; in real designs,
    // an immutable ID is usually easier to manage.
    static final class Customer {
        private String id;
        private final String displayName;

        Customer(String id, String displayName) {
            this.id = Objects.requireNonNull(id, "id");
            this.displayName = Objects.requireNonNull(displayName, "displayName");
        }

        void changeId(String newId) {
            id = Objects.requireNonNull(newId, "newId");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Customer other)) {
                return false;
            }
            return id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    // A Java 17 record: String key stored immutably.
    record AccountKey(String id) {
        AccountKey {
            Objects.requireNonNull(id, "id");
        }
    }

    static void changeCustomerId(
            Set<Customer> customers, Customer target, String newId) {
        Objects.requireNonNull(newId, "newId");

        // Precondition: the collection is currently valid.
        if (!customers.contains(target)) {
            throw new IllegalArgumentException("Customer not found");
        }
        if (target.id.equals(newId)) {
            return;
        }

        // Check for collision with the new ID before removing the old ID.
        if (customers.contains(new Customer(newId, "probe"))) {
            throw new IllegalArgumentException("New customer ID exists");
        }

        if (!customers.remove(target)) {
            throw new IllegalStateException("Cannot remove old ID");
        }
        target.changeId(newId);
        if (!customers.add(target)) {
            throw new IllegalStateException("Cannot add new ID");
        }
    }

    static <V> void moveMapKey(
            Map<AccountKey, V> map, AccountKey oldKey, AccountKey newKey) {
        Objects.requireNonNull(oldKey, "oldKey");
        Objects.requireNonNull(newKey, "newKey");

        if (oldKey.equals(newKey)) {
            return;
        }
        if (!map.containsKey(oldKey)) {
            throw new IllegalArgumentException("Old map key missing");
        }
        if (map.containsKey(newKey)) {
            throw new IllegalArgumentException("New map key exists");
        }

        // Move the entire mapping, even when the stored value is null.
        V value = map.remove(oldKey);
        map.put(newKey, value);
    }

    public static void main(String[] args) {
        Set<Customer> customers = new HashSet<>();
        Customer lan = new Customer("C-01", "Lan");
        customers.add(lan);
        customers.add(new Customer("C-03", "Binh"));

        System.out.println("before old: "
                + customers.contains(new Customer("C-01", "check")));

        changeCustomerId(customers, lan, "C-02");

        System.out.println("after old: "
                + customers.contains(new Customer("C-01", "check")));
        System.out.println("after new: "
                + customers.contains(new Customer("C-02", "check")));
        System.out.println("set size: " + customers.size());

        try {
            changeCustomerId(customers, lan, "C-03");
        } catch (IllegalArgumentException ex) {
            System.out.println("collision blocked");
        }
        System.out.println("after rejected: "
                + customers.contains(new Customer("C-02", "check")));

        Map<AccountKey, String> statuses = new HashMap<>();
        statuses.put(new AccountKey("A-10"), "OPEN");
        moveMapKey(
                statuses, new AccountKey("A-10"), new AccountKey("A-20"));

        System.out.println("map old key: "
                + statuses.containsKey(new AccountKey("A-10")));
        System.out.println("map new value: "
                + statuses.get(new AccountKey("A-20")));
        System.out.println("map entries: " + statuses.size());
    }
}
~~~

Compile and run:

~~~bash
javac KeyChangeDemo.java
java KeyChangeDemo
~~~

**Expected output on Java 17+:**

~~~text
before old: true
after old: false
after new: true
set size: 2
collision blocked
after rejected: true
map old key: false
map new value: OPEN
map entries: 1
~~~

Part-by-part explanation:

- Before the change, `Customer("C-01")` can be found using a different instance with the same ID.
- `changeCustomerId` verifies that the new ID `"C-02"` does not yet exist, **removes `lan` while `lan.id` is still `"C-01"`**, and only then changes `id` and re-adds it. Consequently, lookup for the old ID is `false` and for the new ID is `true`.
- The set still has two customers (`"C-02"` and `"C-03"`). The attempt to change to `"C-03"` is rejected before removing or modifying, so `lan` remains at `"C-02"`.
- For `Map`, `AccountKey` is a record containing an immutable `String`. Instead of mutating a stored key, we remove the `"A-10"` mapping, retain the `"OPEN"` value, and add the `"A-20"` mapping. The old entry disappears; the new entry holds the same value, and the map size stays unchanged.
- `moveMapKey` uses `containsKey` to distinguish **no mapping** from **a mapping with value `null`**; merely checking `remove(...) == null` is insufficient for that case.

**Scope of the example:** the code runs single-threaded on ordinary `HashSet`/`HashMap` with valid data; it illustrates **the sequence of in-memory collection operations**, not a transactional operation with error rollback or multiple concurrent updaters.

## 4. Preconditions to check before transitioning a key

A good key-change operation usually checks all of the following before detaching the old entry:

1. **Old key exists:** the element/entry must currently be in the collection with consistent `equals()`/`hashCode()`. If the structure was already corrupted by an earlier key mutation, `contains` and `remove` are not reliable repair mechanisms.
2. **New key is valid:** validate format, length, normalization rules, and business constraints before removing old data. Do not let validation throw an exception after the element has already been detached.
3. **New key is not already taken:** `Set.add(...)` can return `false` due to duplication; `Map.put(...)` can overwrite an old value. Do not silently treat such situations as successful updates.
4. **Equality semantics do not change mid-way:** `equals()`, `hashCode()`, and key representation rules must agree. Keys that differ as raw strings yet become equal after normalization still constitute a logical collision.
5. **Is the element referenced elsewhere?** If the same object serves as a key in multiple `HashSet`/`HashMap` instances, removing it from one place and mutating its ID can corrupt **all the remaining places**. You must update the key across every related structure or prefer creating a new immutable key.

In the case where `newKey.equals(oldKey)`, the key-transition method can **do nothing** because the logical identity has not changed. Only when the key itself according to the equality definition changes is the key-transition workflow needed.

## 5. Three strategies and when to use them

### Strategy A — Preferred: immutable key, create a new key

Use a `String`, `UUID`, `record`, or another immutable value as the `Map` key; if business logic changes the code, create a new key and move the entry. With a `Set` storing immutable value objects, you can remove the object by the old key and then add the new object.

Advantage: no key object gets secretly mutated while other collections are using it; clearer when passing data across classes or processing threads.

Example with `Map`:

~~~java
// Assume oldKey and newKey are validated immutable keys.
// Existence and collision checks must follow business rules.
V saved = map.remove(oldKey);
map.put(newKey, saved);
~~~

This is **generic method-level pseudocode**, not a standalone Java program; see `moveMapKey` in the runnable example for complete input validation and preserving mappings whose value is `null`.

### Strategy B — Mutable object in `HashSet`, strictly remove → mutate → add

If a legacy design allows changing the ID on an object whose reference is already shared, strictly preserve the order **remove while old ID is intact → mutate ID → re-add**. You must control everywhere else that holds that object as a key. Mutating a key inside a mutable object carries greater risk than creating a new object/key and should be isolated within a single business method.

### Strategy C — Do not change the collection key if only display info changes

If `customerId` is an unchanging identifier while name, contact email, or UI status are updated independently, leave the key untouched. Then there is no need to remove/add simply because non-equality values changed; unnecessary operations also increase the risk of losing elements due to mid-way failures.

**Note:** `Map` distinguishes *key* from *value*. Modifying attributes of a value normally does not alter map lookup as long as those attributes are not part of the key and there is no secondary index based on them.

## 6. Why don't remove/add automatically guarantee atomicity?

In a standard `HashMap`, the sequence `remove(oldKey)` followed by `put(newKey, value)` has a window where the mapping is absent under any key. With a `HashSet` holding a mutable object, the remove → mutate → add sequence also has a phase where the element is temporarily detached from the set. If the operation fails or another thread reads mid-way, the program can observe an incomplete state.

Issues to address at the **business level**:

- **Concurrency:** `HashMap` and `HashSet` are not thread-safe on their own. Two simultaneous key-change calls can both pass collision checks and overwrite each other. If there is concurrent access, you need a synchronization mechanism protecting **the entire check + key-transition step**, or another structure/design with explicit atomic update semantics. Simply replacing the collection with `ConcurrentHashMap` does not turn two independent `remove` then `put` calls into an atomic transaction.
- **Mid-way failures:** checking all checkable preconditions upfront reduces risk; for real workflows involving I/O, callbacks, or other constraints, an explicitly designed rollback or atomic replacement mechanism is needed. The example code does not claim to handle every possible exception after `remove`.
- **Database:** if the business code is also a unique key in a database, in-memory updates must coordinate with transactions, unique constraints, and any related references. Java remove/add does not automatically update foreign keys, database indices, or other sessions' data.
- **Key used in multiple places:** in a system with caches, indices, or other collections, transitioning a key requires updating every place under a consistency policy; you cannot update just one `HashSet` and treat the whole system as done.

With `TreeSet` or `TreeMap`, modifying a field used by `Comparator`/`compareTo` can also corrupt tree ordering, even though `hashCode()` is not used. The idea of detaching while the old key is intact, changing the key, and re-adding remains useful; however, you must verify ordering rules and key-duplicate definitions according to the comparator.

## 7. What if the key was already modified while still in the set/map?

After accidentally modifying an attribute affecting `equals()`/`hashCode()`, **do not rely on `contains(mutableKey)` or `remove(mutableKey)` to recover**, because the hash lookup path itself may already be broken.

In an in-memory structure over which you have exclusive control, you can locate the exact element via iteration and call `Iterator.remove()` to detach it; only then re-establish the data with a valid key. Example of recovering a specific instance:

~~~java
// Illustrative; only use when holding exclusive control of the Set,
// and knowing the exact object reference to detach.
var iterator = customers.iterator();
while (iterator.hasNext()) {
    if (iterator.next() == target) {
        iterator.remove();
        break;
    }
}
// Verify postconditions, resolve conflicts if any,
// and only then add target with a validated key state.
~~~

`Iterator.remove()` removes **the element just returned by the iterator**, without relying on finding the object again by its new hash. Still, this is a **broken-state repair measure**, not a normal flow; you must avoid concurrent modifications to the collection while iterating, verify the object was actually found, and address any other indices that may have been corrupted. A cleaner approach in many cases is **rebuilding the collection from trusted source data**, using a validated set of keys.

For `Map`, you can consider iterating `entrySet().iterator()` and removing the exact entry in a similar situation, or rebuilding the map. Avoid applying a recovery trick if multiple parts of the system hold the same object as a key without knowing their state.

## 8. Practical checklist

Before allowing a business key to be changed, check yourself:

- [ ] Does the attribute to be changed actually participate in `equals()`/`hashCode()` or a comparator?
- [ ] If it is only display info, can it be updated normally without changing the key?
- [ ] Can the key be designed as immutable and replaced with a new instance instead of mutating an object currently used as a key?
- [ ] Have you confirmed the old key exists, and that the new key is valid, unclaimed, and follows the same normalization rules?
- [ ] Does every `remove` happen **while the old key is still intact**?
- [ ] After the change, have you verified `contains/get` by both old and new keys, element/entry counts, and rejection of collisions?
- [ ] Does anywhere else hold the object as a key, is there concurrent access, or is there a database requiring a transaction?
- [ ] If a step fails, is there a plan to ensure no mapping is lost and no object is left half-updated?

**Takeaway:** When an object participates in a structure based on `hashCode()` or ordering, changing a key-defining field can cause the collection to stop finding the element properly. If business logic genuinely requires changing a key, **remove under the old key first, transition to the new key afterward, then re-add and verify**. Prefer immutable keys and handle atomicity at the appropriate level once the problem is no longer single-threaded.