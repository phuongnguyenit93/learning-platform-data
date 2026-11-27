# Reusing Attribute Groups with @Embeddable and @Embedded

In an object-oriented model, an entity often has multiple groups of attributes that describe the same concept. For example, an order has a billing address and a shipping address; a customer has a contact address; a product has dimension or currency information. If every entity declares the same fields repeatedly, code becomes duplicated and data rules can become inconsistent.

JPA provides **@Embeddable** and **@Embedded** to group attributes into a reusable value type:

- **@Embeddable** marks a class that describes a group of attributes that can be embedded into an entity or another embeddable.
- **@Embedded** places a property of an embeddable type inside the owning entity or embeddable.

An embeddable has no independent identifier like an entity. It exists as part of the owning object and is usually mapped as columns in the same table as that entity. This organization keeps the domain model clear, reuses mappings, and groups related rules into a meaningful type.

**Example prerequisites:** the code snippets use Spring Boot 3.x, Java 17 or later, and Jakarta Persistence. The application needs the **spring-boot-starter-data-jpa** dependency, a DataSource, and the corresponding schema. The code blocks are separate source files in a Spring Boot application, not standalone programs runnable solely with **javac**.

## 1. How Do an Entity and an Embeddable Differ?

An entity represents an object with an identity and lifecycle managed by the persistence context. An embeddable represents a group of values belonging to an entity or another embeddable.

| Characteristic | Entity | Embeddable |
|---|---|---|
| JPA identifier | Has a primary key, typically using **@Id** | No independent primary key |
| Lifecycle | Can be persisted, found, and removed independently | Follows the lifecycle of the owning object |
| Separate repository | Can have a repository | No separate repository |
| Common mapping | A table or inheritance strategy | Columns embedded into the owning object's table |
| Main annotation | **@Entity** | **@Embeddable** |
| Usage | Managed as an entity | Declared with **@Embedded** or used in appropriate embeddable mappings |

For example, a customer is an entity because the system needs to identify and look up the customer by ID. A customer's address is usually a value object: it describes a residence or contact location and is managed together with the customer. An address does not necessarily need its own ID or a separate repository.

If an address needs to be shared, managed, and updated independently by multiple entities, that may be a sign that the address should be modeled as a separate entity. Choosing between an entity and an embeddable depends on business meaning and data lifecycle, not just the number of fields.

## 2. Declaring an @Embeddable Class

Suppose the system has multiple entities that need an address. We create an Address class:

~~~java
package com.example.customer.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.util.Objects;

@Embeddable
public class Address {

    @Column(name = "street", nullable = false, length = 150)
    private String street;

    @Column(name = "city", nullable = false, length = 100)
    private String city;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    protected Address() {
        // Constructor for JPA.
    }

    public Address(String street, String city, String postalCode) {
        this.street = requireText(street, "street");
        this.city = requireText(city, "city");
        this.postalCode = postalCode;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
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
            && Objects.equals(city, address.city)
            && Objects.equals(postalCode, address.postalCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, postalCode);
    }
}
~~~

A few points to note:

- **@Embeddable** marks the class as an embeddable type.
- Mapping annotations such as **@Column** can be declared directly on the embeddable's fields.
- A no-argument constructor with **public** or **protected** visibility is required so JPA can instantiate it.
- The example uses field access because annotations are placed on fields. If choosing property access, place mapping annotations consistently on getters.
- The class does not declare **@Id** and has no separate repository.
- **equals()** and **hashCode()** are based on the values forming the address. This is appropriate for immutable or rarely changing value objects.

JPA manages the state of the owning entity. When the entity is loaded, the embeddable is also restored as part of that entity.

## 3. Embedding with @Embedded

The Customer entity can use Address as follows:

~~~java
package com.example.customer.domain;

import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;

    @Embedded
    private Address address;

    protected Customer() {
    }

    public Customer(String fullName, Address address) {
        this.fullName = fullName;
        this.address = address;
    }

    public void changeAddress(Address newAddress) {
        if (newAddress == null) {
            throw new IllegalArgumentException("address must not be null");
        }
        this.address = newAddress;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Address getAddress() {
        return address;
    }
}
~~~

**@Embedded** marks an attribute of an embeddable type. With default mapping, the fields of Address are mapped as columns in the **customers** table. JPA does not require creating a separate Address table.

Schema visualization:

~~~text
customers
+----+-----------+----------------+------------+-------------+
| id | full_name | street         | city       | postal_code |
+----+-----------+----------------+------------+-------------+
|  1 | An Nguyen | 10 Le Loi      | Da Nang    | 550000      |
+----+-----------+----------------+------------+-------------+
~~~

Here:

- **Customer.id** is the primary key of the entity.
- **Address** has no primary key of its own.
- The columns **street**, **city**, and **postal_code** belong to the customer's row.
- Loading a Customer loads the Address values according to the entity's mapping.

This is an important point: **@Embedded** does not mean creating a child table. It embeds the attributes into the storage structure of the owning object.

## 4. Reusing the Same Embeddable Multiple Times

An order may have a billing address and a shipping address. Both use the Address type, but they cannot both map to the same default set of column names such as **street**, **city**, and **postal_code**. We need to rename the columns for each embedded attribute using **@AttributeOverride**.

~~~java
package com.example.order.domain;

import com.example.customer.domain.Address;
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "billing_street", nullable = false, length = 150)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "billing_city", nullable = false, length = 100)
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "billing_postal_code", length = 20)
        )
    })
    private Address billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "shipping_street", nullable = false, length = 150)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "shipping_city", nullable = false, length = 100)
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "shipping_postal_code", length = 20)
        )
    })
    private Address shippingAddress;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Address billingAddress, Address shippingAddress) {
        this.billingAddress = billingAddress;
        this.shippingAddress = shippingAddress;
    }
}
~~~

The corresponding schema may look like:

~~~text
orders
+----+----------------+--------------+---------------------+
| id | billing_street | billing_city | billing_postal_code |
+----+----------------+--------------+---------------------+

+-----------------+---------------+----------------------+
| shipping_street | shipping_city | shipping_postal_code |
+-----------------+---------------+----------------------+
~~~

**@AttributeOverride** changes the mapping of an attribute inside an embeddable at the embedding site. The **name** attribute is the Java attribute name in the embeddable class, such as **postalCode**; the **column.name** attribute is the database column name, such as **billing_postal_code**.

A few notes:

1. The name in **@AttributeOverride(name = ...)** must match the persistent attribute name of the embeddable, including case sensitivity.
2. When the same embeddable type is used multiple times in the same entity, override potentially conflicting column names.
3. Other attributes such as **nullable**, **length**, **precision**, or **scale** can also be overridden if the mapping at the embedding site needs to differ.
4. The override only affects that specific usage site; it does not change the default mapping of the Address class in other entities.

## 5. Nested Embeddables and Overriding Nested Attributes

An embeddable can contain another embeddable. For example, ContactInfo contains Address:

~~~java
@Embeddable
public class ContactInfo {

    @Column(name = "contact_email", length = 150)
    private String email;

    @Embedded
    private Address address;

    protected ContactInfo() {
    }

    public ContactInfo(String email, Address address) {
        this.email = email;
        this.address = address;
    }
}
~~~

An entity can embed ContactInfo:

~~~java
@Entity
@Table(name = "suppliers")
public class Supplier {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private ContactInfo contactInfo;

    protected Supplier() {
    }
}
~~~

The attributes of ContactInfo and Address are still mapped into the **suppliers** table. If you need to rename nested attributes, use a property path in **@AttributeOverride**:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "email",
        column = @Column(name = "primary_email", length = 150)
    ),
    @AttributeOverride(
        name = "address.street",
        column = @Column(name = "primary_street", nullable = false, length = 150)
    ),
    @AttributeOverride(
        name = "address.city",
        column = @Column(name = "primary_city", nullable = false, length = 100)
    ),
    @AttributeOverride(
        name = "address.postalCode",
        column = @Column(name = "primary_postal_code", length = 20)
    )
})
private ContactInfo primaryContact;
~~~

The path **address.street** means the **street** attribute inside the embedded **address** attribute of ContactInfo. This style is useful when the model has multiple nested value layers. If there are multiple nesting levels, the override name must reflect the full attribute path according to the embeddable structure.

Avoid nesting too many levels if it makes the mapping hard to read. An embeddable should group values with clear business meaning, such as Address, Money, Dimensions, or DateRange.

## 6. Difference Between @AttributeOverride and @AssociationOverride

**@AttributeOverride** changes the mapping of a basic attribute inside an embeddable. If an embeddable contains a relationship to another entity, **@AssociationOverride** may be needed to change the mapping of that relationship.

For example, an embeddable holding assignee information:

~~~java
@Embeddable
public class AssignmentInfo {

    @Column(name = "assigned_at")
    private Instant assignedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assignee_id")
    private Employee assignee;

    protected AssignmentInfo() {
    }
}
~~~

If an entity embeds AssignmentInfo but wants to use a different foreign key column name:

~~~java
@Embedded
@AssociationOverride(
    name = "assignee",
    joinColumns = @JoinColumn(name = "reviewer_id")
)
private AssignmentInfo reviewAssignment;
~~~

In this case:

- **assignedAt** is a basic attribute, overridden with **@AttributeOverride** if needed.
- **assignee** is an association to the Employee entity, overridden with **@AssociationOverride**.
- **joinColumns** specifies the new join column.

An embeddable can contain relationship mappings permitted by JPA, but the relationship is still managed within the context of the owning entity. That does not make the embeddable an independent entity.

## 7. Using an Embeddable in a Collection: @ElementCollection

When an entity has multiple value objects of the same type—for example, a customer has multiple delivery addresses—**@ElementCollection** can be used. Unlike a single **@Embedded**, a collection is usually stored in a separate collection table.

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;

    @ElementCollection
    @CollectionTable(
        name = "customer_addresses",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    private List<Address> deliveryAddresses = new ArrayList<>();

    protected Customer() {
    }
}
~~~

The storage tables may look like:

~~~text
customers
+----+-----------+
| id | full_name |
+----+-----------+

customer_addresses
+-------------+----------------+----------+-------------+
| customer_id | street         | city     | postal_code |
+-------------+----------------+----------+-------------+
~~~

Here **Address** is still an embeddable and has no separate entity ID. The collection table stores the Address values along with a foreign key pointing back to Customer. Do not confuse an **@ElementCollection** collection table with an independent entity table.

If each address needs to be referenced independently, has its own lifecycle, or needs its own repository, consider modeling Address as an entity and using a **@OneToMany** relationship instead of a value collection.

## 8. Value-Group Primary Key: @EmbeddedId

An application can use an embeddable as a composite primary key. In this case, use **@EmbeddedId** instead of a regular **@Embedded**.

For example, a key consisting of a warehouse code and a product code:

~~~java
@Embeddable
public class StockId implements Serializable {

    private String warehouseCode;

    private String productCode;

    protected StockId() {
    }

    public StockId(String warehouseCode, String productCode) {
        this.warehouseCode = warehouseCode;
        this.productCode = productCode;
    }

    // equals() and hashCode() based on both key components.
}
~~~

Entity:

~~~java
@Entity
@Table(name = "stock")
public class Stock {

    @EmbeddedId
    private StockId id;

    private Integer quantity;

    protected Stock() {
    }
}
~~~

Differences:

- **@Embedded** embeds a group of attributes into an entity.
- **@EmbeddedId** uses an embeddable as the composite primary key of an entity.
- **@EmbeddedId** still produces an entity with an identifier; the group of values in the embeddable is that identifier.

A composite key must implement **equals()** and **hashCode()** consistently based on the key components. Key values must remain stable after the entity is created and should not change during the persistence lifecycle.

Do not use **@EmbeddedId** merely to group fields neatly. If the group of fields is not a primary key, use regular **@Embeddable** and **@Embedded**.

## 9. Nulls and Lifecycle of an Embeddable

An embeddable has no independent identity, so its state is tied to the owning entity.

For example:

~~~java
Customer customer = new Customer();
customer.changeAddress(
    new Address("10 Le Loi", "Da Nang", "550000")
);
~~~

When Customer is persisted, the Address attributes are written along with the entity according to the mapping. When changing a field of an Address belonging to a managed entity, JPA can detect the change and synchronize it on flush.

~~~java
customer.getAddress().changeCity("Hue");
~~~

The snippet above assumes Address provides a **changeCity** method and Customer is managed within a transaction. No separate repository for Address is needed.

### Null embeddable

An **@Embedded** attribute can be assigned null if the mapping and business rules allow it. However, when all columns of an embeddable in a row are null, how the provider restores the embeddable value can depend on the mapping and provider. Therefore:

- If the value group is required, enforce invariants in the domain/Bean Validation and declare the necessary columns as NOT NULL in the schema.
- If the value group is optional, design the application to handle the null object case explicitly.
- Do not assume that merely using **@Embedded** will automatically give all child attributes default values.
- Test actual behavior with Hibernate and the project's database, especially when using nested embeddables or collections.

**@Embedded** does not have an **optional** attribute like **@ManyToOne(optional = ...)**. Whether a value group is required is typically expressed via domain invariants, Bean Validation, and column nullability.

## 10. Designing an Embeddable as a Value Object

An embeddable typically fits the value object model: two values are considered equal if their constituent attributes are equal, without needing a separate ID.

Example Money:

~~~java
@Embeddable
public class Money {

    @Column(name = "amount", precision = 12, scale = 2)
    private BigDecimal amount;

    @Column(name = "currency", length = 3)
    private String currency;

    protected Money() {
    }

    public Money(BigDecimal amount, String currency) {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("currency must be a 3-letter uppercase code");
        }
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Some design principles:

1. Group attributes that have a semantic relationship, not just because fields appear next to each other.
2. Keep constructors or factory methods to protect invariants.
3. Prefer an immutable design at the domain API level where appropriate; JPA still needs instantiation capability as specified by the provider.
4. Implement **equals()** and **hashCode()** by value if the application needs to compare value objects.
5. Avoid using mutable attributes as keys in a **HashMap** or elements in a **HashSet** after adding them to the collection.
6. Do not add a repository or a separate ID to an embeddable just to manipulate it more conveniently.

Note on money: **BigDecimal.equals()** compares both value and scale, so **new BigDecimal("10.0")** is not equal to **new BigDecimal("10.00")** via equals, even though **compareTo()** returns 0. If Money needs monetary value-based equality rules, normalize the scale/currency or implement equality intentionally.

## 11. Validation and Mapping on an Embeddable

Bean Validation constraints can be placed on an embeddable's attributes:

~~~java
@Embeddable
public class Address {

    @NotBlank
    @Size(max = 150)
    @Column(nullable = false, length = 150)
    private String street;

    @NotBlank
    @Size(max = 100)
    @Column(nullable = false, length = 100)
    private String city;

    protected Address() {
    }
}
~~~

Entity embedding Address:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @Embedded
    @Valid
    private Address address;

    protected Customer() {
    }
}
~~~

**@Valid** instructs Bean Validation to cascade into nested attributes when the validator processes Customer. For JPA lifecycle validation, the provider and validation integration must be configured appropriately; validation groups and lifecycle events also affect when checks run.

Do not confuse **@Valid** with **@Embedded**:

- **@Embedded** is a JPA mapping annotation specifying an embedded group of attributes.
- **@Valid** is a Bean Validation annotation requesting cascade validation into the nested object.

Both annotations can appear together because they serve two different responsibilities.

## 12. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Entity lacks expected table/columns | Embeddable is not embedded or schema does not match | Check **@Embeddable**, **@Embedded**, and migrations |
| Duplicate column names when embedding twice | Using the same default column names | Use **@AttributeOverrides** for each embedding site |
| Constructor not found | Embeddable lacks a suitable no-arg constructor | Add a **protected** or **public** constructor |
| Trying to inject AddressRepository | Confusing an embeddable with an entity | Manage via the owning entity or convert to an entity if an independent lifecycle is needed |
| Validation does not descend into nested object | Missing **@Valid** or provider/configuration issue | Check cascade validation and lifecycle integration |
| Object changes are not saved | Owning entity is detached or outside a transaction | Load a managed entity inside a transaction before modifying |
| Collection of value objects has no separate table | Using a single **@Embedded** instead of **@ElementCollection** | Choose mapping based on cardinality and lifecycle |
| Composite key behaves inconsistently | **equals/hashCode** omits components or key is mutated | Base on all key components and keep keys immutable |

## 13. Checklist for Using @Embeddable and @Embedded

- [ ] Confirm the field group is truly a value object belonging to the owning entity.
- [ ] Mark the class with **@Embeddable**.
- [ ] Declare a suitable no-argument constructor for JPA.
- [ ] Use **@Embedded** on the owning attribute.
- [ ] Check default column names and conflicts when embedding multiple times.
- [ ] Use **@AttributeOverride** for basic attributes whose mapping needs to change.
- [ ] Use **@AssociationOverride** when changing association mappings inside an embeddable.
- [ ] Use **@ElementCollection** if a collection of value objects is needed.
- [ ] Use **@EmbeddedId** only when the embeddable is truly a composite primary key.
- [ ] Clearly define nullability and behavior when the embeddable is null.
- [ ] Protect domain invariants and nested validation with **@Valid** when needed.
- [ ] Keep mappings synchronized with actual migrations/schema.
- [ ] Write tests to persist, load, and update entities containing embeddables.

## 14. Conclusion

**@Embeddable** defines a reusable group of attributes; **@Embedded** places that group of attributes into an owning entity or embeddable. Fields are usually mapped as columns in the owning object's table without needing a separate entity or repository. When embedding the same type multiple times, use **@AttributeOverride** to avoid column name conflicts; for associations, use **@AssociationOverride**.

Choose an embeddable when a group of values has no independent identity and lifecycle. Choose an entity when an object needs an ID, needs to be referenced, or needs to be managed separately. Making the right choice keeps the JPA model aligned with the domain and keeps mappings easy to reuse.
