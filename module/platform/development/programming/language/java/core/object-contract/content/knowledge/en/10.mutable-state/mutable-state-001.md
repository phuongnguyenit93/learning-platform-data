# Impact of Changing Fields Used in `equals()` or `hashCode()`

## 1. The problem: an object remains itself, but its equality relation can change

A Java object can keep the same **reference identity** while its internal fields are modified. If those fields participate in `equals(Object)` or `hashCode()`, modifying them can change how the object compares to others and how a hash-based data structure locates it again.

For example, a `Member` defined by `email`:

```java
// Illustrates the idea, not a complete class.
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof Member other)) return false;
    return email.equals(other.email);
}

@Override
public int hashCode() {
    return email.hashCode();
}
```

When `email` changes from `"a@example.com"` to `"b@example.com"`, the object in memory is still the same object: an alias variable still has `alias == member` evaluate to `true`. However, this object is no longer equal to another `Member` carrying the old email, and the hash code computed from the email may also change.

This is not necessarily a bug in the `equals` method itself: a mutable object changing its equality relation **after the relevant data is modified** does not automatically violate the `Object.equals` contract. The main risk arises when other code relies on a **stable** equality relation and hash code, such as a `HashSet` or a key already inserted into a `HashMap`.

### Distinguishing three things

| Aspect | When a field changes | What to understand |
| --- | --- | --- |
| Object identity (`a == b`) | Does not change just because a field is assigned a new value. | Two aliases still point to the same instance. |
| Result of `a.equals(b)` | May change if a field participating in the equality definition changes. | Two previously equal instances may become unequal, or vice versa. |
| Value of `a.hashCode()` | May change if the data used to compute the hash changes. | A recomputed hash code does not automatically move an entry already inside a hash table. |

The goal of this lesson is to clearly see **the impact of state changes on both the comparison contract and collection behavior**, and then choose a safe design.

## 2. What do the `equals` and `hashCode` contracts say about stability?

The contract of `equals(Object)` includes reflexivity, symmetry, transitivity, consistency, and returning `false` when compared with `null`. The **consistency** rule is qualified by a condition: provided no information used in the comparison is modified, repeated calls to `equals` must continue to return the same result.

Similarly, during a single execution of an application, multiple calls to `hashCode` on the same object must return the same value provided **no information used in `equals` has been modified**. The hash code is not required to remain constant across different runs of the program.

The most important rule when combining both:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

The converse is not true: two unequal objects are allowed to share the same hash code (*hash collision*).

Notable mutation cases:

1. **A field used in both `equals` and `hashCode` changes:** both its equality relation with other objects and its hash may change. If it is currently a key/element in a hash-based collection, lookup operations may fail.
2. **A field used only in `equals` changes:** the hash may remain unchanged, but previously distinct elements may become equal. `HashSet` does not automatically remove duplicate elements or re-establish uniqueness after data inside an element changes.
3. **A field used only in `hashCode` changes:** even though `equals` does not change, the hash code still changes and can break lookup capability. Worse yet, if two objects are equal according to `equals` but have different values in a field used only for hashing, the contract is **already broken from the start**, without waiting for any mutation.
4. **A field used in neither changes:** by design, if it truly does not indirectly affect comparison or hashing, `equals/hashCode` should remain unchanged. This is usually how display state is allowed to change while the identity key stays stable.

**Do not infer that changing a field must always produce a new hash value.** Two different states may happen to produce the same hash. Lookup results in a hash table may therefore appear to still work in a small example; that does not prove using mutable keys is safe.

## 3. Why are `HashMap` and `HashSet` especially sensitive?

When inserting a key into a `HashMap`, the structure uses the hash **at insertion time** to position the entry in its internal storage structure. When looking up, it recomputes the hash from the **query key at lookup time** and compares candidate keys using the appropriate rule.

Simplified mental flow:

```text
At put time:
key.code = "A" -> hash("A") -> select entry storage location

After modifying key.code = "B":
map.get(key) or map.get(new Key("B"))
    -> hash("B") -> search by new hash
    -> not guaranteed to reach the entry stored under hash("A")
```

This is an explanatory model, not a guarantee about the exact bucket structure of every JDK version. What matters is that **the collection receives no notification and does not automatically re-index** when you modify a field inside an object already placed in the collection.

Common consequences:

- `map.get(key)`, `map.containsKey(key)`, or `map.remove(key)` may fail even when `key` is the **exact same reference** previously used to `put`.
- `HashSet.contains(element)` or `HashSet.remove(element)` may fail, even though iterating over the `set` still shows that element.
- If a new object considered equal to the mutated element is added, a `HashSet` may temporarily contain multiple elements currently considered equal by `equals`. The set does not proactively re-scan all elements after every mutation.
- Results may depend on hash values, entry counts, and internal mutation history; therefore you cannot rely on a specific experiment still returning `contains == true`.

**Do not confuse a mutable *value* in `Map<K,V>` with a mutable *key*.** Modifying an object `V` stored under an ordinary stable key does not affect how `HashMap` finds the key. The risk being examined here is modifying the data used to determine `equals/hashCode` of `K` itself.

## 4. Java 17 example: changing hash makes a key hard to find, changing `equals` creates logical duplicates

Create a standalone file `MutableEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class MutableEqualityDemo {
    static final class CodeKey {
        private String code;

        CodeKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        void changeCode(String next) {
            this.code = Objects.requireNonNull(next);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof CodeKey other)) return false;
            return code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    static final class StageKey {
        private String stage;

        StageKey(String stage) {
            this.stage = Objects.requireNonNull(stage);
        }

        void changeStage(String next) {
            this.stage = Objects.requireNonNull(next);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof StageKey other)) return false;
            return stage.equals(other.stage);
        }

        @Override
        public int hashCode() {
            return 1; // Intentionally keep hash constant to isolate the effect of equals.
        }
    }

    public static void main(String[] args) {
        CodeKey storedKey = new CodeKey("A");
        Map<CodeKey, String> map = new HashMap<>();
        map.put(storedKey, "payload");

        System.out.println("before A: " + map.get(new CodeKey("A")));
        storedKey.changeCode("B");
        System.out.println("same reference: " + (storedKey == storedKey));
        System.out.println("equal to new B: " + storedKey.equals(new CodeKey("B")));
        System.out.println("after B by same key: " + map.get(storedKey));
        System.out.println("after B by new key: " + map.get(new CodeKey("B")));
        System.out.println("map size: " + map.size());

        storedKey.changeCode("A");
        System.out.println("restored A: " + map.get(new CodeKey("A")));

        StageKey first = new StageKey("todo");
        StageKey second = new StageKey("done");
        Set<StageKey> set = new HashSet<>();
        set.add(first);
        set.add(second);
        System.out.println("set size before: " + set.size());

        second.changeStage("todo");
        System.out.println("same value now: " + first.equals(second));
        System.out.println("same hash now: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("set size after: " + set.size());
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac MutableEqualityDemo.java
java MutableEqualityDemo
```

Output when run on JDK 17 with standard `HashMap`/`HashSet`:

```text
before A: payload
same reference: true
equal to new B: true
after B by same key: null
after B by new key: null
map size: 1
restored A: payload
set size before: 2
same value now: true
same hash now: true
set size after: 2
```

**Explanation of the `CodeKey` part:**

- During `put`, the key had `code = "A"`. For this pair of values, `"A".hashCode()` is `65` while `"B".hashCode()` is `66`. After modifying `code`, the recomputed hash changes to `66`, whereas the entry was inserted under the old hash.
- `storedKey.equals(new CodeKey("B"))` is true because the **new values** match. Yet `map.get(storedKey)` can still return `null`: `HashMap` does not automatically update the entry's position just because the key object was modified.
- `map.size()` remains `1`: the entry was not removed. Restoring `code` back to `"A"` only allows this small example to find the entry again; **reverting field changes should not be treated as a practical bug-fix strategy**.

**Explanation of the `StageKey` part:**

- `hashCode()` always returns `1`. This implementation is valid with respect to the required relation between `equals` and hashing, but its hash distribution is very poor and **is only for illustration**.
- Initially `"todo"` differs from `"done"`, so both elements are inserted into `HashSet`.
- After changing `second.stage` to `"todo"`, `first.equals(second)` becomes `true` while the set size remains `2`. Keeping the hash unchanged does **not** eliminate the risk of changing the equality relation.

This example clarifies two distinct design flaws: **a changing hash makes lookups unreliable**, while **a changing equality relation can break the logical invariant of a set**, even when the hash is constant.

## 5. Systematically analyzing each kind of change

### 5.1. Changing a field that participates in both `equals` and `hashCode`

Suppose both `InvoiceKey.equals` and `InvoiceKey.hashCode` use `invoiceNumber`. After adding the object to a `HashMap`, modifying `invoiceNumber` can make the key unfindable. If another object with the same new invoice number is added, the collection can end up with a structure that contradicts business expectations.

How to avoid: use an immutable invoice number key, or create a new key and update the mapping in an explicitly managed way (see section 7).

### 5.2. Only a field participating in `equals` changes

For example, `equals` is based on `firstName` and `lastName`, while `hashCode` always returns a constant value. The `equals => same hash` contract is satisfied, but if one of the name fields changes, objects can switch from equal to unequal or vice versa. `HashSet` does not automatically scan to remove newly created logical duplicates.

Omitting a field from the hash **does not make that field safe to modify arbitrarily** while the instance is in a set that relies on `equals`.

### 5.3. Only a field participating in `hashCode` changes

This is often also an independent design bug. Suppose:

```java
// Illustrates broken logic, not a standalone runnable program.
// equals only compares id, but hashCode uses displayName.
return displayName.hashCode();
```

Two objects with the same `id` may be considered equal by `equals`, yet different `displayName` values produce two different hashes: **violating the contract even before any mutation occurs**.

Not every hash formula has to list the exact same field names as `equals`, but it must guarantee that for every equal pair, the hash results are identical. The easiest practice to maintain is deriving the hash from the stable set of fields that define equality, or a consistent transformation of those fields.

### 5.4. Changing a field that participates in neither `equals` nor `hashCode`

If `User` has `final long userId` as its identity and `displayName` as display information, you can intentionally design `equals` and hashing based solely on `userId`. When the name changes, the equality relation does not change. This is safe **if** the business definition truly treats two users with the same `userId` as one entity and IDs are not misused across scopes.

This is the difference between **an object whose display fields can change** and **a key whose logical identity can change**.

## 6. Safe example: immutable key, mutable display data

Create the file `StableKeyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class StableKeyDemo {
    static final class User {
        private final long id;
        private String displayName;

        User(long id, String displayName) {
            this.id = id;
            this.displayName = Objects.requireNonNull(displayName);
        }

        void rename(String name) {
            displayName = Objects.requireNonNull(name);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof User other)) return false;
            return id == other.id;
        }

        @Override
        public int hashCode() {
            return Long.hashCode(id);
        }
    }

    public static void main(String[] args) {
        User user = new User(17L, "An");
        Map<User, String> roles = new HashMap<>();
        roles.put(user, "reader");

        user.rename("Bình");

        System.out.println("hash stable: "
                + (user.hashCode() == new User(17L, "Khác").hashCode()));
        System.out.println("equals stable: "
                + user.equals(new User(17L, "Khác")));
        System.out.println("lookup: "
                + roles.get(new User(17L, "Khác")));
        System.out.println("map size: " + roles.size());
    }
}
```

```bash
javac StableKeyDemo.java
java StableKeyDemo
```

Stdout:

```text
hash stable: true
equals stable: true
lookup: reader
map size: 1
```

Changing `displayName` does not alter the `id` value used in both `equals` and `hashCode`. Therefore, lookup via another `User` instance with the same ID still works. This pattern is only valid if **the ID is a stable business key and unique within the right data domain**.

If uniqueness is by the pair `(tenantId, userId)`, then both values must be immutable and participate together in the equality relation; using a single `userId` across two tenants could mistakenly merge entities.

## 7. How to update data when a logical key must change?

Prefer the following approaches, depending on the model:

**Approach A — design an immutable key from the start.** Use a `final` type with `final` fields, a `record` containing genuinely immutable components, or an identifier class such as `UserId`, `OrderId`. When a key value changes, create a **new key object**, rather than mutating the old key currently used in a collection.

```java
record AccountKey(String tenantId, long accountId) {}
```

With the two components `String` and `long`, this example has appropriate immutable semantics. A `record` automatically provides `equals/hashCode` based on its components.

**Approach B — replace the entry with an explicit operation when changing keys is required.** When logic requires changing a key, remove the mapping under the **old key while its value is still intact**, then insert under the new key:

```java
// Illustration: map is an existing Map<AccountKey, String>;
// oldKey is the old AccountKey that has never been modified;
// newKey is the new key, created independently.
String value = map.remove(oldKey);
if (value != null) {
    map.put(newKey, value);
}
```

This snippet only illustrates the sequence and assumes `null` is not a valid mapping value. If `null` is allowed, `remove` returning `null` cannot distinguish a nonexistent entry from an entry whose value is `null`; a separate existence check must be designed. When replacing a key, you must also decide how to handle collisions if `newKey` already has an entry. On concurrent data, the replacement must be performed within an appropriate synchronization or transaction mechanism.

**Approach C — separate the immutable key from mutable state.** For example, use `Map<Long, User>`, where `long id` serves as the key, and `User` is the value whose name, email, and status can change. Changes to `User` do not affect how entries are looked up by `Long`. If `User` is simultaneously placed into another `HashSet<User>`, that set's contract must be evaluated separately.

### Do not "fix" it with unfounded tricks

- Do not simply call `map.put(existingMutableKey, value)` again after mutation and assume the old entry has vanished. Depending on the hash, this operation can add a hard-to-manage extra mapping.
- Do not rely on `HashMap` rehashing during a resize to relocate all mutated keys; the collection has no contract to track key mutations.
- Do not just cache the hash to force `hashCode` to remain constant while `equals` still changes with another field; the risk of logical duplicates in a set remains. If the cache is not updated consistently with equality values, it can also violate the hash contract.
- Do not arbitrarily substitute `System.identityHashCode`: that is an identity-based hash function and does not guarantee satisfying value-based `equals`.

## 8. Indirect mutation through child objects, arrays, and records

A reference field can be declared `final` while **the referenced object remains mutable**. Therefore, evaluating stability must look at the **entire data graph that `equals/hashCode` uses**, not just the field modifier.

Example:

```java
import java.util.ArrayList;
import java.util.List;

// Illustration: type declaration using Java 17+, not a standalone runnable main.
record GroupKey(List<String> tags) {}

List<String> names = new ArrayList<>(List.of("java"));
GroupKey key = new GroupKey(names);
int before = key.hashCode();
names.add("spring");
int after = key.hashCode();
```

`record` auto-generates `equals/hashCode` based on the `tags` component. `List.equals` and `List.hashCode` depend on the list contents. Even though the `tags` reference in the record cannot be reassigned, `names.add(...)` alters the contents of the list held by the record; the hash of `GroupKey` changes accordingly in this example.

If defensive copying is needed, the record's compact constructor can use:

```java
record GroupKey(List<String> tags) {
    GroupKey {
        tags = List.copyOf(tags);
    }
}
```

`List.copyOf` creates/uses a list that disallows modification through its API and is decoupled from an ordinary mutable source list. However, it is a **shallow copy**: if elements inside the list are mutable objects and their `equals/hashCode` rules depend on state, the key can still change meaning. Those elements must also be copied or made immutable when needed.

Similarly, arrays are mutable. If a class uses `Arrays.equals(array1, array2)` and `Arrays.hashCode(array)` to represent an array's value, modifying array elements changes comparison/hashing. Conversely, a record with an array component uses the array's default reference-based `equals/hashCode`, and **does not automatically perform deep content comparison**; element-wise equality must be designed explicitly if desired.

## 9. Some differences across collections and concurrency

| Where the object is used | Impact when a comparison field is modified |
| --- | --- |
| `HashMap<K,V>` with the object as **key** | Risk of failing to find or remove the mapping due to changed hash/equality. |
| `HashSet<E>` | Risk of `contains/remove` failing or the set containing multiple currently equal elements. |
| `ArrayList<E>` | Does not use hashes to locate elements; `contains`/`indexOf` compare at the time of the call. Results may change after mutation, but there is no old bucket to reach. |
| `TreeMap`/`TreeSet` | Ordering and equivalence depend on `Comparator` or `Comparable`. Modifying a field used by the comparator while the element is stored is also dangerous, even when `hashCode` is unrelated. |
| `IdentityHashMap` | Uses reference identity (`==`) instead of `equals` for keys; unsuitable as a mechanical replacement for `HashMap` when business logic requires value-based keys. |

**Concurrency:** If multiple threads concurrently read and modify fields used by `equals/hashCode`, data races or inconsistent state observations can also occur, even before considering the collection. Plain `HashMap`/`HashSet` are not safe structures for concurrent write access. Using synchronization, immutable snapshots, or appropriate concurrent structures **does not make mutating hash/equality fields of stored keys valid**. A `ConcurrentHashMap` also does not proactively reposition a key when the key object itself is mutated.

**Data replacement and business consistency:** If an object is used as a key across multiple collections/caches, changing an identity field can cause those indices to drift out of sync. Identity changes should be managed at the data layer with immutable keys, creating a new key, updating the necessary indices/caches, and using appropriate transactional mechanisms when changes span multiple places.

## 10. Design and testing checklist

Before using an object type as a `Map` key or an element in a hash-based `Set`, answer:

1. **What is the equality key?** Which exact fields determine `equals`?
2. **Can those fields be modified?** Including indirectly via a `List`, `Map`, array, or child object?
3. **Does the hash follow the equality rule?** For every equal pair, are their hash codes equal?
4. **Has the object already been placed in a collection?** If so, does any code path modify the relevant values before removal?
5. **Can an immutable ID or separate key be used?** If display/status changes, does the logical key itself really need to change?
6. **Is it tested before and after mutation?** Test the old reference, another value-equal instance, logical duplicate cases, and add/remove operations.
7. **Does it depend on external state?** An `equals` based on a clock, database, global variable, or configuration can change results even when the object is not directly modified; avoid such rules for hash keys.
8. **Are there concurrency risks?** Ensure data participating in `equals/hashCode` remains stable throughout the time it is used in an index.

### Self-check exercises

- A key has `equals` by `id` but `hashCode` by `name`: how is it wrong even if both fields are immutable?
- Why can changing a field used only in `equals` still break expectations in a `HashSet` even though the hash stays the same?
- Why can `map.get(oldKey)` return `null` after modifying a field of **`oldKey` itself**?
- Is changing a display name safe if `equals/hashCode` relies solely on `final id`? What business assumption is required?
- Why is `final List<String>` not enough to guarantee that a key based on list contents is immutable?
- If a key must change, in what order should collection and data operations be performed to avoid leaving an entry indexed under the old value?

**Takeaway:** Modifying a field used in `equals` can alter the **equality relation**; modifying data used in `hashCode` can alter **hash-based lookup**. Collections do not automatically update their structure when internal objects are modified. The most reliable design is an **immutable logical key**, a hash consistent with `equals`, and separating mutable attributes from the identity used for lookup.