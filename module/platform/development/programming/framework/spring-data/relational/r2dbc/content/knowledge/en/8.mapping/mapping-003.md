# Mapping Properties to Columns with @Column

In Spring Data Relational R2DBC, a Java entity describes the data the application works with, while database tables and columns follow the designed relational structure. Java property names do not always match physical column names. For example, the application might have a `firstName` property while a legacy table names the column `FIRST_NM` or `customer_name`.

The `@Column` annotation lets you explicitly declare the column name that an entity property maps to. Using mapping metadata, Spring Data R2DBC can generate the appropriate SQL statements when reading, inserting, or updating an entity. This annotation is especially useful when integrating with an existing schema, following a naming convention different from Java, or handling irregular column names.

This lesson covers the placement and usage of `@Column`, its relationship with the naming strategy, how the annotation affects generated SQL, how to handle special identifiers, and cases where `@Column` does not substitute for schema definitions or custom conversions.

## 1. Role of @Column

`@Column` is a Spring Data Relational annotation used to specify the column name corresponding to a persistent property in an entity. With R2DBC, the annotation resides in the package:

~~~java
import org.springframework.data.relational.core.mapping.Column;
~~~

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("customer_name")
    private String name;

    @Column("email_address")
    private String email;

    // Constructor, getters and setters
}
~~~

The entity above maps to the `customer` table. The Java property `name` is stored in the `customer_name` column; the `email` property is stored in the `email_address` column.

When Spring Data generates SQL statements for an entity, it uses mapping metadata to determine table names, column names, primary keys, and properties to write. As a result, Java code can keep readable names like `name` or `email` while the database maintains column names following its own convention.

`@Column` does not rename the property in Java. It only describes how the property maps to the relational structure.

## 2. Distinguishing @Column from Other Mapping Annotations

Mapping annotations each have distinct responsibilities:

| Annotation | Responsibility |
|---|---|
| `@Table` | Identifies the relational table that the entity maps to |
| `@Id` | Marks the identifier/primary key property |
| `@Column` | Identifies the column corresponding to the property |
| `@Transient` | Marks a property that is not stored as persistent data |
| `@Version` | Marks the version property used for optimistic locking |

Combined example:

~~~java
@Table("customer_account")
public class CustomerAccount {

    @Id
    private Long id;

    @Column("account_number")
    private String accountNumber;

    @Column("available_balance")
    private BigDecimal balance;

    @Version
    private Long version;

    @Transient
    private String displayLabel;
}
~~~

In this example, `id` is the primary key, `accountNumber` and `balance` map to two specifically named columns, `version` supports detecting concurrent updates, and `displayLabel` is only for application use.

Do not use `@Column` to declare the table name or primary key. Table names belong to `@Table`; identifiers belong to `@Id`.

## 3. Default Naming Rules and Naming Strategy

Not every entity needs `@Column` declared on every property. Spring Data Relational uses a naming strategy to convert domain property names into column names when no name is explicitly specified.

With the default naming strategy commonly used in Spring Data Relational, camelCase property names are converted to snake_case:

| Java Property | Default Convention Column Name |
|---|---|
| `firstName` | `first_name` |
| `createdAt` | `created_at` |
| `phoneNumber` | `phone_number` |
| `orderStatus` | `order_status` |

Example:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String firstName;

    private LocalDateTime createdAt;
}
~~~

When the naming strategy converts according to the rule above, `firstName` maps to `first_name` and `createdAt` maps to `created_at`. You can omit annotations for columns that already follow that convention.

However, the actual schema might use different names:

| Java Property | Column Name in Legacy Schema |
|---|---|
| `firstName` | `FIRST_NM` |
| `createdAt` | `created_timestamp` |
| `phoneNumber` | `tel_no` |

In that case, declaring explicitly with `@Column` ensures mapping does not depend on whether the naming strategy can derive the column name:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("FIRST_NM")
    private String firstName;

    @Column("created_timestamp")
    private LocalDateTime createdAt;

    @Column("tel_no")
    private String phoneNumber;
}
~~~

The name in `@Column` is the column name according to the schema used by the database. Check the actual name in the database and the database system's case rules, especially when the schema has identifiers created with quotes.

### 3.1. When Should You Declare Explicitly?

Use `@Column` when:

- The column name differs from what the default naming strategy produces.
- Integrating with a legacy schema or a schema managed by another system.
- The column name is an SQL keyword or requires special quoting rules.
- You want to make an important mapping explicit directly in the entity.
- Database conventions require abbreviations or custom prefixes.

If the entire schema consistently follows the naming strategy, do not mechanically add annotations to every property. Keep the entity concise and only override where actual differences exist.

### 3.2. Naming Strategy and @Column

The naming strategy provides the general rule for properties without an explicit column name. `@Column` provides a specific name for a single property.

You can think of the decision order as follows:

~~~text
Persistent property in entity
              |
              v
Is column name declared with @Column?
        /               \
      Yes                No
      |                   |
      v                   v
Use specified        Apply naming strategy
column name          of mapping context
      |                   |
      +---------+---------+
                |
                v
        Mapping metadata
                |
                v
       SQL and row mapping
~~~

If you change the application-wide naming strategy, properties without `@Column` may be mapped to different names. Properties that already declare an explicit column name continue using the name specified in the annotation metadata.

## 4. How to Use @Column

The most common usage is passing the column name into the annotation:

~~~java
@Column("customer_name")
private String name;
~~~

You can place the annotation on persistent properties of the entity. Full example:

~~~java
@Table("customer_profile")
public class CustomerProfile {

    @Id
    private Long id;

    @Column("given_name")
    private String firstName;

    @Column("family_name")
    private String lastName;

    @Column("email_addr")
    private String email;

    @Column("registered_on")
    private LocalDate registeredOn;

    // Constructor, getters and setters
}
~~~

Corresponding mapping:

| Java Property | Database Column |
|---|---|
| `id` | Primary key column per `@Id` mapping and naming metadata |
| `firstName` | `given_name` |
| `lastName` | `family_name` |
| `email` | `email_addr` |
| `registeredOn` | `registered_on` |

The table name is still determined by `@Table("customer_profile")`. The `@Column` annotation does not change table structure or create new columns.

### 4.1. Naming Columns with Underscores

Snake_case column names are common when Java properties use camelCase:

~~~java
@Column("shipping_address")
private String shippingAddress;

@Column("last_login_at")
private LocalDateTime lastLoginAt;
~~~

If the default naming strategy already converts `shippingAddress` to `shipping_address`, the first annotation may be unnecessary. The annotation can still be kept to highlight an important mapping or ensure clarity if the naming strategy changes, though you should maintain a consistent convention across the project.

### 4.2. Uppercase or Abbreviated Column Names

Legacy schemas may contain names such as `CUST_NO`, `ADDR_1`, or `UPD_TS`:

~~~java
@Column("CUST_NO")
private String customerNumber;

@Column("ADDR_1")
private String addressLine1;

@Column("UPD_TS")
private LocalDateTime updatedAt;
~~~

Do not automatically lowercase column names if the actual schema uses identifiers with specific casing rules. How a database handles uppercase and lowercase depends on whether identifiers are quoted and on the database system.

## 5. Special Identifiers and Quoting

A column name might collide with an SQL keyword, contain spaces, or use casing that must be preserved. In such cases, SQL may require quoting the identifier.

Some versions of Spring Data Relational support the `forceQuote` attribute on `@Column`. You can declare:

~~~java
@Column(value = "order", forceQuote = true)
private String order;
~~~

When generating SQL, Spring Data asks the dialect to quote the column name according to the database's rules. PostgreSQL typically uses double quotes for identifiers; other database systems have different rules.

Do not manually embed quote characters into the annotation name unless necessary. Use the quoting mechanism supported by mapping metadata and the dialect. Check the API of the Spring Data Relational version your project uses if you need the `forceQuote` attribute.

Identifier quoting is distinct from parameter binding for values. `@Column` describes the column name in SQL; data values are still passed via parameter binding to avoid SQL string concatenation and reduce SQL injection risk.

## 6. How Does @Column Affect Generated SQL Statements?

When a repository or `R2dbcEntityTemplate` performs operations on an entity, Spring Data uses mapping metadata to construct statements. The column name declared via `@Column` is used when mapping that property.

Suppose an entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String name;

    @Column("email_addr")
    private String email;
}
~~~

When inserting or updating, the generated SQL uses the corresponding physical column names. Illustrative form:

~~~sql
INSERT INTO customer (display_name, email_addr)
VALUES (?, ?);
~~~

When reading an entity, mapping also relies on metadata to populate values from columns into the right Java properties. Placeholder syntax and alias generation may vary by dialect, driver, and operation type; the example only illustrates the column names used.

Thus, application code can still work with `customer.getName()` while the database stores the value in `display_name`.

### 6.1. Property Names in Repository Methods Remain Java Names

`@Column` does not rename properties in the domain model. Derived query methods are named after Java properties:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByName(String name);

    Mono<Customer> findByEmail(String email);
}
~~~

Here `findByName` and `findByEmail` are used because the entity has properties `name` and `email`. Spring Data uses metadata to translate property criteria to the `display_name` and `email_addr` columns.

Do not write `findByDisplayName` just because the physical column is named `display_name`, unless the entity actually has a Java property named `displayName`.

### 6.2. Hand-Written SQL Must Use Physical Column Names

When using `@Query` with hand-written SQL, the SQL string is a statement provided by the developer. `@Column` does not automatically rewrite SQL literal contents.

Example:

~~~java
@Query("""
    SELECT id, display_name, email_addr
    FROM customer
    WHERE display_name = :name
    """)
Flux<Customer> findCustomersByName(@Param("name") String name);
~~~

In the SQL above, you must write the exact table and column names in the database: `customer`, `display_name`, `email_addr`. Do not use Java property names in place of physical column names if the two differ.

For projections or queries with expressions, choose aliases that match the mapping/projection the application expects. For example, if a query returns a computed value, explicit aliases make Spring Data result mapping more predictable.

## 7. @Column Does Not Replace Schema or Migrations

The annotation describes mapping at the application layer. It does not automatically create, rename, or move columns in the database.

Suppose an entity declares:

~~~java
@Column("display_name")
private String name;
~~~

If the `customer` table does not yet have a `display_name` column, SQL operations may fail with a missing-column error. Adding the annotation does not make the database add that column automatically.

When changing mapping from `name` to `display_name`, the schema must be updated using a migration tool or the project's schema management process, such as Flyway or Liquibase. A change typically requires:

1. Checking the current schema and existing data.
2. Writing a migration to rename or create the column as planned.
3. Handling legacy data if transformation is needed.
4. Updating the entity with `@Column`.
5. Running integration tests against a database with the migration applied.
6. Deploying the application and schema in an order compatible with the rollout strategy.

In a running system, renaming a column can affect multiple applications sharing the schema. Coordinate migrations and application versions to avoid a code version reading a column name that the database does not yet have.

## 8. @Column Does Not Determine Data Types or Value Conversion

`@Column` specifies the column name. It is not the place to declare SQL types, string lengths, numeric precision, or value conversion rules.

Example:

~~~java
@Column("total_amount")
private BigDecimal totalAmount;
~~~

The annotation states that `totalAmount` maps to the `total_amount` column. The actual SQL type and precision must be defined in the database schema. Converting between Java types and R2DBC/database types is handled by Spring Data conversion and the driver.

If a Java type needs special conversion rules, use Spring Data custom conversions with appropriate reading and writing converters instead of trying to use `@Column` to change data types.

For example, if the database stores order status as a string while the application uses an enum, verify whether the default converter matches the stored format. If not, declare an appropriate converter in the custom conversions configuration.

Similarly, `NOT NULL`, `UNIQUE`, `CHECK` constraints, default values, and column lengths must be defined in the schema or migrations. `@Column` does not create these constraints automatically.

## 9. Combining @Column with Immutable Entities

Spring Data Relational can map entities via constructors. With immutable entities, properties are initialized through the constructor instead of setters.

Example:

~~~java
@Table("customer")
public class Customer {

    @Id
    private final Long id;

    @Column("display_name")
    private final String name;

    @Column("email_addr")
    private final String email;

    public Customer(Long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Mapping still relies on entity metadata. The physical column name can differ from the Java parameter or property name; `@Column` identifies the column for the persistent property.

When using constructor mapping, ensure Spring Data can select the constructor and that parameters match the entity's properties. Do not rename Java parameters after physical column names just to match the schema.

## 10. Choosing the Right Annotation Package

A common mistake in projects using multiple persistence technologies is accidentally importing JPA's `@Column`.

Spring Data Relational uses:

~~~java
import org.springframework.data.relational.core.mapping.Column;
~~~

JPA uses:

~~~java
import jakarta.persistence.Column;
~~~

The two annotations belong to two different mapping mechanisms. If an entity is managed by Spring Data R2DBC, use the Spring Data Relational annotation. JPA annotations do not replace Spring Data Relational mapping metadata.

This is especially important when a project has both JPA/JDBC and R2DBC modules. Each entity should be designed for the persistence technology that manages it; never assume an annotation from one framework automatically has meaning in the other.

## 11. When Not to Use @Column

You do not need `@Column` in the following situations:

- The column name already matches the naming strategy and there is no requirement to state the mapping explicitly.
- The property is marked `@Transient` and is not stored in the database.
- The property is computed data that exists only in the application.
- You want to change the table name; use `@Table`.
- You want to change the SQL type or value formatting; check the schema and custom conversions.
- You want to write custom SQL; use the exact physical identifiers in the SQL statement.
- You want to create or rename a column; perform a schema migration.

Annotations should describe actually needed mapping rather than replacing the responsibilities of other persistence layers.

## 12. Common Errors

| Error | Cause | Resolution |
|---|---|---|
| Using `jakarta.persistence.Column` for an R2DBC entity | Annotation belongs to JPA mapping | Import `org.springframework.data.relational.core.mapping.Column` |
| Putting a Java property name in `@Column` even though the schema has a different name | Mapping points to a nonexistent column | Use the exact physical column name |
| Changing `@Column` without running a migration | Code and schema are out of sync | Update the schema via migration |
| Using physical column names in derived query methods | Confusing property name with column name | Use Java property names in `findBy...` |
| Expecting `@Column` to rewrite SQL inside `@Query` | Hand-written SQL is not modified by the annotation | Use actual table/column names in SQL |
| Using `@Column` to declare data types or `NOT NULL` | The annotation only describes column-name mapping | Manage types and constraints in schema and converters |
| Ignoring case sensitivity and identifier quoting | Database handles identifiers per dialect | Check the schema and use quoting when needed |
| Adding annotations to every property unnecessarily | Redundant mapping, harder to maintain | Rely on the naming strategy; only override when needed |
| Using `@Column` on non-persistent data | Confusing application properties with database columns | Use `@Transient` or model properties appropriately |

## 13. Workflow for Mapping Properties to Columns

When creating or updating an entity, follow this sequence:

1. Identify the actual table and schema the entity will access.
2. List the entity's persistent properties and their corresponding column names in the database.
3. Check the default naming strategy to see which column names are already derived accurately.
4. Use `@Column` for properties whose column names differ from the default rule or require quoting.
5. Use the exact Spring Data Relational annotation package.
6. Check hand-written SQL and projections to ensure appropriate identifiers are used.
7. Update the schema via migrations if column names or structures change.
8. Run integration tests against a compatible database to verify insert, select, and update.

A simple mapping table during design helps prevent confusion:

| Java Property | Database Column | Declaration |
|---|---|---|
| `firstName` | `first_name` | Per default naming strategy or `@Column` |
| `customerNumber` | `CUST_NO` | `@Column("CUST_NO")` |
| `registeredAt` | `registered_timestamp` | `@Column("registered_timestamp")` |
| `order` | `order` is a keyword needing dialect quoting | `@Column(value = "order", forceQuote = true)` if supported by the version |

## 14. Key Takeaways

- Spring Data Relational's `@Column` maps a Java property to a database column name.
- Import the annotation from `org.springframework.data.relational.core.mapping.Column`.
- The default naming strategy typically converts camelCase to snake_case; `@Column` overrides the column name for a specific property.
- `@Column` does not rename the Java property, change the table name, or automatically rewrite hand-written SQL.
- Derived query methods use Java property names; SQL in `@Query` must use physical identifiers matching the database.
- Use `forceQuote` when identifier quoting is needed and your Spring Data Relational version supports this attribute.
- The annotation does not create columns, declare constraints, or replace schema migrations.
- SQL types and value conversions belong to the schema, driver, and custom conversions.
- Use the right annotation package to avoid confusing JPA mapping with Spring Data R2DBC.
