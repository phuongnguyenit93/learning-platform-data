# Keeping equals(), hashCode(), and Comparison Ordering on the Same Business Model

## 1. The Problem: One Business Entity, Multiple Java Objects

In an application, data for **the same order** may be loaded from the database multiple times or appear in different snapshots. Those two Java objects may have different memory addresses and different display states, yet still represent **the same order**.

For example: `Order("shop-A", 42, 1500)` and `Order("shop-A", 42, 1999)` share the same business key `(tenantId, orderNo) = ("shop-A", 42)`, while `totalCents` is an attribute that can vary across data versions.

If `Order`'s contract specifies that the **business identity** is the pair `tenantId + orderNo`, three mechanisms in Java must all respect that choice:

- **`equals(Object)`** answers "do these two objects represent the same business entity?".
- **`hashCode()`** provides a hash code consistent with `equals()` so that `HashSet`/`HashMap` can locate elements/keys.
- **`compareTo(T)`** (or a `Comparator` for ordered collections) provides ordering; a result of **0** needs to represent the same identity when we want `TreeSet`/`TreeMap` to have the exact business semantics of `equals()`.

The three methods do not have identical roles. `equals()` tests an equivalence relation; `hashCode()` optimizes lookup under that relation; comparison establishes order. They must be **consistent under a single identity model**, though there is no requirement that two `hashCode()` values be equal when two objects differ, or that the result of `compareTo()` equal `hashCode()`.

## 2. Lock In the Business Model Before Choosing Fields for the Methods

Before implementing, determine **what makes two entities the same entity**. This is a business decision, not a decision made by IDE code generation.

For an order belonging to multiple stores/tenants:

| Field | Role | Participates in `equals` | Participates in `hashCode` | Participates in natural order |
| --- | --- | --- | --- | --- |
| `tenantId` | Part of business key | Yes | Yes | Yes, compared first |
| `orderNo` | Part of business key within tenant | Yes | Yes | Yes, compared second |
| `totalCents` | Order amount, can change | No | No | No, if natural order is based on identity |
| `status`, `updatedAt` | Status/metadata | No | No | No, under the same identity model |

You cannot use `orderNo` alone if different tenants can both generate number 42. Conversely, adding `status` to `equals` would turn the exact same order into "a different entity" every time its status changes.

There are two common models; do not mix them:

1. **Entity identity:** the object represents an entity with a stable identity. Compare by key, such as `tenantId + orderNo`; different snapshots remain business-equal.
2. **Value object:** all meaningful attributes constitute the value. Two value objects are equal only when their specified components have equivalent values. For immutable types, this approach is usually natural; for example, two coordinates `(x,y)` with the same pair of values.

An `Order` class that has an amount, status, and update timestamp, but whose identity is defined by order code, should generally use the first approach. If the business truly treats **all content** as the identity, then `equals`, `hashCode`, and the comparison key must all move to that value model, rather than changing just one method.

**Key normalization:** rules for letter case, whitespace, tenant codes, and numeric types must be applied consistently when creating the object. For example, if `shop-A` and `SHOP-A` represent the same tenant in the business domain, normalize both to the same canonical form **before storing the key**; if case-sensitive, preserve as-is. Do not let `equals` ignore case while `compareTo` still compares case-sensitively.

## 3. Java Contracts You Must Understand

### 3.1. `equals(Object)` Is an Equivalence Relation

For non-null reference values `x`, `y`, `z`, `equals` must obey:

- **Reflexive:** `x.equals(x)` is `true`.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` produce the same result.
- **Transitive:** if `x.equals(y)` and `y.equals(z)` then `x.equals(z)`.
- **Consistent:** when the information participating in `equals` does not change, repeated calls must return the same result.
- **For null:** `x.equals(null)` is always `false`.

Do not invent a rule like "two orders are equal if their amounts differ by less than a threshold", because proximity within a threshold may **not be transitive**: A is close to B, B is close to C, yet A is not close to C. Also watch out for situations where a parent class compares using `instanceof` while a subclass adds fields: the two comparison directions can lose symmetry. The example below uses `final class` to lock down the identity semantics and avoid inheritance issues.

### 3.2. `hashCode()` Must Use the Same Identity as `equals()`

Mandatory rule:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

The converse is **not required**: two different orders may share a hash code (hash collision). `HashSet` and `HashMap` still need `equals` to determine whether elements/keys are truly duplicates.

A valid `hashCode()` does not have to be unique, is not a database storage identifier, and does not need to remain stable across application runs. What must be preserved is consistency with `equals` as long as the identity fields do not change.

Typical mistake:

```java
// Incorrect illustration: equals uses only the key, while hashCode adds totalCents.
@Override
public int hashCode() {
    return Objects.hash(tenantId, orderNo, totalCents);
}
```

When two snapshots share the same `tenantId + orderNo` but have different total amounts, `equals` can be `true` while the hash codes differ; the `totalCents` field must be excluded from `hashCode` if it is not part of the identity.

### 3.3. `Comparable.compareTo` or `Comparator.compare` Establishes Order

For natural ordering using the same key, what is desired is:

```text
sign(a.compareTo(b)) == 0   <=>   a.equals(b)
```

Here `sign` is the negative/0/positive sign; there is no requirement for `compareTo` to return strictly `-1` or `1`. Java **strongly recommends** that natural ordering be consistent with `equals`, though the language does not force every class to comply. When placed in a `TreeSet`/`TreeMap`, a comparison result of **0** is the criterion that treats two elements/keys as duplicates; hence inconsistency has tangible consequences.

The ordering must also satisfy sign antisymmetry and transitivity:

```text
sign(compare(a, b)) == -sign(compare(b, a))
compare(a, b) > 0 && compare(b, c) > 0  =>  compare(a, c) > 0
```

Ensure that elements considered equal by the comparator have identical comparison relationships with any third element. When comparing multiple fields, compare sequentially in a fixed order; use `String.compareTo`, `Long.compare`, `Integer.compare`, or chained `Comparator.thenComparing`, avoiding hand-written subtraction that could overflow.

`equals(null)` returns `false`, whereas `compareTo(null)` typically throws `NullPointerException`; the two behaviors do not contradict each other. Only support null in a dedicated `Comparator` when the business needs it, such as `Comparator.nullsFirst(...)`.

## 4. Complete Java 17 Example: One Key for All Three Mechanisms

Create the file **`BusinessContractDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class BusinessContractDemo {
    static final class Order implements Comparable<Order> {
        private final String tenantId;
        private final long orderNo;
        private final long totalCents;

        Order(String tenantId, long orderNo, long totalCents) {
            this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
            if (tenantId.isBlank() || orderNo <= 0 || totalCents < 0) {
                throw new IllegalArgumentException("Invalid order fields");
            }
            this.orderNo = orderNo;
            this.totalCents = totalCents;
        }

        long totalCents() {
            return totalCents;
        }

        String keyLabel() {
            return tenantId + "/" + orderNo;
        }

        String displayLabel() {
            return keyLabel() + "(" + totalCents + ")";
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Order that)) return false;
            return orderNo == that.orderNo
                    && tenantId.equals(that.tenantId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, orderNo);
        }

        @Override
        public int compareTo(Order other) {
            Objects.requireNonNull(other, "other");
            int byTenant = tenantId.compareTo(other.tenantId);
            if (byTenant != 0) return byTenant;
            return Long.compare(orderNo, other.orderNo);
        }
    }

    public static void main(String[] args) {
        Order first = new Order("shop-A", 42, 1500);
        Order snapshot = new Order("shop-A", 42, 1999);
        Order next = new Order("shop-A", 43, 1000);

        System.out.println("equals: " + first.equals(snapshot));
        System.out.println("hashCodes equal: "
                + (first.hashCode() == snapshot.hashCode()));
        System.out.println("compareTo zero: "
                + (first.compareTo(snapshot) == 0));
        System.out.println("distinct instances: " + (first != snapshot));

        Set<Order> hashed = new HashSet<>(List.of(first, snapshot, next));
        Set<Order> ordered = new TreeSet<>(List.of(first, snapshot, next));
        System.out.println("HashSet size: " + hashed.size());
        System.out.println("TreeSet size: " + ordered.size());
        System.out.println("TreeSet keys: "
                + ordered.stream().map(Order::keyLabel).toList());

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("BigDecimal equals: " + x.equals(y));
        System.out.println("BigDecimal compareTo zero: "
                + (x.compareTo(y) == 0));
        System.out.println("BigDecimal HashSet/TreeSet sizes: "
                + new HashSet<>(List.of(x, y)).size() + "/"
                + new TreeSet<>(List.of(x, y)).size());

        List<Order> display = new ArrayList<>(List.of(next, first));
        display.sort(
                Comparator.comparingLong(Order::totalCents)
                        .reversed()
                        .thenComparing(Comparator.naturalOrder())
        );
        System.out.println("Display by total: "
                + display.stream().map(Order::displayLabel).toList());
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac BusinessContractDemo.java
java BusinessContractDemo
```

Output:

```text
equals: true
hashCodes equal: true
compareTo zero: true
distinct instances: true
HashSet size: 2
TreeSet size: 2
TreeSet keys: [shop-A/42, shop-A/43]
BigDecimal equals: false
BigDecimal compareTo zero: true
BigDecimal HashSet/TreeSet sizes: 2/1
Display by total: [shop-A/42(1500), shop-A/43(1000)]
```

Explanation of the key parts:

1. `first` and `snapshot` are **two different objects**, with different total amounts, yet share the same key `shop-A/42`. Under the chosen model, `equals` must return `true`.
2. `hashCode` hashes only `tenantId` and `orderNo`. Because the two instances are business-equal, their hash codes are also equal.
3. `compareTo` compares tenant first, then order number; the same key yields 0. For orders with different keys, Java establishes a stable, transitive order.
4. `HashSet` uses hashing followed by `equals` to remove duplicates, while `TreeSet` uses `compareTo`; **both retain two orders**.
5. `BigDecimal` is a counterexample from the standard library: `1.0` and `1.00` are equal numerically under `compareTo`, but `equals` considers scale as well so it returns `false`. Thus `HashSet` keeps two elements, while `TreeSet` keeps one.
6. The final section **only sorts a `List` for display** in descending order of total amount. `thenComparing(Comparator.naturalOrder())` fixes the order when total amounts tie; this display comparator must not be blindly used as the identity rule for a `TreeSet`.

In the example, `totalCents` is `final` so the output stays deterministic. If this data can change in another object, it still must not participate in hashing or `TreeSet` key ordering when it is not part of the business identity.

## 5. Distinguishing Ordering Used for Deduplication from Ordering Used for Display

Many screens need sorting by "highest amount first", "most recently updated first", or "priority status first". Those are **presentation criteria**, distinct from the question "do two orders have the same identity?".

For the `Order` objects in section 4, the comparator below is suitable for sorting a `List<Order>` (illustrative snippet, not a standalone program):

```java
Comparator<Order> byAmountForDisplay =
        Comparator.comparingLong(Order::totalCents)
                .reversed()
                .thenComparing(Comparator.naturalOrder());
```

However, **do not use that comparator for a `TreeSet`** if the set needs to preserve the meaning "one element per order key". Two snapshots of the same order `shop-A/42` could have different total amounts, causing the display comparator to return non-zero even though `equals` is `true`.

Another mistake is comparing only by total amount:

```java
// Dangerous illustration if used as the comparator for TreeSet<Order>.
Comparator<Order> amountOnly =
        Comparator.comparingLong(Order::totalCents);
```

Two **orders with different keys** and the same total amount yield 0, so `TreeSet` treats them as duplicates and keeps only one. Adding a tie-breaker by key distinguishes different orders with the same total, yet **still does not guarantee** that two snapshots of *the same order* with different total amounts compare as 0. Therefore, if a sorted set must preserve business identity, compare **directly by the business key itself**.

| Scenario | Suitable Approach | What to Verify |
| --- | --- | --- |
| Lookup/deduplicate entities by business key | `HashSet`, `HashMap` with key-based `equals/hashCode` | Stable key, includes tenant, consistent `equals` and `hashCode` |
| Both ordered and deduplicated by business key | `TreeSet`, `TreeMap` comparing by the same key | `compare(a,b)==0` if and only if `a.equals(b)` |
| Display-only list sorted by amount/status/date | `List.sort(Comparator)` | Can differ from the `equals` model; define a tie-breaker if deterministic order is needed |
| Need to sort immutable values differently from entity identity | Separate list/view/model, or explicitly designed secondary index | Do not accidentally treat display order as the deduplication rule |

**Consequence for maps:** `HashMap` finds keys via hashing and `equals`; `TreeMap` determines equal keys via `compareTo` or its `Comparator`. If `compare` returns 0 for two keys that are unequal under `equals`, calling `put` with the second key in a `TreeMap` can overwrite **the value of the same entry**, even though `HashMap` would treat them as two separate keys. A `TreeMap` or `TreeSet` whose ordering is inconsistent with `equals` may still operate according to its comparator rules, but it does not fully satisfy the general `Map`/`Set` contract regarding equal elements/keys.

If a class has no **clear business natural order**, you may omit implementing `Comparable`. Use an explicit `Comparator` wherever ordering is needed, and carefully check consistency with `equals` if the comparator is used for identity in a sorted collection.

## 6. Why Are `BigDecimal` and Normalization Notable Cases?

In Java, `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0` because they have the same numeric value, yet `equals` is `false` because their representations have **different scales**. This is a famous case where natural ordering is inconsistent with `equals`.

Therefore, if **money** is part of a value object's identity, define equality explicitly:

- If `1.0` and `1.00` **must represent the same business value**, normalize them to a consistent representation before storing in the value object; for example, store `long cents` when the currency always uses two decimal places, or normalize `BigDecimal` according to an agreed scale/currency rule.
- If **scale has business meaning** (declared precision or raw input), `BigDecimal.equals` may be right for that value object; in that case, `BigDecimal.compareTo` alone cannot preserve the exact same equivalence classes.
- Do not arbitrarily call `stripTrailingZeros()` or `setScale(...)` without a domain rule: you must account for negative scales, rounding, and currency units.

Once normalized, **every path creating the value** (constructors, parsers, mappers, data from DB/API) must apply the same rule. Do not apply a band-aid fix by ignoring scale only in `equals` while keeping the default `hashCode` on an unnormalized `BigDecimal`.

With `String`, two codes differing in letter case, Unicode normalization, or whitespace can also cause disagreement if one method compares more "leniently" than another. Use key values that have been uniformly canonicalized.

## 7. Designing Immutable Keys and Avoiding the Trap of Mutating While in a Collection

Suppose `Order` uses `status` in `hashCode` and is added to a `HashSet`. After changing the status, the hash code computed from the new status may no longer match the old bucket; `contains(order)` or `remove(order)` may fail to find the very element that was added.

Similarly, when the ordering of `compareTo` or a `TreeSet` comparator depends on a mutable field that is modified externally, the tree structure does not automatically re-sort itself. `contains`/`remove` operations, iteration order, or consistency can break.

Therefore:

1. Choose a **stable business key** across the entity lifecycle; for entities not yet assigned an ID by the database, clearly define the phases before/after ID generation and avoid using a changing key inside hash/sorted collections.
2. Prefer `final` fields or immutable value objects as keys, ensuring nested mutable classes inside the key cannot be modified through another reference.
3. Mutable attributes such as total amount, status, and update time should be data only; to re-rank by them, **re-sort the list** or rebuild the appropriate index structure.
4. Do not use `System.identityHashCode`, `==`, or memory addresses in place of business identity, unless the business intentionally defines equality as **JVM object identity**.
5. If using a natural key like `email`, check whether email can change or be reused in the business domain. If so, a stable ID is usually better suited for entity identity.

`hashCode` is not a unique constraint in the database. Critical data still needs a **constraint/unique index** in the storage system; having a correct `equals` within one JVM does not prevent two separate transactions from creating records with duplicate keys.

## 8. Applying This to Records, Composite Values, and Inheritance

**Record:** Java 17 provides `record` and auto-generates `equals`/`hashCode` over all record components, but **does not auto-generate `Comparable.compareTo`**. Records are well suited to encapsulating an immutable business key:

```java
// Illustrative snippet independent of the Order class in section 4.
record OrderKey(String tenantId, long orderNo)
        implements Comparable<OrderKey> {
    @Override
    public int compareTo(OrderKey other) {
        int c = tenantId.compareTo(other.tenantId);
        return c != 0 ? c : Long.compare(orderNo, other.orderNo);
    }
}
```

When all components of `OrderKey` are normalized and have compatible semantics between `equals` and `compareTo`, a record keeps that contract concise. A record itself only makes **field references final**, and does not automatically make mutable objects inside immutable; do not put a mutable `List` or an unguarded mutable object into a business key.

**Inheritance:** if a superclass and subclass each add identity fields in different ways, `equals` can lose symmetry, and `compareTo` may fail to handle subtypes properly. For business keys used in sets/maps, prefer an immutable final/record key type or a clear type/equality policy applied across the entire hierarchy. Whether to use `getClass()` or `instanceof` must follow the contract; for instance, using `final class Order` prevents subtypes from unilaterally extending identity.

**Technical ID vs. business key:** if `OrderKey` is `tenantId + orderNo`, agree on whether this identifier is database-generated or already exists in the domain. When the ID does not yet exist, do not implicitly use temporary fields in `equals` and then switch to the ID upon persisting without accounting for the impact on collections holding the element.

## 9. Test Matrix for the Identity Contract

Example test data for `Order`:

| A | B | `A.equals(B)` | `A.hashCode()==B.hashCode()` | Sign of `A.compareTo(B)` |
| --- | --- | --- | --- | --- |
| `shop-A/42, 1500` | `shop-A/42, 1999` | `true` | **Must be true** | `0` |
| `shop-A/42, 1500` | `shop-A/43, 1500` | `false` | Unspecified | Negative |
| `shop-A/42, 1500` | `shop-B/42, 1500` | `false` | Unspecified | Negative |
| `shop-B/42, 1500` | `shop-A/42, 1500` | `false` | Unspecified | Positive |

**Do not assert "different hashes" for unequal pairs:** distinct hash codes are not a mandatory invariant, and hash collisions are normal.

A testing checklist capable of catching real bugs:

- **Reflexivity/symmetry/transitivity:** same object, two snapshots, three snapshots with the same business key; `equals(null) == false`.
- **Hash function:** every pair with `equals == true` must have equal `hashCode`; changing `totalCents` on another snapshot does not affect the key's hash.
- **Ordering:** `compare(a,b)==0` if and only if `a.equals(b)` under this model; reversing arguments flips the sign, and ascending key triples preserve transitivity.
- **Collections:** inserting the same data into `HashSet` and `TreeSet` must yield the same number of **business keys**; `HashMap` and `TreeMap` must look up the same business key under a unified policy.
- **Tenant isolation:** same `orderNo` with different `tenantId` must not be treated as duplicates.
- **Boundary data:** null, empty strings, negative/0 IDs, large numeric values; use `Long.compare` to avoid overflow instead of subtraction.
- **Normalization:** different representations that the domain treats as the same key must be normalized to the same form across all object-creation paths.
- **State changes:** changing non-key attributes does not alter the set of entities recognized by `equals`, `hashCode`, or `compareTo`.

These checks are better than merely running an IDE-generated `equals` test on an object with all identical fields: they verify the **identity boundary** chosen by the business domain.

## 10. Real-World Mistakes to Avoid

1. **Choosing fields independently for the three methods:** `equals` by ID, `hashCode` by all fields, `compareTo` by price. As a result, each collection has a different notion of "duplicate".
2. **Using subtraction in comparisons:** `return (int) (a.orderNo - b.orderNo);` can overflow or lose bits. Use `Long.compare(a.orderNo, b.orderNo)`.
3. **Thoughtlessly adding a tie-breaker to a `TreeSet` comparator:** adding `totalCents` makes sorting look nicer, yet can cause two snapshots with the same ID to compare as non-zero. Keep the identity comparator separate from display comparators.
4. **Forgetting composite keys that include tenant:** two orders with matching `orderNo` across tenants are accidentally merged into one.
5. **Putting mutable fields into hash/order:** modifying them after adding to a `HashSet`/`TreeSet` can make lookup/remove operations unreliable.
6. **Assuming `compareTo()==0` always implies `equals()==true` in every library:** `BigDecimal` is a counterexample; understand semantics before using a type as an ordered key.
7. **Assuming records auto-generate every contract:** records auto-generate `equals` and `hashCode` but do not automatically provide ordering; mutable components can also break key stability.
8. **Using a display comparator as the uniqueness rule:** sorting by price or update time is suitable for lists; sorted sets/maps need duplicate semantics matching business intent.
9. **Choosing an unstable key before an entity has an ID:** changing identity while already inside a map/set can cause hard-to-find bugs; design the key lifecycle upfront.

**Guiding principle:** first define one exact business identity model. For the `Order` entity in this article, matching `tenantId + orderNo` must be **equal via `equals`**, **have the same hash code**, and **compare as 0** under the ordering used for `TreeSet`/`TreeMap`. Any ordering for UI or reporting is expressed via separate comparators on lists; never let a display criterion accidentally alter the meaning of "the same entity".