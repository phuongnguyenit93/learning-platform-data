# Default Conventions for Mapping Java Classes to Tables

## 1. What Is Object Mapping in Spring Data Relational R2DBC?

Spring Data Relational R2DBC allows applications to work with relational data through Java classes. Instead of writing SQL manually for every CRUD operation, you can declare a class representing the data and use a repository or `R2dbcEntityTemplate` to read and write those objects.

To do this, Spring Data needs to know how to relate:

- A Java class to a database table.
- A Java property to a table column.
- An identifier property to a record key.
- A Java type to a data type supported by the R2DBC driver and database.

That association process is called object-relational mapping. Spring Data Relational has its own mapping mechanism, used in both Spring Data JDBC and Spring Data R2DBC. This lesson focuses on R2DBC.

Spring Data Relational provides default conventions so you do not have to declare a table name and column name for every property. When names in Java and names in the database do not follow the same convention, you can override them using annotations such as `@Table` and `@Column`.

## 2. Default Naming Conventions

Under Spring Data Relational's default naming strategy, Java class names and property names are converted from PascalCase/camelCase to lowercase snake_case.

### 2.1. Java Class Names Become Table Names

If a class does not specify a table name with `@Table`, Spring Data derives the table name from the class name.

| Java Class Name | Default Convention Table Name |
|---|---|
| Customer | customer |
| Product | product |
| PurchaseOrder | purchase_order |
| OrderItem | order_item |
| ShippingAddress | shipping_address |

Example:

~~~java
public class Customer {
    private Long id;
    private String fullName;
}
~~~

The `Customer` class is mapped to the `customer` table. Spring Data does not automatically pluralize singular names. Therefore, `Customer` defaults to `customer`, not `customers`.

Similarly, `PurchaseOrder` becomes `purchase_order`; Spring Data splits words in the class name and joins them with underscores.

The package name is not prepended to the table name. The class `com.example.domain.Customer` still derives its table name from `Customer`, unless you specify a different name or change the naming strategy.

### 2.2. Java Property Names Become Column Names

If a property does not have an explicitly specified column name, Spring Data derives the column name from the property name using the same snake_case convention.

| Java Property | Default Column Name |
|---|---|
| id | id |
| firstName | first_name |
| createdAt | created_at |
| customerId | customer_id |
| unitPrice | unit_price |
| isActive | is_active |

Example:

~~~java
public class PurchaseOrder {
    private Long id;
    private String orderNumber;
    private Long customerId;
    private Instant createdAt;
}
~~~

By default convention, this class maps to the `purchase_order` table with columns `id`, `order_number`, `customer_id`, and `created_at`.

You should distinguish Java property names from SQL column names. In Java, camelCase is usually easier to read and fits language conventions. In the database, snake_case is commonly used for table and column names. Spring Data bridges these two naming styles through the naming strategy.

### 2.3. Conventions Do Not Automatically Create Tables

The naming strategy only determines the names that mapping metadata uses when generating SQL or reading data. It does not mean Spring Data R2DBC will automatically create tables, columns, primary keys, or constraints in the database.

For example, if an entity has:

~~~java
public class Customer {
    @Id
    private Long id;

    private String fullName;
}
~~~

the naming convention implies table `customer` and columns `id`, `full_name`. However, the actual schema must still contain the corresponding structures. If the actual table is named `customers`, while the code defaults to looking for table `customer`, the generated SQL may fail to run as expected.

Manage the schema with migrations or a DDL tool appropriate for the project. Mapping and schema need to stay aligned with each other.

## 3. Using @Table to Specify the Table Name

The `@Table` annotation allows you to declare a table name explicitly. When this annotation is present, the declared name is used instead of the name derived from the class.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    private String fullName;
}
~~~

In this example:

- The class name is `Customer`.
- Using the default, the table name would be `customer`.
- Because `@Table("customers")` is declared, the class is mapped to the `customers` table.
- The `fullName` column name still follows the default naming strategy and becomes `full_name`.

`@Table` only changes the table name. It does not automatically change all property names, data types, primary keys, or constraints.

### 3.1. When Should You Use @Table?

Use `@Table` when:

- The existing database uses a table name different from the one derived from the Java class.
- The project consistently uses plural table names such as `customers`, `orders`, `products`.
- The table name is a prescribed business name or is shared with other applications.
- You want to state the contract between entity and schema clearly so code readers can easily see it.

Example:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    private String orderNumber;
}
~~~

The `PurchaseOrder` entity will work with the `purchase_orders` table instead of the default `purchase_order` table.

### 3.2. The Table Name in @Table Must Match the Real Schema

Suppose a migration creates the table:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL
);
~~~

Corresponding entity:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    private String orderNumber;
}
~~~

Both sides agree on the table and column names. If the annotation specifies `@Table("purchase_order")` while the database only has `purchase_orders`, the generated query will target a different table and the database may report that the table/relation cannot be found.

The table name must comply with the identifier rules of the database management system in use. How databases handle uppercase, lowercase, double quotes, and reserved names can vary. Prefer simple, consistent names, avoid SQL keywords, and check the actual DDL.

## 4. Using @Column to Specify the Column Name

The `@Column` annotation lets you map a Java property to a specific column name. When `@Column` is present, the declared name replaces the name derived from the property.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;
}
~~~

In this example:

| Java Property | If Using Default | Declared Column Name |
|---|---|---|
| id | id | id |
| fullName | full_name | full_name |
| email | email | email_address |

`fullName` would already be mapped to `full_name`, yet the annotation can still be used to show the column name in the schema explicitly. `email` will be mapped to `email_address` instead of `email`.

### 4.1. When Should You Use @Column?

Use `@Column` when:

- The column name in the database does not follow the snake_case convention derived from Java.
- The database has a legacy schema with fixed column names.
- The Java property name follows a different language or convention than the column name.
- You need to make the column name that the entity depends on explicit.

For example, a legacy database has column `cust_nm`:

~~~java
@Table("customer_master")
public class Customer {
    @Id
    private Long id;

    @Column("cust_nm")
    private String fullName;
}
~~~

The `fullName` property will be read/written through the `cust_nm` column.

### 4.2. @Column Does Not Change the SQL Data Type

`@Column("email_address")` specifies the column name. It does not automatically turn a Java `String` into a `VARCHAR(255)` column, nor does it create `NOT NULL`, `UNIQUE`, or `CHECK`.

Entity example:

~~~java
@Column("email_address")
private String email;
~~~

The corresponding schema can be managed with DDL:

~~~sql
email_address VARCHAR(255) NOT NULL
~~~

Length, nullability, uniqueness, and data rules are determined by the schema and constraints. Mapping a Java type to an SQL type also depends on Spring Data conversion, the R2DBC driver, and the database dialect.

### 4.3. @Column on the Identifier Property

A property with `@Id` still follows column naming rules. If the ID column name in the database differs from the Java property name, you can specify `@Column` on that property:

~~~java
@Table("customers")
public class Customer {
    @Id
    @Column("customer_id")
    private Long id;

    @Column("full_name")
    private String fullName;
}
~~~

In this example, `id` is mapped to `customer_id`. The `@Id` annotation marks the identifier property for Spring Data; `@Column` specifies the corresponding column name. The primary key in the database still needs to be created in the schema.

## 5. Role of @Id in Mapping

Spring Data needs to know which property identifies an entity. The `@Id` annotation marks that property.

~~~java
@Table("products")
public class Product {
    @Id
    private Long id;

    private String name;
    private BigDecimal price;
}
~~~

In this example:

- `Product` is mapped to the `products` table.
- `id` is the identifier property.
- `name` is mapped to the `name` column.
- `price` is mapped to the `price` column.

`@Id` is metadata telling Spring Data which property represents the entity's ID. It is not a DDL command and does not automatically create a primary key in the database.

The schema can be created as follows:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

The exact ID generation mechanism depends on the database system and application configuration. For database-generated IDs, the Java type, column type, and identity/sequence mechanism must be compatible. For application-assigned IDs, code needs to assign the value by design before saving.

Do not simply look at a property named `id` and assume the database already has a primary key. Check both the annotation and the DDL.

## 6. Excluding Non-Persistent Properties with @Transient

Not every property in a Java class is a table column. Some properties only serve display or calculation purposes in the application.

Use `@Transient` to mark a property as excluded from persistent mapping:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String displayName;
}
~~~

`displayName` can be computed from `firstName` and `lastName`:

~~~java
public String getDisplayName() {
    return firstName + " " + lastName;
}
~~~

This property is not treated as a column to read/write in the `customers` table. Therefore, the schema does not need a `display_name` column just because the Java class has a `displayName` property.

Use `@Transient` for derived data or data that exists only in memory. If you want to persist that value to the database, remove the annotation and create the corresponding column in the schema.

Be sure to distinguish Spring Data's `@Transient` from annotations or modifiers with the same name in other libraries. When working with Spring Data Relational mapping, use `org.springframework.data.annotation.Transient`.

## 7. Complete Example: From Java Class to SQL Table

Suppose an application manages customers and the database uses plural table names and snake_case column names.

Entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;

    private Instant createdAt;

    @Transient
    private String displayLabel;

    public Customer() {
    }

    public Customer(Long id, String fullName, String email, Instant createdAt) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getDisplayLabel() {
        return displayLabel;
    }
}
~~~

Corresponding SQL schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Mapping table:

| Java | Database | Convention Source |
|---|---|---|
| Class `Customer` | Table `customers` | `@Table("customers")` |
| Property `id` | Column `id` | `@Id` and default name |
| Property `fullName` | Column `full_name` | `@Column("full_name")` |
| Property `email` | Column `email_address` | `@Column("email_address")` |
| Property `createdAt` | Column `created_at` | Default naming strategy |
| Property `displayLabel` | No column | `@Transient` |

You can use a repository to work with the entity:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Spring Data uses the mapping metadata of `Customer` to build repository operations. When calling `save`, `findById`, or other CRUD methods, table and column names are taken from the mapping metadata.

The example above assumes the schema has already been created and the column types are compatible with the Java types. Simply adding the entity and repository is not enough to create the `customers` table.

## 8. Default Conventions and Hand-Written SQL

It is important to distinguish SQL generated by Spring Data from mapping metadata from SQL written directly by developers.

With repositories or entity-mapping APIs, Spring Data can use metadata to determine table and column names. For example, entity `PurchaseOrder` maps by default to `purchase_order`, and property `createdAt` maps to `created_at`.

However, if you write SQL manually with `DatabaseClient`, the table and column names in the SQL string are the ones you specify:

~~~java
databaseClient.sql("""
    SELECT id, created_at
    FROM purchase_order
    WHERE customer_id = :customerId
    """)
    .bind("customerId", customerId);
~~~

`DatabaseClient` does not automatically parse every SQL string to turn `PurchaseOrder` into `purchase_order` or `createdAt` into `created_at`. Always write SQL names that match the actual schema.

If you want to map query results to a Java type, you can use `DatabaseClient`'s mapping mechanism or an appropriate conversion. Mapping the results does not mean the input SQL string is automatically renamed.

This is especially important when a project uses `@Table` and `@Column` to work with a schema whose names differ from conventions. Manual SQL statements must still use the exact actual table and column names.

## 9. Java Types and SQL Types Are Another Part of Name Mapping

Class names and property names only answer the question "which table and column to read from / write to." The question "which SQL type stores the Java value" involves the type conversion system and the R2DBC driver.

Some common examples:

| Java Type | Typical Corresponding SQL Type | Notes |
|---|---|---|
| Long | BIGINT | Check range and ID generation mechanism |
| Integer | INTEGER | Used for integers within the appropriate range |
| String | VARCHAR or TEXT | Length and column type defined by the schema |
| BigDecimal | DECIMAL / NUMERIC | Suitable for decimals requiring precision |
| Boolean | BOOLEAN or equivalent type | Depends on the database system |
| LocalDate | DATE | Represents a calendar date |
| LocalDateTime | TIMESTAMP | Does not carry time-zone information |
| Instant | Timestamp type suitable for driver/database | Align on UTC and time-zone conventions |

This table is a common guideline, not a guarantee that every driver and database supports the exact same conversion. Always check the dialect, driver, and schema in use. For custom types, application-configured read/write converters may be required.

For example, the property:

~~~java
private BigDecimal unitPrice;
~~~

can be mapped to the `unit_price` column, but the column's type and precision must be defined in the schema:

~~~sql
unit_price DECIMAL(12, 2) NOT NULL
~~~

The naming strategy does not determine `DECIMAL(12, 2)`. Column name and column type are two separate concerns.

## 10. Table Names, Column Names, and Database Rules

Even though Spring Data has a naming strategy, the database still applies its own identifier rules.

Some database systems automatically fold unquoted identifiers to lowercase or uppercase. Quoted identifiers may be case-sensitive in a database-specific way. Therefore, the table names `Customer`, `customer`, and `"Customer"` are not necessarily equivalent.

Guidelines when designing names:

- Consistently use lowercase and snake_case for tables/columns if that is the project's convention.
- Avoid names that collide with SQL keywords such as `order`, `user`, `group` whenever a clearer name can be chosen.
- Do not arbitrarily change casing between annotations and DDL.
- If you must work with a legacy schema containing special identifiers, check the database's quoting rules and how Spring Data Relational configures names.
- Give columns meaningful names; avoid overly short names or names that rely on context not expressed in the name itself.

For example, `orders` or `purchase_orders` is usually easier to read than a generic name like `order`, which can run into keyword or quoting rules depending on the database system.

## 11. NamingStrategy Can Be Customized

The snake_case convention is the default, not a mandatory rule for every project. Spring Data Relational allows customizing how table and column names are derived through `NamingStrategy`.

A project may need a different naming strategy when:

- An existing database uses uppercase or a custom naming convention.
- Tables are prefixed by module.
- An organization shares a naming standard across multiple applications.
- You want a convention different from the default while still keeping mapping consistent.

When customizing, make sure the strategy is used consistently in the application's mapping context. How the strategy is registered depends on the Spring Data Relational/R2DBC configuration style used by the project. Configure according to your current Spring Data version and inspect the actual SQL generated.

Do not change the naming strategy just to fix one or two special table names. For isolated exceptions, `@Table` and `@Column` are usually easier to understand. A naming strategy is appropriate when the convention needs to change broadly.

## 12. Cases to Watch Out for When Mapping

### 12.1. Singular vs. Plural Table Names

Spring Data does not automatically infer singular/plural semantics to rename tables. `Customer` defaults to `customer`, and `OrderItem` defaults to `order_item`.

If your project uses `customers`, `orders`, `order_items`, use `@Table` for names that differ from the default or configure an appropriate naming strategy. Do not assume that Spring Data always appends `s`.

### 12.2. Properties Named Like Keywords or Unclear Names

A Java name may be valid, yet the derived column name may not fit the schema or database rules. Use `@Column` to map to a clear column name, avoid keywords, and check the actual identifier.

Example:

~~~java
@Table("app_users")
public class AppUser {
    @Id
    private Long id;

    @Column("user_status")
    private String status;
}
~~~

### 12.3. Derived Properties

If a property is purely a computed result and is not stored in the database, mark it with `@Transient`. Otherwise, Spring Data may treat it as a persistent property and look for a corresponding column during mapping operations.

### 12.4. Subclasses and Composite Properties

Not every Java property is a simple column. Spring Data Relational also has rules for embedded objects, aggregates, and mapped collections. Those cases must be modeled with the corresponding annotations, such as `@Embedded` or `@MappedCollection`, rather than assuming every nested object will automatically become a column or table as intended.

In particular, Spring Data Relational organizes data around aggregates. A foreign key in the database does not automatically create bidirectional object relationships or lazy loading like JPA. Clearly define the aggregate root, child table structure, and how related data is queried.

### 12.5. Working with an Existing Database

When an application connects to an existing database, read the schema DDL or metadata before writing entities. You should not rename tables/columns in the database just to match the naming strategy if other applications depend on that schema.

Instead, use `@Table` and `@Column` to map entities to the actual names. This keeps Java names clean while staying compatible with the existing schema.

## 13. Workflow for Mapping a New Java Class

When creating a new entity in Spring Data Relational R2DBC, you can proceed in this order:

1. Identify the actual table name in the database.
2. Name the Java class in PascalCase and determine the default table name that the naming strategy will derive.
3. If the actual table name differs from the default, declare `@Table`.
4. Identify the identifier property and mark it with `@Id`.
5. Compare each property against its derived snake_case column name.
6. If the actual column differs from the default, declare `@Column`.
7. Mark non-persisted properties with `@Transient`.
8. Choose Java types compatible with the SQL types, driver, and converters.
9. Check relationships/collections according to the aggregate model and corresponding annotations.
10. Create or update the schema via migrations, including primary keys, foreign keys, nullability, unique constraints, and business constraints.
11. Use a repository or `R2dbcEntityTemplate` to verify mapping operations; for manual SQL, write table and column names explicitly according to the schema.
12. Confirm that mapping works with the project's actual database and driver.

## 14. Combined Example with Two Entities

Suppose the database has two tables: `customers` and `purchase_orders`. Each order stores `customer_id` to reference the customer.

Customer entity:

~~~java
@Table("customers")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;
}
~~~

Order entity:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @Column("order_number")
    private String orderNumber;

    private Instant createdAt;
}
~~~

Illustrative DDL:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
~~~

Here, `customerId` is mapped to the `customer_id` column, yet a Java `Long` property by itself does not guarantee that the customer exists. The foreign key in the DDL enforces referential integrity.

Similarly, `@Table("purchase_orders")` ensures Spring Data uses the plural table, while `UNIQUE(order_number)` and the foreign key are database rules. Mapping metadata and SQL constraints have separate responsibilities, yet they must align.

## 15. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| Class `Customer` automatically maps to table `customers` | Default is `customer`; use `@Table` or a naming strategy if you want another name |
| Property `createdAt` maps to `createdAt` in SQL | By default it is converted to `created_at` |
| `@Table` changes all column names | `@Table` only specifies the table name |
| `@Column` creates the column in the database | `@Column` only provides mapping metadata; DDL/migrations create columns |
| `@Id` automatically creates a primary key | `@Id` marks the identifier property for Spring Data; the schema still needs a primary key |
| Every Java property is persisted | `@Transient` properties do not participate in persistent mapping |
| The naming strategy creates the schema | The naming strategy only determines names in mapping metadata |
| SQL written in `DatabaseClient` automatically converts camelCase to snake_case | Hand-written SQL must use the exact table/column names from the schema |
| The column name determines the SQL type | Column types are determined by the schema and the driver/framework conversion mechanism |

## 16. Self-Check Exercises

### Exercise 1: Deriving Default Names

Given the class:

~~~java
public class ShippingAddress {
    private Long id;
    private String recipientName;
    private String postalCode;
    private Instant updatedAt;
}
~~~

Determine the default table name and column names.

Hint: The table is `shipping_address`; the columns are `id`, `recipient_name`, `postal_code`, and `updated_at`.

### Exercise 2: Mapping to an Existing Table

The database has table `app_users` with columns `user_name` and `email_address`. Write the `AppUser` entity with properties `userName` and `email`.

Hint:

~~~java
@Table("app_users")
public class AppUser {
    @Id
    private Long id;

    @Column("user_name")
    private String userName;

    @Column("email_address")
    private String email;
}
~~~

### Exercise 3: Application-Only Property

A `Product` entity has `price`, `quantity`, and `totalValue`. `totalValue` is computed from the first two properties and does not need to be saved to the database. What should you do?

Hint: Mark `totalValue` with `@Transient` and compute the value in Java. If you want to persist this value, remove `@Transient` and create the corresponding column.

### Exercise 4: Distinguishing Mapping from Schema

An entity has `@Id private Long id;`, yet the database table has no primary key. Does `@Id` automatically fix this issue?

Hint: No. `@Id` is mapping metadata. Add a primary key via migration/DDL and ensure existing data satisfies the constraint before applying it.

### Exercise 5: Manual SQL

Entity `PurchaseOrder` has `@Table("purchase_orders")` and property `createdAt`. If you write manual SQL to filter by creation time, which column name should you use?

Hint: Use `created_at` per the schema. Manual SQL does not automatically rename Java properties.

## 17. Key Takeaways

- Spring Data Relational provides a default naming strategy to derive table names from classes and column names from properties.
- A class name like `PurchaseOrder` is typically converted to `purchase_order`; a property `createdAt` becomes `created_at`.
- By default, table names are not automatically pluralized.
- `@Table` overrides the table name; `@Column` overrides the column name.
- `@Id` marks the identifier property; `@Transient` excludes a property from persistent mapping.
- Mapping annotations do not automatically create tables, columns, primary keys, or constraints.
- SQL types depend on the schema, Spring Data conversion, R2DBC driver, and database system.
- Hand-written SQL must use actual table/column names; do not rely on the naming strategy to rewrite SQL strings.
- For existing databases, map entities to the actual schema and manage changes with migrations.

When creating an entity in Spring Data Relational R2DBC, start from the actual table and column names, compare them against the default naming strategy, and use annotations for any names that need overriding. This keeps mapping readable, consistent, and aligned with the schema your application uses.
