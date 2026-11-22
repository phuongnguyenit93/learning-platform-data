# Choosing Core, Derived, and Cached Data When Designing `equals()` and `hashCode()`

## 1. Why Must Data Be Classified Before Defining "Equality"?

Two Java objects can store many fields, yet **not every field determines whether the two objects are considered the same value or the same entity**. When overriding `equals(Object)`, the first step is to answer the business question:

> In this context, changing which information will cause two objects to **no longer be considered equal**?

Only after answering do we choose which fields to compare. The answer cannot be deduced mechanically from the number of fields, from a variable named `id`, or from whether a field is declared `final`.

A model typically has three kinds of data:

1. **Core data for equality** (*equality-defining state*): information that directly defines the chosen equality criterion. If this information differs, two objects may no longer be equal.
2. **Derived data** (*derived/computed data*): results that can be recomputed from other data, such as a display name concatenated from first and last name, a label combined from product code and description, or a total price computed from quantity and unit price. Derived values may be meaningful to the application, yet usually **do not need to be compared redundantly** if all of their inputs are already compared.
3. **Cached data** (*cached/memoized data*): computed results stored to avoid repeated work, such as a generated label, parsed result, precomputed hash code, or lazily loaded lookup data. A cache must reflect the source state; whether the cache is populated or not usually **does not change equality semantics**.

"Core" here means **core to the equality relation being designed**, not that all other data is useless. A field can be essential for display, invoicing, or auditing while still being excluded from `equals`.

## 2. Deciding the Semantics: Same Entity or Same Value?

There is no single `equals` field list shared across all classes. Two common design styles are:

| Equality relation | Question | Typical fields considered | Example |
| --- | --- | --- | --- |
| **Entity identity** – same entity | Is this the same entity in the business domain? | Stable identifier, unique within the appropriate scope | Two `Customer` objects with the same `customerId` are considered one customer, even if the display name changes. |
| **Value equality** – same value | Do two objects represent the same defined value? | Components that determine the entire value | Two `Money` objects are equal when they have the same amount and currency according to domain conventions. |

For example, two product records with the same SKU but different descriptions **can** be considered the same entity if SKU is the stable identifier. Conversely, if the class represents a *snapshot of a product description* and requires all attributes constituting the snapshot to match, ignoring the description would be inappropriate.

The deciding condition is **business domain semantics**, not “every class with an ID only compares the ID”. For an entity not yet assigned an ID (such as an ORM entity before persistence), the ID may still be `null` or change across its lifecycle; using it in equality requires an explicit policy to avoid treating two new entities as equal merely because both have `null`.

### Four Questions Before Choosing Fields

1. What do users or APIs consider two objects to be **the same thing**: same user, same monetary amount, same record, or same current state?
2. Is there a **stable identifier** field? Is that identifier guaranteed unique within the scope under consideration?
3. Which fields are merely **functions of other fields**, or differ only because they have not been computed/cached yet?
4. Which fields **can change after the object is used as a key** in a `HashMap` or an element in a `HashSet`?

If the semantics have not been determined yet, do not write `equals` by automatically comparing every field listed by the IDE.

## 3. Field Classification Table in a Concrete Model

Suppose a system has an `InventoryItem` class and the business rule is: **a normalized SKU uniquely identifies an item**. The following fields play different roles:

| Field | Example | Role | Participates in SKU-based equality? |
| --- | --- | --- | --- |
| `sku` | `"AB-12"` | Normalized core identifier | **Yes** |
| `description` | `"Bút màu xanh"` | Editable descriptive information | **No**, under the rule that same SKU means same item |
| `displayLabel` | `"AB-12 - Bút màu xanh"` | Data derived from SKU and description | **No** |
| `cachedLabel` | Precomputed `displayLabel` string | Cache of derived data | **No** |
| `lastViewedAt` | Timestamp when UI read the info | Operational or observational metadata | **No** |

This table holds **only under the stated SKU contract**. If an `ItemSnapshot` class instead defines “equal when all attributes of the snapshot are identical”, then `description` could be a core component and must be included. What matters is modeling the policy before writing code.

Specifically:

- Derived data **is not automatically meaningless data**: an aggregated value might be the canonical form stored exclusively in the system, in which case it can also be core data.
- Cached data may store the result of a function belonging to equality itself, such as a precomputed hash code. However, **whether the “cache is empty or populated”** does not create a difference in value.
- The Java keyword `transient` relates only to Java's default serialization mechanism for the field; it **does not automatically exclude a field from `equals`**. Conversely, a field not declared `transient` does not necessarily have to participate in equality.

## 4. Java 17 Example: Description and Cache Change, Identity Does Not

The following example defines `InventoryItem` with a stable SKU. The label string is computed from SKU and description, then cached. When the description updates, the cache is cleared for recomputation. Because this model's equality considers only SKU, `equals` and `hashCode` do not depend on description or cache.

```java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class EqualityStateDemo {
    static final class InventoryItem {
        // Core data for equality: normalized, immutable SKU.
        private final String sku;

        // Descriptive data: useful, but does not determine SKU-based identity.
        private String description;

        // Memoized/cached data: can be discarded and recomputed.
        private String cachedLabel;

        InventoryItem(String rawSku, String description) {
            String normalized = Objects.requireNonNull(rawSku, "sku")
                    .trim()
                    .toUpperCase(Locale.ROOT);
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("SKU must not be blank");
            }
            this.sku = normalized;
            this.description = Objects.requireNonNull(description, "description");
        }

        String displayLabel() {
            if (cachedLabel == null) {
                cachedLabel = sku + " - " + description;
            }
            return cachedLabel;
        }

        void updateDescription(String description) {
            this.description = Objects.requireNonNull(description, "description");
            cachedLabel = null; // Invalidate cache when input changes.
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof InventoryItem that)) {
                return false;
            }
            return sku.equals(that.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }
    }

    public static void main(String[] args) {
        InventoryItem first = new InventoryItem(" ab-12 ", "Tên cũ");
        InventoryItem second = new InventoryItem("AB-12", "Tên khác");

        Set<InventoryItem> items = new HashSet<>();
        items.add(first);

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(items.contains(second));
        System.out.println(first.displayLabel());

        first.updateDescription("Tên mới");
        System.out.println(first.displayLabel());
        System.out.println(items.contains(first));
        System.out.println(items.contains(second));
    }
}
```

Save the file `EqualityStateDemo.java` as UTF-8 and run:

```bash
javac -encoding UTF-8 EqualityStateDemo.java
java EqualityStateDemo
```

Output:

```text
false
true
true
true
AB-12 - Tên cũ
AB-12 - Tên mới
true
true
```

**Explanation:**

- `first == second` is `false` because two `new` calls create two distinct objects.
- `first.equals(second)` is `true` because the input `" ab-12 "` is normalized to `"AB-12"` and shares the same SKU as the second object.
- Two equal objects produce the same `hashCode`, so `HashSet` can look up `second` after adding `first`.
- The first `displayLabel()` call generates and stores `"AB-12 - Tên cũ"`. After `updateDescription`, the old cached value is invalidated, and the new label is `"AB-12 - Tên mới"`.
- `contains` results remain accurate because **there is no change to `sku`**, the sole field determining equality and hash.

This is a single-threaded example. Because `description` and `cachedLabel` mutate without synchronization, **do not infer** that this caching approach is safe if the object is shared across multiple threads. If concurrent access is needed, a separate synchronization/memory-visibility mechanism must be designed; that requirement is independent of field selection for equality.

## 5. Derived Data: Compare the Source or Compare the Result?

Suppose a user has `firstName` and `lastName`, while `fullName` is simply a string concatenated from those two fields. If the equality relation is “same name pair as currently stored”, comparing `firstName` and `lastName` is sufficient. Comparing `fullName` as well is redundant, and can cause bugs if a cache has not been refreshed.

However, **not every piece of derived data can substitute for its source**:

- Two pairs `("An", "Binh")` and `("An Binh", "")` can produce the same display string under one concatenation scheme, yet do not necessarily represent the same name-pair value. If equality is based on **the component pair**, comparing only `fullName` is semantically wrong.
- A total price may be computed from unit price × quantity, yet also depend on rounding rules, taxes, and exchange rate timing. If inputs or calculation policies differ, having the same rounded total does not necessarily mean the same business object.
- Derived data that depends on the current clock, configuration, or external services can change **even when the object's underlying data does not**. For instance, age calculated from birth date changes over time; “today's age” should not be used as a hash component of a long-lived key.

A practical rule: **compare a stable dataset that is sufficient to distinguish according to the defined semantics**. If two equal components always yield the same derived result, there is no need to additionally use the derived result to prove equality. If the derived result carries separate information or constraints, bring that information into the model specification and evaluate it directly.

## 6. Cache Is a Performance Mechanism, Not Business Truth

A cache is a copy or intermediate result; it may appear after the first read, be cleared on update, or be rebuilt after deserialization.

### Mistake: Including Cache State in `equals`

The snippet below illustrates **an incorrect design** inside a class having `sku` and `cachedLabel`:

```java
// Wrong if cachedLabel is only a memoized result.
@Override
public boolean equals(Object other) {
    return other instanceof InventoryItem that
            && Objects.equals(sku, that.sku)
            && Objects.equals(cachedLabel, that.cachedLabel);
}
```

Two objects with the same SKU could differ solely because one has called `displayLabel()` and the other has not. Then **reading the display label** can alter equality results, even though no real change in identity occurred. If `hashCode` also includes the cache, the hash code can change after the first label computation, making use of the object as a hash key unstable.

To avoid this bug, choose the source fields for `equals` and `hashCode`; if you need to cache the `hashCode` result itself, do so only when all data the hash depends on is guaranteed immutable, and also address concurrency when multiple threads are involved.

### When Can a Cache Be Part of Equality?

When a field that appears to be a “cache” actually holds state **committed as part of the value** and cannot be derived from the remaining fields, revisit its name and the model. It is no longer purely a cache in the sense of “discard and recompute without losing information”. Classify by **role and semantics**, not by variable name.

## 7. Consequences of Mutable State for `HashSet` and `HashMap`

The `Object` contract requires:

- `equals` must be reflexive, symmetric, transitive, consistent when the information used for comparison does not change, and return `false` for `null`.
- If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must hold.
- There is no requirement that two **unequal** objects have different hash codes; hash collisions are permitted.

This raises an issue: if a field **participating in equality** is modified after the object is already inside a `HashSet` or used as a `HashMap` key, lookups may no longer find the element as expected.

Illustrative example of the hazardous case (code snippet is not a standalone program):

```java
// Suppose class MutableKey has equals/hashCode based on code.
MutableKey key = new MutableKey("A");
Set<MutableKey> set = new HashSet<>();
set.add(key);
key.setCode("B"); // Changes hash-based lookup information of the stored key.
// set.contains(key) may no longer behave as expected at this point.
```

Do not turn the example result into a claim that `contains` *always* returns `false`: observed behavior also depends on before/after hash codes, buckets, and implementation. The issue is that **there is no longer any basis to rely on lookup working correctly as with an immutable key**.

For `InventoryItem` in the runnable example above, changing `description` does not affect the contract because that field does not participate in equality. Conversely, if `sku` could be changed, the risk would arise. That is why `sku` is declared `final` and normalized right in the constructor.

**Immutability in the sense of equality does not require every attribute of an object to be immutable.** Only the data determining equality and hash needs to remain stable throughout the required lifecycle; in practice, immutable value objects are usually simpler and safer.

## 8. Notes on Normalization, Nested Structures, and `record`

### 8.1. Input Normalization

Two strings `"ab-12"` and `"AB-12"` are considered the same SKU only if business rules recognize case-insensitivity. The example chose `trim()` and `toUpperCase(Locale.ROOT)`; this is **a model policy**, not a Java rule applying to every identifier.

Do not automatically normalize every field: usernames might be case-sensitive, product codes might preserve meaningful spaces, and Unicode or natural-language rules may need specialized handling. If normalization determines equality, perform it consistently at the object creation boundary or apply the same consistent rule in both `equals` and `hashCode`.

### 8.2. Nested Objects and Arrays

If a value object's equality depends on a list or array, decide whether to compare by **contents**, order, or container identity. For Java arrays, inherited `Object.equals` compares by reference; `Arrays.equals`, `Arrays.deepEquals`, and the corresponding hash functions may be needed. If a mutable array is stored in a `final` field, the `final` keyword only prevents reassigning the reference; **array elements can still be modified**. Consider a defensive copy or immutable structure if the array participates in equality.

Similarly, if `equals` inspects fields inside a mutable child object, having all `final` fields on the parent object still does not guarantee stable equality.

### 8.3. Java `record`

A Java 17 `record` automatically generates `equals`, `hashCode`, and `toString` based on its record components. That is suitable when every chosen component belongs to the value to be compared.

```java
record Money(long cents, String currency) {}
```

This snippet illustrates a type declaration; it can be placed at the top level in an appropriate Java file. Under the policy “cents and currency together determine the value”, both components are meaningful for equality. Avoid adding `cachedDisplayText` as a component merely to hold a cache: it will by default participate in the auto-generated methods unless behavior is explicitly overridden by design. Using `record` also does not automatically make mutable objects passed into components deeply immutable.

### 8.4. ORM and Entity Lifecycle

In database-persisted entity models, IDs generated after saving, proxies, the same entity across different sessions, and transient states can all affect how `equals`/`hashCode` should be chosen. Do not mechanically apply the “use ID in `equals`” example to an entity without an assigned ID or whose ID can change. You must clearly determine when the ID stabilizes, the semantics while the ID is still `null`, and the requirements of the framework in use.

## 9. Practical Workflow for Choosing the Right Equality Data

Before writing `equals` and `hashCode`, clarify step by step:

1. **State it in one sentence:** “Two objects of type X are equal when …”. This sentence must use business language, without relying on specific field names unnecessarily.
2. **List the fields:** mark which fields directly determine equality, which are derived, and which are caches or operational metadata.
3. **Check sufficiency and minimality:** could two states differing in core data ever be mistaken as equal? Are you redundantly comparing results completely derivable from already-checked fields?
4. **Check mutability:** can the data participating in equality mutate? If so, is the class used as a key in hash collections?
5. **Ensure `hashCode` compatibility:** every equal pair must share the same hash code; also choose an appropriate hash distribution to avoid unnecessary collisions.
6. **Evaluate edge cases:** `null`, objects of different types, inheritance, proxies, arrays, Unicode/normalization values, unassigned-ID states, and concurrency if applicable.
7. **Test read and cache scenarios:** create two objects with the same core but different caches; invoke methods that compute derived data, clear/rebuild the cache, and mutate non-equality data. `equals`/`hashCode` results must hold according to the declared semantics.

### Test Matrix for the SKU-Identifier Model

| Scenario | Expectation |
| --- | --- |
| Two objects with the same SKU after normalization, different descriptions | `equals == true`; equal hashes |
| Two objects with different SKUs | `equals == false`; hashes **may** collide |
| One has not populated the label cache, the other has | Equality unchanged |
| Update description and invalidate cache | Equality/hash unchanged |
| Compare with the object itself | `true` |
| Compare with `null` | `false` |
| Compare with an object of a different type | `false` |

Tests must assert **contract behavior**, not assert that hashes of any two different SKUs differ or inspect the bucket structure of `HashSet`.

## 10. Practice Scenarios

**Scenario A:** An `OrderLine` has `productId`, `quantity`, `unitPrice`, `totalPrice = quantity × unitPrice`, and `cachedFormattedTotal`. The requirement is to compare **the value of an order line** by product, quantity, and unit price. How should equality data be selected?

**Suggested answer:** Consider `productId`, `quantity`, and `unitPrice` according to the defined value representation/semantics. `totalPrice` is derived from the two already-considered numbers so it needs no repetition; `cachedFormattedTotal` is only a display cache and does not participate. If unit price or quantity can be edited, avoid using this mutable object directly as a long-term hash key or design an immutable snapshot.

**Scenario B:** A `Session` has `sessionId`, `lastAccessedAt`, and `cachedPermissions`. The system specifies that the same `sessionId` means the same session. An access updates `lastAccessedAt` and reloads permissions. Should `equals` change?

**Suggested answer:** No, if `sessionId` is truly an immutable identifier within the comparison scope. The other two fields are operational metadata/cache under this model. Of course, having the same session ID does not by itself confirm that both permission caches are still valid; session validity is a separate problem from equality.

**Scenario C:** A `Point` stores `x`, `y`, and caches `distanceFromOrigin`. Two points are considered equal when their coordinates match. Should the cached distance be compared?

**Suggested answer:** No. Two points with different coordinates can have the same distance to the origin; moreover, the cache might not yet be computed. `x` and `y` are the sufficient data to determine equality. If coordinates can be modified, the cache must be invalidated and the risks of using `Point` as a key must be considered.

## 11. Takeaways

- **Choose semantics first, fields second.** “Core data” is the set of fields determining the equality relation, depending on whether entities or values are being compared.
- **Derived data** usually does not need to be compared if it is completely determined by the core dataset already examined; avoid using a lossy representation alone in place of the source.
- **Caches** are usually omitted from equality because computed/uncomputed state does not change the object's essence. Caches must have an invalidation policy when sources change.
- **`equals` and `hashCode` must follow the same equality relation**: equal ⇒ same hash; the converse is not required.
- **Stability in hash collections**: avoid mutating data participating in equality/hash after inserting the object into a `HashSet` or using it as a `HashMap` key.
- **Do not equate keywords `final`, `transient`, field name `id`, or `record` with the equality decision**: you must understand the actual meaning and lifecycle of the data.

Official specification references: [`Object.equals` and `Object.hashCode` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), [`HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [`Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).