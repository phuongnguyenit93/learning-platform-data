# Distinguishing Between an Entity and a Value Object

## Objectives

After this lesson, you will be able to distinguish between an Entity and a Value Object in a domain model; explain the identity, lifecycle, and equality rules of each type; choose how to map them using `@Entity`, `@Embeddable`, `@Embedded`, and `@ElementCollection`; and avoid turning every object into an entity or creating separate tables for values that have no independent identity.

## 1. Why Distinguish Between an Entity and a Value Object?

A business model typically contains multiple kinds of objects. Some objects represent an entity that exists independently over time, such as a customer or an order. Other objects merely describe a value, such as a shipping address, a time range, a monetary amount, or coordinates.

If every object is treated as an entity, the model ends up with more primary keys, repositories, relationships, and tables than necessary. If everything is treated as a value object, the application may lose the identity, history, and referenceability of objects that must be managed independently.

Distinguishing between the two helps decide whether an object needs a stable identity, whether it has its own lifecycle, whether a change means updating the object or replacing it with a new value, and whether it needs its own repository/table or can simply be embedded into an owning entity.

## 2. What Is an Entity?

An **Entity** is an object with its own identity. Two entities can contain the exact same data yet still be two different objects if their identities differ.

For example, two customers with the same name and the same address can still be two different customers. They can be distinguished by a customer code, an identification number, or a primary key in the system.

Common characteristics of an entity:

1. Has a stable identity within the business or system scope.
2. Has its own lifecycle: created, updated, and possibly deactivated or deleted.
3. Its state can change while its identity remains the same.
4. Other objects can reference that entity.
5. Comparing two entities is primarily based on their identity or chosen business key, not on whether all current fields are identical.

In JPA, an entity is marked with `@Entity` and must have an identifier marked with `@Id` or `@EmbeddedId`. The JPA provider manages the persistence lifecycle of the entity and maps it to the corresponding table or storage structure.

Example: `Customer` has its own `id`. When its address changes, the customer is still the same customer; only the entity's state changes.

## 3. What Is a Value Object?

A **Value Object** is identified by the values it carries and has no independent identity in the business model. Two value objects with the same value components are considered equivalent according to the equality rules of that type.

For example, two `Money(100000, "VND")` values can be considered equal if they have the same amount and the same currency. An `Address` with the same street number, street, and city can also be considered the same address value.

Common characteristics of a value object:

1. Has no independent identity in the domain.
2. Equality is based on all components that form the value.
3. Usually immutable: changing a component produces a new value object.
4. Its lifecycle typically depends on the entity or aggregate that owns it.
5. Usually does not need its own repository or primary key.

Value Objects help express business meaning more clearly. Instead of passing a loose string `"100000"` alongside a string `"VND"`, a `Money` type expresses that this is a monetary value with its own rules. An `Address` type groups address components into a unified concept.

## 4. Comparing Entity and Value Object

| Criterion | Entity | Value Object |
| --- | --- | --- |
| How it is identified | Own identity | Values of its components |
| Equality | By identity or stable business key | By value components |
| Lifecycle | Can exist independently and be referenced | Usually depends on the owning entity |
| State change | Updates the same identity | Usually replaced with a new value |
| Primary key | Usually requires `@Id`/`@EmbeddedId` in JPA | Does not need its own identity |
| Repository | Usually has a repository if independent querying/management is needed | Usually accessed through the owning entity |
| Common JPA mapping | `@Entity` | `@Embeddable`, `@Embedded`, `@ElementCollection`, or basic type/converter |
| Examples | Customer, Product, Order | Money, Address, DateRange, Coordinates |

This is a domain design rule, not a classification based on the number of fields. An object with only one field can still be a value object; an entity can have many identical fields and still be identified by its identity.

## 5. Do Not Confuse Domain Concepts with JPA Annotations

Entity and Value Object are domain design concepts, commonly discussed in Domain-Driven Design (DDD). `@Entity` and `@Embeddable` are Jakarta Persistence mapping annotations.

In a typical model, a Domain Entity is usually mapped with JPA `@Entity`; a Domain Value Object is usually mapped with `@Embeddable`/`@Embedded`, or stored as a basic type, `@ElementCollection`, converter, or another appropriate structure.

The two pairs of concepts are not strictly identical. A domain value object type may be stored using a converter or JSON instead of `@Embeddable`. Likewise, a JPA entity does not automatically become an aggregate root in DDD. An aggregate root is a decision about business consistency boundaries, not an annotation name.

## 6. Mapping an Entity with @Entity

For example, `CustomerEntity` is an entity because a customer has its own identity, can be referenced by orders, and has an independently managed lifecycle.

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_identity_examples")
@Access(AccessType.FIELD)
public class CustomerEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected CustomerEntity() {
        // Constructor for JPA.
    }

    public CustomerEntity(String name) {
        this.name = requireText(name, "name");
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = requireText(newName, "newName");
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }
}
```

`id` is the database-generated identity. When the customer's name changes via `rename`, the identity remains unchanged. JPA tracks the entity's state in the persistence context and synchronizes changes to the database on flush.

An entity is usually accessed through a repository:

```java
package com.example.learning.customer;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerEntityRepository
        extends JpaRepository<CustomerEntity, Long> {
}
```

A repository operates on entities by primary key. This is an important difference compared to value objects: we usually ask "Which id does this Customer have?" or "Find Customer by email?", whereas with Address we usually read or replace the address value of a Customer.

## 7. Mapping a Value Object with @Embeddable and @Embedded

JPA allows describing a group of fields as a type that can be embedded into an entity. The value class is marked with `@Embeddable`; the entity's attribute uses `@Embedded` to embed its columns into the owning entity's table.

For example, `Address` has no primary key of its own and no independent lifecycle. It only describes the customer's current address:

```java
package com.example.learning.customer;

import java.util.Objects;
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
@Access(AccessType.FIELD)
public class Address {
    @Column(name = "street_name", nullable = false, length = 160)
    private String street;

    @Column(name = "city_name", nullable = false, length = 100)
    private String city;

    protected Address() {
        // Constructor for JPA.
    }

    public Address(String street, String city) {
        this.street = requireText(street, "street");
        this.city = requireText(city, "city");
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public Address withCity(String newCity) {
        return new Address(street, newCity);
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Address address)) {
            return false;
        }
        return Objects.equals(street, address.street)
            && Objects.equals(city, address.city);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city);
    }
}
```

`Address` has a `protected` no-argument constructor for JPA, while business code creates objects through a validating constructor. There is no `@Id`, because Address has no independent identity in this model. `equals` and `hashCode` are based on the value components.

Entity embedding Address:

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers_with_address")
@Access(AccessType.FIELD)
public class CustomerWithAddress {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @Embedded
    private Address address;

    protected CustomerWithAddress() {
    }

    public CustomerWithAddress(String name, Address address) {
        this.name = name;
        this.address = requireAddress(address);
    }

    public Long getId() {
        return id;
    }

    public Address getAddress() {
        return address;
    }

    public void changeAddress(Address newAddress) {
        this.address = requireAddress(newAddress);
    }

    private static Address requireAddress(Address address) {
        if (address == null) {
            throw new IllegalArgumentException("address must not be null");
        }
        return address;
    }
}
```

With field access, Hibernate reads the fields of Address and maps them as columns in the same `customers_with_address` table. There is no `addresses` table just because an `Address` class exists. When changing the address, the entity remains the same Customer; the Address value is replaced.

For an entity with computed fields not stored in the database, you can mark the member chosen as the persistent access point with `@Transient`. For example, `displayLabel` computed from `street` and `city` can be a derived property; it does not need its own column. Place `@Transient` on the field when using FIELD access or on the getter when using PROPERTY access.

### 7.1. Embedding the Same Type Multiple Times with @AttributeOverride

If Customer has both a billing address and a shipping address, the same `Address` type is embedded twice. Since the two groups of columns need distinct names, use `@AttributeOverride` or `@AttributeOverrides` to rename the columns:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street", nullable = false)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city", nullable = false)
    )
})
private Address billingAddress;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "shipping_street", nullable = false)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "shipping_city", nullable = false)
    )
})
private Address shippingAddress;
```

This is a snippet to place inside an entity already declared with `@Entity` and having the corresponding Jakarta Persistence imports. `name` in `@AttributeOverride` is the Java attribute name of the embeddable (`street`, `city`), while `column.name` is the column name in the owning entity's table.

## 8. Collections of Value Objects with @ElementCollection

When an entity owns multiple values of the same kind, `@ElementCollection` can be used. Basic or embeddable values are stored in a collection table and linked to the owning entity via a foreign key.

For example, a customer has multiple string tags:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tags",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag_value", nullable = false, length = 50)
private Set<String> tags = new HashSet<>();
```

This is a snippet placed inside the Customer entity. Required imports include `jakarta.persistence.ElementCollection`, `CollectionTable`, `JoinColumn`, `Column`, and `java.util.Set`/`HashSet`.

The `customer_tags` collection table has the join column `customer_id` and the value column `tag_value`. Each tag does not need its own entity or repository. When Customer is deleted, the rows belonging to the collection are typically handled according to the owning relationship of the collection mapping.

A collection of embeddables can be used when the value has multiple components:

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
@Access(AccessType.FIELD)
public class ContactPoint {
    @Column(name = "contact_type", nullable = false, length = 30)
    private String type;

    @Column(name = "contact_value", nullable = false, length = 160)
    private String value;

    protected ContactPoint() {
    }

    public ContactPoint(String type, String value) {
        this.type = type;
        this.value = value;
    }
}
```

In the entity:

```java
@ElementCollection
@CollectionTable(
    name = "customer_contact_points",
    joinColumns = @JoinColumn(name = "customer_id")
)
@OrderColumn(name = "position_index")
private List<ContactPoint> contactPoints = new ArrayList<>();
```

`@OrderColumn` stores the element order of the List. If order is not meaningful, you can choose `Set` and implement appropriate equality/hashCode for the embeddable. Collection values still belong to Customer's lifecycle and have no independent identity.

## 9. Equality: Entity Identity vs. Value Object Value

This is the most important difference when designing `equals()` and `hashCode()`.

### Value Object

A Value Object compares by all meaningful components of its value. With Address, two objects with the same street and city can be equal even if created at different times.

Value Objects should generally be immutable. Instead of modifying an Address currently in a `HashSet`, create a new Address and replace the old value. If an object is used as a `HashMap` key or a `HashSet` element, mutating a field involved in `hashCode` after adding it to the collection can prevent finding the element again.

### Entity

An Entity is identified by its identity. Two Customers with the same name and address but different IDs are still two distinct entities. Conversely, a Customer that changes its name or address is still the same entity if its identity has not changed.

Writing `equals()` for a JPA entity requires care:

- A database-generated ID may be `null` before persisting; two new entities must not be considered equal merely because both have a null id.
- If `hashCode()` changes after persisting while the entity is in a `HashSet`, the collection's lookup behavior can break.
- Hibernate may use proxy subclasses; naively comparing classes with `getClass()` can produce unexpected results with proxies.
- Using mutable fields such as `name` or `address` for equality causes an entity's identity to change with its data.

There is no single `equals/hashCode` implementation suitable for every entity. Choose a strategy based on a stable, unique, business-immutable identity or natural key; account for provider proxies; and test transient, managed, and detached states. If you do not yet need the entity as an element in hash collections, do not write complex equality from a copied template without understanding its consequences.

## 10. When Should a Value Object Become an Entity?

A value may start as a Value Object and later become an Entity when business requirements change. For example, `Address` initially is just an address embedded in Customer. However, if the system needs to:

- Identify an address and allow multiple customers to reference the same verified address.
- Manage its own history, verification status, verifier, or effective period.
- Link the address to delivery orders, zones, shipping routes, or other records.
- Update the address independently without replacing the Customer's state.

then an `Address` entity with its own identity and repository may be more appropriate. At that point, ownership relationships, foreign keys, cascades, and deletion policies must be clearly decided.

Conversely, do not create an Entity merely because an object has many fields or because you want to put it in a separate table. Ask whether the object has its own business identity and lifecycle.

## 11. Relationship Between Entity and Value Object

Entities typically own or contain value objects:

```text
Customer (Entity, customer_id)
├── name
├── Address (Value Object)
│   ├── street
│   └── city
└── tags (Collection of Value Objects)
    ├── "priority"
    └── "newsletter"
```

In this example, Customer has its own identity and lifecycle; Address describes the current address value; Tags are values belonging to Customer. If Customer changes its Address or tags, Customer keeps its identity.

In DDD, an entity and the value objects it owns usually reside in the same aggregate. The aggregate root controls changes to protect invariants. However, not every `@Embedded` belongs to an aggregate root, and not every JPA relationship corresponds to an aggregate boundary. Determine the business boundaries first, then choose the mapping.

## 12. Common Design and Mapping Mistakes

| Practice | Problem | Improvement |
| --- | --- | --- |
| Creating `@Entity` for every class | Produces too many identities, repositories, and relationships | Only use Entity when there is a distinct identity/lifecycle |
| Using `@Embeddable` for an object that needs to be referenced independently | No identity for other entities to reference directly | Convert to an entity if business requirements need identification |
| Value Object has public setters and is mutated arbitrarily | Equality and invariants easily change out of control | Prefer an immutable API, replacing with a new object |
| Not overriding columns when embedding the same type twice | Duplicate column names in the same table | Use `@AttributeOverride(s)` |
| Using `Set` for an embeddable without proper equality | Duplicate values or unpredictable collection behavior | Implement value-based equality/hashCode |
| Using mutable Entity fields in hashCode | Entity changes hash when its state changes | Base on a stable identity/natural key and understand the ID lifecycle |
| Assuming `@Embeddable` always creates a separate table | Misunderstanding the mapping | `@Embedded` usually places columns in the owning entity's table; `@ElementCollection` uses a collection table |
| Assuming a Value Object can never be stored separately | Confusing domain concepts with storage mechanisms | Choose a converter, JSON, or appropriate mapping; if a separate identity is needed, re-evaluate as an Entity |

## 13. Design Workflow

1. Determine whether the object has a stable business identity.
2. Ask whether the object has an independent lifecycle and needs to be referenced from multiple places.
3. If it is only a value, identify all components that define equality.
4. Prefer immutability for Value Objects; validate nulls, value ranges, formats, and business rules upon creation.
5. Choose the storage approach: basic type, `@Embeddable`/`@Embedded`, `@ElementCollection`, converter, or another suitable structure.
6. If embedding the same type multiple times, name columns using `@AttributeOverride(s)`.
7. If it is an Entity, define its identity, relationships, cascade, orphan removal, and transaction boundaries.
8. Write tests for equality, persist, load, update, and delete according to the lifecycle.
9. Inspect the schema and generated SQL to ensure the mapping accurately reflects the model.

## 14. Example Testing Value Object and Entity

Testing equality of Address:

```java
package com.example.learning.customer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class AddressTest {
    @Test
    void sameComponentsRepresentSameValue() {
        Address first = new Address("1 Main Street", "Hanoi");
        Address second = new Address("1 Main Street", "Hanoi");

        assertThat(first).isEqualTo(second);
        assertThat(first.hashCode()).isEqualTo(second.hashCode());
    }
}
```

This test checks value-based equality. It does not need a database because Address equality is a pure domain rule.

For Customer, an integration test should verify that two persisted entities have different identities even when their business fields are identical, and that when the address changes, the Customer's id stays the same. `@DataJpaTest` with a test database and `EntityManager` can be used to verify this.

```java
package com.example.learning.customer;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerWithAddressTest {
    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void customerIdentityRemainsWhenAddressChanges() {
        CustomerWithAddress customer = new CustomerWithAddress(
            "Ada", new Address("1 Main Street", "Hanoi")
        );
        entityManager.persist(customer);
        entityManager.flush();
        Long originalId = customer.getId();

        customer.changeAddress(new Address("2 Lake Road", "Hanoi"));
        entityManager.flush();
        entityManager.clear();

        CustomerWithAddress reloaded = entityManager.find(
            CustomerWithAddress.class, originalId
        );
        assertThat(reloaded.getId()).isEqualTo(originalId);
        assertThat(reloaded.getAddress().getStreet()).isEqualTo("2 Lake Road");
    }
}
```

This test is in the same package as `CustomerWithAddress` and `Address`, with `spring-boot-starter-data-jpa` and a test database. `flush()` writes changes to the database within the test transaction; `clear()` detaches entities from the persistence context so the subsequent `find` must reload from the database.

## Conclusion

An Entity is identified by its identity and has its own lifecycle; a Value Object is identified by its values and typically depends on an owning entity. In JPA, use `@Entity` for objects requiring identification, `@Embeddable`/`@Embedded` for embedded values, and `@ElementCollection` for collections of values. Let business requirements drive the model, keep Value Objects immutable when possible, and test equality as well as the persistence lifecycle to avoid unnecessary mapping complexity.
