# Inheritance Mapping and Limitations Compared to JPA

In a Spring Data Relational R2DBC application, Java entities are mapped to relational tables through mapping metadata. Java lets a class inherit properties and behavior from a superclass, yet language-level inheritance does not mean the framework supports every inheritance mapping strategy found in JPA.

JPA is an ORM with its own entity inheritance model: an entity hierarchy can share a single table, span multiple joined tables, or use a separate table per concrete class. Spring Data Relational focuses on mapping aggregates and entities onto relational table structures; it does not provide the full suite of JPA inheritance mapping strategies.

Two ideas must be separated:

- **Inheritance in Java:** a subclass inherits fields and methods from a superclass to reuse models and behavior.
- **Inheritance in ORM:** the framework automatically determines how to store multiple entity types across one or more tables, resolves subtypes when reading data, and builds polymorphic queries.

Spring Data R2DBC can work with Java class models that have inherited properties, yet you should not expect `@Inheritance`, discriminators, or JPA annotations to create corresponding storage strategies. This lesson explains that boundary and how to model relational data when an application needs objects sharing common fields.

## 1. Java Class Inheritance and Relational Mapping Are Two Separate Concerns

Suppose an application has several account types. Every account has an identifier, owner name, and creation timestamp, while each type also has its own specific data.

You can use a superclass to gather shared properties:

~~~java
public abstract class BaseAccount {

    @Column("owner_name")
    private String ownerName;

    @Column("created_at")
    private LocalDateTime createdAt;

    // Constructor, getters
}
~~~

Concrete classes:

~~~java
@Table("savings_account")
public class SavingsAccount extends BaseAccount {

    @Id
    private Long id;

    @Column("interest_rate")
    private BigDecimal interestRate;
}
~~~

~~~java
@Table("checking_account")
public class CheckingAccount extends BaseAccount {

    @Id
    private Long id;

    @Column("overdraft_limit")
    private BigDecimal overdraftLimit;
}
~~~

In this model, subclasses inherit Java properties from `BaseAccount`. Each concrete class has its own `@Table`, so the data model intends a `savings_account` table for savings accounts and a `checking_account` table for checking accounts.

Spring Data mapping metadata is constructed for each persistent type and the properties recognized on that type, including inherited properties discovered in the class hierarchy. Those properties are mapped as properties of the concrete entity. This does not create a separate table for the superclass, does not generate joins between parent and child tables, and does not generate a discriminator to select subtypes.

When using property inheritance, verify mapping metadata and generated SQL on your project's exact Spring Data Relational version. In particular, avoid redeclaring a property with the same name in a subclass, as that can cause ambiguity during mapping.

## 2. How Does Spring Data Relational Map Entities to Tables?

A persistent entity is typically defined by a concrete Java type and its mapping metadata. `@Table` specifies the table, `@Id` specifies the identifier, `@Column` specifies the column, and other annotations describe property or relationship characteristics.

Example:

~~~java
@Table("employee")
public class Employee {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("department_code")
    private String departmentCode;
}
~~~

The `Employee` entity maps to the `employee` table. When a repository performs an insert, select, or update, Spring Data uses the entity's metadata to generate SQL and convert result rows into Java objects.

If `Employee` extends a Java class with persistent properties, those recognized properties can participate in `Employee`'s mapping like other properties. Nevertheless, the framework still maps the concrete entity to its own table.

For example, a superclass does not automatically become a table just because it has inherited properties:

~~~java
public abstract class Auditable {

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("updated_at")
    private LocalDateTime updatedAt;
}

@Table("employee")
public class Employee extends Auditable {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;
}
~~~

This model illustrates reusing audit properties in Java. The `created_at` and `updated_at` columns are treated as properties of `Employee` and reside in the `employee` table, provided the project version's mapping metadata recognizes inherited properties as expected.

This is property inheritance in the object model, not an inheritance mapping strategy with parent and child tables.

## 3. Which Inheritance Strategies Does JPA Support?

JPA defines three primary strategies via `@Inheritance`:

| JPA Strategy | How Data Is Stored |
|---|---|
| `SINGLE_TABLE` | Entire entity hierarchy stored in one table; a discriminator identifies the concrete type |
| `JOINED` | Superclass and subclasses have separate tables; subtype queries typically require joins |
| `TABLE_PER_CLASS` | Each concrete class has a table containing both inherited and specific columns |

JPA also provides `@MappedSuperclass` to share property mappings from a superclass without turning the superclass into an entity with its own table.

These mechanisms belong to JPA's ORM model. You cannot simply place those annotations on an R2DBC entity and expect Spring Data Relational to create the same structure or behavior.

### 3.1. SINGLE_TABLE

JPA example:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "account_type")
public abstract class Account {
    @Id
    private Long id;
    private String ownerName;
}

@Entity
@DiscriminatorValue("SAVINGS")
public class SavingsAccount extends Account {
    private BigDecimal interestRate;
}

@Entity
@DiscriminatorValue("CHECKING")
public class CheckingAccount extends Account {
    private BigDecimal overdraftLimit;
}
~~~

JPA can store both account types in a single `account` table. The `account_type` column indicates which subtype each row represents. Subtype-specific columns are typically nullable for the other type.

With Spring Data Relational, you can design a single-table approach explicitly: create an entity mapped to that table, declare the discriminator column as a regular property, and convert to the concrete domain type at the application layer. Spring Data R2DBC does not automatically apply `@DiscriminatorColumn` and `@DiscriminatorValue` like JPA.

### 3.2. JOINED

In JPA, the superclass has its own table containing shared columns. Each subclass has its own table containing specialized columns and a key linking back to the superclass row. Querying subtypes may require joining tables.

With Spring Data Relational, you can model these tables with separate entities and repositories, then run explicit join queries via SQL or `DatabaseClient`. Reading data and assembling domain objects must be written explicitly in the application. There is no automatic JPA-equivalent `JOINED` strategy.

### 3.3. TABLE_PER_CLASS

JPA can create a separate table for each concrete class and repeat inherited columns in each table. A query on the parent type may need to union data from multiple tables according to the provider's strategy.

With Spring Data Relational, you can create a separate entity for each concrete table. If the application needs to search across multiple types, write a combined query appropriate for the database or invoke separate repositories and merge results at the service layer. The framework does not automatically perform polymorphic queries across all hierarchy tables as in JPA's strategy.

### 3.4. Mapped Superclass

JPA uses `@MappedSuperclass` to declare shared properties inherited by child entities. The superclass has no table of its own and cannot be queried as a standalone entity.

In Spring Data Relational, sharing properties can be achieved with an ordinary Java superclass whose properties are recognized by the mapping framework on concrete entities. Do not treat `jakarta.persistence.MappedSuperclass` as a configuration annotation for R2DBC; JPA annotations do not replace Spring Data Relational metadata.

## 4. Limitations of Inheritance Mapping in Spring Data R2DBC

When moving from JPA to R2DBC, adjust expectations regarding what the framework handles automatically.

### 4.1. No JPA @Inheritance Strategies

Spring Data Relational does not provide `SINGLE_TABLE`, `JOINED`, or `TABLE_PER_CLASS` strategies through `@Inheritance` like JPA. The following annotations are not ways to configure inheritance mapping for R2DBC entities:

- `jakarta.persistence.Inheritance`
- `jakarta.persistence.InheritanceType`
- `jakarta.persistence.DiscriminatorColumn`
- `jakarta.persistence.DiscriminatorValue`
- `jakarta.persistence.MappedSuperclass`

If both JPA and R2DBC are on the classpath, mistakenly importing these annotations can let code compile while the annotations do not participate in the mapping metadata Spring Data Relational uses.

### 4.2. No Automatic Subtype Resolution via Discriminator Like JPA

An `account_type` column in the database is simply column data to normal mapping. It does not automatically make Spring Data R2DBC instantiate `SavingsAccount` or `CheckingAccount` when a repository reads a row into a parent type.

If polymorphism is needed, the application must decide how to read the discriminator, identify the subtype, and instantiate the corresponding object. This can be done via a shared storage entity, custom mapping/conversion, or queries and factories at the application layer.

### 4.3. No Automatic Join Generation for Class Hierarchies

Java inheritance does not cause Spring Data to join parent and child tables automatically. If the schema stores common attributes in one table and subtype attributes in another, the application must write an explicit join query using `DatabaseClient` or custom SQL, then map the result into a projection/DTO.

### 4.4. No JPQL-Style Polymorphic Queries

JPA has JPQL and an entity query model that allow querying a parent type and potentially including subtypes per the provider's inheritance strategy. Spring Data R2DBC typically uses derived queries on properties, `@Query` with SQL, or `DatabaseClient`.

Consequently, polymorphic queries across multiple tables must be designed around real SQL and the actual schema. You cannot port a JPQL query over an entity hierarchy verbatim to R2DBC without adaptation.

### 4.5. No Persistence Context or Lazy Proxies Like JPA ORM

JPA typically manages entities inside a persistence context, tracks changes, and can load associations lazily through proxies on access. Spring Data R2DBC does not provide JPA's persistence context, dirty checking, or lazy loading model.

The application must invoke necessary repositories or queries explicitly and compose results in a reactive pipeline. Having a Java property typed as a superclass or subclass does not cause database relationships to load automatically when a getter is called.

## 5. Reusing Common Properties with a Java Superclass

If the goal is simply to avoid repeating common fields like `id`, `createdAt`, `updatedAt`, or `tenantId`, a Java superclass can be a suitable choice.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;

public abstract class AuditableEntity {

    @Id
    private Long id;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("updated_at")
    private LocalDateTime updatedAt;

    protected AuditableEntity() {
    }

    protected AuditableEntity(
            Long id,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {
        this.id = id;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public Long getId() {
        return id;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Concrete entity:

~~~java
@Table("purchase_order")
public class PurchaseOrder extends AuditableEntity {

    @Column("order_number")
    private String orderNumber;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public PurchaseOrder() {
    }

    // Constructor and necessary getters
}
~~~

Here, `PurchaseOrder` still maps to a single `purchase_order` table. Audit properties are reused in Java code and mapped as properties of the concrete entity.

A shared superclass should focus on properties that share identical semantics and storage behavior across child entities. Avoid stuffing all persistence behavior into an overly large base class; different entities can have different lifecycles, primary keys, and storage rules.

### 5.1. Watch Out for Duplicate Property Names

Avoid redeclaring a property that already exists in the superclass:

~~~java
public abstract class BaseEntity {
    private String status;
}

@Table("shipment")
public class Shipment extends BaseEntity {
    private String status;
}
~~~

Two properties with the same name at different levels of the hierarchy can make mapping, constructor binding, or property access unpredictable. Choose a single definition or rename the separate property if they genuinely mean different things.

### 5.2. Constructors and Immutable Entities

If an entity uses constructors instead of setters, ensure Spring Data can instantiate the entity from mapped properties. You can use an appropriate constructor or `@PersistenceCreator` when you need to designate the constructor to use.

When properties live in a superclass, ensure the subclass constructor initializes all required state and that constructor parameters align with the property model. Verify materialization with integration tests on your project's framework version.

### 5.3. Non-Persistent Properties

If a superclass holds data solely for application logic, mark that property transient per Spring Data:

~~~java
import org.springframework.data.annotation.Transient;

public abstract class BaseEntity {

    @Transient
    private String displayLabel;
}
~~~

Do not use `@Column` on properties that are purely computed and do not exist in the schema.

## 6. Using Composition Instead of Inheritance to Share Data

Inheritance fits when entity types truly have an "is-a" relationship and share the same core property set. If you only want to group related data, composition is usually clearer.

For example, multiple entities have a contact address:

~~~java
public class Address {

    private String street;
    private String city;
    private String postalCode;
}
~~~

You can embed the value object in an entity using Spring Data Relational's `@Embedded`:

~~~java
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Embedded.Nullable
    private Address address;
}
~~~

`@Embedded` represents a value object's properties as part of the containing row, rather than creating an independent entity with its own identity. You can use a prefix when needed to avoid column name collisions among embedded properties, following the API of the Spring Data Relational version in use.

Composition helps the domain model clearly express a group of values sharing the same lifecycle as its containing entity. If an address has its own identity, is referenced by multiple aggregates, or has an independent lifecycle, consider modeling it as a table and appropriate relationship instead of embedding it.

## 7. Modeling a Single Table with a Discriminator Using Explicit SQL

If business logic requires multiple subtypes in one table, you can store a classification column as ordinary data.

Schema example:

~~~sql
CREATE TABLE payment_method (
    id BIGINT PRIMARY KEY,
    method_type VARCHAR(30) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    card_last_four VARCHAR(4),
    bank_account_number VARCHAR(100)
);
~~~

Shared storage entity:

~~~java
@Table("payment_method")
public class PaymentMethodRecord {

    @Id
    private Long id;

    @Column("method_type")
    private String methodType;

    @Column("display_name")
    private String displayName;

    @Column("card_last_four")
    private String cardLastFour;

    @Column("bank_account_number")
    private String bankAccountNumber;
}
~~~

The application layer can convert the record into a concrete domain model:

~~~java
public sealed interface PaymentMethod
        permits CardPayment, BankTransfer {
}

public record CardPayment(
        Long id,
        String displayName,
        String lastFourDigits) implements PaymentMethod {
}

public record BankTransfer(
        Long id,
        String displayName,
        String accountNumber) implements PaymentMethod {
}
~~~

A factory reads `methodType` and instantiates the subtype:

~~~java
PaymentMethod toDomain(PaymentMethodRecord record) {
    return switch (record.getMethodType()) {
        case "CARD" -> new CardPayment(
                record.getId(),
                record.getDisplayName(),
                record.getCardLastFour());
        case "BANK_TRANSFER" -> new BankTransfer(
                record.getId(),
                record.getDisplayName(),
                record.getBankAccountNumber());
        default -> throw new IllegalArgumentException(
                "Unsupported payment method type");
    };
}
~~~

This approach requires managing several details:

- Discriminator values must be constrained via enums, database constraints, or domain rules.
- Columns not applicable to the current subtype may be nullable, yet validity conditions must be clearly enforced.
- When adding a new subtype, update the schema if new columns are needed, along with the factory and tests.
- Never assume every discriminator value in the database is valid.
- When reading a list of multiple subtypes, read the records and map each one in the reactive pipeline.

The example only illustrates design; add constructors/getters, repositories, and validation appropriate for the application.

## 8. Modeling JOINED Style with Separate Entities and Queries

If you want to separate shared data and specialized data across multiple tables, you can represent that structure explicitly.

Example:

~~~sql
CREATE TABLE vehicle (
    id BIGINT PRIMARY KEY,
    manufacturer VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    vehicle_type VARCHAR(30) NOT NULL
);

CREATE TABLE car_detail (
    vehicle_id BIGINT PRIMARY KEY REFERENCES vehicle(id),
    door_count INTEGER NOT NULL
);

CREATE TABLE motorcycle_detail (
    vehicle_id BIGINT PRIMARY KEY REFERENCES vehicle(id),
    engine_capacity INTEGER NOT NULL
);
~~~

You can create separate entities for the base table and each detail table:

~~~java
@Table("vehicle")
public class VehicleRecord {

    @Id
    private Long id;

    private String manufacturer;
    private String model;

    @Column("vehicle_type")
    private String vehicleType;
}
~~~

~~~java
@Table("car_detail")
public class CarDetail {

    @Id
    @Column("vehicle_id")
    private Long vehicleId;

    @Column("door_count")
    private Integer doorCount;
}
~~~

When a complete vehicle object is needed, the service can read `VehicleRecord`, inspect `vehicleType` to query the appropriate detail table, and assemble the domain object. If better performance or consistency is required, write an explicit SQL join and map results into a projection/DTO.

Multi-table writes require a transaction when changes must succeed or roll back together. A reactive transaction can wrap the corresponding repository or `DatabaseClient` publishers, provided they share the same connection factory and transaction context.

This is explicit relational modeling. Spring Data R2DBC does not generate joins from Java class hierarchies like JPA `JOINED`.

## 9. Modeling TABLE_PER_CLASS with Separate Entities

If each subtype has its own table and shared fields are repeated in every table, you can turn each table into an independent entity.

Example:

~~~java
@Table("physical_product")
public class PhysicalProduct {

    @Id
    private Long id;

    private String name;

    @Column("shipping_weight")
    private BigDecimal shippingWeight;
}
~~~

~~~java
@Table("digital_product")
public class DigitalProduct {

    @Id
    private Long id;

    private String name;

    @Column("download_url")
    private String downloadUrl;
}
~~~

You can share Java interfaces or classes for domain behavior at the application layer, while each entity keeps its own repository and table mapping.

If you need a combined product list, use SQL `UNION ALL` with normalized columns and a discriminator, or query each repository and merge publishers. Keep pagination, sorting, and total counts in mind, because merging results from multiple tables in the application behaves differently from a single database query.

## 10. Aggregate Relationships and @MappedCollection

Spring Data Relational prioritizes the aggregate model: the aggregate root controls the lifecycle of objects belonging to the aggregate. For collections of child objects stored in separate tables, `@MappedCollection` describes how aggregate-owned relationships are mapped.

Example:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_number")
    private List<OrderLine> lines;
}
~~~

`OrderLine` is data belonging to the `PurchaseOrder` aggregate, not a subtype of `PurchaseOrder`. When saving the aggregate, Spring Data Relational manages collection elements according to the declared mapping.

Do not use `@MappedCollection` to emulate JPA inheritance. It describes the relationship between an aggregate root and elements managed in a collection. If child objects have independent lifecycles and ownership, select a relationship model and repository aligned with aggregate boundaries.

## 11. Comparing Spring Data R2DBC and JPA

| Capability | JPA | Spring Data Relational R2DBC |
|---|---|---|
| Java property inheritance | Yes | Can reuse mapped properties on concrete types |
| `@MappedSuperclass` | Yes | Does not use this JPA annotation as mapping metadata |
| `@Inheritance` | Yes | No equivalent inheritance strategy |
| `SINGLE_TABLE` with automatic discriminator | Yes | Must model and handle discriminator explicitly |
| Automatic `JOINED` | Yes | Requires explicit entities/join queries |
| `TABLE_PER_CLASS` | Yes | Use separate entities/tables and aggregate queries manually when needed |
| Persistence context | Yes | No JPA-style persistence context |
| Dirty checking | Yes | Typically explicit save/update calls |
| Lazy loading via proxy | Available | No JPA-style lazy proxies |
| JPQL | Yes | Uses SQL, derived queries, or `DatabaseClient` |
| Aggregate mapping | Not the sole focus | Core design focus of Spring Data Relational |

Spring Data R2DBC is a reactive relational data-access solution, not a reactive clone of the entire JPA ORM. Choosing R2DBC should be based on data-access patterns and non-blocking application requirements, accepting that some ORM conveniences must be expressed more explicitly.

## 12. Common Errors When Migrating from JPA to R2DBC

| Error | Why It Happens | Resolution |
|---|---|---|
| Keeping `@Inheritance` and expecting subtypes to persist automatically | Annotations belong to JPA ORM | Design tables and discriminators explicitly |
| Using JPA's `@MappedSuperclass` for R2DBC entities | Spring Data Relational does not use that annotation as mapping metadata | Use a plain Java superclass to reuse properties, then verify mapping |
| Expecting a parent-typed repository to read all subtypes automatically | No automatic polymorphic mapping like JPA | Read record/discriminator and map subtypes manually |
| Expecting the framework to join parent/child tables | Java inheritance does not create SQL relationships | Use SQL joins and explicit projection mapping |
| Copying JPQL verbatim into `@Query` | R2DBC's `@Query` works with SQL | Write SQL matching the schema and dialect |
| Expecting getters to lazy-load associations | R2DBC does not use JPA lazy proxies | Create query publishers for related data and combine results |
| Sharing one base repository for subtypes with different schemas | Tables may have distinct identifiers and properties | Use repositories tailored to concrete entities/tables |
| Assuming a superclass always maps to a table | Java inheritance and table inheritance are two separate concepts | Declare `@Table` explicitly and design the schema |

## 13. Workflow for Choosing a Model

When designing a system with multiple entity types sharing properties, start from the data structure and business lifecycle:

1. Determine whether the object types are truly subtypes of the same domain concept or merely happen to share a few fields.
2. If you only need to reuse properties such as audit fields, consider a plain Java superclass.
3. If a group of fields is a value object sharing the entity's lifecycle, consider composition and `@Embedded`.
4. If subtypes belong in one table, design a discriminator column and explicit record mapping.
5. If subtypes have separate detail tables, use separate entities/repositories and explicit join queries.
6. If each type has its own table and lifecycle, use independent entities; share interfaces or behavior at the domain/service layer.
7. Verify mapping metadata, generated SQL, and constructor materialization with integration tests.
8. Wrap multi-table writes in a reactive transaction when atomicity is required.
9. Never use JPA annotations as configuration for Spring Data R2DBC.

## 14. Key Takeaways

- Java class inheritance helps reuse properties and behavior; it does not automatically create table inheritance strategies.
- Spring Data Relational maps concrete entities to tables using the entity's mapping metadata and recognized properties.
- You can use a plain Java superclass to share properties, without treating it as JPA's `@MappedSuperclass` or `@Inheritance`.
- Spring Data R2DBC does not automatically provide JPA's `SINGLE_TABLE`, `JOINED`, or `TABLE_PER_CLASS` strategies.
- Discriminators, joins, and polymorphic queries must be designed and handled explicitly.
- Composition and `@Embedded` suit grouping value objects; `@MappedCollection` describes aggregate-owned elements, not inheritance.
- Every entity must use Spring Data Relational annotations rather than relying on `jakarta.persistence.*`.
- When migrating from JPA, adjust assumptions about persistence contexts, lazy loading, dirty checking, and JPQL.
- Choose the model based on schema, aggregate boundaries, and real queries; verify with integration tests on the target database.
