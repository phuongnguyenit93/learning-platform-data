# Choosing Field or Property Access with @Access

## Objectives

After this lesson, you will be able to distinguish JPA's two access strategies, `FIELD` and `PROPERTY`; determine how JPA selects the default strategy; use `@Access` to declare explicitly or override per attribute; apply them safely with entity inheritance and embeddables; and avoid duplicate mapping errors or unexpected getter/setter behavior.

## 1. What does the access type determine?

A Java entity can store state in fields and provide getters/setters to read and mutate that state. JPA needs to know where it will read and write persistent state. This decision is called the **access type**.

Jakarta Persistence defines two values in the `AccessType` enum:

- `AccessType.FIELD`: the provider directly accesses the persistent fields of the class.
- `AccessType.PROPERTY`: the provider accesses Java properties through getters and setters following JavaBeans conventions.

`@Access` is the annotation used to specify this strategy. It belongs to the `jakarta.persistence` package in Spring Boot 3 and above:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
```

The access type controls how JPA reads/writes object state. It does not determine which database is used, does not change the nature of SQL, and is not Java's `public`/`private` visibility modifier. For example, JPA can still map a `private` field when using field access.

## 2. How does JPA determine the default strategy?

If an entity does not declare `@Access` at the class level, JPA determines the default strategy based on where the identifier annotation is placed:

- `@Id` or `@EmbeddedId` is on a field: default is `FIELD`.
- `@Id` or `@EmbeddedId` is on a getter: default is `PROPERTY`.

For example, the following placement of `@Id` selects field access:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String email;
}
```

Conversely, placing `@Id` on the getter selects property access:

```java
@Entity
public class Customer {
    private Long id;
    private String email;

    @Id
    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
    public void setEmail(String email) {
        this.email = email;
    }
}
```

The placement of `@Id`/`@EmbeddedId` is the key signal for inferring the access type. Do not arbitrarily put mapping annotations on fields for some attributes and on getters for others. If annotation placement is inconsistent without `@Access` specifying the strategy, mapping behavior may be undefined under the specification.

In real-world code, explicitly declare `@Access` at the class level when you want readers to immediately see the entity's convention. This is especially useful when an entity has many attributes, inheritance, or needs to mix the two access modes.

## 3. Field access: JPA works directly with fields

When using `FIELD`, mapping annotations are placed on fields. The provider reads and writes fields directly, even when fields are `private`; getters/setters are not the persistence entry points.

Example:

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
@Table(name = "customers")
@Access(AccessType.FIELD)
public class FieldAccessCustomer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email_address", nullable = false, length = 160)
    private String email;

    protected FieldAccessCustomer() {
        // JPA requires a no-argument constructor.
    }

    public FieldAccessCustomer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

In this example:

- `@Id`, `@GeneratedValue`, and `@Column` are placed on fields.
- Hibernate reads/writes `id` and `email` directly.
- The getters/setters remain useful for business code or serialization, but JPA does not need to call them to read/write these two attributes.
- Fields can be `private`; there is no need to make them `public` for JPA to map them.

### Advantages and caveats

Field access is often suitable when preserving encapsulation: fields remain private, the application controls mutations through business methods, and JPA uses reflection to read/write state.

However, because the provider accesses fields directly, it can bypass logic inside setters. If a setter performs validation, normalization, or event publishing, do not assume that logic always runs when JPA loads an entity. Important invariants should be enforced in constructors or business methods; do not rely solely on setters to protect data.

## 4. Property access: JPA works through getters/setters

When using `PROPERTY`, mapping annotations are placed on getters. JPA calls getters to read values and setters to write values when hydrating an entity.

Example:

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
@Table(name = "property_customers")
@Access(AccessType.PROPERTY)
public class PropertyAccessCustomer {
    private Long id;
    private String email;

    protected PropertyAccessCustomer() {
        // JPA requires a no-argument constructor.
    }

    public PropertyAccessCustomer(String email) {
        this.email = email;
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    @Column(name = "email_address", nullable = false, length = 160)
    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

In this example, `@Id` and `@Column` are on getters. The provider uses `getId()`, `setId(...)`, `getEmail()`, and `setEmail(...)` according to the access strategy. The primary key setter can be `protected` in this example because it serves entity hydration and is not necessarily a public API for the business layer.

### JavaBeans conventions

Property access relies on accessor naming:

- `getName()` corresponds to the `name` property.
- `isActive()` is typically used for boolean properties.
- `setName(String name)` is the setter for the `name` property.

Getters must return the appropriate data type and setters must accept a value of the same type. Use consistent getter/setter names so the provider recognizes properties accurately. In typical code, keep getters/setters `public` or `protected` and avoid accessors with side effects.

### Advantages and caveats

Property access is useful when you want the provider to go through accessors, or when the model needs to represent a persistent property via getters/setters. However, getters/setters become part of the persistence path.

Getters are called by JPA when reading values and setters are called when populating values. Therefore, getters should return stable state, not query the database, not mutate data, not trigger side effects, and not depend on invocation order. Setters should perform simple state assignment; avoid calling repositories, publishing business events, or performing operations that might fail midway through entity hydration.

## 5. Comparing FIELD and PROPERTY

| Criterion | FIELD | PROPERTY |
| --- | --- | --- |
| Where are mapping annotations placed? | On fields | On getters |
| Provider reads state via | Direct field access | Getters |
| Provider writes state via | Direct field access | Setters |
| Are getters/setters required for JPA mapping? | No | Matching accessors required |
| Does setter logic run during hydration? | Not called just to write the field | Yes, because the provider uses the setter |
| Suitable when | Keeping fields private and managing changes via business methods | Wanting persistence to go through accessors |
| Common risk | Bypassing validation/logic in setters | Getters/setters with side effects or call-order dependencies |

Both strategies are valid. Choose based on your domain model and stay consistent within an entity. Field access is a popular choice in many Hibernate applications because mappings sit close to the data state; property access remains useful when accessors are an intentional persistence interface.

## 6. Explicitly specifying the access type with @Access

`@Access` can be placed at the class level to define the default strategy for the class's attributes:

```java
@Entity
@Access(AccessType.FIELD)
public class Product {
    @Id
    private Long id;

    private String name;
}
```

Here JPA uses field access for the persistent attributes of `Product`, regardless of whether getters exist.

Class-level placement with property access:

```java
@Entity
@Access(AccessType.PROPERTY)
public class Product {
    private Long id;
    private String name;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Once an access type is explicitly chosen at the class level, place mapping annotations in the corresponding location. With `FIELD`, place annotations on fields; with `PROPERTY`, place annotations on getters.

## 7. Mixing the two strategies for a single attribute

Sometimes an entity has a default strategy, yet one attribute needs the other approach. JPA supports attribute-level overrides by placing `@Access` on that attribute's field or getter.

Example where the entity defaults to field access, but `displayName` is persisted via getter/setter:

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

@Entity
@Table(name = "mixed_access_customers")
@Access(AccessType.FIELD)
public class MixedAccessCustomer {
    @Id
    private Long id;

    @Column(name = "first_name")
    private String firstName;

    @Column(name = "last_name")
    private String lastName;

    @Transient
    private String displayName;

    protected MixedAccessCustomer() {
    }

    @Access(AccessType.PROPERTY)
    @Column(name = "display_name")
    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

In this example:

- By default, attributes are mapped via fields.
- `id`, `firstName`, and `lastName` use field access.
- The `displayName` field is annotated with `@Transient` so it is not mapped under the default FIELD strategy.
- The `getDisplayName()` getter has `@Access(AccessType.PROPERTY)`, so the `displayName` property is mapped via property access and stored in the `display_name` column.
- The setter is used by the provider when loading this attribute's value.

An important rule is that access overrides must be explicit and apply only to the exact attribute. Do not place mapping annotations simultaneously on both the field and the getter of the same attribute without clear intent and the matching `@Access` rule. If the same attribute is mapped twice, the provider may report a mapping error or produce invalid metadata.

### Example overriding in the opposite direction

An entity can default to property access while one field is mapped directly:

```java
@Entity
@Access(AccessType.PROPERTY)
public class ExternalReference {
    private Long id;
    private String referenceCode;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @Access(AccessType.FIELD)
    @Column(name = "reference_code")
    private String referenceCode;
}
```

In this case, `id` uses property access, while `referenceCode` uses field access. Do not add `@Column` for the same `referenceCode` on a getter.

Only use mixed access when there is a specific reason. Every exception forces readers to check an extra rule when reviewing mappings, so a uniform strategy is generally easier to maintain.

## 8. @Transient and non-persisted attributes

`@Transient` marks an attribute as not belonging to persistent state. Annotation placement must match the attribute's access strategy:

- With field access, place `@Transient` on the field.
- With property access, place `@Transient` on the getter.
- With mixed access, place the annotation on the member actually chosen as the attribute's access point.

Field access example:

```java
@Entity
@Access(AccessType.FIELD)
public class Person {
    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String searchLabel;

    public String getSearchLabel() {
        return firstName + " " + lastName;
    }
}
```

`searchLabel` is computed in the application and is not stored as a column. A field with the Java `transient` modifier is also not a persistent field under field access rules; however, `@Transient` generally expresses mapping intent more clearly and works for properties as well.

Do not confuse JPA's `@Transient` with excluding a property from JSON or marking a database column nullable. Those are different mechanisms.

## 9. Access type with inheritance and @MappedSuperclass

Entities can inherit persistent attributes from a `@MappedSuperclass`. Attributes declared in a mapped superclass also need a clear access strategy.

Example of a mapped superclass using field access:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
@Access(AccessType.FIELD)
public abstract class BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    protected Long id;

    public Long getId() {
        return id;
    }
}
```

Child entity:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Entity;

@Entity
@Access(AccessType.FIELD)
public class Invoice extends BaseEntity {
    private String invoiceNumber;

    protected Invoice() {
    }

    public Invoice(String invoiceNumber) {
        this.invoiceNumber = invoiceNumber;
    }
}
```

Here `id` is declared in the mapped superclass and inherited as a persistent attribute of the entity. Declare the access strategy clearly where attributes are owned, especially when the hierarchy has multiple levels or multiple mapping groups.

Do not infer the access type solely from a getter in a child class if the primary key is declared in the parent class. When an entity hierarchy or mapped superclass has differing strategies, inspect the exact class declaring each attribute and specify `@Access` explicitly so metadata is unambiguous.

## 10. Access type with @Embeddable

An embeddable does not have an independent identity like an entity. It is embedded into an entity via `@Embedded` or used in an embedded key structure `@EmbeddedId`.

Example `Address` value object using field access:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
@Access(AccessType.FIELD)
public class Address {
    @Column(name = "street_name")
    private String street;

    @Column(name = "city_name")
    private String city;

    protected Address() {
    }

    public Address(String street, String city) {
        this.street = street;
        this.city = city;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }
}
```

Entity using the value object:

```java
@Entity
@Access(AccessType.FIELD)
public class Supplier {
    @Id
    private Long id;

    @Embedded
    private Address address;

    protected Supplier() {
    }
}
```

An embeddable's default access type is often inferred from its usage context, so if the same embeddable is used across multiple entities with different access types, declare `@Access` directly on the embeddable. This keeps how the provider reads/writes the value object's fields or properties explicit, independent of where it is embedded.

## 11. Common errors

| Symptom or pattern | Cause | Resolution |
| --- | --- | --- |
| `@Id` placed on a field while `@Column` for another attribute is on a getter | Mapping annotations mixed between FIELD and PROPERTY without an override declaration | Choose one class-level access type or use `@Access` on the exception attribute |
| `@Access(PROPERTY)` but getters/setters do not follow JavaBeans conventions | Provider cannot recognize the persistent property as expected | Use `getX`/`isX` and a `setX` setter with matching types |
| Setter does not run when Hibernate loads the entity | Entity uses FIELD access | Place mappings on getters and select PROPERTY if the provider must call setters; or move invariants to appropriate business methods |
| Getter triggers queries or mutates state | Property access invokes getters during persistence | Keep getters simple with no side effects |
| An attribute appears twice in metadata | Both field and getter are mapped | Put `@Transient` on the unused member and declare `@Access` on the chosen member |
| Child entity does not map parent attributes as expected | Unclear access strategy in hierarchy or mapping annotations placed on the wrong class | Check which class declares the attribute and specify the access strategy explicitly |
| Embeddable used in entities with different access types | Default access mode of the embeddable may become ambiguous | Place `@Access` explicitly on the embeddable |
| Computed-only attribute creates a column | Attribute is still recognized as persistent | Place `@Transient` on the member selected by the access strategy |

## 12. Process for choosing and verifying an access strategy

1. Locate `@Id` or `@EmbeddedId` in the entity hierarchy to understand JPA's inferred default.
2. Choose `FIELD` or `PROPERTY` based on how the model wants the provider to read/write state.
3. For an explicit convention, declare `@Access` at the appropriate entity, mapped superclass, or embeddable level.
4. Place all mapping annotations of an attribute on the right member: field or getter.
5. If an exception attribute is needed, use `@Access` on that attribute's field/getter and mark the other member `@Transient` when needed.
6. Inspect superclasses, subclasses, and reused embeddables to avoid ambiguous access types.
7. Write an integration test that persists and reads back the entity to verify values are stored and hydrated properly.
8. Inspect the schema/SQL if column names or entity state differ from expectations.

## 13. Verifying with an integration test

Example test for a field-access entity in a Spring Boot application configured with JPA and a test database:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class FieldAccessCustomerTest {
    @Autowired
    private TestEntityManager entityManager;

    @Test
    void persistsAndLoadsEmail() {
        FieldAccessCustomer customer =
            new FieldAccessCustomer("ada@example.test");

        entityManager.persist(customer);
        entityManager.flush();
        entityManager.clear();

        FieldAccessCustomer loaded = entityManager.find(
            FieldAccessCustomer.class, customer.getId()
        );

        assertThat(loaded.getEmail()).isEqualTo("ada@example.test");
    }
}
```

`flush()` forces the provider to synchronize changes to the database within the test transaction; `clear()` evicts the entity from the persistence context so the subsequent `find` must reload from the database. Thus, the test verifies both writing and hydration, rather than just reading back the same managed object.

For property access, a similar test can be written for `PropertyAccessCustomer`. If you need to prove that a setter is invoked during hydration, use a test with appropriate instrumentation; do not put side effects into production entities just for testing.

## 14. Which strategy should you choose?

| Situation | Recommended choice |
| --- | --- |
| Entity has private fields and business methods controlling changes | FIELD |
| Want the provider to read/write through JavaBean accessors | PROPERTY |
| Existing mappings are already standardized on fields | Continue with FIELD |
| Existing mappings are already standardized on getters | Continue with PROPERTY |
| One attribute genuinely needs a different access mode | Use `@Access` at the attribute level intentionally |
| Embeddable shared across entities with different access types | Place `@Access` explicitly on the embeddable |

Neither strategy automatically makes an entity better. The greatest value comes from consistency and predictability: readers know where JPA reads data from, which logic runs during hydration, and which member is actually mapped.

## Conclusion

`FIELD` makes JPA read/write fields directly; `PROPERTY` makes JPA go through getters/setters. The default is usually inferred from the placement of `@Id` or `@EmbeddedId`, while `@Access` lets you declare a strategy explicitly at the class level or override it in a controlled manner per attribute. Place mapping annotations in the right spot, avoid duplicate field/getter mappings, and keep accessors simple so entities behave reliably across persist, flush, and hydrate.
