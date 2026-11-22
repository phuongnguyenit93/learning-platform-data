# Value Objects and Entities with Business Identity: Choosing Equality Semantics in Java

## 1. The Question Before Writing `equals`: "Equal" in What Sense?

In Java, `==` between two reference variables indicates whether they point to **the same object**. `equals(Object)` expresses **logical equality rules** decided by the class. By default, `Object.equals` compares by reference identity, but a class can override it to express domain meaning.

When designing a model, distinguish between two concepts:

- **Value Object:** what matters is **the value and meaningful attributes**; two separate instances are still considered equal if the component values to be compared are equal. Examples: coordinates, a monetary amount with its currency, a date range, an address used purely as an attribute.
- **Entity (with business identity):** what matters is **whether they are the same entity across its lifecycle**; two representations of the same entity are still considered equal when state changes. Examples: a customer identified by `CustomerId`, an order by `OrderId`.

**Having the same attributes does not necessarily make two objects the same entity.** Two customers named “Lan” are not one customer just because of that. Conversely, a customer who changes their name is still that same customer.

This is a context-dependent modeling decision. For instance, a shipping address used only to describe a location can be a Value Object; however, a pickup/delivery point with its own management code, history, and lifecycle can be an Entity.

## 2. Comparing Nature and Consequences

| Aspect | Value Object | Entity with Business Identity |
| --- | --- | --- |
| Primary question | “Do they have the same value?” | “Are they the same entity?” |
| `equals` criteria | Meaningful value components | Stable identifier within a defined scope |
| Two separate instances | Can have `equals == true` if values match | Can have `equals == true` if identifiers match |
| Mutable state | Usually create a new Value Object, avoid mutating in place | Allows state changes while identity remains unchanged |
| Data not to use as equality key | Fields outside value semantics | Frequently changing fields such as name, contact address, status |
| Example | `Address("Lê Lợi", "Đà Nẵng")` | `Customer("C001", "Lan")` |

In Java, a **`record`** is often suitable for representing a small Value Object because it generates `equals`, `hashCode`, and accessors based on its components. However, a record does not automatically satisfy every domain rule and is only immutable at the level of its reference fields (`final`), **not guaranteeing deep immutability** if it holds a `List`, array, or mutable object inside.

An Entity typically needs a class with an `id` attribute representing a stable identity, alongside updatable state attributes. Not every object with an `id` field is an entity; what decides is the object's existential meaning and lifecycle in the business domain.

## 3. Compilable and Runnable Java 17+ Example

The example uses `Address` as a Value Object: two address instances with the same street and city are considered equal. `Customer` is an Entity: two instances with the same `customerId` represent the same customer, even if their display names differ. Here `customerId` is assigned **before creating the object**, is always non-empty, and never changes.

Save the following code in `ValueVsEntityDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ValueVsEntityDemo {
    record Address(String street, String city) {
        Address {
            Objects.requireNonNull(street, "street");
            Objects.requireNonNull(city, "city");
        }
    }

    static final class Customer {
        private final String customerId;
        private String displayName;

        Customer(String customerId, String displayName) {
            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException("customerId must not be blank");
            }
            this.customerId = customerId;
            this.displayName = Objects.requireNonNull(displayName);
        }

        void rename(String name) {
            this.displayName = Objects.requireNonNull(name);
        }

        String displayName() {
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
        Address addressA = new Address("Le Loi", "Da Nang");
        Address addressB = new Address("Le Loi", "Da Nang");
        System.out.println("same address reference: " + (addressA == addressB));
        System.out.println("same address value: " + addressA.equals(addressB));

        Customer customerA = new Customer("C001", "Lan");
        Customer customerB = new Customer("C001", "Lan Nguyen");
        Customer customerC = new Customer("C002", "Lan");
        System.out.println("same customer reference: " + (customerA == customerB));
        System.out.println("same customer identity: " + customerA.equals(customerB));
        System.out.println("different customer identity: " + customerA.equals(customerC));
        System.out.println("different display names: "
                + !customerA.displayName().equals(customerB.displayName()));

        Set<Customer> customers = new HashSet<>();
        customers.add(customerA);
        customerA.rename("Lan Tran");
        System.out.println("found after rename: " + customers.contains(customerA));
        System.out.println("found by same ID: " + customers.contains(customerB));
        System.out.println("equals null: " + customerA.equals(null));
    }
}
```

Run in the directory containing the file:

```bash
javac ValueVsEntityDemo.java
java ValueVsEntityDemo
```

Output:

```text
same address reference: false
same address value: true
same customer reference: false
same customer identity: true
different customer identity: false
different display names: true
found after rename: true
found by same ID: true
equals null: false
```

Here `Address`, generated by `record`, compares component by component; two `new` calls create two separate objects, yet `addressA.equals(addressB)` returns `true`. `Customer` uses `customerId` in both `equals` and `hashCode`: two distinct Java objects representing customer `C001` are still equal, while the name is merely state. Changing `displayName` does not alter the hash code, so `HashSet` still finds the object added before renaming.

## 4. The `equals` and `hashCode` Contract Remains Mandatory

Regardless of whether you choose a Value Object or an Entity, the `equals` implementation must satisfy these rules:

1. **Reflexive:** `x.equals(x)` is `true` for non-`null` `x`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` give the same result.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
4. **Consistent:** if the information used for comparison does not change, the result does not change across invocations.
5. **Comparison with `null`:** for non-`null` `x`, `x.equals(null)` must be `false`.

In particular, if `a.equals(b)` is `true`, it is **mandatory** that `a.hashCode() == b.hashCode()`. The converse is not required: two unequal objects may still have the same hash code. `HashMap` and `HashSet` rely on both `hashCode` and `equals`, so modifying one method while ignoring the other will cause incorrect behavior.

For a Value Object, the components participating in `equals` must also be compatible with `hashCode`. For an Entity, the ID used for comparison must remain stable while the object is stored in a hash-based structure. The example above uses `final customerId` and avoids including `displayName` in both methods.

## 5. Common Pitfalls When Choosing Equality Semantics

### 5.1. Using Mutable State as Entity Identity

Suppose you write `Customer`'s `equals` based on `displayName`. When renamed, the entity suddenly “is not equal to its old self”; two customers with the same name also risk being treated as one. If these fields are used to compute `hashCode`, changing the name while the object is inside a `HashSet`/`HashMap` can cause lookup or removal by the object to fail.

Do not automatically use `email`, phone number, username, or status to identify an Entity: such data can change, be reused, or fail to be unique depending on the business domain. Only a **truly stable business key, unique within a defined scope**, is suitable.

### 5.2. Using Database-Generated IDs While Ignoring the Lifecycle

For example, a newly created Entity has `id == null` and only receives an ID from the database after `INSERT`. A naive implementation pattern is `Objects.equals(this.id, other.id)`: if unhandled, **two distinct new Entities that both have `null` ID** are treated as equal. In addition, if `hashCode()` is based on the ID, the hash code changes after saving, easily breaking lookups in hash collections.

There are different approaches depending on architecture: assign an immutable ID immediately upon Entity creation (such as an application-assigned UUID); or if the ID is only available after saving, clearly define the comparison rule for unsaved Entities (typically equal only by same reference), while keeping `hashCode` appropriate and stable for the lifecycle that needs to be supported. Do not copy the `Customer` example above verbatim for a JPA Entity whose ID is generated after `persist` without reviewing the strategy.

**A technical ID does not always equate to business identity.** If using a database ID as the criterion, you must determine its scope of uniqueness (single table, tenant, system) and whether unsaved Entities, splitting/merging, or exporting to another system changes the identity semantics.

### 5.3. Using `==` to Compare Representations Instead of Meaning

Two separately created `new Customer("C001", ...)` objects will evaluate `a == b` as `false`, even though both identify customer `C001` and `a.equals(b)` is `true` under this model. `==` remains useful for reference comparison or `null` checks, but it does not replace logical equality comparison.

### 5.4. Value Objects Containing Mutable Structures or Incorrect Monetary Comparison Semantics

`record` does not protect the contents of an array or mutable list component. If elements change after the Value Object has become a `HashMap` key, the hash value can change. Prefer immutable components; make defensive copies of mutable objects, and define the appropriate comparison method (such as `Arrays.equals` when array contents represent the value meaning).

For monetary values, do not compare only the numeric amount and forget the currency unit. Also, `BigDecimal.equals` distinguishes `scale`: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false`, even though `compareTo` returns `0`. If the domain treats those two amounts as the same value, you must define and normalize a consistent value rule for **both `equals` and `hashCode`**, rather than patching only `equals` with `compareTo`.

### 5.5. Inheritance, Proxy Classes, and Identity Scope

When inheritance is involved, how classes are compared (`getClass()` vs `instanceof`) affects symmetry/transitivity and the meaning of the ID. Do not let two different Entity types become equal simply because they share the string `"C001"` if they belong to two different identity types. With ORM/JPA, proxies can make direct class comparison require careful consideration; the `equals` rule must be compatible with the mapping technology and actual Entity lifecycle. The example uses a plain Java `final` `Customer` class, so there is no proxy issue.

## 6. Workflow for Choosing `equals` When Designing a Class

1. Ask: does the object represent **a value** or **an entity with its own history and lifecycle**? Do not decide solely by whether it has an ID or how many fields it has.
2. If it is a Value Object, select the components that constitute the value; prefer immutability, and consider using `record` when component-based comparison rules fit.
3. If it is an Entity, identify the unique business identity, the identifier scope, and when it is assigned; ensure state changes do not alter identity.
4. Implement `equals` and `hashCode` with the same semantics; consider `null`, subclasses/proxies, unsaved objects, and placement in `HashMap`/`HashSet`.
5. Test two different instances with the same value/ID, two instances with identical data but different IDs, state mutations, `null` cases, and hash code stability.

**Guiding rule:** a Value Object answers “do they have the same value?”; an Entity answers “are they the same entity?”. Designing `equals` around the right question keeps collections, caches, and business rules from confusing state with identity.