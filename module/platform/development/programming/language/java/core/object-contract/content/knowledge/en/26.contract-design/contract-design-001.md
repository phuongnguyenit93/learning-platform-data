# Defining the Meaning of Equality Before Generating Code (Java)

**Topic: Object Contract Design.** Before letting the IDE generate `equals()` and `hashCode()` methods, and before choosing Lombok or a Java `record`, the critical question is: **when are two objects considered equal in the business domain?** Generated code can compile cleanly yet still reflect the wrong meaning if the wrong fields are chosen.

## 1. Three Types of Equality to Distinguish

| Concept | Question | Common Java Representation | Example |
| --- | --- | --- | --- |
| **Reference identity** | Do two references point to the same instance? | `a == b` | Two variables referencing the same object |
| **Value equality** | Do two instances represent the same value? | `equals()` based on value components | Two coordinates with the same x/y |
| **Entity identity** | Do two instances represent the same entity over time? | `equals()` based on a stable ID or using reference identity depending on the model | The same customer before/after a name change |

And **comparison by order or by a specific criterion** such as price, creation date, or approximate proximity usually has a separate API: `Comparator`, `compareTo()`, or a dedicated method. Do not arbitrarily turn secondary criteria into default equality.

For reference types, `==` asks whether two variables hold *the same instance*; `equals()` uses the class's rule. For primitives, `==` compares primitive values. If a class does not override `Object.equals()`, default equality is also reference identity.

~~~java
String a = new String("Java");
String b = new String("Java");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Not every class needs to override `equals()`. A request context, controller, or resource holder can reasonably keep reference identity. For a value object, content comparison is usually needed; for an entity, stable identity across its lifecycle is usually needed.

## 2. Write the Contract in Words Before Choosing Fields

Write a sentence that can be put into a test:

> Two `ProductKey` instances are equal when they have the same `sku` and the same `market`, with case-sensitive comparison.

> Two `Customer` instances are equal when they have the same immutable `customerId`, even if the display name changes.

Then answer in order:

1. **Is this a value object, an entity, or an object compared by reference?**
2. **Which fields actually participate in equality?** Do not confuse identifiers with descriptions, timestamps, caches, display states, or computed results.
3. **Can those fields change?** If used as a `HashMap` key or `HashSet` element, the data determining equality/hash must remain stable while inside the collection.
4. **Is data normalization needed?** Two codes differing in letter case, two `BigDecimal` numbers differing in scale, strings with accents/whitespace, or currency codes need specific domain rules.
5. **What if the ID has not been assigned yet?** Two new entities both with `id == null` are not automatically the same entity.
6. **Are there subclasses, ORM proxies, collections, arrays, or circular references?** They affect symmetry, stability, cost, and recursion.
7. **Are there multiple comparison purposes?** If you only need sorting or searching by a criterion, use a separate comparator/method and avoid forcing every rule into `equals()`.

A decision table before generating code:

| Type | Participates in Equality | Excluded | Condition |
| --- | --- | --- | --- |
| `ProductKey` | `sku`, `market` | None | Immutable components |
| `Customer` | `customerId` | `displayName`, `lastViewedAt` | UUID present from creation and immutable |
| `Money` | `amount`, `currency` after published normalization | Input text representation | Immutable value |
| `RequestContext` | Reference identity | State fields | Do not override `equals()` |

This table represents **decisions for the illustrative classes**, not rules for all classes sharing those names. For example, an email can change or be reused, so it is not automatically an immutable business ID.

## 3. Rules of `Object.equals()` and `hashCode()`

The `equals()` contract requires:

- **Reflexive:** `x.equals(x) == true`.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` produce the same result.
- **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
- **Consistent:** if the compared components do not change, repeated calls return the same result.
- **For null:** `x.equals(null) == false`.

The hashing contract requires:

- If `x.equals(y) == true`, then **`x.hashCode() == y.hashCode()`**.
- If equality components do not change, the hash code must remain consistent according to the contract.
- Two identical hashes do **not** mean two objects are equal; collisions are valid.

When overriding `equals()`, you must implement a matching `hashCode()`. For example, two instances equal by email that keep the default `Object.hashCode()` may receive different hashes, causing `HashSet` to fail deduplication or `HashMap` to fail key lookup. Never use matching hashes to conclude equality.

`Objects.equals(a, b)` handles null safely; `Objects.hash(field1, field2)` conveniently builds a hash. However, utilities do not replace the requirement to choose the exact **same set of components** for both equality and hashing.

## 4. Standalone Runnable Java 17 Example

The example has three separate contracts:
- `ProductKey` is a value object; the record compares both `sku` and `market` components.
- `Customer` is an entity with an immutable UUID; renaming does not change identity.
- `Money` is a value object with a predefined normalization policy for amount and currency code.

Save to file **`EqualityDesignDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public class EqualityDesignDemo {

    record ProductKey(String sku, String market) {
        ProductKey {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(market, "market");
        }
    }

    static final class Customer {
        private final UUID customerId;
        private String displayName;

        Customer(UUID customerId, String displayName) {
            this.customerId = Objects.requireNonNull(customerId, "customerId");
            this.displayName = Objects.requireNonNull(displayName, "displayName");
        }

        void rename(String newName) {
            displayName = Objects.requireNonNull(newName, "newName");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            return other instanceof Customer that
                    && customerId.equals(that.customerId);
        }

        @Override
        public int hashCode() {
            return customerId.hashCode();
        }
    }

    record Money(BigDecimal amount, String currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
            if (currency.isBlank()) {
                throw new IllegalArgumentException("currency is blank");
            }
            amount = amount.stripTrailingZeros();
            currency = currency.trim().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        ProductKey p1 = new ProductKey("SKU-7", "VN");
        ProductKey p2 = new ProductKey("SKU-7", "VN");
        ProductKey p3 = new ProductKey("SKU-7", "US");

        Set<ProductKey> keys = new HashSet<>();
        keys.add(p1);
        keys.add(p2);
        keys.add(p3);

        System.out.println("ProductKey p1 equals p2: " + p1.equals(p2));
        System.out.println("ProductKey p1 equals p3: " + p1.equals(p3));
        System.out.println("Unique product keys: " + keys.size());

        UUID id1 = UUID.fromString("00000000-0000-0000-0000-000000000001");
        UUID id2 = UUID.fromString("00000000-0000-0000-0000-000000000002");

        Customer a = new Customer(id1, "Minh");
        Customer sameId = new Customer(id1, "Minh Nguyen");
        Customer otherId = new Customer(id2, "Minh");

        System.out.println("Same customer ID: " + a.equals(sameId));
        System.out.println("Different customer ID: " + a.equals(otherId));

        Map<Customer, String> statuses = new HashMap<>();
        statuses.put(a, "active");
        System.out.println("Lookup by same ID: " + statuses.get(sameId));

        a.rename("Minh updated");
        System.out.println("Lookup after rename: " + statuses.get(a));

        Money m1 = new Money(new BigDecimal("1.0"), "usd");
        Money m2 = new Money(new BigDecimal("1.00"), "USD");
        System.out.println("Normalized money equal: " + m1.equals(m2));
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac EqualityDesignDemo.java
java EqualityDesignDemo
~~~

Exact stdout:

~~~text
ProductKey p1 equals p2: true
ProductKey p1 equals p3: false
Unique product keys: 2
Same customer ID: true
Different customer ID: false
Lookup by same ID: active
Lookup after rename: active
Normalized money equal: true
~~~

**Explanation:**

- Record `ProductKey` generates equality and hash based on both components. `p1` and `p2` are two distinct instances with the same value; `HashSet` stores only one representative for them, plus `p3`.
- `Customer` compares only `customerId`. Same ID with different names are still equal; different IDs with the same name are not. Renaming does not affect the hash of the key already in `HashMap`.
- `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is normally `false` because it checks scale as well, even though `compareTo() == 0`. The `Money` constructor proactively normalizes amount with `stripTrailingZeros()` and currency to uppercase, so the two illustrative values are equal. If scale is meaningful in the business domain, this normalization must not be applied.

The case-sensitive rule of `ProductKey` and assigning a UUID upon `Customer` creation are decisions **explicitly stated before coding**, not mandatory Java defaults.

## 5. Pitfalls When Choosing Fields

### Putting Every Field of an Entity into Equality

If `Customer` compares name, update timestamp, and display status as well, two instances representing the same customer after a rename could be treated as different entities. This is a bug if the domain has defined identity by ID.

Conversely, for a coordinate value object, omitting the y-axis would cause two different values to be treated as one. There is no rule to "always compare only ID" or "always select all fields".

### Hash-Determining Fields That Can Change

When a key is added to a `HashSet`, the collection picks a bucket based on the current hash. If you later modify a field participating in `hashCode()`, the collection does not automatically relocate the element; `contains()` or `remove()` may fail even though the object is still in the set.

~~~java
// ILLUSTRATIVE CODE; MutableKey needs to be defined separately.
// Suppose equals/hashCode uses a mutable name field.
Set<MutableKey> set = new HashSet<>();
MutableKey key = new MutableKey("before");
set.add(key);
key.setName("after"); // Hash may change; the collection does not automatically rehash.
~~~

This snippet is **not a standalone program**. The solution is to use immutable keys or separate a stable identifier; when a key truly must change, manage remove/reinsert according to the contract. Do not arbitrarily drop fields from equality to mask the symptom.

### Entities Without an ID Yet and Database-Generated IDs

The following snippet is **wrong for two independent new entities that both have a null ID**:

~~~java
// WARNING SNIPPET — not an implementation to use directly.
return Objects.equals(this.id, other.id);
~~~

Because `Objects.equals(null, null)` is `true`, two new objects may be treated as one. Moreover, when the database assigns an ID after persisting, a hash code depending on the ID can change, causing issues for hash collections.

You need to establish a policy for transient, persisted, detached, and proxy entities. You can assign an immutable UUID at creation time, use reference identity during the transient phase with a consistent contract, or separate a value object as a business key. With JPA/Hibernate, you must test the actual proxy/lifecycle behavior and not blindly apply one ID-based equality formula to every entity.

### Inheritance Breaking Symmetry

Suppose `Point` compares x/y and accepts `instanceof Point`; `ColorPoint extends Point` adds color. Then the following can happen:

~~~text
point.equals(colorPoint) == true
colorPoint.equals(point) == false
~~~

This is a **symmetry** violation. Design approaches include `final`/value classes or `record`, composition, or an equality contract across subclasses proven to be consistent. `getClass()` accepts only the exact concrete class; `instanceof` accepts subtypes but can fail when a subclass adds fields. ORM proxies make testing this choice against the real framework necessary.

### Mechanically Comparing Bidirectional Relationships

If one entity references another entity which has a back-reference, auto-generated code recursively comparing all relationships can overflow the stack, trigger excessive lazy-loading, or run very slowly. An entity contract can inspect only the ID; if the domain requires structural equality of a graph, a dedicated algorithm handling cycles and shared references is needed.

## 6. When Separate Comparisons Are Better Than `equals()`

**Comparator:** Two products with different IDs may have the same price; a price comparator returns `0` even though `equals()` returns `false`. `TreeSet` and `TreeMap` determine duplicate elements/keys by comparator result, so they can have different uniqueness logic from `HashSet`. If you need to group products by price, use a comparator or separate grouping operation and document its meaning clearly.

**Approximate comparison:** For floating-point numbers, `Math.abs(a - b) < epsilon` is generally not transitive: a is close to b, b is close to c, yet a is not close to c. Therefore, do not use an arbitrary tolerance to implement `Object.equals()`. Provide `approximatelyEquals(other, tolerance)` or a stable quantization/canonicalization policy when needed as a key.

**Arrays and collections:** `Objects.equals(arrayA, arrayB)` normally compares array references. A record containing an array component also does not automatically compare element contents. If the domain requires element-by-element comparison, use `Arrays.equals()/Arrays.deepEquals()` and `Arrays.hashCode()/Arrays.deepHashCode()` accordingly, while also controlling array mutability. A record having `final` fields does not automatically make objects inside them deep-immutable.

**Strings and normalization:** Whether `"ABC"` equals `"abc"` is a domain decision. Codes, usernames, emails, whitespace, Unicode, and locales require case-by-case policies. If you want case normalization for technical codes, use an appropriate locale such as `Locale.ROOT`, rather than relying on the host machine's default locale.

## 7. Choosing Tools After Defining Equality

| Mechanism | Best Fit | Mandatory Checks |
| --- | --- | --- |
| IDE Generate `equals()`/`hashCode()` | Regular classes, fields finalized | Fields, null, inheritance, arrays, mutable data |
| Lombok `@EqualsAndHashCode` | Reducing boilerplate | Include/exclude, `callSuper`, proxies, and inheritance |
| Java `record` | Value objects with suitable components | By default **all** components participate in equality; components can point to mutable objects |
| Hand-written | Entity IDs, normalization, or custom rules | Synced equals/hash, symmetry, transitivity, lifecycle |
| Do not override | Reference identity needed | Ensure API callers do not expect value equality |

For example, `record EmployeeRecord(String id, String name)` by default treats both ID and name as part of the value. If the domain defines "the same employee even when renamed", this record is not necessarily suitable as an entity, even if the generated code is valid. You can use `EmployeeId` as a record value object and a separate class for the entity.

## 8. Testing Based on the Chosen Contract

After generating or writing code, verify:

1. `x.equals(x)`, `x.equals(null)`, and valid null-value cases.
2. Symmetry and transitivity on sample object sets.
3. Two equal objects have equal hash codes.
4. Value objects differing in a meaningful component must not be equal.
5. Entities with the same ID and different names are still equal if ID is the contract; different IDs with the same name are not.
6. `HashSet` deduplicates properly and `HashMap` looks up keys using an equivalent instance.
7. Changing allowed mutable fields does not break lookup.
8. Test transient/persisted/proxy states, BigDecimal scale, Unicode, arrays, or cycles if present in the model.
9. Test comparators if a result of `0` does not necessarily mean equals.

Illustrative assertion (placed in test code where two variables `a`, `b` are prepared):

~~~java
if (a.equals(b) && a.hashCode() != b.hashCode()) {
    throw new AssertionError("Equal objects must have equal hashes");
}
~~~

This check only catches one kind of violation; you still need to test **unequal** pairs, symmetry, transitivity, and stability.

## 9. Pre-Generate Checklist

- [ ] Write one sentence "Two objects of type X are equal when..." in business terms.
- [ ] Identify whether it is value equality, entity identity, or reference identity.
- [ ] Choose the right participating fields; justify excluded fields.
- [ ] Specify handling for null, unassigned IDs, normalization, mutable fields, inheritance/proxies, and collections.
- [ ] Keep components determining equality/hash stable when using objects as keys.
- [ ] Choose IDE, Lombok, record, hand-written, or default behavior appropriately.
- [ ] Test the Object contract and real-world usage in maps/sets.

**Principle:** `equals()` describes the **meaning of equality**; `hashCode()` must be consistent with that meaning. Only generate code after the contract has been defined.