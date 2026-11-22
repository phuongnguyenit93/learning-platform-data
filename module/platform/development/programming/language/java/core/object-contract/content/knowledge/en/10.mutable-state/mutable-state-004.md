# Prefer Immutable Keys in HashMap and HashSet

## 1. Why use immutable keys?

For hash-based structures such as `HashMap`, `HashSet`, and `LinkedHashMap`, the safest approach is to use an **immutable key**: the data that determines the key's `equals()` and `hashCode()` does not change throughout the time the key resides in the structure.

The core point is that a key is **looked up again** using its hash code and equality:

1. When placing key `k` into a `HashMap`, the map determines its storage location from `k.hashCode()`, then uses `equals()` to distinguish matching keys when needed.
2. If the information used in `k`'s own `hashCode()` changes after insertion, the stored location **is not automatically updated** to match the new hash code.
3. Calling `map.get(k)`, `map.containsKey(k)`, `map.remove(k)`, or looking up with another value-equal key **may fail to find the stored entry**.
4. `HashSet` faces the same risk: `add`, `contains`, and `remove` depend on the element's hashing semantics.

This is **the reason to prefer immutable keys**, rather than Java strictly forbidding keys with mutable fields. What is mandatory for a key residing in a hash table is that **the information participating in equality comparisons and hash code computation must remain stable**. An object may still have mutable fields for logging, access counts, or UI purposes if those fields do not participate in `equals()`/`hashCode()` and do not alter the key's meaning.

### Distinguishing two contracts

- **The contract between `equals()` and `hashCode()`:** if `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()`. Equal hash codes do not require `equals()` to be equal.
- **Stability once the key is stored:** if an attribute determining key equality is modified after insertion into a hash table, lookups can break. An `equals()`/`hashCode()` pair, even if consistent at every individual instant, is **not enough** to guarantee a key can safely mutate.

A hash code is neither a memory address nor a unique identifier. Objects can have hash collisions; the dangerous problem here is **changing values related to hashing and equality after storing the key**, not collisions themselves.

## 2. What does "immutable" mean?

A *truly immutable* key allows no observable change to the state used to define its value after creation. Examples:

- A `String` key has unchangeable contents; Java already provides consistent `equals()` and `hashCode()`.
- A `record` holding `String` values or other immutable types is usually a simple choice for multi-field keys.
- A `final` class with `private final` fields, no setters, and no leaked references to modifiable data is usually suitable as a key.

**Note:** `final` only prevents reassigning the variable or reference field; it does not make the referenced object immutable. For instance, `private final List<String> parts` can still be modified via `parts.add(...)` if the list is mutable. When that happens, `List.equals()`/`List.hashCode()` also change with the elements, leading to the same risks as a normal mutable key.

A Java `record` makes record components `final` and auto-generates `equals()`/`hashCode()` from the components, yet **provides only shallow immutability**. For components of type `List`, `Set`, array, or another mutable object, you must consider **defensive copying** and controlling references exposed outside.

### When a key only needs to be "effectively immutable"

An object does not have to be completely immutable to serve as a key: it may have mutable auxiliary state, as long as the properties participating in `equals()` and `hashCode()` remain unchanged while the key is in a `Map` or `Set`. However, fully immutable types are generally easier to test, easier to share, and less error-prone.

## 3. Complete example with Java 17+

The program below illustrates three cases: modifying a key attribute after storing it, using a `record` with immutable components, and copying a mutable list to create a stable key.

Create the file **`ImmutableKeyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ImmutableKeyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void changeId(int newId) {
            this.id = newId;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof MutableKey key && id == key.id);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    record OrderKey(String tenant, String orderNumber) {
        OrderKey {
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(orderNumber);
        }
    }

    record PartsKey(List<String> parts) {
        PartsKey {
            parts = List.copyOf(parts); // Create an unmodifiable copy.
        }
    }

    public static void main(String[] args) {
        Map<MutableKey, String> fragile = new HashMap<>();
        MutableKey mutable = new MutableKey(1);
        fragile.put(mutable, "stored");
        System.out.println("hash before mutation: " + mutable.hashCode());

        mutable.changeId(2);
        System.out.println("hash after mutation: " + mutable.hashCode());
        System.out.println("lookup after mutation: " + fragile.get(mutable));

        mutable.changeId(1);
        System.out.println("lookup after restoring id: "
                + fragile.get(mutable));

        OrderKey first = new OrderKey("shop", "ORD-01");
        OrderKey equivalent = new OrderKey("shop", "ORD-01");

        Map<OrderKey, String> orders = new HashMap<>();
        orders.put(first, "paid");
        System.out.println("record keys equal: "
                + first.equals(equivalent));
        System.out.println("record lookup: " + orders.get(equivalent));

        Set<OrderKey> uniqueOrders = new HashSet<>();
        uniqueOrders.add(first);
        uniqueOrders.add(equivalent);
        System.out.println("record set size: " + uniqueOrders.size());

        List<String> external = new ArrayList<>(List.of("north", "retail"));
        PartsKey safe = new PartsKey(external);
        Map<PartsKey, String> segments = new HashMap<>();
        segments.put(safe, "active");

        external.set(0, "south");
        System.out.println("snapshot contents: " + safe.parts());
        System.out.println("snapshot lookup: "
                + segments.get(new PartsKey(List.of("north", "retail"))));
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac ImmutableKeyDemo.java
java ImmutableKeyDemo
~~~

Typical output on **OpenJDK 17+**:

~~~text
hash before mutation: 1
hash after mutation: 2
lookup after mutation: null
lookup after restoring id: stored
record keys equal: true
record lookup: paid
record set size: 1
snapshot contents: [north, retail]
snapshot lookup: active
~~~

**Detailed explanation:**

1. `MutableKey` uses `id` to implement both `equals()` and `hashCode()`. Initially `id = 1`; after `changeId(2)` the hash code becomes `2`. In OpenJDK 17's `HashMap` implementation with default table sizing, lookup searches the region corresponding to the new hash code, while the key is stored at the old code's location: `get(mutable)` yields `null`.
2. When `id` is changed back to `1`, the hash code matches the key at insertion time, so the call in this example finds `"stored"` again. **Do not use "revert and look up again" as an application solution.** The Java API does not guarantee every detailed behavior shown in the example across all hash table implementations, and mutating keys can also cause semantic collisions with other keys.
3. `OrderKey` is a record consisting of two immutable strings. Two records with different references but the same `tenant` and `orderNumber` are considered equal, have equal hash codes, so `HashMap` finds the entry and `HashSet` keeps only one logical element.
4. `PartsKey` accepts an external list but uses `List.copyOf(parts)` in its compact constructor. After `external` is modified, the snapshot inside the key still holds `[north, retail]`, and lookup with an equivalent key still succeeds. The elements here are immutable `String` values.

Do not assume that every `get` call with a mutated key **must** return `null`. The observed result depends on the new hash code, collisions, and hash structure implementation; the general rule is that **lookup behavior is no longer guaranteed** once key-comparison data changes.

## 4. Common immutable key design patterns

### Case 1: record containing only immutable components

~~~java
// Illustrative snippet, not a standalone runnable file.
record CustomerKey(String tenantId, long customerNumber) {
    CustomerKey {
        java.util.Objects.requireNonNull(tenantId);
    }
}
~~~

Java automatically generates `equals()` and `hashCode()` across both components. A pair of keys with the same `tenantId` and `customerNumber` will be equal and have the same hash code. Neither `String` nor `long` poses a risk of being modified through a reference.

### Case 2: regular class with `private final`

~~~java
// Standalone illustrative snippet, not an independent program.
final class CustomerKey {
    private final String tenantId;
    private final long customerNumber;

    CustomerKey(String tenantId, long customerNumber) {
        this.tenantId = java.util.Objects.requireNonNull(tenantId);
        this.customerNumber = customerNumber;
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof CustomerKey key
                    && customerNumber == key.customerNumber
                    && tenantId.equals(key.tenantId));
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(tenantId, customerNumber);
    }
}
~~~

The immutability of the fields participating in `equals()`/`hashCode()` keeps the hash value stable. You do not need to override `toString()` to satisfy the hash contract; display formatting is separate from equality.

### Case 3: key containing a collection or array

You must **defensively copy when receiving data**, while also not returning internal mutable references through getters.

- For `List<String>`: `List.copyOf(source)` creates an unmodifiable list that preserves order while rejecting a `null` list and `null` elements. `String` instances themselves are immutable.
- For `Set<String>`: `Set.copyOf(source)` fits if order does not participate in key meaning. For `Map`, `Map.copyOf(source)` can be used when data fits.
- For `byte[]` or `int[]` arrays: copy with `array.clone()` on input, and return a copy from the accessor. Because default `array.equals()` and `array.hashCode()` compare by identity, if content equality is needed, implement a consistent pair of `Arrays.equals(...)` and `Arrays.hashCode(...)`. For multidimensional arrays, consider `Arrays.deepEquals(...)` and `Arrays.deepHashCode(...)`.
- **Shallow copying is not enough** if elements can also change. For example, a `List<MutableItem>` copied via `List.copyOf` still holds the old `MutableItem` instances; modifying an element's fields can change `List.equals()` and `List.hashCode()`. Convert each element to an immutable value or deep copy appropriately for the data model.

Do not substitute the `final` keyword alone for defensive copying: the reference is held fixed, yet internal contents can still change.

## 5. Does "immutable Map" mean "immutable key"?

**No.** There are three separate concepts:

| Concept | Primary guarantee | What is not automatically guaranteed |
| --- | --- | --- |
| Immutable key | State determining the key's equality and hash code is stable | That the map cannot be edited |
| `Map.of(...)` or `Map.copyOf(...)` | Disallows adding, removing, or replacing entries through the returned map | That key/value objects inside are immutable |
| `Collections.unmodifiableMap(map)` | Blocks modifications through the returned view | That the underlying map stops changing or that key objects are immutable |

For example, creating `Map.of(mutableKey, value)` does not make `mutableKey` immutable. Even a structurally unmodifiable map can still run into issues when the state determining a key's `hashCode()`/`equals()` is modified externally.

Similarly, changing a **value** via `map.put(key, newValue)` in a modifiable map is normal; what must stay stable is the **key**, especially the attributes used to compute the hash and compare keys.

## 6. What if business data truly has to change?

Not every business object should be completely immutable. Usually you should separate **stable key identity** from **updatable state**:

- Use a stable code such as `orderId`, `customerId`, or a `(tenantId, entityId)` pair as the key.
- Store the business object with mutable state as the `Map` **value**, instead of putting all mutable state into the key's `hashCode()`.
- If the key identity criterion itself changes (such as changing a code), use a controlled operation: remove the entry under the **old valid key**, create a new immutable key, and reinsert. Key collisions and operation atomicity must be handled when the application requires it.

Model example:

~~~java
// Illustrative snippet, to be placed inside a method with an appropriate map and data.
record ProductKey(String sku) {}

Map<ProductKey, String> names = new java.util.HashMap<>();
ProductKey oldKey = new ProductKey("SKU-01");
names.put(oldKey, "Widget");

String name = names.remove(oldKey); // Remove using the still-valid old key.
names.put(new ProductKey("SKU-02"), name); // Create a new immutable key.
~~~

For multithreaded applications, immutable keys by themselves **do not make `HashMap` thread-safe**. If multiple threads modify the map concurrently, synchronization or an appropriate structure like `ConcurrentHashMap` is needed, in addition to keeping keys stable.

## 7. Common mistakes and how to avoid them

1. **Modifying a field participating in `hashCode()` after `put`.** The hash table does not automatically relocate the stored entry; use immutable keys or keep those fields stable.
2. **Using `final List` and then calling `add`/`remove`.** `final` only fixes the reference. Use an unmodifiable copy, and ensure appropriate elements.
3. **Believing a record is always deeply immutable.** A record with `List`, array, or mutable object components can still expose state through its accessor; defensive copying and proper `equals()`/`hashCode()` semantics are needed.
4. **Putting a random field or update counter in `hashCode()` but not in `equals()`.** Two keys equal under `equals()` may receive different hash codes, violating the contract.
5. **Using `System.identityHashCode()` to "fix" value-mutable keys.** Identity hash codes bypass overridden `hashCode()` and are incompatible with value-based equality semantics when two distinct instances are considered equal.
6. **Thinking keeping the hash code constant is enough.** If `equals()` changes while the key is stored, the key can still exhibit unexpected lookup behavior. Keep the data participating in equality unchanged as well.
7. **Automatically relying on immutable keys to solve multithreading.** Key stability prevents one class of logic bugs, while concurrent operations on the map must be controlled separately.

### Checklist during design and testing

- Clearly identify the fields participating in `equals()` and `hashCode()`.
- Can those fields change or be modified indirectly through a reference?
- If the key contains a collection or array, do the constructor and getter handle defensive copying properly?
- Create two key instances with the same data: does `equals()` return `true` and are their hash codes equal?
- After inserting a key and looking it up with a new equivalent instance, do `HashMap.get` and `HashSet.contains` work properly?
- Have you avoided modifying equality-defining data while the key is present in a hash structure?
- If an identifier must change, is there a workflow that removes the old key and inserts the new key in the right order?

## 8. Self-check questions

**Question 1.** Does `record Key(List<String> parts) {}` guarantee an immutable key just because `parts` is a record component?

**Answer:** No. A record is immutable at the component reference level; if the list passed in is mutable, the record's hash value can change when the list contents change. Defensively copy it and use immutable elements.

**Question 2.** A class has a `private final String id` field and an incrementing `int viewCount` field. Can it be used as a key?

**Answer:** Yes, if `equals()` and `hashCode()` rely solely on `id` and all data relevant to the key definition remains stable. That is an *effectively immutable* key, even though the object has mutable auxiliary state.

**Question 3.** If a key was modified causing `map.get(key)` to fail, will calling `map.put(key, value)` to update it reliably fix the bug?

**Answer:** No. The `put` call may insert a new entry under the new hash code, leaving behind an old hard-to-reach entry and breaking the map's logical consistency. The proper design is to avoid modifying keys while stored; if changing an identifier is required, remove with the valid old key and add a new key.

**Question 4.** Does `Map.of(...)` make mutable key objects immutable?

**Answer:** No. `Map.of` protects the returned map structure from being modified; it does not freeze the state of the objects passed into it.

**Takeaway:** **Prefer immutable keys**, especially in `HashMap` and `HashSet`. What must be protected is the stability of the data used in `equals()` and `hashCode()` from the moment the key is added until it is removed. For mutable state inside keys, proactively perform defensive copying and prevent external references from altering the key's meaning.