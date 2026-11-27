# Choosing Entity Inheritance or Object Composition

## Objectives

After this lesson, you can:

- Distinguish the "is-a" relationship of inheritance from the "has-a" relationship of object composition.
- Understand four common modeling approaches in JPA: entity inheritance, `@MappedSuperclass`, `@Embeddable`, and entity association.
- Choose the `SINGLE_TABLE`, `JOINED`, or `TABLE_PER_CLASS` strategy based on data structure and queries.
- Recognize the impact of discriminators, joins, nullability, cascades, and entity lifecycles.
- Design extensible models without creating rigid inheritance trees.
- Test mappings, polymorphic queries, and relationships between objects.

## 1. How Do Inheritance and Object Composition Differ?

Inheritance describes an "is a kind of" (is-a) relationship. For example:

- Car is a kind of Vehicle.
- CreditCardPayment is a kind of PaymentMethod.
- SavingsAccount is a kind of BankAccount.

Object composition describes a "has a" or "uses a" (has-a/uses-a) relationship. For example:

- Customer has an Address.
- PurchaseOrder has many OrderLines.
- Payment has a PaymentMethod.
- Product has a PricingPolicy.

In object-oriented design, inheritance allows a subclass to receive state and behavior from a superclass. Object composition allows an object to contain or reference other components, and then coordinate behavior through collaborators.

JPA provides multiple ways to map these structures to a database. Not every Java inheritance relationship needs entity inheritance, and not every shared data field needs a parent entity.

### Example of Model Selection

Suppose a sales system has multiple types of payment methods:

- CreditCardPayment has a card token number and a transaction reference code.
- BankTransferPayment has a bank code and a recipient account.
- CashPayment may have cashier information.

If all payment types share the identity, lifecycle, and behavior of PaymentMethod, and the application frequently queries "all payment methods", entity inheritance can make sense.

Conversely, if Customer has a shipping address, and the address is a value belonging to Customer without an independent lifecycle or identity, then `@Embeddable` is more appropriate.

If Customer has a Profile that can be managed, shared, or queried independently, using an association to another entity is clearer.

## 2. Entity Inheritance in JPA

Entity inheritance allows an entity class to inherit from another entity class. JPA supports three primary storage strategies:

1. `SINGLE_TABLE`: the entire hierarchy resides in one table.
2. `JOINED`: the parent class and each subclass have their own tables, joined by primary key.
3. `TABLE_PER_CLASS`: each concrete entity class has its own table, repeating inherited columns.

`@Inheritance` is declared on the root entity of the hierarchy. If no strategy is specified, JPA defaults to `SINGLE_TABLE`.

### 2.1. SINGLE_TABLE

All entities in the hierarchy are stored in the same table. A discriminator column distinguishes the entity type.

Example:

~~~java
package com.example.fleet;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;

@Entity
@Table(name = "vehicles")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "vehicle_type",
    discriminatorType = DiscriminatorType.STRING
)
public abstract class Vehicle {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String manufacturer;

    protected Vehicle() {
    }

    protected Vehicle(String manufacturer) {
        this.manufacturer = manufacturer;
    }

    public Long getId() {
        return id;
    }

    public String getManufacturer() {
        return manufacturer;
    }
}
~~~

Subclasses:

~~~java
@Entity
@DiscriminatorValue("CAR")
public class Car extends Vehicle {

    @Column(name = "seat_count")
    private Integer seatCount;

    protected Car() {
    }

    public Car(String manufacturer, int seatCount) {
        super(manufacturer);
        this.seatCount = seatCount;
    }

    public Integer getSeatCount() {
        return seatCount;
    }
}
~~~

~~~java
@Entity
@DiscriminatorValue("TRUCK")
public class Truck extends Vehicle {

    @Column(name = "load_capacity_kg")
    private Integer loadCapacityKg;

    protected Truck() {
    }

    public Truck(String manufacturer, int loadCapacityKg) {
        super(manufacturer);
        this.loadCapacityKg = loadCapacityKg;
    }

    public Integer getLoadCapacityKg() {
        return loadCapacityKg;
    }
}
~~~

The `vehicles` table may contain data like the following:

| id | vehicle_type | manufacturer | seat_count | load_capacity_kg |
|---:|---|---|---:|---:|
| 1 | CAR | Toyota | 5 | NULL |
| 2 | TRUCK | Volvo | NULL | 12000 |

**Advantages**

- Querying the entire hierarchy usually does not require joins.
- Reading a child entity can retrieve data from a single table.
- Simple structure, easy to understand, and often performs well for polymorphic queries.

**Limitations**

- Columns that apply only to a single subtype usually must allow NULL.
- The table can become wide as the number of subtypes and subtype-specific attributes grows.
- Difficult to enforce a simple NOT NULL constraint for a column that is only required in one subtype.
- Subtypes can cause the table to contain many sparsely used columns.

If you need to enforce subtype-specific attributes, you can use a CHECK constraint in a migration. For example, when `vehicle_type = 'CAR'`, `seat_count` must have a value; when it is TRUCK, `load_capacity_kg` must have a value. Do not rely solely on Java validation if the database also needs to protect data integrity.

### 2.2. JOINED

The root table stores shared attributes. Each subclass has its own table, using the same primary key as a foreign key referencing the parent table.

Example:

~~~java
@Entity
@Table(name = "payment_methods")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class PaymentMethod {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String ownerName;

    protected PaymentMethod() {
    }

    protected PaymentMethod(String ownerName) {
        this.ownerName = ownerName;
    }
}
~~~

~~~java
@Entity
@Table(name = "credit_card_payments")
@PrimaryKeyJoinColumn(name = "payment_method_id")
public class CreditCardPayment extends PaymentMethod {

    @Column(nullable = false, length = 80)
    private String cardToken;

    protected CreditCardPayment() {
    }

    public CreditCardPayment(String ownerName, String cardToken) {
        super(ownerName);
        this.cardToken = cardToken;
    }
}
~~~

~~~java
@Entity
@Table(name = "bank_transfer_payments")
@PrimaryKeyJoinColumn(name = "payment_method_id")
public class BankTransferPayment extends PaymentMethod {

    @Column(nullable = false, length = 30)
    private String bankCode;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(String ownerName, String bankCode) {
        super(ownerName);
        this.bankCode = bankCode;
    }
}
~~~

Conceptual data structure:

~~~text
payment_methods
---------------
id (PK)
owner_name

credit_card_payments
--------------------
payment_method_id (PK, FK -> payment_methods.id)
card_token

bank_transfer_payments
----------------------
payment_method_id (PK, FK -> payment_methods.id)
bank_code
~~~

**Advantages**

- Subtype-specific attributes reside in separate tables, making NOT NULL constraints easy to apply.
- Avoids an overly wide root table with many subtype columns.
- Relational structure aligns closely with a normalized model.

**Limitations**

- Querying a subtype usually requires joining the parent table and the child table.
- Polymorphic queries on the root may require multiple joins.
- Insert/update/delete operations involve more tables.
- Hierarchy migrations must keep primary keys/foreign keys consistent.

JOINED is suitable when subtypes have many distinct attributes and need clear data constraints, while the join cost is acceptable.

### 2.3. TABLE_PER_CLASS

Each concrete entity class has its own table and repeats inherited attributes. There is no mandatory shared table for the root entity.

Conceptual example:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Document {

    @Id
    private UUID id;

    private String title;
}
~~~

~~~java
@Entity
@Table(name = "invoices")
public class Invoice extends Document {

    private BigDecimal total;
}
~~~

~~~java
@Entity
@Table(name = "delivery_notes")
public class DeliveryNote extends Document {

    private LocalDate deliveredOn;
}
~~~

Both the invoices and delivery_notes tables contain inherited columns such as id and title, along with the subclass's own columns.

**Advantages**

- Each concrete subtype has an independent table.
- Querying a specific subtype does not require joining a parent table.
- Can be suitable when subtypes are stored and queried nearly independently.

**Limitations**

- Shared data is duplicated across multiple tables.
- Polymorphic queries through the root may have to combine data from multiple tables, typically using UNION.
- Foreign keys referencing an abstract root are not straightforward because there is no single root table.
- Key generation and polymorphic queries have portability limitations and provider/database dependencies.

Only choose TABLE_PER_CLASS when there is a clear reason and you have verified provider support, ID strategy, polymorphic queries, and referencing relationships. Do not choose it merely because you want each subtype to have its own table.

### Comparison of the Three Strategies

| Criterion | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Number of tables | One table for the hierarchy | Root table and one table per subtype | One table per concrete subtype |
| Polymorphic queries | Usually simple, no joins | Requires joins | May require UNION |
| Subtype columns | Many nullable columns | Located in child tables | Repeated in each table |
| NOT NULL constraints per subtype | Harder, usually requires CHECK | Easy to place on child tables | Easy to place on each table |
| Data writes | Usually one table | Multiple tables | One subtype table |
| Normalization | Less normalized | More normalized | Shared data duplicated |
| When suitable | Small hierarchy, frequent polymorphic queries | Many subtype-specific attributes, clear constraints needed | Independent subtypes and rare shared queries |

## 3. When to Use @MappedSuperclass?

Sometimes entities only need to share common mappings such as ID, creation time, update time, or creator. That does not mean they must be subtypes of the same entity in the domain.

`@MappedSuperclass` allows a parent class to provide mappings to child entities, while the parent class itself is not an entity and has no table of its own.

Example:

~~~java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
public abstract class AuditedEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    public Long getId() {
        return id;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Child entity inheriting the mapping:

~~~java
@Entity
@Table(name = "customers")
public class Customer extends AuditedEntity {

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }
}
~~~

The id and createdAt columns are mapped into the customers table. If Product also extends AuditedEntity, those columns will be mapped into the products table.

Use `@MappedSuperclass` when:

- You only want to reuse state and mappings.
- The parent class does not need polymorphic queries.
- The child classes are not truly subtypes of a shared domain entity.
- No JPA relationships need to reference the parent class.

You cannot write a JPQL query on AuditedEntity as a root entity because it is not an entity. You cannot declare a JPA association whose target entity is a mapped superclass.

## 4. When to Use Composition with @Embeddable?

Composition is usually appropriate when a piece of data is a value object: it holds values and belongs to its owning entity, without needing an independent identity.

For example, Address as a value object of Customer:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    @Column(name = "street", length = 160)
    private String street;

    @Column(name = "city", length = 100)
    private String city;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
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
}
~~~

Customer embedding Address:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private Address billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "shipping_street")
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "shipping_city")
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "shipping_postal_code")
        )
    })
    private Address shippingAddress;

    protected Customer() {
    }
}
~~~

The fields of Address are stored directly in the customers table. When embedding the same type twice, `@AttributeOverrides` renames the columns to avoid collisions.

A value object has no primary key of its own and is not queried as an independent entity. If Address needs to be shared, have its own lifecycle managed, be audited separately, or be referenced by multiple entities, consider modeling it as an entity instead of an embeddable.

### Collection of Value Objects

If an entity has a collection of values that do not need identity, you can use `@ElementCollection`:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_tags",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @Column(name = "tag", nullable = false)
    private Set<String> tags = new HashSet<>();

    protected Customer() {
    }
}
~~~

The tags are stored in a collection table and tied to the customer. They are not independent entities and do not have their own IDs. If each tag needs state, relationships, history, or independent management, create an entity.

## 5. When Does Composition Need an Association to Another Entity?

Not every composition uses `@Embeddable`. If a component object has its own identity or needs to be queried and referenced independently, use an association.

For example, Customer has a LoyaltyAccount:

~~~java
@Entity
@Table(name = "loyalty_accounts")
public class LoyaltyAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String accountNumber;

    protected LoyaltyAccount() {
    }
}
~~~

Customer can reference the account:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "loyalty_account_id", unique = true)
    private LoyaltyAccount loyaltyAccount;

    protected Customer() {
    }
}
~~~

This is an association between two entities with identities. If the account can live independently, do not arbitrarily set cascade REMOVE or orphanRemoval. If it is truly a dependent component of Customer, clearly define its lifecycle, ownership, and deletion behavior.

Composition in domain design is about object relationships and lifecycles. A JPA association is merely one way to map that relationship; cascade and orphanRemoval must accurately reflect business rules.

## 6. Choosing Inheritance or Composition?

Start from the domain model first, then choose annotations.

| Design Question | Entity Inheritance | Composition |
|---|---|---|
| Is the relationship truly "is-a"? | Yes, subtype is substitutable for base type | No subtype relationship needed |
| Are polymorphic queries on the parent class needed? | Can be very suitable | Usually queried via association or separate root |
| Do the types share the same identity and lifecycle? | Usually yes | Components can have separate lifecycles or just be values |
| Do shared attributes need a common table/identity? | Depends on inheritance strategy | Can use embedded or mapped superclass |
| Do behavioral variants need to be added at runtime? | Can make the class tree rigid | Easier to swap collaborators or policies |
| Data structure | SINGLE_TABLE, JOINED, or TABLE_PER_CLASS | Embedded columns, collection table, or related entity table |

### Selection Rules

- Choose entity inheritance when subtypes are a stable domain classification, can substitute for the base type, and the application needs polymorphic queries.
- Choose `@MappedSuperclass` when you only want to reuse common mappings without needing a root entity.
- Choose `@Embeddable` when the component is a value object without its own identity.
- Choose an association to another entity when the component has its own identity or independent lifecycle.
- Choose composition when you want to combine changeable behaviors, such as Payment using PricingPolicy or Notification using DeliveryChannel.
- Avoid creating an entity inheritance tree just to share a few fields or utility methods.

A good subtype must adhere to the base type's contract. If subtypes have differing required rules to the point where callers constantly have to check concrete types, the model may be misusing inheritance.

## 7. Queries and Polymorphic Relationships

With entity inheritance, JPQL can query the root entity and receive subtypes. Example:

~~~java
List<Vehicle> vehicles =
        entityManager.createQuery(
            "select v from Vehicle v",
            Vehicle.class
        ).getResultList();
~~~

If you need to filter by subtype, you can use `TYPE`:

~~~java
List<Vehicle> cars =
        entityManager.createQuery(
            "select v from Vehicle v where type(v) = Car",
            Vehicle.class
        ).getResultList();
~~~

Depending on the inheritance strategy, the SQL can be very different:

- SINGLE_TABLE filters by discriminator on a single table.
- JOINED needs to join the subtype table to construct the concrete entity.
- TABLE_PER_CLASS may have to combine results from multiple tables.

Do not decide based solely on the number of tables. Look at the main queries, record counts, frequency of root queries, and actual subtype data.

With composition, queries typically go through associations or projections. If you only need a few attributes of a component, you can use DTO projections to avoid loading the entire object graph.

## 8. Cascade, Lifecycle, and Aggregates

Inheritance does not determine cascades. Cascade belongs to association relationships between entities. Composition in the domain may suggest a dependent lifecycle, but it does not automatically mean you must use `CascadeType.ALL`.

Before enabling cascade or orphanRemoval, answer:

- Can the child component/entity exist if the parent is deleted?
- Can it be shared by multiple parents?
- Does independent history need to be preserved?
- Does removing it from a collection mean deleting the record?
- Is there an operation to move the component to another parent?

For example, OrderLine usually depends on PurchaseOrder, so cascade PERSIST and orphanRemoval can make sense. Product, referenced by many OrderLines, should not be deleted when one OrderLine is deleted.

For an aggregate, place business methods on the root to protect invariants. Do not let code in many places mutate collections or foreign keys directly and leave domain state inconsistent.

## 9. Design and Testing

For inheritance:

- Verify discriminator and subtype mappings.
- Verify NOT NULL/CHECK constraints for subtype-specific fields.
- Verify root queries return all subtypes.
- Verify joins and query counts for the JOINED strategy.
- Verify shared ID generators across tables in the hierarchy if required by the provider/database.

For composition:

- Verify value objects are persisted along with their owner.
- Verify `@AttributeOverride` produces the right column names when embedded multiple times.
- Verify collection tables and foreign keys.
- Verify the lifecycle of component entities and cascades.
- Verify lazy/eager associations according to use cases.

For all models:

- Run integration tests on the same database type planned for deployment, or Testcontainers if database-specific behavior must be confirmed.
- Verify the schema via migrations, not solely via auto-DDL.
- Check query counts to detect N+1 issues.
- Check API serialization to avoid object graph cycles.
- Measure critical queries before optimizing mappings.

## 10. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Entity inheritance tree becomes increasingly complex | Using inheritance for code reuse rather than subtype modeling | Extract value objects or collaborators using composition |
| SINGLE_TABLE table has many null columns | Many attributes apply to only one subtype | Consider JOINED or extracting into an association |
| Subtype queries are slow | JOINED requires joining many tables or TABLE_PER_CLASS requires UNION | Measure queries and reconsider strategy based on workload |
| Cannot query the parent class | Used @MappedSuperclass instead of a root @Entity | Use entity inheritance if polymorphic queries are needed |
| Embedded fields collide on column names | Embedded the same type multiple times without overrides | Use @AttributeOverrides |
| Deleting parent deletes shared entities | Misconfigured cascade REMOVE/orphanRemoval | Clarify actual ownership and lifecycle |
| Child entities are not loaded with parent | Inappropriate fetch plan | Use EntityGraph or query fetch tailored to the use case |
| API JSON infinite recursion | Bidirectional associations serializing back and forth | Use DTOs or explicit serialization configuration |

## Pre-Merge Checklist

- [ ] "Is-a" or "has-a" model is determined based on business domain.
- [ ] Entity inheritance is used only when shared subtypes and identity are needed.
- [ ] Inheritance strategy is chosen based on queries and data constraints.
- [ ] @MappedSuperclass is used only for shared mappings, without needing a root query.
- [ ] @Embeddable is reserved for value objects without their own identity.
- [ ] Associations are used when components are entities with separate identity/lifecycle.
- [ ] Cascade and orphanRemoval accurately reflect ownership.
- [ ] Polymorphic queries, fetch plans, and schema have been tested.
- [ ] No unexpected JSON cycles or N+1 queries exist.

## Conclusion

Entity inheritance is appropriate when child classes are genuinely subtypes of a root entity and need shared identity, lifecycle, or polymorphic queries. Composition is appropriate when combining value objects, shared mappings, or entity collaborators without creating a rigid inheritance tree. In JPA, `@Inheritance`, `@MappedSuperclass`, `@Embeddable`, and associations have different storage semantics; choose according to domain, queries, lifecycle, and database constraints. Test actual schemas and queries before finalizing the model.
