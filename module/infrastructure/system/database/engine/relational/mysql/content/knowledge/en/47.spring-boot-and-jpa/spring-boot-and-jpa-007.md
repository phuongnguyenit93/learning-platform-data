# Entities, Table/Column Names, Backticks, and Platform Case Sensitivity

In a Spring Boot application using JPA with MySQL, the Entity class name, Java property names, and database table/column names are related but do not have to match identically. JPA/Hibernate translates Entity mappings into SQL; naming strategies may transform names by convention; and MySQL enforces its own rules regarding identifiers, reserved words, and case sensitivity. Failing to control these layers can result in an application that runs on a developer machine yet fails with `Table doesn't exist`, `Unknown column`, or mapping errors when deployed to Linux.

This lesson covers mapping Entities using `@Entity`, `@Table`, and `@Column`, how Hibernate applies implicit and physical naming strategies, using backticks when dealing with special identifiers, and the impact of `lower_case_table_names` across platforms. Examples use Spring Boot, Hibernate ORM, and MySQL; confirm exact behavior against your deployed versions.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish the Entity name in JPQL from the physical table name in MySQL.
- Explicitly map table, column, and foreign key names using JPA annotations.
- Explain implicit naming strategies and physical naming strategies.
- Avoid SQL keyword conflicts and know when to quote identifiers with backticks.
- Distinguish case-sensitivity rules for database/table names versus column names in MySQL.
- Check `lower_case_table_names` and identify risks when moving applications between Windows, macOS, and Linux.
- Keep JPA mappings aligned with schema migrations and verify against real MySQL.

## 1. Four Name Layers to Distinguish

When reading an Entity, distinguish these four names:

| Name Layer | Example | Where Is It Used? |
|---|---|---|
| Java class name | `PurchaseOrder` | Java code, reflection, and the type system |
| Entity name | `PurchaseOrder` or the name set in `@Entity(name = ...)` | JPQL/HQL, e.g., `SELECT p FROM PurchaseOrder p` |
| Physical table name | `purchase_order` | SQL sent to MySQL |
| Physical column name | `customer_id`, `created_at` | SQL and MySQL table structure |

The Entity name is not the table name. For example, `@Entity(name = "PurchaseOrder")` sets the name used in JPQL; `@Table(name = "purchase_order")` specifies the physical table Hibernate queries. Similarly, the Java property `customerId` can map to the `customer_id` column.

JPQL uses Entity names and Java properties, whereas SQL uses physical table and column names. Confusing these two name spaces is a common mistake when writing queries or reading Hibernate logs.

## 2. Explicit Entity Mapping with Annotations

Example Entity representing the `purchase_order` table:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false, length = 30)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    // Constructor, getters, and business methods omitted.
}
```

Here:

- `@Entity` marks the class as a persistent entity.
- `@Table(name = "purchase_order")` explicitly specifies the MySQL table.
- `@Id` identifies the JPA-level primary key.
- `@Column(name = "customer_id")` maps the Java property to the physical column name.
- `@Enumerated(EnumType.STRING)` persists the enum name instead of its ordinal position; this prevents enum reordering from corrupting the meaning of historical data.

Column names in `@Column` must match the live schema after applying the naming strategy. `nullable`, `length`, and similar annotation attributes describe mapping/DDL metadata; they do not replace SQL migrations in production.

### 2.1. Entity Name Different from Table Name

You can assign a distinct Entity name for JPQL:

```java
@Entity(name = "Purchase")
@Table(name = "purchase_order")
public class PurchaseOrder {
    // Fields...
}
```

JPQL uses the Entity name:

```java
@Query("select p from Purchase p where p.customerId = :customerId")
List<PurchaseOrder> findByCustomer(@Param("customerId") Long customerId);
```

Native SQL uses database table and column names:

```java
@Query(value = "SELECT * FROM purchase_order WHERE customer_id = :customerId",
       nativeQuery = true)
List<PurchaseOrder> findNativeByCustomer(@Param("customerId") Long customerId);
```

Do not use `purchase_order` as the Entity name in JPQL unless that is the declared Entity name. Conversely, do not use `Purchase` in native SQL if no physical table bears that name.

### 2.2. Foreign Key Mapping

Foreign key column names can be specified with `@JoinColumn`:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

If the `Customer` Entity has `@Table(name = "customer")` and primary key `id`, the mapping above uses the `customer_id` column on `purchase_order` as the reference. Ensure data types, signedness, indexes, and constraints match on both sides in MySQL.

When a column is mapped both via a scalar field and as a join column, avoid letting both mappings write to the same column. If reading the scalar value separately is truly necessary, configure one mapping as read-only via `insertable = false, updatable = false`, while keeping write ownership clear.

## 3. Implicit Naming and Physical Naming Strategies

Hibernate applies two naming stages:

1. **Implicit naming strategy** derives the logical name when a mapping omits an explicit full name. For example, a table name may be derived from the Entity class name; a column name may be derived from the property name.
2. **Physical naming strategy** converts the logical name into the physical name used in the database. This strategy can convert camelCase to snake_case, lowercase names, or enforce organizational naming rules.

Example without explicit names:

```java
@Entity
public class CustomerAccount {
    @Id
    private Long id;

    private LocalDateTime createdAt;
}
```

A Spring-style physical naming strategy can produce physical names such as `customer_account` and `created_at`. However, exact results depend on the implicit strategy, physical strategy, Spring Boot/Hibernate version, and application configuration. Never guess the schema purely from class names.

### 3.1. Configuring the Physical Naming Strategy

Spring Boot lets you configure the strategy via a property:

```properties
spring.jpa.hibernate.naming.physical-strategy=org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
```

The strategy class must exist in the Hibernate version your application runs. A project may also use a custom strategy or the default configured by Spring Boot. Before changing it, inspect the active configuration and the SQL emitted by Hibernate.

A physical naming strategy typically applies to both implicitly derived logical names and explicitly specified names in mappings. Thus, if an annotation specifies `customerId` and the strategy converts it to `customer_id`, the schema must match that final physical name. Using physical-ready names directly in annotations is more predictable.

### 3.2. Choosing a Stable Convention

A common convention for MySQL is:

- Java classes and properties use `PascalCase`/`camelCase`.
- Database, table, and column names use lowercase with underscores.
- Avoid spaces, hyphens, or special characters in identifiers.
- Table names are clear business nouns, e.g., `customer_account`, `purchase_order`, `payment_transaction`.
- Foreign key names reflect the relationship, e.g., `customer_id`, `warehouse_id`.
- Avoid SQL keywords and confusing names like `order`, `group`, `rank`, `user` unless checked against your MySQL version's reserved word list.

Choose a convention before creating the schema and apply it consistently across Entities, migration SQL, native queries, views, stored procedures, and operational scripts. A good naming strategy cannot automatically rewrite hardcoded legacy names inside native SQL.

## 4. SQL Keywords and Backticks in MySQL

MySQL uses backticks (`` ` ``) to quote identifiers. Identifiers include database, table, column, index, and other object names. Backticks allow names that collide with SQL keywords or contain characters requiring quoting.

For example, if you must work with a legacy table named `order`:

```sql
SELECT id, customer_id
FROM `order`
WHERE id = 1001;
```

If column names also collide with keywords:

```sql
SELECT `rank`, `group`
FROM `order`;
```

In MySQL, string literals use single quotes:

```sql
SELECT *
FROM purchase_order
WHERE order_status = 'PAID';
```

Never use backticks to quote data values; backticks are exclusively for identifiers.

### 4.1. Quoting Identifiers in Hibernate Mappings

Hibernate supports backtick syntax in mapping names to request dialect-appropriate identifier quoting:

```java
@Entity
@Table(name = "`order`")
public class LegacyOrder {

    @Id
    private Long id;

    @Column(name = "`rank`")
    private Integer rank;
}
```

This is a Hibernate quoting syntax, not a portable rule across all JPA providers. Hibernate interprets backticks in mappings and the MySQL dialect emits properly quoted SQL. If the application switches JPA providers, re-verify the mappings.

For new tables, pick non-keyword names such as `purchase_order` instead of relying on quoting. Quoting is a compatibility tool for legacy schemas or identifiers that cannot be renamed.

### 4.2. Backticks in SQL and Literal Backtick Characters in Names

In MySQL, a literal backtick inside a quoted identifier is escaped by doubling it (two consecutive backticks). However, names containing backticks are hard to read and error-prone during SQL generation; never name new objects this way.

Some database systems use double quotes for identifiers. In MySQL, double quotes normally denote string literals by default; when the `ANSI_QUOTES` SQL mode is enabled, double quotes denote identifiers and can no longer be used as normal string literals. Therefore, avoid writing SQL that depends on double quotes if SQL mode is not strictly controlled.

Check SQL mode:

```sql
SELECT @@SESSION.sql_mode;
SELECT @@GLOBAL.sql_mode;
```

Do not toggle `ANSI_QUOTES` arbitrarily, as it changes how existing SQL is parsed.

### 4.3. Should You Quote Every Identifier?

Hibernate provides an option to quote all identifiers globally, such as `hibernate.globally_quoted_identifiers`. While this can prevent keyword collisions, it alters generated SQL and interacts with metadata, identifier casing, migrations, and native queries.

Do not enable global quoting just to mask a few poorly named tables or columns. Prefer safe naming conventions, quote selectively for legacy schemas, and inspect generated SQL after any configuration change.

## 5. Case Sensitivity in MySQL

MySQL does not apply the same case-sensitivity rules to all identifier types. The most critical detail for cross-platform deployments is that database and table names can differ in case sensitivity depending on the operating system and `lower_case_table_names`.

### 5.1. `lower_case_table_names`

Check the running value:

```sql
SELECT @@GLOBAL.lower_case_table_names;
```

Primary values:

| Value | How Database/Table Names Are Stored | How Comparisons Work |
|---:|---|---|
| `0` | Preserves letter case at creation | Case-sensitive |
| `1` | Stored in lowercase | Case-insensitive |
| `2` | Preserves letter case on supporting filesystems, compared in lowercase | Case-insensitive |

Common defaults vary by platform: Linux typically uses `0`, Windows typically uses `1`, and macOS often uses `2`. Actual values depend on the installation, filesystem, and how the server was initialized; always query the variable on the target instance rather than assuming from the OS alone.

In MySQL 8.0, `lower_case_table_names` must be chosen when initializing the data directory and cannot be changed arbitrarily afterward. The value must be compatible with the filesystem; the server may refuse to start if configured incompatibly on that platform.

### 5.2. Example Failure Moving from Windows to Linux

Suppose a schema contains a table named `CustomerAccount`:

```sql
CREATE TABLE CustomerAccount (
  id BIGINT PRIMARY KEY,
  email VARCHAR(255) NOT NULL
);
```

On a case-insensitive server (common on Windows with `lower_case_table_names=1`), `SELECT * FROM customeraccount` finds that table. On Linux with `lower_case_table_names=0`, `CustomerAccount` and `customeraccount` are two distinct identifiers; the same lowercase query fails with table not found. This is why physical names must be standardized across migrations and mappings, then tested against production-like settings.

If a system has both `User` and `user` tables, they can coexist in a case-sensitive environment but cannot be distinguished in a case-insensitive environment. Resolve such schema conflicts before migrating platforms.

### 5.3. Column Names Differ from Table Names

Column names in MySQL are case-insensitive, unlike database and table names. For instance, `customer_id` and `CUSTOMER_ID` refer to the same column. That does not mean you should mix casing; consistent casing keeps SQL readable and reduces errors when porting to other engines.

Aliases, Entity names, and Java properties follow their own rules. Java is case-sensitive, and Entity/property names in JPQL must match the mapping. A property `customerId` cannot be written as `CustomerID` in JPQL just because MySQL column names are case-insensitive.

## 6. Physical Names, Reserved Words, and Schema Migrations

Entity mappings must match the actual schema. In production Spring Boot applications, manage schema changes via Flyway or Liquibase instead of letting Hibernate create or alter tables automatically.

Example migration SQL:

```sql
CREATE TABLE purchase_order (
  id BIGINT NOT NULL AUTO_INCREMENT,
  customer_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  order_status VARCHAR(30) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_purchase_order_customer (customer_id)
) ENGINE = InnoDB;
```

JPA mappings must point to these exact table and column names. If you rename `customer_id` in a migration and forget to update `@Column` or the naming strategy, the application will fail at query time.

### 6.1. Using Schema Validation

In production, configure Hibernate to validate mappings rather than automatically modifying the schema:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

`validate` instructs Hibernate to verify that the existing schema is compatible with entity mappings. It does not generate migrations and does not replace thorough checks for indexes, data, constraints, or performance. In development, other modes may fit your workflow, but never use `update` as a production schema management tool.

### 6.2. Inspecting Actual Tables and Columns

When encountering `Table doesn't exist` or `Unknown column`, inspect the physical definitions:

```sql
SHOW CREATE TABLE app.purchase_order\G

SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'app'
ORDER BY TABLE_NAME;

SELECT COLUMN_NAME, COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'purchase_order'
ORDER BY ORDINAL_POSITION;
```

Compare results against:

- `@Table`, `@Column`, and `@JoinColumn` in Entities.
- Configured implicit and physical naming strategies.
- Native queries, JPQL, and repository queries.
- Migrations already applied in the target environment.
- The database's `lower_case_table_names` setting.

Do not merely patch the failing SQL statement; trace the source producing the mismatched physical name so future Entities and migrations do not keep drifting.

## 7. Observing SQL Generated by Hibernate

When mappings mismatch, check the actual SQL Hibernate emits. In development, enable SQL logging:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

With Hibernate 6, bind-parameter logging can be enabled via:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind-parameter logs may include emails, tokens, personal information, or sensitive payloads. Never enable `TRACE` in production without data-protection controls, masking, and log retention limits.

To observe emitted names, run a repository query or flush operation in a test environment and compare the SQL against `SHOW CREATE TABLE`. Note that Hibernate may defer DML until flush; calling `save()` does not necessarily send SQL at that exact line of code.

### 7.1. Common Errors and Investigation Steps

| Error | Common Cause | What to Check |
|---|---|---|
| `Table 'app.customer_account' doesn't exist` | Physical name from naming strategy differs from migration or differs in case | `SHOW CREATE TABLE`, `@@lower_case_table_names`, naming strategy |
| `Unknown column 'created_at'` | `@Column`/strategy mismatches schema or migration has not run | `INFORMATION_SCHEMA.COLUMNS`, Hibernate logs |
| `You have an error in your SQL syntax` near table name | Identifier collides with reserved word or lacks quoting | Keyword list and backticks in SQL |
| JPQL reports Entity not found | Using table name instead of entity name, or wrong Entity name | `@Entity(name=...)` and JPQL query |
| Works on Windows, fails on Linux | Mixed-case table name and differing `lower_case_table_names` | Standardize physical names and test on Linux |
| Migration ran yet Hibernate cannot find table | Migration created a different name from physical strategy output | Compare migration SQL with final physical name |

## 8. Naming Design Workflow for New Projects

When creating a new Spring Boot/JPA module, follow these steps:

1. Choose a physical naming convention for databases, tables, columns, indexes, and constraints.
2. Pick implicit/physical naming strategies aligned with that convention.
3. Use `@Entity`, `@Table`, `@Column`, and `@JoinColumn` to make mappings explicit where it matters.
4. Avoid reserved words, spaces, hyphens, and identifiers differing only by case.
5. Create the schema with Flyway/Liquibase using the agreed physical names.
6. Set `ddl-auto=validate` in production to catch mapping drift.
7. Run integration tests against MySQL with the same major version and case-sensitivity settings as production.
8. Inspect Hibernate-generated SQL and `SHOW CREATE TABLE` prior to release.

For legacy systems, never rename tables en masse simply by swapping the naming strategy. Changing the strategy causes Hibernate to emit SQL against different names across many Entities. Plan controlled migrations compatible with old and new application versions, along with data migration or views if needed.

## 9. Cross-Platform Testing

If developers use Windows or macOS while production runs on Linux, testing solely on H2 or local MySQL can miss case-sensitivity bugs. Use real MySQL in integration tests—for example via Testcontainers—with an image and configuration matching production.

Tests should cover:

- Initializing the schema from all migrations on an empty database.
- Starting the Spring context and letting Hibernate validate mappings.
- Executing repository queries, JPQL, and native SQL.
- Checking table/column names with mixed case or reserved words in legacy schemas.
- Verifying `lower_case_table_names` on the test server matches production.
- Running upgrade migrations from prior schema versions, not just fresh installs.

Never create two tables differing only by letter case for business logic. If a legacy schema already has colliding names, rename via migration before moving to a platform with different rules.

## 10. Hands-On Exercise

A Spring Boot application runs on Windows in development and Linux in production. The current Entity is:

```java
@Entity
public class UserOrder {
    @Id
    private Long id;

    private Long customerId;
    private LocalDateTime createdAt;
}
```

The production migration creates a table `user_order` with columns `customer_id` and `created_at`. One native query references table `User_Order`, while another legacy table is named `order`.

Complete the following tasks:

1. Explain how the Entity name, class name, and physical table name differ.
2. Write explicit `@Table` and `@Column` mappings for `user_order`, `customer_id`, and `created_at`.
3. Determine which physical names implicit and physical naming strategies might produce if annotations are omitted.
4. Fix the native query to use the correct table and column names.
5. If querying the legacy table named `order` is unavoidable, write SQL using backticks and explain why renaming is preferable when possible.
6. Compare `lower_case_table_names=0`, `1`, and `2`; explain why an app working on Windows can fail on Linux.
7. Explain why backticks cannot make `Order` and `order` two distinct tables on a case-insensitive server.
8. Describe how to verify the schema using `SHOW CREATE TABLE`, `INFORMATION_SCHEMA`, and Hibernate logs.
9. Propose a schema validation configuration and migration workflow for production.
10. Design an integration test to catch table/column naming mismatches before release.

Try running migrations on a test MySQL instance configured like production, starting Spring Boot with `ddl-auto=validate`, executing repository queries, and comparing logged SQL against table definitions.

## Conclusion

JPA Entity names, Java class names, and physical table/column names are separate naming layers. `@Entity`, `@Table`, `@Column`, and `@JoinColumn` make mappings explicit, while implicit and physical naming strategies control how names are derived and transformed. MySQL uses backticks to quote identifiers, though quoting does not alter the server's case-sensitivity rules. In particular, `lower_case_table_names` governs database and table names and must be chosen when initializing the data directory. Standardize on lowercase snake_case names, avoid reserved words, manage schemas via migrations, and test on MySQL configured like production.
