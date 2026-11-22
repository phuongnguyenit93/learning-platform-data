# Documenting Comparison Fields and Intentional Exclusions

When defining `equals(Object)` and `hashCode()` for a Java class, the most important decision is: **which attributes make two objects count as the same value according to the business domain's semantics?** This decision must be written down explicitly as a contract; simply reading lines of `Objects.equals(...)` is rarely enough for users of the class to understand why a field was included or excluded.

In this topic, "intentional exclusion" (or "intentional exception") means **a field deliberately omitted from comparison**, or a choice departing from common intuition that has been weighed and documented. It does not refer to Java's `Exception`-throwing mechanism.

## 1. Start From the Business Domain's Definition of Equality

Before listing fields, answer two questions:

1. **Can two different objects be considered the same entity/value?** For example, two copies of a product with the same code in the same store may represent the same item, even if their display names and stock quantities differ.
2. **Which changes alter that identity?** If the product code or owning store changes, it is no longer the same item; if only the display name is edited, it is still that item.

There are two common perspectives:

- **Value equality:** compares a combination of meaningful components, such as currency code and amount for a monetary value. Every component that contributes to defining the value must be considered.
- **Business identity:** compares a stable business key, such as `(tenantId, sku)`. Attributes that can be updated later do not necessarily belong to the identity key.

No rule like "put every field into `equals`" or "use only `id`" holds true for every class. Field names, annotations, declaration order, and whether a field is a database key **do not automatically decide** the domain's equality semantics.

## 2. Explicitly State Which Fields Participate and Which Are Excluded

Suppose a `Product` class describes an item across multiple stores, where each store may reuse the same SKU string. We choose **the identity key as the pair `(tenantId, sku)`**.

| Field | Participates in `equals/hashCode`? | Reason and Rule |
| --- | --- | --- |
| `tenantId` | **Yes** | Distinguishes two stores using the same SKU code; immutable after creation. |
| `sku` | **Yes** | Unique code within the scope of `tenantId`; immutable after creation. |
| `displayName` | **No, intentionally excluded** | Display name can be changed, translated, or typo-corrected without turning the item into a different business object. |
| `stock` | **No, intentionally excluded** | Stock fluctuates with transactions; changing stock does not change the identity key. |

Alongside this table, the contract documentation should state assumptions that could cause misunderstandings:

- `tenantId` and `sku` must not be `null`; keys are compared **case-sensitively**. `"SKU-7"` differs from `"sku-7"` because the example does not auto-normalize.
- The key pair must be unique within the business domain under consideration; having two objects with the same key and different states is **acceptable in this model**.
- Do not change the key after placing the object into a `HashMap` or `HashSet`. In the example, both key components are `final`.
- `displayName` and `stock` are excluded **from both `equals` and `hashCode`**. Including a field in one while omitting it from the other breaks the requirement that equal objects must have the same hash code.

## 3. Javadoc Right Next to Implementation and a Runnable Example

The class description should sit close to the code so maintainers see the contract when modifying `equals` or `hashCode`. The following Java 17+ program illustrates a complete way to write it.

Save as **`EqualityContractDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class EqualityContractDemo {
    public static void main(String[] args) {
        Product first = new Product("shop-a", "SKU-7", "Mechanical Keyboard", 3);
        Product sameKey = new Product("shop-a", "SKU-7", "Keyboard", 0);
        Product otherShop = new Product("shop-b", "SKU-7", "Mechanical Keyboard", 3);

        System.out.println("same key: " + first.equals(sameKey));
        System.out.println("same hash: " + (first.hashCode() == sameKey.hashCode()));
        System.out.println("different shop: " + first.equals(otherShop));

        Map<Product, String> approved = new HashMap<>();
        approved.put(first, "approved");
        System.out.println("lookup same key: " + approved.get(sameKey));

        first.rename("New name");
        first.setStock(0);
        System.out.println("lookup after updates: " + approved.get(first));
    }

    /**
     * Item identified by (tenantId, sku).
     *
     * <p>Participating fields: tenantId and sku; both are non-null,
     * immutable, and compared case-sensitively.
     *
     * <p>Intentional exclusions: displayName and stock, because changes
     * to presentation/inventory do not alter the item's identity.
     * hashCode uses the exact same two fields that participate in equals.
     *
     * <p>Final class: subclasses cannot extend the identity rules.
     */
    static final class Product {
        private final String tenantId;
        private final String sku;
        private String displayName;
        private int stock;

        Product(String tenantId, String sku, String displayName, int stock) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.sku = Objects.requireNonNull(sku);
            this.displayName = Objects.requireNonNull(displayName);
            this.stock = stock;
        }

        void rename(String name) {
            displayName = Objects.requireNonNull(name);
        }

        void setStock(int quantity) {
            stock = quantity;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Product other)) {
                return false;
            }
            return tenantId.equals(other.tenantId)
                    && sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, sku);
        }
    }
}
```

Compile and run:

```bash
javac EqualityContractDemo.java
java EqualityContractDemo
```

Output:

```text
same key: true
same hash: true
different shop: false
lookup same key: approved
lookup after updates: approved
```

**Explanation:** `first` and `sameKey` share the same two key fields—even though `displayName` and `stock` differ—so `equals` returns `true` and their `hashCode` values match. `otherShop` has a different `tenantId`, so it is not equal to `first`. `HashMap` finds the value via an equivalent key, and mutating the excluded fields does not alter `first`'s hash code.

The line `same hash: true` illustrates the mandatory direction of the contract: **if `a.equals(b) == true`, then `a.hashCode() == b.hashCode()`**. The converse is **not required**: two unequal objects can still share a hash due to collisions.

The example intentionally uses `final class` to prevent subclasses from adding fields to `equals` and breaking symmetry with the superclass. If a design permits inheritance, the comparison policy across types must be specified and verified separately.

## 4. Exclusion Decisions Must Have Verifiable Reasons

Do not write `// ignore stock` without explaining the consequences. Good documentation follows **decision → business domain rationale → verification scenario → consequence**.

### Excluding Frequently Changing Fields

For example, `stock` changes every minute while the item retains `(tenantId, sku)`. Putting `stock` into `hashCode` can cause the key to be "lost" after the object is placed into a `HashMap` or `HashSet`. State clearly: "Stock is transient state; intentionally excluded from identity and may be modified while the object serves as a collection key."

However, if the class actually represents an **inventory snapshot record**, quantity may be part of the value. In that case, change the definition and documentation rather than mechanically copying `Product`'s rules.

### Excluding Technical, Derived, or Associative Fields

Some classes carry update timestamps, computed labels, caches, or back-links to other objects. If these fields do not constitute the value/identity, they can be excluded, provided the documentation explains **why differing values are still considered equal**.

For example: `lastViewedAt` is a UI marker and does not change item identity. Conversely, `currency` generally cannot be excluded when comparing monetary values, because `100 USD` and `100 VND` are not the same value.

### Keys Assigned After Object Creation

An auto-generated database key may initially be `null` and assigned upon saving. If you choose this key for identity, clarify how unsaved objects are compared, when the hash value changes, and whether storing them in hash collections is safe. **Do not arbitrarily conclude that two objects with `id == null` are equal.** Rules for ORM entities also depend on lifecycle and proxies; design and document them separately before implementing.

### Normalizing Values During Comparison

If the business treats `"SKU-7"` and `"sku-7"` as the same code, clearly define the **normalization point** (such as inside the constructor via `toUpperCase(Locale.ROOT)`), whitespace rules, locale, and `null` handling. `equals` and `hashCode` must use the same normalized value. Do not merely use `equalsIgnoreCase` in `equals` while hashing the original string case-sensitively.

## 5. Java Contracts That Must Be Preserved

Documenting participating comparison fields requires checking these properties of `equals`:

- **Reflexive:** for a non-`null` object, `x.equals(x)` is `true`.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` return the same result.
- **Transitive:** if `x` equals `y` and `y` equals `z`, then `x` equals `z`.
- **Consistent:** when information used for comparison does not change, repeated calls return the same result.
- **Against `null`:** `x.equals(null)` is `false`.

For `hashCode`: two equal objects must return the same hash value; repeated calls on the same object must remain stable while data participating in `equals` does not change. Hashing **does not need to be unique** across distinct objects.

Arbitrarily adding or removing a field in `equals` can change the behavior of `Set.contains`, `Map.get`, caches, grouping/deduplication, and test outcomes. Such a change must be treated as a **contract change impacting callers**, not merely an internal optimization.

## 6. Decision Template and Review Checklist

You can use the following short structure in Javadoc or design docs to keep decisions consistent:

```text
Equality definition:
  Two Product instances are equal when they have the same tenantId and sku.

Participating fields:
  tenantId, sku — non-null, immutable, case-sensitive.

Intentional exclusions:
  displayName — presentation changes do not alter identity.
  stock       — inventory updates do not alter identity.

Boundaries:
  Applies to final Product; does not imply two snapshots have identical content.

Consequences:
  Changing displayName/stock does not affect equals/hashCode.
  Changing tenantId/sku requires a different business key object.

Cases to test:
  Same key/different state; different tenant/same SKU;
  comparison with null; three objects with the same key; HashMap lookup.
```

When reviewing an implementation, verify the following points:

1. **Equality is defined in business domain language**, instead of merely describing "compares two fields".
2. **Every significant field is classified**, especially fields that might seem required for comparison but are intentionally excluded.
3. **`equals` and `hashCode` use the same combination of fields**, upholding reflexivity, symmetry, transitivity, and consistency.
4. **Key immutability is guaranteed or its limits are explicitly stated**, especially if the object is used as a hash collection key.
5. **Policies for `null`, normalization, case sensitivity, and inheritance are published** if they affect results.
6. **Examples or tests exist for exclusion choices**, such as same identity with differing stock still being equal; do not only test two objects with all identical fields.
7. **If using a `record`**, remember that default `equals/hashCode` generated by a record inspect all record components; if exclusions are desired, reconsider the record model or deliberately redefine and document the change.

**Remember:** the field names present in `equals`/`hashCode` only show *how the code runs*; documentation of chosen fields, intentional exclusions, and immutability constraints explains *why that is the right contract*.