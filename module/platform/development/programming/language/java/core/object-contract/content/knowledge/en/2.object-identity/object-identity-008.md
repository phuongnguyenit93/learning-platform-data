# In-Memory Object Identity and Business Identifiers in Java

## 1. Learning Objectives

After this lesson, you can:

- Distinguish **object identity within a single JVM execution** from a **business identifier of a domain entity**.
- Correctly explain the roles of `==`, `equals()`, `hashCode()`, and `System.identityHashCode()`.
- Design how to compare two objects representing the same entity, even when loaded in two separate operations.
- Avoid confusing memory addresses, object display strings, or hash codes with business IDs; recognize bugs when storing entities in a `HashSet`, using them as `HashMap` keys, or assigning IDs after saving to a database.

## 2. Two Kinds of Identity Answer Two Different Questions

**Object/reference identity** asks: “Do two reference variables point to **the exact same object** in the JVM?” For two object references, the expression `a == b` answers this question. Each regular `new` object creation produces an object with its own identity, even if its fields hold identical values to another object. Assigning `b = a` only creates an additional reference to the same object.

**Business identifier** asks: “Do these two representations refer to **the same system entity**?” For example, two `Customer` objects with `customerId = "CUS-001"` may be two different Java instances yet both represent the same customer. The ID is defined by the application or data source; it can persist across databases, APIs, events, and program executions.

Example reference diagram:

```text
a -----+
       +----> Customer object #1 { customerId = "CUS-001" }
alias -+

b ----------> Customer object #2 { customerId = "CUS-001" }

a == alias         -> true  (same object)
a == b             -> false (two different objects)
a.id().equals(b.id()) -> true (same business ID)
```

The `#1`/`#2` labels in the diagram are merely illustrative labels for two instances; they are **not** real addresses, IDs, or hash numbers provided by the JVM.

| Criterion | Object Identity in the JVM | Business Identifier |
| --- | --- | --- |
| What is identified | A specific instance during execution | A meaningful entity in the application domain |
| Common check | `a == b` for references | Comparing IDs by domain rules, often via `equals()` |
| Scope | One JVM process's object space | Can span databases, sessions, processes, and services |
| When cloning or reloading from a database | Different reference: `==` is usually `false` | Can still be the same entity if the ID matches |
| When restarting the application | Old references lose meaning | Persistent IDs can continue identifying the record |
| What determines it | Java's reference semantics | Business design and data constraints |
| Uniqueness to understand | No two different objects are the same reference at the same time | An ID is unique only within its **defined scope** (e.g., per tenant) |

**Terminology note:** “In-memory identity” is a convenient phrase. Java does not expose the real machine address of every object to serve as an ID. The garbage collector may move objects while the `==` relationship between references retains the same meaning.

## 3. `==`, `equals()`, and `hashCode()` Are Not Interchangeable

### 3.1. The `==` Operator

- For **two references**, `==` checks whether they refer to the same object, including when both are `null`.
- For **primitive types** such as `int`, `==` compares primitive values (no object identity).
- Two different instances with identical data still yield `false` when comparing references with `==`. Conversely, two variable names pointing to the same instance always yield `true`.
- Do not use `==` to compare `String` contents or `String`-typed IDs; use `String.equals()`, or `Objects.equals()` if `null` is possible.

### 3.2. The `equals()` Method

The `Object` class by default implements `equals()` using reference identity. A subclass can override it to describe a **semantic equality** relation:

- **Entity:** can treat two objects as equal if they carry the same stable, valid ID within the proper business scope.
- **Value object:** typically treats two objects as equal when their meaningful values are equal. For example, `record Point(int x, int y) {}` automatically gets `equals()` based on components `x` and `y`.
- **Not every class should compare by ID.** Override `equals()` by business ID only when it matches the domain's entity-identification rules.

A proper `equals()` implementation must preserve reflexivity, symmetry, transitivity, and consistency when relevant state does not change; compared against `null`, it must return `false`. Using a `final class` in the example below avoids symmetry pitfalls when inheritance is involved.

### 3.3. The `hashCode()` Method

If `a.equals(b)` is `true`, it is **mandatory** that `a.hashCode() == b.hashCode()`. The converse is not true: two objects with equal hash codes can still be unequal because hashes can collide.

`HashMap` and `HashSet` rely on both `hashCode()` and `equals()`, so when changing equality to be ID-based, you must implement a consistent `hashCode()`. In particular, **do not mutate fields participating in `equals()`/`hashCode()` while an object is being used as a `HashMap` key or resides in a `HashSet`**; if the hash changes, lookup/duplicate detection can fail.

## 4. Runnable Java 17+ Example

The `Customer` class below identifies a customer by an immutable `customerId`. The display name can differ without changing the business identity. Two `new Customer(...)` calls create two different instances, even when the ID matches.

Save to the file `IdentityVsBusinessId.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class IdentityVsBusinessId {
    static final class Customer {
        private final String customerId;
        private final String displayName;

        Customer(String customerId, String displayName) {
            this.customerId = Objects.requireNonNull(customerId, "customerId");
            this.displayName = Objects.requireNonNull(displayName, "displayName");
        }

        String id() {
            return customerId;
        }

        String name() {
            return displayName;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Customer customer)) return false;
            return customerId.equals(customer.customerId);
        }

        @Override
        public int hashCode() {
            return customerId.hashCode();
        }
    }

    public static void main(String[] args) {
        Customer a = new Customer("CUS-001", "An");
        Customer b = new Customer("CUS-001", "An (another load)");
        Customer c = new Customer("CUS-002", "An");
        Customer alias = a;

        System.out.println("a == b: " + (a == b));
        System.out.println("a == alias: " + (a == alias));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.equals(c): " + a.equals(c));
        System.out.println("Same business ID: " + a.id().equals(b.id()));

        Set<Customer> customers = new HashSet<>();
        customers.add(a);
        customers.add(b);
        customers.add(c);
        System.out.println("HashSet size: " + customers.size());

        Map<Customer, String> ordinaryMap = new HashMap<>();
        ordinaryMap.put(a, "Note for a");
        System.out.println("HashMap get(b): " + ordinaryMap.get(b));

        Map<Customer, String> identityMap = new IdentityHashMap<>();
        identityMap.put(a, "Note for a");
        System.out.println("IdentityHashMap get(b): " + identityMap.get(b));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac IdentityVsBusinessId.java
java IdentityVsBusinessId
```

Standard output:

```text
a == b: false
a == alias: true
a.equals(b): true
a.equals(c): false
Same business ID: true
HashSet size: 2
HashMap get(b): Note for a
IdentityHashMap get(b): null
```

**Point-by-point explanation:**

1. `a` and `b` are two objects created by two `new` calls, so `a == b` is `false`, even though both have ID `CUS-001`. The variable `alias` directly references `a`, so `a == alias` is `true`.
2. `Customer.equals()` intentionally compares `customerId`. Consequently, `a.equals(b)` is `true` and `a.equals(c)` is `false`.
3. `HashSet` contains two distinct entities by ID (`CUS-001` and `CUS-002`). It does not add `b` as a third element because `b.equals(a)` is `true` and the hash matches.
4. `HashMap` finds the value using key `b` because key `b` is considered equal to key `a` under `equals()` and `hashCode()`.
5. `IdentityHashMap` compares keys **by reference** (`==`), so key `b` does not match the added instance `a`; `get(b)` returns `null`. This is a specialized structure useful in certain algorithms that need instance tracking (for example, object-graph traversal), not the default way to index by business ID.

The example assumes `customerId` is always assigned before object creation and never changes. Having two objects with the same ID and different display names is common when data is loaded at different times; comparing entities by ID **does not mean** the copies have completely identical state.

## 5. Is `System.identityHashCode()` an In-Memory ID?

`System.identityHashCode(obj)` returns an `int` representing an identity-based hash value for the object, regardless of how the class overrides `hashCode()`. Within a single run, repeated calls on the same object return the same result. However:

- **Not a memory address.** You cannot infer a real address, allocation location, or post-GC location from that hash number.
- **Not guaranteed unique.** Two different objects can receive the same hash value due to the finite `int` range and collisions.
- **Not a business ID.** Do not use it as a database key, an ID in an HTTP API, an invoice number, an event ID, or an identifier across JVM runs.
- **Not a replacement for `==`.** To tell whether two references point to the same object, compare `a == b` directly; comparing `identityHashCode(a) == identityHashCode(b)` can yield the wrong conclusion if hashes collide.

Similarly, default strings looking like `SomeClass@1a2b3c` do not prove a real address or uniqueness. Default `Object.toString()` concatenates the class name with the hex representation of `hashCode()`; a class can override `toString()`/`hashCode()`. Such log strings only help diagnostics to a limited degree and have no meaning as business identifiers.

## 6. Designing Business Identifiers Properly

### 6.1. Define the Entity and Uniqueness Scope

For example, `orderId` for an order, `customerId` for a customer, or a reservation code. Before choosing an ID strategy, answer:

- What **entity type** does the ID identify? An `Order` and a `Customer` with the same string `"123"` do not become the same entity.
- Is the ID globally unique across the system, within a company, or **only within a single tenant**? If unique only within a tenant, identification may require the pair `(tenantId, localId)`.
- Is the ID assigned at entity creation, upon database save, or by another service? Is there a period when the entity does not yet have a valid ID?
- Is the ID stable throughout the entity's lifetime? Mutable display codes (phone number, email, username, or editable order number) are usually unsuitable as immutable identity.
- Where is uniqueness enforced? Unique/primary key constraints and collision handling are needed at the data source; `equals()` alone cannot prevent two records with the same ID from arising.

Also distinguish: a **database primary key** (e.g., an auto-increment numeric column) and a **business key** (e.g., a customer code used by the business) may be the same or different. A surrogate primary key is only a technical key yet can still be used by the application as a durable entity ID; conversely, a business key may change and be unsuitable as the `equals()` key. Decide based on actual lifecycle and data contracts.

### 6.2. Prefer Stable IDs When Implementing ID-Based Equality

A simple approach for a pure Java domain model is to assign the ID at creation time and keep it `final`, such as an ID from a sequence generator service or `UUID.randomUUID()` if appropriate for the requirements. Use the ID to implement `equals()`/`hashCode()` and avoid putting mutable attributes like name or order status into the entity's hash function. This makes the entity safer to use in hash collections when ordinary attributes change.

**When the database assigns the ID after insert:** a new entity may have `id == null` until saved. Never automatically write `Objects.equals(this.id, other.id)` and conclude that all unsaved entities are equal: two `null` IDs would be treated as equal even though they are intended to be two independent entities. Nor can you arbitrarily switch the hash from a `null`-based value to an ID-based hash after the object has already been placed into a `HashSet`/`HashMap`. Clearly define the equality strategy for unsaved and saved states based on framework/ORM constraints, entity lifecycle, and collection usage; or assign a stable ID early if the business domain allows.

### 6.3. Do Not Confuse IDs with Access Permissions or Synchronized Data

- Receiving a `customerId` from a request does not mean the sender is authorized to view or edit that customer. Authentication, authorization, and tenant scope must be checked separately.
- Two objects with the same ID do not necessarily have the same data version. After re-fetching from a database or exchanging between services, they may carry different state; synchronization mechanisms, versioning, or optimistic locking are needed if the business requires them.
- Even for the same database entity, a Java object freshly deserialized from JSON is normally a new instance. Do not rely on `==` across APIs, queues, JVMs, distributed caches, or subsequent restarts.
- If the ID is a `String`, define clear formatting/canonicalization: for example, case sensitivity or trimming whitespace is a business policy, not an ad-hoc rule inside `equals()`.

## 7. Practical Scenarios and How to Choose a Comparison

| Scenario | Right Question | Appropriate Approach |
| --- | --- | --- |
| Two variables point to the same Java instance? | Is it actually the same current object? | `a == b` |
| Two `Customer`s loaded in two transactions are the same customer? | Do they share a valid business key? | Compare IDs in the right scope, or use `equals()` designed around entity ID |
| Two `Money`/`Point` objects have the same value? | Do they have equal constituent values? | Value-object `equals()`; consider using `record` |
| Deduplicating customers by ID in a `HashSet`? | Consistent equality and hash rules? | `equals()` and `hashCode()` based on a stable ID |
| Tracking visited objects to avoid reference cycles? | Have we encountered this exact instance? | Consider `IdentityHashMap` or an appropriate identity set |
| Logging object identification for investigation? | Which entity should the event correlate with? | Log business ID and request/trace correlation IDs as appropriate; do not rely on identity hash numbers |

A classic mistake:

```java
Customer first = new Customer("CUS-001", "An");
Customer second = new Customer("CUS-001", "An");
if (first == second) {
    System.out.println("Found the same customer");
}
```

The condition here is `false` because they are two separate instances. If the goal is to compare customers by an established stable ID, use `first.equals(second)` as in the main `Customer` class example, or compare `first.id().equals(second.id())` directly. Do not mechanically replace every `==` with `equals()`: checking reference identity remains right when that is precisely what the algorithm requires.

## 8. Misconceptions to Avoid

1. **“Same data means `==` must be `true`.”** False for references: two objects can have different identities in the JVM yet be equal by value or entity ID.
2. **“`equals()` compares IDs by default.”** False: `Object.equals()` defaults to identity. Comparing by ID requires explicit design and implementation consistent with `hashCode()`.
3. **“Different hashes mean two different objects; matching hashes mean the same object.”** False: neither `hashCode()` nor `identityHashCode()` proves unique identity; collisions exist.
4. **“`System.identityHashCode()` is a RAM address.”** False: the JVM makes no such guarantee, and GC can change physical locations.
5. **“Two records with the same ID in the database are the same Java instance.”** False: ORMs, deserialization, two sessions, or two processes can create multiple instances representing the same entity.
6. **“Unassigned IDs are all `null`, so two new entities are equal.”** False: unsaved entities need their own rule; comparing IDs via `Objects.equals(null, null)` leads to wrong conclusions.
7. **“Just comparing IDs in code makes data unique and valid.”** False: storage-layer constraints, namespace/tenant scoping, permission checks, and conflict handling are required.

## 9. Self-Check

**Question 1.** `Order x = new Order("O-9")` and `Order y = new Order("O-9")` are created with two `new` calls. Assume `Order.equals()` is properly implemented by immutable ID. What are the expected results of `x == y` and `x.equals(y)`?

**Answer:** `false` and `true`. `==` answers about the same instance; ID-based `equals()` answers about the same entity.

**Question 2.** Two customers in tenants `T1` and `T2` share the internal code `"100"`. Should you compare only the string `"100"` to conclude they are the same customer?

**Answer:** No, if the code is unique only within each tenant. You must include `tenantId` in the identifying key or use a truly system-wide unique ID per the data contract.

**Question 3.** An entity is added to a `HashSet` while `id == null`, then the database assigns an ID and `hashCode()` changes from the hash of `null` to the hash of the new ID. What is the risk?

**Answer:** The hash bucket position may no longer match; `contains()`/`remove()` may fail to find the added object. You need a stable equality/hash strategy suited to the entity lifecycle.

**Question 4.** Two objects have equal `System.identityHashCode()` values. Can you conclude `a == b`?

**Answer:** No; hashes can collide. Use `a == b` when the question is reference identity.

---

**Remember:** `==` (for references) identifies **the same object existing in the JVM**; a business ID identifies **the same entity by domain rules**. `equals()` can be designed to reflect the business ID, and `hashCode()` must be consistent with that choice. These two layers of identification serve different decisions in a Java application.