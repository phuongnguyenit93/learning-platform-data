# Impact of Primitive Types, Wrapper Types, and Null Values on Identity

In Spring Data Relational R2DBC, the Java type of an identifier property directly affects how the application represents a new entity, how Spring Data decides to execute INSERT or UPDATE, and how values are mapped to database columns. The difference between primitive types like `long` and wrapper types like `Long` is especially important because primitive types always have a default value, whereas wrapper types can be `null`.

For a database-generated primary key, `Long id` is usually a clear choice: a new entity has `id == null`; after a successful INSERT, Spring Data receives the generated identifier and populates it on the returned entity. With `long id`, the default value is `0`, so Spring Data must rely on the zero-value convention as a new-entity signal under the default strategy for primitive identifier properties. This convention has limitations if 0 is a valid identifier or if the application assigns IDs itself.

## 1. Identifiers in Spring Data Relational Entities

An entity typically has a property annotated with `@Id` so Spring Data knows the identifier column:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;
}
```

`@Id` here is the Spring Data annotation (`org.springframework.data.annotation.Id`). It tells the mapping layer which property represents the row's identifier in the table. When the repository performs `save`, Spring Data needs to know whether the entity already exists or is still a new entity to choose the appropriate save operation.

With `ReactiveCrudRepository`, the save API looks like:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

```java
Mono<Customer> result = customerRepository.save(customer);
```

`save` does not simply always perform INSERT or always perform UPDATE. Spring Data checks the entity's new/existing state using its newness detection strategy. The identifier type, its current value, and any `@Version` property can all influence that decision.

## 2. Primitive and Wrapper Types in Java

Java has primitive types such as `byte`, `short`, `int`, `long`, `float`, `double`, `boolean`, and `char`. Each has a default value when a field is unassigned:

| Primitive Type | Default Field Value |
|---|---:|
| `byte` | `0` |
| `short` | `0` |
| `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `boolean` | `false` |
| `char` | `\u0000` |

The corresponding wrapper types are `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `Boolean`, and `Character`. They are object references and therefore can hold `null`.

```java
private long primitiveId;  // Defaults to 0L
private Long wrapperId;    // Defaults to null

private int primitiveAge; // Defaults to 0
private Integer age;      // Defaults to null
```

This difference matters whenever an unprovided value must be distinguished from a valid value of 0 or `false`.

## 3. Why Is `Long` Usually Suitable for Auto-Generated IDs?

With a primary key automatically created by the database, an entity normally does not have an ID before INSERT. `Long` represents this state naturally:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }
}
```

When creating a new instance:

```java
Customer customer = new Customer("An");
// customer.getId() == null
```

The `null` value indicates that the application does not have an identifier yet. Under the default strategy without a version property, Spring Data treats an entity with a null ID as new. The repository can execute INSERT; if the database generates an ID, the R2DBC driver and Spring Data can retrieve the generated value and populate it on the returned entity.

```java
Mono<Customer> saved = customerRepository.save(customer)
    .doOnNext(value -> {
    // After INSERT succeeds, value.getId() can contain the database-generated ID.
    System.out.println(value.getId());
    });
```

Publishers are lazy: the save operation executes only when there is a subscriber. Therefore, compose `save` into the reactive pipeline or let the framework subscribe; do not read the ID immediately after calling `save` before completion.

Using `Long` does not mean the database allows a null primary key. Null is the state on the object side before saving. The database can still declare the ID column as `PRIMARY KEY` and `NOT NULL`; the database generates the real value during INSERT.

## 4. Default Behavior When Detecting New Entities

Spring Data needs a rule to distinguish a new entity from an already saved entity. Under the default metadata-based strategy, there are two points to understand:

1. If the entity has a `@Version` property, the version property takes precedence for determining newness.
2. If there is no version property, Spring Data inspects the identifier property.

For the property used to determine newness:

- A `null` value is treated as a signal for a new entity.
- If the property type is a numeric primitive, the default value `0` is used as a signal for a new entity.
- For a non-null reference type, Spring Data by default treats that value as a signal for an existing entity.

The second point explains why `long` and `Long` can lead to different outcomes even when both hold the numeric value 0.

### 4.1. Comparison Table of Primitive vs. Wrapper IDs

Suppose the entity has no `@Version` property and uses the default newness strategy:

| ID Declaration | Current Value | Default Interpretation |
|---|---:|---|
| `long id` | `0L` | New entity by primitive numeric zero convention |
| `long id` | `25L` | Existing entity |
| `Long id` | `null` | New entity |
| `Long id` | `25L` | Existing entity |
| `Long id` | `0L` | Non-null value, treated by default as an existing entity |

This is Spring Data's entity detection rule, not a SQL rule. The database does not understand 0 as meaning a new entity; it is a persistence-layer decision made before the statement is generated.

### 4.2. Why Is `Long` Equal to 0 Different from `long` Equal to 0?

The following two declarations have the same numeric value but different types:

```java
long primitiveId = 0L;
Long wrapperId = 0L;
```

With `long`, Spring Data recognizes that it is a primitive type and applies the zero-value convention. With `Long`, `0L` is a non-null object, so the default ID-based strategy treats it as an existing identifier.

This can cause surprises if the application creates a new entity with `new Customer(0L, ...)` for a `Long` field. If the ID is database-generated, leave the wrapper in the null state rather than assigning 0.

## 5. What Limitations Do Primitive IDs Have?

Example:

```java
@Table("customer")
public class Customer {

    @Id
    private long id;

    private String name;
}
```

When creating a new object, `id` defaults to `0`. Spring Data can use that value to detect a new entity. This approach can work when the system guarantees 0 is never a valid ID and the database generates positive IDs.

However, it has limitations:

- Cannot represent an unassigned ID state using `null`.
- Cannot distinguish an unassigned ID from a real ID equal to 0.
- If the application uses assigned keys and 0 is a valid value, the default strategy may treat the entity as new.
- If code accidentally sets 0 on an existing entity, `save` may take the INSERT branch instead of UPDATE.
- When mapping a nullable column to a primitive field, Java cannot preserve the SQL NULL state.

Therefore, for database-generated IDs, the wrapper type `Long` usually expresses intent more clearly. Use a primitive only when the ID convention and the application's newness strategy genuinely fit.

## 6. Null Values and Nullable Database Columns

Java `null` and SQL `NULL` are related, though not identical to new-entity state.

- `null` in Java is an object reference that points to no object.
- `NULL` in SQL represents an unknown or missing value in a column.
- A null ID on an entity is typically used by Spring Data as a signal for a new entity.
- A primary key column in a database is normally not allowed to contain SQL NULL.

A wrapper field can represent both concrete values and the state of having no value yet:

```java
private Integer retryCount; // Can be null, 0, 1, 2, ...
private Boolean verified;   // Can be null, true, or false
```

Meanwhile:

```java
private int retryCount;     // Cannot be null
private boolean verified;   // Cannot be null
```

If a database column allows NULL and business logic needs to distinguish "undetermined" from 0 or false, use wrapper types. For example, `verified = null` can mean not checked yet, `false` means checked and not verified, and `true` means verified.

With primitive fields, Java has no null state. Depending on the mapping path and converter, a SQL NULL value may be converted to a default value or raise an error during assignment/conversion. Do not rely on that default behavior to express business logic. Use wrappers or define the column as NOT NULL with an appropriate default value.

## 7. Null Does Not Mean Zero

In Java:

```java
Long idA = null;
Long idB = 0L;

System.out.println(idA == null); // true
System.out.println(idB == null); // false
```

In SQL, `NULL` is also not equal to 0. A `column = NULL` condition cannot check for null values because SQL uses three-valued logic. You must use `IS NULL`:

```sql
SELECT id, name
FROM customer
WHERE external_code IS NULL;
```

Do not write:

```sql
-- Not the way to check for SQL NULL.
SELECT id, name
FROM customer
WHERE external_code = NULL;
```

If using `DatabaseClient` to bind a null parameter, you must specify the Java type for the driver:

```java
databaseClient.sql("""
        SELECT id, name
        FROM customer
        WHERE external_code IS NULL
        """)
    .map((row, metadata) -> {
        Customer customer = new Customer(row.get("name", String.class));
        customer.setId(row.get("id", Long.class));
        return customer;
    })
    .all();
```

If you truly need to bind null in a SQL expression, you can use `bindNull("parameter", String.class)` with the corresponding type. However, for null filtering conditions, `IS NULL` is usually the clearest approach. Using `column = :value` with a null value does not have the same semantics as `column IS NULL`.

## 8. A Wrapper Type Does Not Automatically Mean ID Generation

`Long id` can be null, but the data type alone does not make the database generate an ID. ID generation depends on the schema, the database's ID strategy, the driver, and the INSERT operation.

PostgreSQL table example:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
```

Entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;
}
```

When the ID is null and the entity is detected as new, Spring Data R2DBC can execute INSERT using the driver/database's generated-values mechanism and update the ID on the returned entity.

```java
Mono<Customer> create(String name) {
    Customer customer = new Customer(name);

    return customerRepository.save(customer)
        .doOnNext(saved -> {
            // ID is checked after the INSERT operation completes.
            System.out.println("Generated id: " + saved.getId());
        });
}
```

Do not assign `0L` to a wrapper ID intending to ask the database to auto-generate it. Under the default strategy, a non-null `Long` can cause the entity to be treated as existing and take the UPDATE branch.

In addition, `@GeneratedValue` is a familiar annotation from JPA. Spring Data Relational R2DBC does not rely on JPA's `@GeneratedValue` to determine key generation the way JPA does. Use `@Id`, schema configuration, and the generated-values mechanisms supported by Spring Data R2DBC and the driver.

## 9. Assigned IDs vs. Database-Generated IDs

There are two common ways to supply IDs:

| ID Provisioning Style | Example | New Entity State |
|---|---|---|
| Database-generated | Identity/sequence issued by the database | ID is usually null before INSERT |
| Application-assigned | UUID or business code created in the application | ID may already be present before INSERT |

With database-generated IDs, `Long id = null` is the natural approach. With application-assigned IDs, an entity can have an ID as soon as it is created. Under the default ID-based strategy, a non-null ID can cause the entity to be treated as existing even though the record has never been inserted.

Example:

```java
@Table("external_customer")
public class ExternalCustomer {

    @Id
    private String id;

    private String name;
}
```

If the application creates a UUID/string ID before saving, `id` is already non-null. There must be an appropriate way to determine newness so that the first save performs an INSERT.

### 9.1. Using Persistable When Controlling Newness Is Needed

Spring Data supports `Persistable<ID>` so an entity can provide its own new state via `isNew()`:

```java
import org.springframework.data.domain.Persistable;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Table;

@Table("external_customer")
public class ExternalCustomer implements Persistable<String> {

    @Id
    private String id;

    private String name;

    @Transient
    private boolean newEntity = true;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
```

When the entity is newly created in the application, `newEntity` can be true so `save` chooses INSERT even though the ID is already assigned. After INSERT succeeds, the application must switch the flag to false. When the entity is loaded from the database, the flag must also be set to false via an appropriate factory or lifecycle callback. Forgetting this step can cause a loaded entity to keep reporting `isNew() == true` and be inserted again.

Illustrative example marking the entity after a successful save:

```java
Mono<ExternalCustomer> saveNew(ExternalCustomer customer) {
    return repository.save(customer)
        .doOnNext(ExternalCustomer::markPersisted);
}
```

This snippet only handles the flag after saving. In a complete application, make sure entities constructed from database rows are also initialized with `newEntity = false`, for instance via a callback/factory mechanism appropriate for your Spring Data Relational version. `@Transient` ensures this flag does not become a database column.

Do not implement `Persistable` if the default ID strategy already expresses entity state accurately. It is a tool for cases where the ID is pre-assigned or business newness rules differ from the default.

## 10. Impact of `@Version` on New-Entity Detection

If an entity has a `@Version` property, Spring Data prioritizes the version property when determining new/existing state. This matters for optimistic locking as well as entities with assigned IDs.

Example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;
}
```

With a wrapper version, `version == null` signals a new entity under the default strategy. After saving, Spring Data manages the version according to the optimistic locking mechanism. With a primitive version, the value 0 signals a new entity under the primitive convention.

| Version Property | Value | Default Newness |
|---|---:|---|
| `Long version` | `null` | New |
| `Long version` | `0L` | Existing by null check |
| `long version` | `0L` | New by primitive convention |
| `long version` | `3L` | Existing |

When `@Version` is present, do not look solely at the ID to conclude whether `save` will INSERT or UPDATE. An entity with an assigned ID can still be treated as new if the version is in the state representing a new entity.

For entities using optimistic locking, do not set the version arbitrarily. Let Spring Data manage the version according to mapping and database rules, and handle optimistic locking errors when data has been updated by another transaction.

## 11. Which ID Type Should You Choose?

Choose the ID type based on how IDs are provisioned and your data rules:

| Java Type | Can Represent Null | Usually Suitable When | Notes |
|---|---|---|---|
| `Long` | Yes | Database-generated numeric ID | Widely recommended for generated IDs; null indicates no ID yet |
| `long` | No | System uses 0 as sentinel and 0 is not a valid ID | Cannot distinguish null from zero |
| `Integer` | Yes | Small numeric ID or nullable numeric field | Can be null before insert |
| `int` | No | Numeric field always has a value and zero convention is clear | Unsuitable when representing an absent state |
| `UUID` | Yes | ID created in application or database | ID is often already present before INSERT if generated by application |
| `String` | Yes | Business code or string-form identifier | Assigned IDs require an appropriate newness strategy |

For auto-incrementing numeric primary keys, `Long` is a straightforward choice because no zero convention is needed. For UUIDs, `UUID` is usually clearer than `String` if the schema and driver support a UUID type. For business codes, `String` can be appropriate, though newness must be handled if codes are issued before saving.

## 12. Wrappers and Null for Non-ID Properties

The primitive/wrapper distinction also affects other properties in an entity:

```java
private int retryCount;
private Integer retryLimit;
private boolean active;
private Boolean verified;
```

These cases carry different meanings:

- `retryCount = 0`: current retry count is 0.
- `retryLimit = null`: no retry limit configured yet.
- `active = false`: state is explicitly inactive.
- `verified = null`: no verification outcome yet.

If business logic needs to distinguish "unknown" from false, `Boolean` is more appropriate than `boolean`. If the `retry_limit` column allows NULL, `Integer` preserves the distinction between unconfigured and a limit of 0.

Conversely, if a column is always `NOT NULL` and the database has a clear default, a primitive may be suitable. Java types and schema nullability should align with business rules, avoiding accidental nulls or unintended default values.

## 13. Interacting with DatabaseClient and Binding Null

When using a repository or `R2dbcEntityTemplate`, Spring Data mapping handles converting entity properties to database values. When using `DatabaseClient`, the application binds parameters directly and must handle null explicitly.

Parameter-binding example:

```java
DatabaseClient.GenericExecuteSpec spec = databaseClient.sql("""
        INSERT INTO customer(name, external_code)
        VALUES (:name, :externalCode)
        """)
    .bind("name", name);

if (externalCode == null) {
    spec = spec.bindNull("externalCode", String.class);
} else {
    spec = spec.bind("externalCode", externalCode);
}

Mono<Long> inserted = spec.fetch().rowsUpdated();
```

R2DBC binding needs to know the data type when a value is null. You cannot call `.bind("externalCode", null)` as a normal value; use `.bindNull(...)` with the appropriate type. This example assumes the `external_code` column allows SQL NULL.

If a column is a database-generated primary key, there is normally no need to bind null into the ID column in an INSERT statement. The statement should let the database apply its ID generation mechanism using syntax supported by that database. `@Id` on the entity and Spring Data's insert strategy handle this automatically in repositories and templates.

## 14. Common Errors Related to ID and Null

| Error | Why It Happens | How to Fix |
|---|---|---|
| Using `long` for ID when needing to distinguish unassigned ID from ID 0 | Primitives cannot be null | Use `Long` or a clear newness convention |
| Using `Long id = 0L` for a new entity | Non-null wrapper may default to being treated as existing | Leave ID null if the database generates keys |
| Using an assigned ID without customizing newness | Non-null ID causes entity to be treated as existing | Use `Persistable` or an appropriate version strategy |
| Treating `0` and `null` as identical | Java and SQL distinguish the two values | Design data types and SQL conditions with proper semantics |
| Using a primitive for a nullable column | Primitives cannot hold SQL NULL | Use a wrapper or change schema to NOT NULL |
| Expecting JPA `@GeneratedValue` to control R2DBC | Annotation belongs to Jakarta Persistence | Use `@Id`, schema, and R2DBC generated-value support |
| Reading ID right after calling `save` | Reactive publisher may not have executed yet | Read ID from the entity emitted after `save` completes |
| Checking only ID when `@Version` is present | Version takes precedence in newness detection | Check version state as well |
| Using `column = NULL` in SQL | Comparing with NULL never evaluates to true | Use `IS NULL` or `IS NOT NULL` |
| Using `Persistable` without updating the flag after load/save | Existing entity may still report `isNew()` | Manage the flag via an appropriate factory/callback/lifecycle |

## 15. Combined Examples: Database-Generated ID vs. Assigned ID

### 15.1. Database-Generated ID

Schema:

```sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
```

Entity:

```java
@Table("product")
public class Product {

    @Id
    private Long id;

    private String name;

    public Product(String name) {
        this.name = name;
    }
}
```

Create and save:

```java
Mono<Product> createProduct(String name) {
    return productRepository.save(new Product(name));
}
```

The initial `id == null` state helps Spring Data detect the new entity. The database assigns the ID, and the save result returns the entity with the ID populated after INSERT succeeds.

### 15.2. Application Pre-Assigned ID

Suppose the application creates the code `CUS-2026-001` before saving. The ID is non-null from the start, so new entities must be detected by another mechanism if no suitable version property exists.

```java
@Table("external_customer")
public class ExternalCustomer implements Persistable<String> {

    @Id
    private String id;

    private String name;

    @Transient
    private boolean newEntity = true;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        newEntity = false;
    }
}
```

When creating a new object, `isNew()` returns true. After a successful save, mark the entity as existing. When loading the entity from the database, the initialization/callback mechanism must also set `newEntity` to false. This is the responsibility of the `Persistable` implementation; it does not happen automatically just because `@Transient` is present.

## 16. Design Principles

- For numeric database-generated IDs, prefer a wrapper like `Long` to represent the unassigned-ID state as null.
- Do not use `0L` for a new wrapper ID when relying on the default newness strategy.
- Use a primitive ID only when the zero-value convention is a valid sentinel and cannot collide with real data.
- Distinguish Java null, SQL NULL, and numeric 0; they have different semantics.
- Use wrappers for nullable columns or when business logic needs to distinguish "unknown" from a default value.
- If an entity has `@Version`, consider the version when determining newness because version takes precedence in the default strategy.
- For assigned IDs, consider `Persistable<ID>` or a version property to control new/existing state.
- If using `Persistable`, manage the `isNew` state both after successful insert and after loading the entity.
- Do not use JPA `@GeneratedValue` as an ID generation mechanism for Spring Data Relational R2DBC.
- With `DatabaseClient`, bind nulls using `bindNull` and the appropriate type; in SQL, use `IS NULL` to check for NULL.
- Verify save behavior with integration tests against a real database and driver, covering generated IDs, assigned IDs, insert, update, and optimistic locking.

Primitive and wrapper types are not merely a matter of Java syntax. They determine whether null can be represented and can change how Spring Data detects new entities. When you choose the right ID type, understand version/newness rules, and align nullability between Java and the schema, applications avoid wrong-branch INSERT/UPDATE calls, preserve the meaning of 0, and handle database-generated or application-assigned identifiers clearly.
