# Class, Property, Table, and Column Mapping Conventions

When writing applications with **Spring Data Relational JDBC (Spring Data JDBC)**, Java classes and SQL tables often follow two different naming conventions. Java typically uses `CustomerOrder`, `customerId`, `createdAt`, while databases commonly use `customer_orders`, `customer_id`, `created_at`. To let these two worlds communicate, Spring Data JDBC uses **mapping metadata** and **`NamingStrategy`** to determine table names, column names, and join/reference column names.

Understanding these conventions helps you answer very practical questions: Why does a repository report “relation does not exist” even though the table was created? Why is the `firstName` field looked up in the `FIRST_NAME` column? Why does a `List` require an extra column to store positions? When should you use `@Table`, `@Column`, or `@MappedCollection`?

> **Guiding principle:** The Java model describes objects and relationships within an aggregate; the database has its own schema and identifiers. Spring Data JDBC maps between the two sides, but **does not automatically rename tables or columns in the database** to match Java. Any schema rename must be managed through migrations and corresponding mapping updates.

## 1. The Big Picture of the Mapping Process

A repository works with Java objects, yet ultimately still needs to generate SQL compatible with the database:

~~~mermaid
flowchart LR
    A["Java class<br/>CustomerOrder"] --> B["Mapping metadata<br/>@Table, @Column, @Id"]
    B --> C["NamingStrategy<br/>conventions when explicit names are absent"]
    C --> D["SQL names<br/>CUSTOMER_ORDER, CREATED_AT"]
    D --> E[("Physical table/column in database")]
~~~

There are three main sources of information:

1. **Default conventions**: Java class and field names are converted into SQL names according to `NamingStrategy`.
2. **Explicit annotations**: `@Table`, `@Column`, `@MappedCollection`, `@Embedded`, etc. specify exact names or mapping behavior.
3. **Global mapping configuration**: a custom `NamingStrategy` or changes to identifier quoting can apply across many entities in the application.

The names Spring Data JDBC *expects* must be compatible with the actual names in the schema. Annotations change how the framework looks up tables and columns; they do not issue `ALTER TABLE` statements to rename physical objects.

### Distinction from Spring Data JPA

Spring Data JDBC does not use JPA/Hibernate entity mapping mechanisms. The appropriate annotations for Spring Data JDBC live in Spring Data packages, such as:

| Purpose | Spring Data JDBC Annotation / API |
| --- | --- |
| Table name, schema | `org.springframework.data.relational.core.mapping.Table` |
| Column name | `org.springframework.data.relational.core.mapping.Column` |
| Identifier column | `org.springframework.data.annotation.Id` |
| Non-persisted property | `org.springframework.data.annotation.Transient` |
| Child properties in the same table | `org.springframework.data.relational.core.mapping.Embedded` |
| Collection reference column names | `org.springframework.data.relational.core.mapping.MappedCollection` |
| Customizing naming conventions | `org.springframework.data.relational.core.mapping.NamingStrategy` |

Therefore, `@Entity`, `@JoinColumn`, `@OneToMany`, or `spring.jpa.hibernate.naming.*` properties are not the tools used to configure naming for Spring Data JDBC.

## 2. Default Convention: Java Class Name → Table Name

When no table name is specified via `@Table`, Spring Data JDBC takes the **short class name** (without the package) and converts camel/PascalCase boundaries into underscores.

According to the convention described in the Spring Data Relational documentation, for example:

| Java Class Name | Derived Table Name |
| --- | --- |
| `Customer` | `CUSTOMER` |
| `CustomerOrder` | `CUSTOMER_ORDER` |
| `SavingsAccount` | `SAVINGS_ACCOUNT` |
| `OrderLine` | `ORDER_LINE` |
| `InvoicePayment` | `INVOICE_PAYMENT` |

The default format is expressed as **`SNAKE_CASE`** (uppercase in the framework's mapping examples). More important than uppercase formatting is **the final identifier name and how the database handles quoting**; Section 5 (and Section 7) explains this in detail.

Two consequences that are easy to overlook:

- **No automatic pluralization.** The class `CustomerOrder` does not automatically look for a table named `customer_orders`. If your design uses plural names, declare `@Table("customer_orders")` or configure a matching naming strategy.
- **The package does not become part of the table name.** `com.example.sales.Customer` and `com.example.crm.Customer` can both resolve to the table name `CUSTOMER`. If two aggregates share the same database/schema and need separate tables, configure them explicitly.

Do not try to infer rules for complex acronyms such as `URLMapping` or `HTTPStatus` from just a few examples. If physical names are a long-term contract, specify `@Table` and `@Column` explicitly to avoid surprises across version upgrades or strategy changes.

## 3. Default Convention: Property Name → Column Name

For properties stored in the same table, `NamingStrategy` also converts camelCase to snake case. For example:

| Java Field | Derived Column Name |
| --- | --- |
| `id` | `ID` |
| `firstName` | `FIRST_NAME` |
| `customerId` | `CUSTOMER_ID` |
| `createdAt` | `CREATED_AT` |
| `unitPrice` | `UNIT_PRICE` |
| `isActive` | `IS_ACTIVE` |

An example without explicit naming annotations:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;

public class CustomerOrder {
    @Id
    private Long id;

    private Long customerId;
    private Instant createdAt;
    private String orderStatus;
}
~~~

By convention, Spring Data JDBC expects the columns `ID`, `CUSTOMER_ID`, `CREATED_AT`, and `ORDER_STATUS` in the `CUSTOMER_ORDER` table. `@Id` marks the property that identifies a row; it does not mean the column name is forced to be `id` if the Java property has a different name.

For instance, a field named `orderId` annotated with `@Id` still maps to the `ORDER_ID` column by default, or must be specified with `@Column("id")` if the primary key in SQL is actually named `id`.

### Why Don't Getters/Setters Dictate the Entire Mapping?

Spring Data JDBC builds metadata based on **object properties/fields**. By converter convention, fields are used to transfer data; it does not simply take every public JavaBean getter name and treat it as a column.

~~~java
public class Customer {
    private String fullName;

    public String getDisplayName() {
        return fullName == null ? "" : fullName.trim();
    }
}
~~~

`getDisplayName()` is a computed method; it does not automatically create a `DISPLAY_NAME` column. Conversely, if a field in the model is recognized as a persisted property, the framework must know its corresponding column name even if you do not declare a getter.

Rules around constructors, records, accessors, and immutable objects belong to a different part of object mapping; **column naming rules** still rely on each property's metadata.

## 4. Complete Example: Using 100% Default Names

Suppose an aggregate is defined as:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;

public class CustomerProfile {
    @Id
    private Long id;
    private String fullName;
    private String emailAddress;
    private Instant registeredAt;
}
~~~

If you choose to keep the default names and Spring Data JDBC's identifier quoting rules, PostgreSQL may require a schema whose naming matches exactly as follows:

~~~sql
CREATE TABLE "CUSTOMER_PROFILE" (
    "ID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "FULL_NAME" VARCHAR(150) NOT NULL,
    "EMAIL_ADDRESS" VARCHAR(320) NOT NULL UNIQUE,
    "REGISTERED_AT" TIMESTAMPTZ NOT NULL
);
~~~

This example illustrates **quoted uppercase SQL identifiers**. It does not mean you must use uppercase conventions in every project. If your schema uses `customer_profiles` and `email_address` in PostgreSQL, a more stable approach is usually explicit annotations or a `NamingStrategy` aligned with the existing schema.

## 5. Using `@Table` and `@Column` to Specify Explicit Names

This is the most common solution when tables already exist, table names are plural, or column names do not match the convention derived from field names.

### 5.1. Mapping to Existing Tables/Columns

A PostgreSQL database created via migrations:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(320) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);
~~~

Java model:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    @Column("id")
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;

    @Column("created_at")
    private Instant registeredAt;

    // Constructors, getters, and domain methods...
}
~~~

| Java | Annotation | Column in `customers` Table |
| --- | --- | --- |
| `Customer` | `@Table("customers")` | `customers` table |
| `id` | `@Id @Column("id")` | `id` |
| `fullName` | `@Column("full_name")` | `full_name` |
| `email` | `@Column("email_address")` | `email_address` |
| `registeredAt` | `@Column("created_at")` | `created_at` |

Notice two intentionally different pairs of names: `email` ↔ `email_address` and `registeredAt` ↔ `created_at`. This is a key reason to use `@Column` even when a global naming convention is already in place.

The `@Table("customers")` annotation only changes **the table name**; it does not automatically convert all column names from default uppercase to lowercase. In the example, the columns are stated explicitly to stay consistent with an unquoted PostgreSQL migration.

### 5.2. `@Column` Does Not Change the Java Property Name

You still write:

~~~java
Customer customer = ...;
String email = customer.getEmail();
~~~

While the SQL statement can be:

~~~sql
SELECT email_address
FROM customers
WHERE id = 10;
~~~

Spring Data JDBC connects the two names through mapping metadata; they do not need to be identical. Repository methods and service classes continue working with Java property names. For hand-written SQL, the developer must use the physical column names in the database.

### 5.3. `@Id` Does Not Create a Primary Key

~~~java
@Id
@Column("customer_key")
private Long id;
~~~

This snippet states that the Java field `id` is the aggregate identifier and is stored in the `customer_key` column. It **does not automatically create** `PRIMARY KEY(customer_key)` in the database.

Constraints, indexes, data types, `NOT NULL`, and ID generation strategies must be created in separate schema migrations. A mapping configuration pointing to the wrong primary key column can cause insert/update failures or read incorrect data.

## 6. Schema Name: A Separate Part from the Table Name

A relational database can contain multiple schemas. PostgreSQL example:

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);
~~~

Spring Data JDBC supports specifying the schema explicitly in `@Table`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {
    @Id
    @Column("id")
    private Long id;

    @Column("order_number")
    private String orderNumber;
}
~~~

Here `sales` is the schema, and `purchase_orders` is the table name. The framework combines both values into a qualified identifier according to the corresponding SQL dialect.

If `schema` is omitted, the framework uses the connection's default schema or the schema provided by `NamingStrategy.getSchema()`, depending on configuration. That means the same name `purchase_orders` can refer to different tables if the application connects with a different default schema.

Do not assume the string `@Table("sales.purchase_orders")` is always equivalent to declaring the two attributes separately: the dot may be handled differently depending on how the API interprets a quoted identifier. **Prefer `@Table(schema = "sales", name = "purchase_orders")`** when explicit schema mapping is needed.

## 7. Distinguishing SQL Names, Case Sensitivity, and Quoting

This is a common source of errors when moving from H2 to PostgreSQL.

### 7.1. Databases Have Their Own Identifier Normalization Rules

In PostgreSQL:

~~~sql
CREATE TABLE customer_order (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL
);
~~~

Because the identifiers are unquoted, PostgreSQL stores the names in lowercase: `customer_order`, `id`, `created_at`.

However:

~~~sql
CREATE TABLE "CUSTOMER_ORDER" (
    "ID" BIGINT PRIMARY KEY,
    "CREATED_AT" TIMESTAMP NOT NULL
);
~~~

creates **case-sensitive** identifiers: `"CUSTOMER_ORDER"` is a different name from `customer_order`.

These two queries are not synonymous in PostgreSQL:

~~~sql
SELECT * FROM customer_order;
SELECT * FROM "CUSTOMER_ORDER";
~~~

The first looks for the lowercase table; the second looks for the quoted uppercase table. A table can exist while Spring JDBC still reports that it cannot be found if the final SQL name does not match.

### 7.2. Spring Data JDBC May Quote Identifiers by Default

According to the Spring Data Relational mapping documentation, table and column names derived from classes and properties are **quoted by default** in generated SQL; names specified by `@Column` are also quoted when `forceQuote` is enabled. The framework provides mechanisms such as `JdbcMappingContext.setForceQuote(false)` or context factories for plain (unquoted) identifiers to change this during infrastructure configuration.

Illustrative examples:

| Identifier Targeted by Spring Data JDBC | Name Created in PostgreSQL | Matches? |
| --- | --- | --- |
| `"CUSTOMER_ORDER"` | `CREATE TABLE "CUSTOMER_ORDER" ...` | Yes |
| `"CUSTOMER_ORDER"` | `CREATE TABLE customer_order ...` | No |
| `"customer_order"` | `CREATE TABLE customer_order ...` | Yes |
| `"created_at"` | Unquoted column created as `created_at` | Yes |

**Quoting and case are two related but distinct issues.** A custom `NamingStrategy` that produces lowercase names can match a lowercase schema even if the framework still quotes identifiers; turning off quoting does not automatically fix singular/plural differences or business naming mismatches.

### 7.3. Avoid Relying on Differences Across Database Engines

H2, PostgreSQL, MySQL, SQL Server, and Oracle have different case rules and configurations. An example that passes on H2 is not proof that the SQL names will match PostgreSQL. Names like `user`, `order`, or `group` also easily collide with SQL keywords; clear names such as `app_users` or `purchase_orders` reduce the need for special quoting.

Choose one consistent convention (for example **lowercase snake_case in the database**) and ensure annotations, naming strategy, and migrations all follow that same convention.

## 8. Which Fields Are Mapped to Columns?

Not every member of a Java class corresponds to a database column.

### 8.1. `@Transient`: Excluding a Property from Persistence Mapping

~~~java
import org.springframework.data.annotation.Transient;

@Table("customers")
class Customer {
    @Id
    @Column("id")
    Long id;

    @Column("full_name")
    String fullName;

    @Transient
    String displayLabel; // Used only in the application; no display_label column needed.
}
~~~

Spring Data's `@Transient` tells the framework that this property is not persisted. It is different from simply assigning an arbitrary column name with `@Column`. If a persistence constructor requires a value for a transient property without a way to supply it, object materialization from SQL results can also run into issues.

### 8.2. `@ReadOnlyProperty` and Database-Generated Columns

Sometimes a column is read from the database, but the application should not write to it when saving:

~~~java
import org.springframework.data.annotation.ReadOnlyProperty;

@ReadOnlyProperty
@Column("generated_label")
private String generatedLabel;
~~~

This describes how a column is mapped for reading; it is not a renaming mechanism and does not configure a SQL generation formula on its own. If the database computes the column, the schema must provide that mechanism.

### 8.3. `@Version` Also Has a Column Name

Spring Data JDBC supports optimistic locking with `@Version`. If the Java field is `versionNumber`, the default naming rules apply just like any other property; if the schema uses `row_version`, you need `@Column("row_version")`:

~~~java
import org.springframework.data.annotation.Version;

@Version
@Column("row_version")
private Long versionNumber;
~~~

`@Version` determines the concurrency-control semantics of the value; `@Column` specifies the SQL column that stores it.

### 8.4. Type Conversion Is Not Renaming

`MappingJdbcConverter` and `CustomConversions` can convert `Instant`, enums, value types, and so on into appropriate JDBC values. Choosing a column name and converting data types are two separate responsibilities. For example, `@Column("unit_price") BigDecimal price` specifies the column name; the SQL type `NUMERIC(12,2)` is still defined by the schema.

## 9. Join Column Names When an Aggregate Contains Child Entities

Naming conventions do not stop at simple columns. In Spring Data JDBC, a child entity within an aggregate usually lives in a separate table and needs a column referencing back to the aggregate root (**back reference**).

Suppose an order contains multiple lines:

~~~mermaid
erDiagram
    PURCHASE_ORDERS ||--o{ ORDER_LINES : contains
    PURCHASE_ORDERS {
        bigint id PK
        bigint customer_id
    }
    ORDER_LINES {
        bigint id PK
        bigint purchase_order_id FK
        integer line_position
        varchar sku
    }
~~~

### 9.1. Default Back-Reference Convention

The Spring Data Relational documentation explains that the column name referencing the parent entity from a child entity **defaults to being based on the table name of the owning entity**, rather than simply the collection property name.

For a `List` or `Map`, the child entity also has a column representing **the position index or map key**. The default name of that column is derived from the back-reference column name with a `_KEY`-style suffix.

This leads to an easy surprise: if `PurchaseOrder` maps to `purchase_orders` and has a `List<OrderLine>`, do not assume the framework will automatically look for `order_id` and `line_no` just because those are sensible domain names. **Default names follow their own rules**, and depend on `@Table` and the configured naming strategy.

### 9.2. Using `@MappedCollection` for Clear, Consistent Names

Model:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    @Column("id")
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @MappedCollection(
        idColumn = "purchase_order_id",
        keyColumn = "line_position"
    )
    private List<OrderLine> lines = new ArrayList<>();
}

@Table("order_lines")
public class OrderLine {
    @Id
    @Column("id")
    private Long id;

    @Column("sku")
    private String sku;

    @Column("quantity")
    private int quantity;
}
~~~

Corresponding schema:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL
        REFERENCES purchase_orders(id),
    line_position INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    CONSTRAINT uq_line_position
        UNIQUE (purchase_order_id, line_position)
);
~~~

Here:

- `idColumn = "purchase_order_id"` identifies **the column in the child table** that holds the parent order's ID. It does not rename `id`, which is `OrderLine`'s own primary key.
- `keyColumn = "line_position"` specifies the column storing the `List` element position. For a `List`, the key in model terms is an integer index.
- `@Table("order_lines")` selects the child entity's table; `@Column("sku")` and `@Column("quantity")` specify the child's business data columns.
- The `purchase_order_id` and `line_position` columns are managed by the framework as collection metadata. There is no need to add them as regular persisted fields in `OrderLine` just to duplicate the FK and index names.

The example above chooses explicit mapping so the database and Java model stay consistent. Even when column names are declared in `@MappedCollection`, **SQL foreign keys** and **unique constraints** must still be created in migrations; annotations do not create constraints.

### 9.3. Distinguishing `Set`, `List`, and `Map`

| Parent Property Type | Back-Reference Column | Key/Index Column |
| --- | --- | --- |
| `Set<Child>` | Requires a column referencing the parent | No positional semantics; `keyColumn` does not apply |
| `List<Child>` | Requires a column referencing the parent | Requires an extra column storing element index |
| `Map<K, Child>` | Requires a column referencing the parent | Requires an extra column holding key `K` as supported by mapping |
| A single child entity | Parent–child relationship requires a reference column | No collection position column needed |

The back-reference column name can be customized via `NamingStrategy.getReverseColumnName(...)`; the collection key column name can be customized via `NamingStrategy.getKeyColumn(...)`. When a concrete schema already exists, `@MappedCollection` is usually easier to read and less surprising.

### 9.4. Relationships to Independent Aggregates

Customer and order can be **two independent aggregates**. In that case, declaring:

~~~java
@Column("customer_id")
private Long customerId;
~~~

on `PurchaseOrder` is a way to represent a reference by ID, not a child entity collection. If you want stronger type expression in Java, Spring Data JDBC also supports `AggregateReference<Customer, Long>`.

A relationship between two aggregates does not mean Spring Data JDBC automatically generates joins or FK constraints. You still need to declare `customer_id` with the right name and create a `FOREIGN KEY` in the database if the business domain requires referential integrity enforcement.

## 10. `@Embedded` and Column Name Prefix Rules

A **value object** can be stored directly in the parent table instead of a separate table. The `@Embedded` annotation supports this.

Suppose each order has shipping address details:

~~~java
import org.springframework.data.relational.core.mapping.Column;

public class Address {
    @Column("street_name")
    private String street;

    @Column("postal_code")
    private String postalCode;
}
~~~

In the aggregate:

~~~java
import org.springframework.data.relational.core.mapping.Embedded;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    @Column("id")
    private Long id;

    @Embedded.Nullable(prefix = "shipping_")
    private Address shippingAddress;
}
~~~

The schema has the columns directly inside `purchase_orders`:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    shipping_street_name VARCHAR(200),
    shipping_postal_code VARCHAR(20)
);
~~~

Because of the `shipping_` prefix and the inner columns declared as `street_name` and `postal_code`, the two final SQL names are `shipping_street_name` and `shipping_postal_code`.

If you add a billing address:

~~~java
@Embedded.Nullable(prefix = "billing_")
private Address billingAddress;
~~~

then the framework can map the same `Address` value object to the columns `billing_street_name` and `billing_postal_code` without colliding with the shipping columns.

`@Embedded.Nullable` specifies how to handle the case where all inner columns are `NULL` (the embedded object can be `null`). This annotation does not mean the database automatically allows all columns to be nullable; SQL constraints remain the ultimate source of truth.

**Core distinction:** `@MappedCollection` represents child entities that can live in a separate table and need a back-reference column; `@Embedded` flattens a value object's properties into **columns of the parent table**, and prefixes prevent name collisions.

## 11. Customizing `NamingStrategy` Application-Wide

If many entities follow the same physical convention (for example, PostgreSQL using lowercase snake_case), writing `@Column` on every field is verbose and easy to forget. You can declare a custom `NamingStrategy` to change how the framework derives default names.

Spring configuration example:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.NamingStrategy;
import org.springframework.data.relational.core.mapping.RelationalPersistentProperty;

@Configuration
public class JdbcNamingConfiguration {

    @Bean
    NamingStrategy lowerSnakeCaseNamingStrategy() {
        return new NamingStrategy() {
            @Override
            public String getTableName(Class<?> type) {
                return NamingStrategy.super.getTableName(type)
                    .toLowerCase(Locale.ROOT);
            }

            @Override
            public String getColumnName(RelationalPersistentProperty property) {
                return NamingStrategy.super.getColumnName(property)
                    .toLowerCase(Locale.ROOT);
            }
        };
    }
}
~~~

This strategy keeps the underscore-based camel-case splitting rule while applying lowercase to **the derived base table and column names**. Thus, a `CustomerOrder` class with a `createdAt` field targets `customer_order` and `created_at`, unless overridden by explicit annotations.

This is a **partial customization example**: back-reference names, key columns, schemas, and other collection rules still need to be checked so they follow the expected convention as well. To apply the new naming convention consistently across the whole system, also consider `getReverseColumnName(...)` and `getKeyColumn(...)` when using child entities, `List`, or `Map`.

### 11.1. Precedence Between Annotations and Strategy

Typically:

1. The table name specified in `@Table` is used instead of the table name derived from the class.
2. The column name specified in `@Column` is used instead of the column name derived from the field.
3. When an annotation does not supply a name, `NamingStrategy` resolves the default convention.
4. For collections, `@MappedCollection(idColumn = ..., keyColumn = ...)` lets you set explicit names instead of the derived back-reference/key names.

Therefore, after adding a new `NamingStrategy`, an entity already annotated with `@Table("legacy_orders")` can continue mapping to the `legacy_orders` table. This is useful when the application follows one shared convention while a few legacy tables require exceptions.

### 11.2. Spring Boot and Manual Configuration

In Spring Boot–based Spring Data JDBC setups, the documentation supports providing a `NamingStrategy` in the application context. With manual configuration extending `AbstractJdbcConfiguration`, you can also adjust the naming strategy configuration hooks of the JDBC infrastructure. Choose **one** mechanism consistent with how the application bootstraps Spring Data JDBC, avoiding multiple mapping contexts/strategies that cause repositories and DAOs to diverge.

Do not copy Hibernate configuration into JDBC. `spring.jpa.hibernate.naming.physical-strategy` is for Hibernate/JPA and is not how you configure Spring Data JDBC's `NamingStrategy`.

### 11.3. Should You Disable Identifier Quoting?

There are APIs such as `JdbcMappingContext.setForceQuote(false)` or factories for creating a context with plain identifiers, depending on the Spring Data version. However, disabling quoting can change how the database normalizes identifiers, causing issues with uppercase names, keyword collisions, and existing schemas. Follow an agreed-upon convention rather than turning off quoting just to mask mismatched table names.

If your project uses lowercase snake_case in PostgreSQL, using **explicit lowercase names** or an appropriate naming strategy is usually easier to maintain than mixing quoted uppercase identifiers with unquoted lowercase identifiers.

## 12. Do Hand-Written SQL and Repositories Rename the Same Way?

Suppose an entity uses:

~~~java
@Table("customers")
class Customer {
    @Id
    @Column("id")
    Long id;

    @Column("email_address")
    String email;
}
~~~

CRUD repositories generated by Spring Data JDBC rely on metadata, so the framework knows the configured table and column names. However, if you write SQL in a DAO:

~~~java
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;

public class CustomerLookupDao {
    private final NamedParameterJdbcOperations jdbc;

    public CustomerLookupDao(NamedParameterJdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    public Long findIdByEmail(String email) {
        return jdbc.queryForObject(
            """
            SELECT id
            FROM customers
            WHERE email_address = :email
            """,
            Map.of("email", email),
            Long.class
        );
    }
}
~~~

then you must write `customers` and `email_address` according to the physical schema yourself. `NamedParameterJdbcOperations` substitutes **parameter values** like `:email`, rather than reading `@Table`/`@Column` annotations to rewrite column names inside the SQL string.

The same applies to Spring Data JDBC's `@Query`: the query string you declare is SQL you are responsible for, while mapping the results into objects uses the corresponding metadata/converters.

**Renaming a Java column mapping does not automatically update hand-written SQL.** When refactoring `emailAddress` to `email`, review both places that query by Java property names and places that write SQL column names directly.

## 13. Renaming Classes, Properties, and Schemas Over Time

A change that looks like a pure Java refactor can alter SQL names if you are relying on derived conventions.

Examples:

| Change in Java | Risk When No Explicit Names Are Set |
| --- | --- |
| Rename class `CustomerOrder` to `PurchaseOrder` | Derived table name changes from `CUSTOMER_ORDER` to `PURCHASE_ORDER` |
| Rename field `createdAt` to `orderedAt` | Derived column name changes from `CREATED_AT` to `ORDERED_AT` |
| Change `List<OrderLine>` to `Set<OrderLine>` | No longer requires a key/index column under `Set` semantics vs. `List` |
| Change `@Table("orders")` to `@Table("purchase_orders")` | Repository targets a different table name; old data is not moved automatically |
| Replace global `NamingStrategy` | Many table, column, and join names can change all at once |

For an application already running in production, **renaming SQL objects must be treated as a schema change**:

1. Identify the existing physical names and the intended target names.
2. Update Flyway/Liquibase migrations or your schema management mechanism accordingly.
3. Update annotations/strategies and any hand-written SQL queries.
4. Check foreign keys, indexes, views, triggers, reports, and other applications using those tables/columns.
5. For rolling deployments, consider multi-version compatibility strategies (such as expand–migrate–contract) so older instances do not break mid-rollout.

For long-lived business tables, explicitly declaring important physical names makes Java refactoring less tightly coupled to the SQL layout.

## 14. How to Diagnose Name Mapping Errors

Typical symptoms:

| Symptom | Likely Cause | Where to Check |
| --- | --- | --- |
| PostgreSQL reports `relation does not exist` | Table/schema name or quote/case mismatch | `@Table`, `NamingStrategy`, `search_path`, actual table name |
| Reports `column ... does not exist` | Java field renamed, missing/wrong `@Column`, or quoted uppercase name | Field mappings, DDL, generated SQL |
| Passes on H2 but fails on PostgreSQL | Different identifier normalization rules between the two DBs | Actual SQL statements and physical table/column names |
| Saving collection reports missing column in child table | Back-reference/index column does not match convention | `@MappedCollection(idColumn, keyColumn)` and migrations |
| Two embedded value objects overwrite/collide on names | Missing prefix or duplicate prefixes | `@Embedded(prefix = ...)` |
| Repository CRUD works but `@Query` fails | Hand-written SQL uses Java names instead of physical names | SQL strings in `@Query`, DAOs |
| Refactoring class name causes repository not to find table | Relying on default derived table name | Add an explicit `@Table` or migration |
| Entity name differs from table name after changing strategy | Explicit annotation override or a different mapping context | `@Table`, `NamingStrategy` bean, repository configuration |

### Inspecting the Actual Schema

In PostgreSQL, you can check table names from the catalog:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
~~~

And column names:

~~~sql
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customers'
ORDER BY ordinal_position;
~~~

If the actual table is named `"CUSTOMERS"`, filtering `table_name = 'customers'` will not return the corresponding rows. That is why checking **the actual stored names** in the catalog is better than guessing from migration files.

### Observing SQL in Development

When using Spring Boot, you can enable logging for Spring JDBC:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

Inspect the SQL statements emitted by the framework (including table/column names and quotes) against the schema. If deeper logging is needed, be mindful of sensitive data in SQL parameters; avoid enabling overly verbose logging in production.

## 15. Recommended Conventions for Spring Data JDBC Projects

A maintainable set of rules:

- **Java:** `PascalCase` classes; `camelCase` fields/methods with domain-meaningful names, such as `PurchaseOrder`, `customerId`, `orderedAt`.
- **Database:** standardize on one style such as `lowercase_snake_case` for tables, columns, foreign keys, and indexes; use descriptive names and avoid SQL keywords.
- **Mapping:** use `@Table` and `@Column` for physical names that differ from conventions, or choose a global `NamingStrategy` when the schema is genuinely consistent.
- **Child aggregate parts:** use `@MappedCollection` when FK or `List`/`Map` index columns have specific requirements; use `@Embedded(prefix = ...)` when a value object shares the parent table and could collide on column names.
- **Migrations:** treat physical names as a versioned contract; do not rely on Java renames to reshape the schema automatically.
- **Hand-written SQL:** use physical table/column names and bind values via parameters; never concatenate user-supplied identifiers into SQL arbitrarily.

Quick decision table:

| Situation | How to Handle |
| --- | --- |
| Classes/fields and DDL follow the same convention | Can let `NamingStrategy` derive names |
| Table uses plural or legacy names | `@Table("actual_table")` |
| Column has a different name from the Java field | `@Column("actual_column")` |
| Entity resides in a non-default schema | `@Table(schema = "...", name = "...")` |
| Entire application uses lowercase snake_case | Register a consistent `NamingStrategy` |
| Child collection uses custom FK/index column names | `@MappedCollection(idColumn = "...", keyColumn = "...")` |
| Value object embedded multiple times | `@Embedded(prefix = "...")` |
| Developer-written SQL queries | Use real database names; metadata does not rewrite SQL |
| Renaming already-deployed objects | Write a migration and update related mappings/SQL |

## 16. Practice Exercises

### Exercise 1 — Inferring Default Names

Given the class:

~~~java
public class InventoryItem {
    @Id Long itemId;
    String displayName;
    Integer stockQuantity;
}
~~~

Write down the table and column names Spring Data JDBC will derive when no explicit naming annotations are present, and explain why `itemId` does not automatically become the `ID` column.

### Exercise 2 — Mapping an Existing Schema

Given the table:

~~~sql
CREATE TABLE sales.order_headers (
    order_id BIGINT PRIMARY KEY,
    buyer_email VARCHAR(320),
    ordered_at TIMESTAMPTZ
);
~~~

Write an `OrderHeader` class with appropriate `@Table`, `@Id`, and `@Column` annotations so that it has the fields `id`, `email`, and `createdAt`. Make sure to explicitly specify `schema = "sales"` rather than relying on a default schema.

### Exercise 3 — Mapping a `List`

An order stores a list of order lines, and the child table has `parent_order_id` and `sort_index`. Use `@MappedCollection(idColumn = "parent_order_id", keyColumn = "sort_index")` to express this relationship; explain why the child table still needs its own primary key column and appropriate constraints.

### Exercise 4 — Investigating Quote/Case Errors

A PostgreSQL migration creates `customer_order` unquoted, while repository logs show queries against `"CUSTOMER_ORDER"`. Propose at least two valid fixes and state when a migration is required.

### Exercise 5 — Safe Refactoring

You rename the `createdAt` field to `registeredAt` while wanting to keep the `created_at` column for backward compatibility with existing data. Add the appropriate annotation and list the hand-written SQL queries that may need to be reviewed.

## 17. Official Documentation for Further Reading

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping conventions, `@Table`, `@Column`, `@MappedCollection`, `@Embedded`, back references, and identifier quoting.
- [Spring Data Relational — `NamingStrategy` API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/relational/core/mapping/NamingStrategy.html): hooks for table, column, schema, back-reference, and collection key names.
- [Spring Data Relational — `@Table` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/Table.html): `value`/`name` and `schema`.
- [Spring Data Relational — `@MappedCollection` API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/relational/core/mapping/MappedCollection.html): `idColumn` and `keyColumn`.
- [Spring Data Relational — JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html): how repositories work with mapping and aggregates.

**Key takeaway:** Java class and property names can be transformed into table and column names via `NamingStrategy`, and final names can be overridden with annotations. Collection join columns and embedded fields also have their own rules. When designing with Spring Data JDBC, decide on your SQL naming convention, configure the mapping accordingly, and keep schema migrations aligned with the names your repositories actually use.
