# Impact of Inheritance, Field Hiding, and Lombok on Mapping

In **Spring Data Relational JDBC**, Spring maps a Java object to relational data based on type metadata, constructors, and persistent properties. Therefore, class structure directly affects which properties the framework discovers, how values are read/written, and which column names are used in generated SQL.

Three topics commonly cause confusion:

- **Inheritance:** properties declared on a superclass can become part of the mapped state of a concrete entity type. That does not mean Spring Data JDBC supports full table-inheritance strategies like JPA.
- **Field hiding:** a subclass declares a field with the same name as a field in the superclass. Java maintains two separate storage locations, yet mapping metadata has no natural, stable way to treat both as two distinct columns.
- **Lombok:** annotations can generate getters/setters, constructors, builders, `equals`/`hashCode`, and `toString`. Those generated members can affect how Spring Data instantiates objects and accesses properties, even though Lombok itself does not define SQL schemas.

Understanding these distinctions helps you design predictable entities, prevent instantiation errors, and avoid reading/writing data through an unintended property.

## 1. What Does Spring Data JDBC Map from a Class?

Spring Data JDBC uses mapping metadata from Spring Data Relational. Metadata describes:

| Component | Meaning for Mapping |
| --- | --- |
| Persistent entity | Java type stored/read as a relational entity, typically tied to a table |
| Persistent property | Property treated as data to be mapped |
| Constructor used to create objects | How the framework instantiates the class when reading a row |
| Property accessor | How values are read from or assigned to the object |
| Mapping annotations | Table/column names, keys, relationships, and mapping options |

Simple example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    private String email;

    protected Customer() {
    }

    public Customer(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }
}
```

In this example:

- `@Table("customer")` specifies the table.
- `@Id` marks the identifier key.
- `@Column("full_name")` specifies a column name differing from the Java property name `fullName`.
- `email` is mapped according to the naming strategy when no renaming annotation is present.
- The no-arg constructor is kept `protected` to support required instantiation scenarios; which constructor Spring Data selects still depends on object creation rules and the constructors present.

Spring Data JDBC does not simply scan every method in a class and turn it into a column. It builds metadata from the type, fields/properties, annotations, and mapping rules. Computed methods, utility methods, or properties marked transient do not automatically become columns.

## 2. Java Inheritance and Limits of Relational Mapping

Java allows a class to inherit fields and methods from a superclass:

```java
import java.time.Instant;

public abstract class AuditedRecord {
    private Instant createdAt;
    private Instant updatedAt;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}

@Table("customer")
public class Customer extends AuditedRecord {
    @Id
    private Long id;

    private String email;
}
```

In Java terms, `Customer` can read and use the inherited `createdAt` and `updatedAt`. Spring Data mapping metadata can treat inherited persistent properties as part of the concrete type's state, depending on access rules and framework metadata. If those properties are considered persistent, the concrete table's schema must contain the corresponding columns.

However, distinguish **code/property inheritance in Java** from **entity inheritance strategies in an ORM**:

- Java inheritance enables reusing fields and behavior.
- Relational/ORM inheritance consists of rules determining whether data for multiple subtypes is stored in one table, joined across multiple tables, or one table per subtype.

Spring Data JDBC does not provide a JPA-style entity inheritance model with `SINGLE_TABLE`, `JOINED`, `TABLE_PER_CLASS` strategies and automatic discriminators. Do not expect that merely defining an abstract superclass and subclasses will make the framework design schemas, auto-join tables, or instantiate subtypes based on a discriminator.

If using a superclass to share technical properties such as creation/update timestamps, each concrete aggregate root still needs an explicit table and schema. If a business model has multiple variants with different structures, consider composition, separate aggregate roots, or intentional custom mappings/queries.

### 2.1. Using a Superclass for Shared Properties

For example, multiple tables may share audit columns:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE supplier (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

A superclass can hold shared audit fields:

```java
import java.time.Instant;

public abstract class AuditedRecord {
    private Instant createdAt;
    private Instant updatedAt;

    protected AuditedRecord() {
    }

    protected AuditedRecord(Instant createdAt, Instant updatedAt) {
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }
}
```

Concrete classes declare their own tables and inherit from it:

```java
@Table("customer")
public class Customer extends AuditedRecord {
    @Id
    private Long id;
    private String email;
}

@Table("supplier")
public class Supplier extends AuditedRecord {
    @Id
    private Long id;
    private String companyName;
}
```

This is **Java structural reuse**. Each table's DDL must still include the matching audit columns; the superclass does not execute `ALTER TABLE` or generate schemas automatically.

Spring Data JDBC also provides auditing via annotations such as `@CreatedDate` and `@LastModifiedDate` when auditing configuration is enabled. If using auditing, configure the auditing/callback infrastructure properly rather than expecting a field named `createdAt` to be populated automatically just because it lives in a superclass.

### 2.2. When Modeling Multiple Subtypes

Suppose the domain has two payment method types:

```java
abstract class PaymentMethod {
    private String displayName;
}

class CardPayment extends PaymentMethod {
    private String lastFourDigits;
}

class BankTransfer extends PaymentMethod {
    private String bankCode;
}
```

Do not assume Spring Data JDBC will automatically:

1. Create a single table containing both `lastFourDigits` and `bankCode`.
2. Create a discriminator column to record the subtype.
3. Read the discriminator and instantiate `CardPayment` or `BankTransfer` when querying a `PaymentMethod`.

Those are behaviors typically associated with ORM inheritance strategies. In Spring Data JDBC, define the relational model explicitly: for instance, a single `Payment` aggregate with appropriate properties, or separate tables/aggregates with explicit relationships. If a polymorphic read model is needed, write custom queries/projections/converters to explicitly decide the Java type.

Composition often expresses a "has-a" relationship more clearly:

```java
public record PaymentDetails(
        String method,
        String providerReference,
        String maskedAccount
) {}

@Table("payment")
public record Payment(
        @Id Long id,
        Long orderId,
        PaymentDetails details
) {}
```

This is only a Java model sketch. To persist `PaymentDetails`, choose a mapping matching the schema, such as an embedded value object or explicitly declared columns; do not assume every nested object is automatically persisted into the same row. Spring Data JDBC provides relational annotations such as `@Embedded` for value objects and `@MappedCollection` for aggregate member collections; choose the right structure based on data semantics.

## 3. Field Hiding: Same Name, Two Storage Locations

In Java, fields are not overridden like methods. If a subclass declares a field with the same name as a superclass field, the subclass field **hides** the superclass field:

```java
class BaseRecord {
    protected String status = "BASE";

    String baseStatus() {
        return status;
    }
}

class OrderRecord extends BaseRecord {
    private String status = "ORDER";

    String orderStatus() {
        return status;
    }
}
```

The two `status` fields are two independent variables. When accessing a field directly, which one is picked depends on the declared type of the reference and visibility; when calling methods, override/dispatch rules differ.

Example:

```java
OrderRecord order = new OrderRecord();
System.out.println(order.orderStatus()); // OrderRecord's field: ORDER
System.out.println(order.baseStatus());  // BaseRecord's field: BASE
```

Both methods merely let you observe the two storage slots in the example; they do not change Java rules. The core point is that Java stores two separate fields rather than merging them into a single property.

### 3.1. Why Is Field Hiding Dangerous for Mapping?

Spring Data must build a set of persistent properties for an entity type. Yet two fields with the same name in one hierarchy raise ambiguous questions:

- Which column is `status` in the superclass?
- Which column is `status` in the subclass?
- Which field does getter `getStatus()` read?
- Which field does setter `setStatus(...)` write?
- If both are mapped, which column name and property metadata will the framework pick?

Exact outcomes can depend on mapping metadata, access strategy, and framework version. Do not rely on reflection ordering or expect the framework to automatically distinguish two identically named fields. A duplicated property name in a hierarchy is not a clean mapping design.

Example to avoid:

```java
abstract class BaseOrder {
    private String status;
}

@Table("customer_order")
class CustomerOrder extends BaseOrder {
    private String status; // Hides field with the same name
}
```

Even when annotating both fields with `@Column`, duplicated property names make metadata/access confusing and prone to unintended mappings. Annotations do not turn two Java fields into a supported relational inheritance model.

### 3.2. Rename to Express Distinct Meanings

If the two statuses truly represent different concepts, give them distinct names and distinct columns:

```java
abstract class BaseOrder {
    @Column("lifecycle_status")
    private String lifecycleStatus;
}

@Table("customer_order")
class CustomerOrder extends BaseOrder {
    @Column("approval_status")
    private String approvalStatus;
}
```

DDL:

```sql
CREATE TABLE customer_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    lifecycle_status VARCHAR(30) NOT NULL,
    approval_status VARCHAR(30) NOT NULL
);
```

Property names express two distinct business concepts; explicit column names keep the schema readable. If a subclass only wants to **change how the same state is represented**, override the appropriate method or use converters/intentional property access—do not introduce a second field with the same name.

### 3.3. Overriding a Getter Is Not Field Hiding

Methods can be overridden:

```java
class BaseRecord {
    protected String status;

    public String getStatus() {
        return status;
    }
}

class OrderRecord extends BaseRecord {
    @Override
    public String getStatus() {
        return status == null ? "NEW" : status;
    }
}
```

This is a valid method override. However, if mapping uses field access, the framework may read the field directly without running the getter logic. If mapping uses property access, the getter may be the read path. Therefore, do not write getters with side effects, time-dependent values, or return values differing from persisted data assuming every access strategy observes the same behavior.

## 4. Field Access vs. Property Access

Spring Data mapping supports accessing values through fields or JavaBean properties. By default, Spring Data's mapping infrastructure generally uses **field access**. You can select property access using `@AccessType(AccessType.Type.PROPERTY)` when getters/setters are genuinely needed as the access path.

Example choosing property access:

```java
import org.springframework.data.annotation.AccessType;

@AccessType(AccessType.Type.PROPERTY)
@Table("customer")
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
        this.email = email == null ? null : email.trim();
    }
}
```

When property access is chosen, getters/setters become part of the mapping contract. The setter in the example trims the string; thus the value after population may differ from the raw input. Do this only if it is the intended domain rule.

With field access, the framework can read/write fields directly without calling getters/setters. That is helpful when getters serve display formatting or setters contain side effects that should not run during data reads. Still, if you want a property excluded from mapping, use the proper transient annotation rather than merely hiding the getter.

`@AccessType` should be applied intentionally and consistently. When changing the access strategy, re-check which properties are mapped, which fields or getters carry annotations, and which constructor instantiates the object.

## 5. How Does Lombok Affect Object Mapping?

Lombok is an annotation processor that generates Java code at compile time. It can generate methods/constructors that do not appear directly in source code. Spring Data operates on compiled classes and mapping metadata, so you need to understand what Lombok actually generates.

| Lombok Annotation | Code Typically Generated | Possible Impact on Spring Data |
| --- | --- | --- |
| `@Getter` | Getters | Matters with property access or when application code needs getters |
| `@Setter` | Setters | Matters with property access; with field access, setters are not necessarily called |
| `@Data` | Getters, setters, `equals/hashCode`, `toString`, and required-args constructor | Can alter available constructors and method behavior; does not define SQL mapping |
| `@NoArgsConstructor` | No-arg constructor | Adds an instantiation option; check persistence constructor selection rules |
| `@AllArgsConstructor` | Constructor accepting all fields | Can introduce extra constructors and make constructor selection ambiguous if others exist |
| `@RequiredArgsConstructor` | Constructor for final fields and uninitialized `@NonNull` fields | Can be a suitable constructor for immutable objects, yet parameter names/order must be checked |
| `@Builder` | Builder API | Does not mean Spring Data JDBC will automatically use the builder to restore entities |
| `@SuperBuilder` | Builder supporting Lombok hierarchies | Helps construct objects via builder in application code; creates no relational inheritance strategy |
| `@Value` | Immutable class/fields, getters, and constructor | Usable with constructor-based mapping if constructor metadata aligns |
| `@With` | Copy method changing one property | Useful for immutable objects; check how property accessors use withers |

Lombok does not replace `@Table`, `@Column`, `@Id`, or mapping annotations. A class annotated with `@Data` still needs relational metadata matching the schema.

### 5.1. Lombok-Generated Getters and Setters

Example:

```java
@Getter
@Setter
@Table("customer")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;
}
```

With default field access, Lombok simply adds methods for Java callers; the presence of getters/setters does not automatically turn columns into different SQL names. If the class selects property access, generated getters/setters become part of how the framework accesses values.

Watch out for options such as `@Accessors(fluent = true)`: they can generate methods shaped like `email()`/`email(value)` instead of JavaBean `getEmail()`/`setEmail(...)`. Under property access, non-JavaBean accessor names can prevent properties from being discovered as expected. If property access is needed, use standard accessors or verify actual mapping metadata.

### 5.2. Auto-Generated Constructors Can Change How Spring Creates Objects

Spring Data must create an instance before populating remaining properties. It picks the persistence constructor according to Spring Data object mapping rules:

- A single constructor can be selected automatically.
- When multiple constructors exist, designate the persistence constructor with `@PersistenceCreator` if the framework cannot select unambiguously.
- For the chosen constructor, parameter names must match persistent properties so the framework supplies the right values.
- Immutable objects need a constructor receiving required values; mutable objects can be populated via accessors after creation.

Example immutable class with an explicit constructor:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {
    @Id
    private final Long id;
    private final String email;

    @PersistenceCreator
    public Customer(Long id, String email) {
        this.id = id;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

If Lombok adds extra constructors, verify which constructor Spring Data selects. For example, `@NoArgsConstructor` plus `@AllArgsConstructor` produces two constructors; do not rely on annotation ordering to guess which one is picked. Keep an explicit persistence constructor and annotate it with `@PersistenceCreator`.

### 5.3. `@Data` Is Not a Mapping Annotation

`@Data` is a Lombok shortcut bundling several features:

- Getters for fields.
- Setters for non-final fields.
- `equals` and `hashCode` based on fields.
- `toString`.
- Required-args constructor.

It **does not** automatically:

- Create tables or columns.
- Determine SQL names from the schema.
- Designate a primary key if `@Id` is missing.
- Create aggregate relationships or foreign keys.
- Make Spring Data JDBC use a builder.

In particular, `equals/hashCode/toString` generated across all eligible fields can pull in large relationships/collections, recurse through object graphs, or print sensitive data. That is not a SQL mapping rule, yet it can cause issues when logging entities, comparing objects, or storing entities in collections. For complex aggregates, consider writing these methods intentionally instead of using `@Data` blindly.

### 5.4. `@Builder` and `@SuperBuilder` Do Not Drive Spring Data

Example:

```java
@Getter
@Builder
@Table("customer")
public class Customer {
    @Id
    private Long id;
    private String email;
}
```

Application code can create an instance:

```java
Customer customer = Customer.builder()
        .email("an@example.test")
        .build();
```

A builder is a convenient creation API for developers. Spring Data JDBC does not default to calling `Customer.builder()` and setting each property merely because a class has `@Builder`. When reading rows from the database, Spring still uses constructors/property accessors per mapping infrastructure.

`@SuperBuilder` lets Lombok generate builders supporting class hierarchies when related superclasses are also annotated accordingly. That only addresses the Java construction ergonomics; it creates no discriminators, joins, or per-subclass tables in the database.

### 5.5. Immutable Classes and `@Value`

Immutable entities can work well when all needed data is passed through a constructor:

```java
import lombok.Value;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Value
@Table("customer")
public class Customer {
    @Id
    Long id;
    String email;
}
```

`@Value` creates an immutable class by Lombok conventions, with final fields, getters, and a constructor. Spring Data can use constructor-based materialization when constructor parameter names map to persistent properties. Verify compiler settings and constructor parameter metadata in the project; if multiple constructors exist or Lombok's generated constructor is not selected unambiguously, write an explicit constructor with `@PersistenceCreator`.

When the database generates a new ID, an immutable object may need to be recreated with the generated ID. Spring Data supports mechanisms for updating immutable objects within its mapping infrastructure, yet the specific design must match the framework version and constructor/wither style. Do not assume an arbitrary builder will be invoked to assign the ID.

## 6. Inheritance Combined with Lombok: Common Pitfalls

When using Lombok on both a superclass and subclass, multiple constructors and accessors can be generated without appearing explicitly in source code:

```java
@Getter
@NoArgsConstructor
abstract class BaseRecord {
    private String status;
}

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Table("customer_order")
class CustomerOrder extends BaseRecord {
    @Id
    private Long id;
    private String orderNumber;
}
```

Points to check:

1. The subclass constructor must be able to invoke a valid superclass constructor. If the superclass only has parameterized constructors, a Lombok-generated no-arg constructor in the subclass may fail to compile without an appropriate call.
2. If both superclass and subclass declare a field named `status`, field hiding still happens even though Lombok generates getters/setters.
3. `@AllArgsConstructor` on a subclass does not automatically accept all inherited fields the way you might expect; generated constructors depend on the fields of the annotated class. With hierarchies, inspect the actual code after annotation processing.
4. `@SuperBuilder` can support builders across hierarchies, yet it does not solve Spring Data mapping hidden fields.
5. Multiple constructors can make the persistence constructor ambiguous; mark the intended constructor explicitly.

To inspect what Lombok actually generates, use Lombok's *delombok* feature or view bytecode/decompiled classes in your IDE. Verify constructors, getters/setters, visibility, and parameter names rather than guessing from annotations alone.

## 7. Designing Easy-to-Map Entities

Practical guidelines:

### 7.1. Use Inheritance Sparingly

Inheritance fits when a superclass represents truly shared, stable properties and concrete tables can hold those columns. For example, audit metadata can be shared. Do not build hierarchies solely to imitate ORM strategies that Spring Data JDBC does not provide out of the box.

If a superclass holds state used by only a few subtypes, composition or separate entities are often clearer.

### 7.2. Never Hide Persistent Fields

Avoid:

```java
class Parent {
    private String code;
}

class Child extends Parent {
    private String code;
}
```

If they are two concepts, rename them to `parentCode` and `childCode` and map them to two separate columns. If you only want to change behavior, override methods or use intentional property access; never create duplicate field names.

### 7.3. Declare Important Mappings Explicitly

For schemas with special conventions, use `@Table`, `@Column`, and `@Id` to specify table/column/key names. Do not rely on Lombok or getter names to infer SQL names. For aggregate relationships, declare collection/back-reference mappings explicitly.

### 7.4. Keep Persistence Constructors Stable

For mutable classes, keep constructors simple alongside suitable accessors. For immutable classes, define a clear persistence constructor, use `@PersistenceCreator` when needed, and ensure parameter names map to properties. Whenever adding Lombok constructor annotations, re-verify constructor selection.

### 7.5. Use Lombok in Moderation

`@Getter`/`@Setter` can cut down boilerplate. For entities with invariants, avoid exposing public setters for every field purely out of convenience. For `@Data`, weigh the impact of `equals`/`hashCode`/`toString`. For builders, remember that builders serve application code, not the persistence mapping contract.

## 8. Combined Example: Entity with an Audit Superclass

A clean design can place audit fields in a superclass, use distinct field names, and define an explicit constructor:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

public abstract class AuditedRecord {
    @Column("created_at")
    private final Instant createdAt;

    @Column("updated_at")
    private final Instant updatedAt;

    protected AuditedRecord(Instant createdAt, Instant updatedAt) {
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}

@Table("customer")
public class Customer extends AuditedRecord {
    @Id
    private final Long id;

    @Column("email_address")
    private final String email;

    @PersistenceCreator
    public Customer(Long id, String email,
                    Instant createdAt, Instant updatedAt) {
        super(createdAt, updatedAt);
        this.id = id;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

Matching PostgreSQL schema:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

This example illustrates grouping audit fields in a superclass and declaring a concrete constructor that receives all properties. When applying in a real project, verify that the mapping metadata of the Spring Data JDBC version in use recognizes inherited properties and constructor parameters as intended. If using automatic auditing, add the appropriate auditing/callback configuration; this example does not auto-populate timestamps.

If Lombok is added, `@Getter` can reduce getter boilerplate, yet keeping an explicit persistence constructor is still wise when hierarchies and immutable fields make constructor selection critical. Do not add `@Data` merely to generate getters.

## 9. Investigating Inheritance/Lombok Mapping Errors

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Missing audit column when reading entity | Superclass property mapped yet DDL lacks matching column | Check inherited persistent properties and schema |
| Property value not as expected | Field hiding or getter/setter accesses a different field | Inspect both superclass/subclass and access strategy |
| Mapping produces one `status` value despite two fields | Duplicate property name in hierarchy | Eliminate field hiding; give properties/columns distinct names |
| Cannot instantiate entity on query | Unsuitable constructor, wrong private/protected visibility, or ambiguous multiple constructors | Check constructors and `@PersistenceCreator` |
| Constructor values swapped or null | Parameter names/order mismatch properties or parameter metadata unavailable | Check compiled parameter names and persistence constructor |
| Adding `@NoArgsConstructor` changes behavior | Framework picks a different instantiation path or final fields get default-initialized | Check constructor selection and post-population state |
| `@Builder` works in service yet DB read fails | Builders are not automatically used by Spring Data | Verify actual constructor/accessor mapping |
| Lombok getter not invoked | Mapping uses field access rather than property access | Check `@AccessType` and mapping metadata |
| Property disappears after `@Accessors(fluent = true)` | Accessor does not follow JavaBean convention under property access | Use standard accessors or field access |
| `toString()` causes overly long or recursive logs | `@Data` generates `toString` across multiple fields/relationships | Write controlled `toString` or use `@ToString.Exclude` |

When investigating, inspect in order:

1. **Actual compiled class after Lombok:** generated fields, constructors, getters/setters, and parameters.
2. **Mapping metadata:** persistent properties, column names, access type, and selected constructor.
3. **Schema:** actual tables/columns, nullability, data types, keys.
4. **Executed SQL:** which columns are queried/inserted/updated and the underlying JDBC exception.
5. **Framework version:** confirm behavior against the exact Spring Data Relational version in the dependency tree.

Do not look solely at annotated source code and assume the framework uses a specific constructor or getter.

## 10. Practice Exercises

**Exercise 1 — Inheriting audit fields.** Create an abstract class with `createdAt` and `updatedAt`, have `Customer` extend it, create a table with matching columns, and test reads/writes via a repository. Try removing one column from the schema to observe the failure.

**Exercise 2 — Field hiding.** Create a superclass and subclass both containing a `status` field. Observe values through references of each type and getters. Then rename them to `lifecycleStatus` and `approvalStatus`, mapping them to two separate columns.

**Exercise 3 — Lombok-generated constructors.** Try `@NoArgsConstructor`, `@AllArgsConstructor`, and `@RequiredArgsConstructor` on an entity. Use delombok or your IDE to inspect the resulting constructors; annotate an explicit persistence constructor when needed.

**Exercise 4 — Builder.** Create an entity with `@Builder` and use the builder in tests/services. Then load the same entity via a repository to distinguish the builder API from Spring Data's object creation mechanism.

**Exercise 5 — Field access vs. property access.** Compare ordinary getters/setters against `@AccessType(AccessType.Type.PROPERTY)`; add a setter that trims strings and observe values after reading from the database. Ensure intended behavior does not silently depend on the access strategy.

## 11. Things to Remember

Java inheritance helps share properties and behavior, yet it does not automatically create relational inheritance strategies. Field hiding creates two storage locations with the same name and makes mapping ambiguous; give properties distinct names. Lombok only generates Java code: getters/setters, constructors, and builders can influence access paths or object creation, yet they never replace SQL metadata. When an entity involves a hierarchy or immutable fields, the persistence constructor and access strategy must be explicitly defined, and the schema must match the actual persistent properties.

### References

- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): object creation, property population, constructors, and accessors.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): entity mapping, tables/columns, and relationships in Spring Data JDBC.
- [Project Lombok — @Data](https://projectlombok.org/features/Data): methods and constructors generated by `@Data`.
- [Project Lombok — Constructors](https://projectlombok.org/features/constructor): rules for constructor annotations.
- [Project Lombok — @Builder](https://projectlombok.org/features/Builder): builder generation.
- [Project Lombok — @SuperBuilder](https://projectlombok.org/features/experimental/SuperBuilder): builders for hierarchies.
