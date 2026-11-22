# Unassigned Identifiers and the Risk of Changing Equality Semantics in Java

## 1. The Problem to Solve

In an application with **entities** (objects whose identity persists over time), two different Java objects can represent the same business entity; conversely, two objects with seemingly identical contents can represent two different entities. When an entity's ID is assigned by the database after object creation, the `id` field is initially `null`. This phase raises the question: **what does equality mean when the ID does not yet exist, and what happens when the ID changes from `null` to a real value?**

The following example only illustrates state; the `Order` class and constructor are not defined here:

```java
Order first = new Order(null, "CUSTOMER-7");
Order second = new Order(null, "CUSTOMER-7");
```

Two `new` statements create two references to two different objects. If these are two independent new orders, they should **not** be treated as the same entity merely because both IDs are `null` or they share the same customer code. On the other hand, after saving, two objects loaded at different times with the same ID can be considered equal in business identity.

Learning objectives after this lesson:
- Choose an appropriate `equals` rule when the ID has not yet been assigned.
- Understand why `Objects.equals(null, null)` commonly causes bugs in entity models with post-assigned IDs.
- Identify the impact when a field participating in `equals`/`hashCode` changes while the object is inside a `HashSet` or used as a `HashMap` key.
- Distinguish between using post-assigned IDs, upfront application-assigned IDs, and immutable business keys.
- Verify behavior with a standalone Java 17 program and accurately explain the results.

The context is **Java Core and equality semantics**. With JPA/Hibernate, proxy generation and per-session entity management must also be considered; the pure Java example here is not a complete ORM class.

## 2. Reference Identity, Entity Identity, and Value

| Concept | Question | Commonly used mechanism |
|---|---|---|
| Object identity | Is it literally the exact same Java object? | `a == b` |
| Entity identity | Does it represent the same business entity across loads? | Confirmed ID or a designed business key |
| Value equality | Does it have the same meaningful value contents? | `equals` over chosen immutable components |

`Object.equals` defaults to reference identity. When overriding it, we must define an **equivalence relation** that is reflexive, symmetric, transitive; consistent if the compared data does not change; and satisfies `x.equals(null) == false`.

`hashCode` must obey: if `a.equals(b)` then `a.hashCode() == b.hashCode()`. The converse is not required: two different entities may have the same hash. While an object is used as a hash-based key, data that alters its hash should not change during storage.

### Typical Lifecycle of a Storage-Assigned ID

| Moment | Object | ID | Meaning |
|---|---|---|---|
| Just created | `a` | `null` | A new entity; compared by reference with itself |
| Another created at the same time | `b` | `null` | Another new entity; `a.equals(b)` must usually be `false` |
| After ID assignment | `a` | `101` | Persistent identity can start being compared by ID |
| Reloaded | `c` | `101` | `a != c` but `a.equals(c)` can hold |
| Another entity | `d` | `102` | Not equal to entity ID `101` |

Do not assume an ID is assigned immediately after a `persist` or `save` call: timing depends on the ID generation strategy, ORM, transaction, flush, and actual INSERT statement.

## 3. First Mistake: Two `null` IDs Treated as Equal

An under-constrained implementation:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Order that)) {
        return false;
    }
    return Objects.equals(id, that.id);
}
```

This snippet is an illustration only, not a standalone Java file. `Objects.equals(null, null)` returns `true`. If `a` and `b` are two independent new entities, both having `id == null`, this expression makes `a.equals(b)` return `true` even though there is no basis to claim they are the same entity.

Consequences when placed in collections:
- `HashSet` may reject a new object thinking it duplicates an existing entity.
- `HashMap.put(b, value)` may overwrite the value stored under key `a`.
- Existence/deduplication checks may silently drop logical data even though the entities have not been saved.

If choosing the policy **compare only by assigned ID**, check that the ID is non-`null`:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Order that)) {
        return false;
    }
    return id != null && id.equals(that.id);
}
```

Here `this == other` guarantees reflexivity even before an ID is assigned. The type check suits the illustrative `final` class. With an inheritance hierarchy or ORM proxies, type comparison must be designed to preserve symmetry without breaking identity.

## 4. Second Mistake: Hash Changes When the ID Is Assigned

If `hashCode` returns `Objects.hashCode(id)`:
- `null` ID → hash equals `0`.
- ID of `Long.valueOf(100)` → hash equals `100`.

Inserting an object into a `HashSet` when its hash is `0` and then updating its ID so the hash becomes `100` can cause lookups to fail. The collection uses the hash to locate the bucket; it does not automatically move an element to a new bucket when the object's attribute changes.

Another common mistake:

```java
@Override
public int hashCode() {
    return id.hashCode();
}
```

If the ID does not yet exist, the code above throws `NullPointerException`. Changing it to `Objects.hashCode(id)` only avoids the NPE; it does not solve the problem of the hash changing when the ID appears.

Nor should other mutable fields be used as the hash just for “temporary stability” if they can be edited later, or if they can differ between two objects carrying the same ID. If `equals` treats two entities with the same ID as equal while the hash relies on differing state, the `equals`/`hashCode` contract is broken.

## 5. Third Mistake: The Equality Relation Changes State

A subtler characteristic is that **the `equals` result between two objects can change over their lifecycle**. For example, before IDs are assigned, two new objects `a` and `b` with different references are unequal; later, if both are associated with the same entity ID, `a.equals(b)` can change to `true`.

Java's `equals` contract requires consistency **when the information used for comparison is not modified**. Therefore, a change in equality when the ID changes does not necessarily violate `equals`'s consistency condition on its own. However, **collections do not recompute equal pairs**. If two objects were added while still unequal, and later become equal, a `HashSet` may still retain both. A constant hash alone is not enough to cure this kind of issue.

This is why you must consider both **when an object is added to a collection** and **whether equality can still change while stored**.

## 6. Java 17 Example: Reproducing the Bug and Two Approaches

Create the file **`UnassignedIdDemo.java`**. All three nested classes are `final` to keep type checks simple:
- `BadOrder` demonstrates the `null/null` bug and mutating hash.
- `GeneratedOrder` demonstrates a post-assigned ID, `equals` distinguishing new entities, and a fixed per-class hash.
- `ClientAssignedOrder` demonstrates an immutable ID present immediately upon object creation.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public class UnassignedIdDemo {
    public static void main(String[] args) {
        BadOrder bad = new BadOrder();
        BadOrder anotherBad = new BadOrder();

        System.out.println("bad null IDs equal: "
                + bad.equals(anotherBad));

        Set<BadOrder> badSet = new HashSet<>();
        badSet.add(bad);
        System.out.println("bad hash before: " + bad.hashCode());
        System.out.println("bad contains before: "
                + badSet.contains(bad));

        bad.assignId(100L);
        System.out.println("bad hash after: " + bad.hashCode());
        System.out.println("bad contains after: "
                + badSet.contains(bad));

        GeneratedOrder first = new GeneratedOrder();
        GeneratedOrder second = new GeneratedOrder();
        System.out.println("safe null IDs equal: "
                + first.equals(second));

        Set<GeneratedOrder> safeSet = new HashSet<>();
        safeSet.add(first);
        first.assignId(100L);
        System.out.println("safe contains after: "
                + safeSet.contains(first));

        second.assignId(100L);
        System.out.println("safe same persisted ID: "
                + first.equals(second));
        System.out.println("safe lookup by second: "
                + safeSet.contains(second));

        UUID key1 = UUID.fromString(
                "00000000-0000-0000-0000-000000000001");
        UUID key2 = UUID.fromString(
                "00000000-0000-0000-0000-000000000002");

        ClientAssignedOrder assigned1 = new ClientAssignedOrder(key1);
        ClientAssignedOrder sameId = new ClientAssignedOrder(key1);
        ClientAssignedOrder assigned2 = new ClientAssignedOrder(key2);

        System.out.println("assigned same ID: "
                + assigned1.equals(sameId));
        System.out.println("assigned different ID: "
                + assigned1.equals(assigned2));
    }

    // INTENTIONALLY WRONG: null/null are treated as the same entity and hash changes with ID.
    static final class BadOrder {
        private Long id;

        void assignId(long value) {
            if (value <= 0) {
                throw new IllegalArgumentException("invalid ID");
            }
            if (id != null) {
                throw new IllegalStateException("ID already assigned");
            }
            id = value;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BadOrder that
                    && Objects.equals(id, that.id);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(id);
        }
    }

    // Entity with post-assigned ID: null is not equal to another instance's ID.
    static final class GeneratedOrder {
        private Long id;

        void assignId(long value) {
            if (value <= 0) {
                throw new IllegalArgumentException("invalid ID");
            }
            if (id != null) {
                throw new IllegalStateException("ID already assigned");
            }
            id = value;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof GeneratedOrder that)) {
                return false;
            }
            return id != null && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            // Fixed per class instead of mutable ID.
            return GeneratedOrder.class.hashCode();
        }
    }

    // Entity with pre-assigned application ID; final ID.
    static final class ClientAssignedOrder {
        private final UUID id;

        ClientAssignedOrder(UUID id) {
            this.id = Objects.requireNonNull(id, "id");
        }

        static ClientAssignedOrder createNew() {
            return new ClientAssignedOrder(UUID.randomUUID());
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof ClientAssignedOrder that
                    && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }
}
```

Run with JDK 17 or newer:

```bash
javac --release 17 UnassignedIdDemo.java
java UnassignedIdDemo
```

Output on common JDK 17 `HashSet`/`HashMap` implementations:

```text
bad null IDs equal: true
bad hash before: 0
bad contains before: true
bad hash after: 100
bad contains after: false
safe null IDs equal: false
safe contains after: true
safe same persisted ID: true
safe lookup by second: true
assigned same ID: true
assigned different ID: false
```

**Block-by-block explanation:**

1. `BadOrder` is wrong because `Objects.equals(null, null)` is `true`. Assigning ID `100L` changes the hash from `0` to `100`; with buckets in common JDK 17 builds, `HashSet.contains(bad)` after the update returns `false`. By contract, lookup after mutating the hash of a stored element **is not guaranteed**; do not generalize that every version or every ID value must print `false`.
2. `GeneratedOrder` does not treat two new objects with `null` IDs as equal. Comparing an object to itself remains equal thanks to `this == other`. Because the hash is fixed per class, assigning an ID after the object is already in `HashSet` does not change its bucket.
3. After `first` and `second` both receive ID `100`, they represent the same entity in the simulated scenario. `equals` returns `true` and their hashes match, so the element in `safeSet` can be looked up via `second`.
4. `ClientAssignedOrder` uses a `UUID` ID as a `final` field, meaning the hash is stable. Two objects carrying the same ID are considered equal; two distinct explicit IDs differ. `createNew()` uses `UUID.randomUUID()` when creating real entities, but is not used in output so that the program always prints deterministic results.

### Is a Constant Hash Really Correct?

With `GeneratedOrder` as a `final` class, every instance returns `GeneratedOrder.class.hashCode()`. If two entities are equal, their hashes are guaranteed to match, so the hash contract is satisfied. However, all instances of the same class share the same hash, causing many collisions and potentially slowing down collection operations at large scale. This is a trade-off choice, not the optimal answer in every context.

The `Class.hashCode()` value here serves as a hash in **JVM memory**, not an ID that can be persisted or transmitted across processes. Do not rely on the specific hash value to identify records.

### Constant Hash Still Does Not Preserve Uniqueness If Equality Changes

Suppose two different new `GeneratedOrder` objects are added to a `HashSet` while both IDs are `null`. The set will contain two elements because they are unequal. If a synchronization bug causes both to later carry the same ID, they become equal yet the set will not automatically remove the duplicate element. Therefore, choosing a constant hash only solves **hash bucket stability**; the application must still manage when IDs appear and when objects are placed into collections.

## 7. Three Practical Implementation Strategies

### A. Assigning an Immutable ID Upon Object Creation

If the architecture permits, the application can assign a UUID right in the constructor/factory. `equals` and `hashCode` both rely on the immutable ID; thus they are stable even before the entity is saved. Reloaded objects must retain **their existing ID**, not generate a new one.

Uniqueness limits and storage design must be accounted for: random UUIDs have a very small collision probability without an absolute mathematical guarantee; IDs must be compatible with the schema and all relevant services.

### B. ID Assigned Later by Storage

When the ID is initially `null`, the common policy for a `final` Java class is:

1. If same reference (`this == other`), return `true`.
2. If not the same entity type, return `false`.
3. If the ID is not yet present, do not consider it equal to another object.
4. If the ID is present, compare IDs according to business semantics.
5. Choose a hash stable across the expected lifecycle, or defer placing the object into hash collections until identity stabilizes.

Consider the cost of a constant hash and the risk of equality changing relative to other objects. A manageable option is to create a hash key from the ID **only after the ID is confirmed**.

### C. Using an Immutable, Unique Business Key

A data pair like `tenantId + externalOrderId` can identify an entity before the database assigns a surrogate key, **if** the business domain truly guarantees it is immutable and unique within the defined scope. Do not pick a customer name, email, note, status, or any mutable attribute as a key merely because it currently appears unique.

If the business requires editing the key, you must reconsider identity rules and collection consequences; in that case, an upfront technical key may be more appropriate.

| Criterion | Upfront application-assigned ID | DB post-assigned ID + constant hash | Immutable business key |
|---|---|---|---|
| ID/key available at creation | Yes | Not yet | Yes, if supplied by business |
| Can keep hash stable | Yes | Yes, with a non-ID-based hash | Yes, if key fields do not change |
| Equality between two representations | By same ID | By ID once assigned | By business key |
| Main risk | Improper ID distribution/storage/recreation | Collisions and equality changing over lifecycle | Uniqueness or immutability not holding as assumed |

## 8. Specifically for ORM/JPA/Hibernate

You cannot drop `GeneratedOrder` above verbatim into every ORM entity: some providers use proxies/subclasses and require specific constructors and access rules. `getClass()` can return a proxy class, whereas `instanceof` can lead to inappropriate comparisons within an inheritance hierarchy. Type comparison rules must be designed consistently and tested on the specific provider.

Scenarios to verify:
- New entity without an ID, two different new instances.
- Entity assigned an ID after insert/flush under the specific strategy.
- Two representations of the same record loaded in different sessions.
- Detached entity and entity after merge.
- Proxy and non-proxy of the same entity, if the provider uses proxies.
- Lazy or mutable associations should not be pulled into equality in ways that cause cycles or unintended database queries.

Do not infer from a pure Java example that `persist` always assigns an ID immediately, that `final` is always valid with ORM proxies, or that every entity class uses a single `hashCode` pattern.

## 9. Exercises for Checking Equality Semantics

### Cases to Predict

| Input | Result under post-assigned ID policy |
|---|---|
| `a.id == null`, check `a.equals(a)` | `true` |
| `a != b`, both IDs `null` | `false` |
| `a.id == 101`, `b.id == 101`, same entity type | `true` |
| `a.id == 101`, `b.id == 102` | `false` |
| `a.id == 101`, `b.id == null` | `false` |
| `a.equals(null)` | `false` |
| `a.equals(b)` is `true` | `a.hashCode() == b.hashCode()` must hold |
| Object already stored in `HashSet`, then field participating in hash changes | Lookup is no longer reliable |
| Two objects in `HashSet`, then equality between them changes to `true` | Collection does not automatically merge elements |

### Practical Exercises

1. Write reflexivity, symmetry, and transitivity checks for three objects carrying ID `101` and objects still having `null`. Do not forget comparisons with `null` and with objects of another type.
2. Change `GeneratedOrder.hashCode()` to `Objects.hashCode(id)` in a separate test copy. Rerun and observe the change; explain why inspecting a single run is insufficient to prove a design is safe.
3. Use a `BadOrder` object as a `HashMap` key before assigning an ID; try `get` with that same object before and after assigning the ID. Explain why the value may no longer be found.
4. Add two `GeneratedOrder` objects missing IDs into a `HashSet`, then in a simulated scenario assign the same ID to both. Check the set size before/after and explain why a constant hash does not guarantee the set cleans itself up.
5. Write an immutable `OrderKey` value object containing an existing `tenantId` and `orderId`; compare stability when using `OrderKey` as a `Map` key versus using an entity with a post-assigned ID.
6. If the application uses an ORM, write integration tests across two sessions and actual proxies, not only unit tests with plain POJOs.

A snippet checking equality semantics (using the nested `GeneratedOrder` class of `UnassignedIdDemo` in the same demo file, or adjusting to a qualified name when moving to another file):

```java
GeneratedOrder a = new GeneratedOrder();
GeneratedOrder b = new GeneratedOrder();

assert a.equals(a);
assert !a.equals(b);
assert !a.equals(null);

a.assignId(101L);
b.assignId(101L);
assert a.equals(b);
assert b.equals(a);
assert a.hashCode() == b.hashCode();
```

This is an illustrative snippet **that does not run standalone**. In Java, `assert` statements are disabled by default unless `-ea` is enabled; in real projects, use JUnit assertions or an appropriate testing framework so results are always checked.

## 10. Checklist Before Placing Entities Into Collections

- Is business identity truly determined by the ID, or is there another immutable key?
- Can the ID be `null` at the moment the entity or collection key is created?
- Are two independent new objects mistakenly equated merely because both have `null` IDs?
- Does `equals` check `this == other` to preserve reflexivity for entities without an ID yet?
- Does `hashCode` depend on the ID or any field that can still mutate?
- Can two objects already inside a collection transition from unequal to equal?
- When reloading an object, is its existing identity preserved instead of assigning a new ID?
- If using an ORM, do entity type comparisons and proxy handling break symmetry/transitivity or trigger implicit queries?
- Can a separate immutable key be used instead of using the entity directly as a `HashMap` key?

**Point to remember:** `null` means **no ID assigned yet**, not a shared ID for all new entities. When the ID appears, equality and hash code can change; you must proactively choose an identity policy, design `equals` and `hashCode` consistently, and manage when entities are used in collections.