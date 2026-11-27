# Mapping Tables and Schemas with @Table

## 1. Role of @Table in Spring Data R2DBC

Spring Data R2DBC maps Java objects to rows in a relational database through metadata and naming conventions. The `@Table` annotation tells the framework which table a class maps to and, when needed, which schema it resides in.

`@Table` belongs to the package:

```java
import org.springframework.data.relational.core.mapping.Table;
```

This is a Spring Data Relational annotation shared across relational modules such as Spring Data JDBC and Spring Data R2DBC. Do not confuse it with JPA's `jakarta.persistence.Table`. An R2DBC application should use the annotation from `org.springframework.data.relational.core.mapping`.

Simple example:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String email;
    private String displayName;
}
```

The `Customer` class is mapped to the `customer` table. Repository operations or `R2dbcEntityTemplate` use this metadata to determine the table when generating SQL.

`@Table` can also be used without a name:

```java
@Table
public class Customer {
    @Id
    private Long id;
    private String email;
}
```

When no name is specified, Spring Data uses `NamingStrategy` to derive the table name from the class. The exact derivation depends on the naming strategy and identifier processing in the version being used.

## 2. @Table Is Mapping Metadata, Not a Table Creation Command

`@Table` describes how Spring Data locates a table when reading or writing an entity. The annotation does not automatically create schemas, tables, indexes, constraints, or sequences.

Example:

```java
@Table(value = "customer", schema = "crm")
public class Customer {
    @Id
    private Long id;
    private String email;
}
```

This code requests mapping to the `crm.customer` table according to how the database/dialect represents identifiers. It is not equivalent to DDL:

```sql
CREATE SCHEMA crm;

CREATE TABLE crm.customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
```

DDL must be managed with migrations such as Flyway, Liquibase, or the project's schema deployment workflow. When changing `@Table` from an old name to a new name, a corresponding migration is needed so that the actual table exists.

## 3. Attributes of @Table

In current Spring Data Relational Javadoc, the annotation has three main attributes:

| Attribute | Meaning |
| --- | --- |
| `value` | Table name |
| `name` | Alias of `value` for specifying the table name |
| `schema` | Schema (or corresponding user/schema depending on the database) containing the table |

`value` and `name` are interchangeable ways to specify the table name. `schema` identifies the namespace preceding the table name.

### 3.1. Using value

This is the common shorthand syntax:

```java
@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Equivalent to:

```java
@Table(value = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

### 3.2. Using name

Versions that include the `name` attribute allow writing:

```java
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

`name` is an alias for `value`, not the name of a different field in the database. For readability and compatibility with common examples, `value` can be used.

### 3.3. Using schema

To map to a table in a specific schema:

```java
@Table(value = "purchase_order", schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

A schema is the table's namespace. When `schema` is specified, Spring Data uses it as a prefix for the table name according to the dialect's identifier rendering rules.

### 3.4. Specifying schema While Leaving the Table Name to Convention

You can specify `schema` while still letting Spring Data derive the table name:

```java
@Table(schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

The table name is derived from the class via `NamingStrategy`, while the schema is fixed to `sales`.

### 3.5. Omitting schema

If `schema` is omitted, Spring Data uses the default schema from `NamingStrategy.getSchema()` if provided by the strategy, or lets the database apply the connection/user's default schema.

Example:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;
}
```

Leaving out `schema` does not mean the table is always in the `public` schema. The default schema might be `public` in PostgreSQL, `dbo` in SQL Server, the default schema/user in Oracle, or the selected database/schema in MySQL. Verify the actual user and database configuration.

## 4. Distinguishing Table, Schema, Database, and Catalog

These concepts are related but not synonymous:

- **Table:** object that stores rows of data.
- **Schema:** namespace used to group and qualify tables, views, sequences, or other objects.
- **Database:** database unit managed by the server and usually selected by the connection when connecting.
- **Catalog:** higher-level namespace layer in some database systems and metadata APIs.

Terminology and structure vary across databases:

| Database System | Example Interpretation |
| --- | --- |
| PostgreSQL | One database contains multiple schemas; the default schema is typically `public` |
| SQL Server | A database contains schemas; the default schema for many users is `dbo` |
| MySQL | `SCHEMA` is commonly used synonymously with `DATABASE` |
| Oracle | Schema is tied to a user; the `@Table` Javadoc also mentions the schema/user case |
| H2 | A database can contain multiple schemas |

`@Table.schema` specifies a schema namespace in Spring Data's abstraction. It does not change the host, port, or database/catalog that `ConnectionFactory` connects to. With MySQL, take particular care to distinguish the database selected in the connection from how the driver/dialect renders schema names.

If you want to switch to another database, you must configure the corresponding `ConnectionFactory`/R2DBC URL. You cannot switch servers or database connections merely by changing `@Table(schema = ...)`.

## 5. How Spring Data Derives Table Names

When no name is provided in `@Table`, Spring Data uses `NamingStrategy`.

The default naming strategy splits camelCase parts with underscores. Examples:

| Java Name | Derived Logical Name |
| --- | --- |
| `Customer` | `customer` |
| `PurchaseOrder` | `purchase_order` |
| `SavingsAccount` | `savings_account` |
| `OrderLineItem` | `order_line_item` |

Final casing and identifier quoting depend on the dialect and mapping configuration. Mapping documentation across versions may describe different rendered output due to changes in identifier processing.

Example:

```java
@Table
public class SavingsAccount {
    @Id
    private Long id;
    private String accountNumber;
}
```

Spring Data derives the table name from the class and column names from properties. In camelCase convention, `accountNumber` is converted to the logical name `account_number`.

### 5.1. Table Name Comes from the Simple Class Name

The default table name is based on the simple class name, not the full package name. Two classes in different packages with the same simple name can conflict if they share the same mapping context and naming strategy.

In that case, use `@Table` to specify an explicit name:

```java
@Table("billing_customer")
public class Customer {
    @Id
    private Long id;
}
```

### 5.2. Column Names Are Not Set by @Table

`@Table` specifies the table/schema. If a property name does not match the physical column name, use `@Column`:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String displayName;
}
```

Here `@Table` selects the `customer` table; `@Column` maps the `displayName` property to the `display_name` column.

## 6. Mapping an Entity to a Specific Schema

Example of an entity located in the `crm` schema:

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table(value = "customer", schema = "crm")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private String email;

    @Column("display_name")
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Repository:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

The schema/table must exist in the database:

```sql
CREATE SCHEMA crm;

CREATE TABLE crm.customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL,
    display_name VARCHAR(150)
);
```

This is illustrative DDL using PostgreSQL syntax. Other databases may use different identity/auto-increment and schema syntax.

When calling:

```java
customerRepository.findById(10L);
```

Spring Data uses entity metadata to generate the operation against the declared table. The actual schema/table name in SQL is rendered according to the dialect.

## 7. Mapping Multiple Tables with the Same Name in Different Schemas

A database can have multiple schemas, each containing a table with the same name. For example, both `crm` and `archive` schemas have a `customer` table.

You can declare two separate entities:

```java
@Table(value = "customer", schema = "crm")
public class CurrentCustomer {
    @Id
    private Long id;
    private String email;
}

@Table(value = "customer", schema = "archive")
public class ArchivedCustomer {
    @Id
    private Long id;
    private String email;
}
```

The two entities represent two different physical tables:

- `crm.customer`.
- `archive.customer`.

Separate repositories can be used:

```java
public interface CurrentCustomerRepository
        extends ReactiveCrudRepository<CurrentCustomer, Long> {
}

public interface ArchivedCustomerRepository
        extends ReactiveCrudRepository<ArchivedCustomer, Long> {
}
```

Meaningful class names help avoid confusing active data with archived data. Both entities still share the same Spring Data Relational mapping annotations.

## 8. Default Schema Using NamingStrategy

If most entities reside in the same schema, you can provide a `NamingStrategy` bean instead of repeating `schema` in every annotation.

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.NamingStrategy;

@Configuration
class RelationalNamingConfiguration {

    @Bean
    NamingStrategy namingStrategy() {
        return new NamingStrategy() {
            @Override
            public String getSchema() {
                return "app";
            }
        };
    }
}
```

With this strategy, the default schema for mapping is `app`. An entity can specify just the table:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;
}
```

If an entity has `@Table(schema = "audit")`, the schema specified directly on the annotation is used for that entity. The `@Table` Javadoc states that the annotation's schema is used as the table's schema; when omitted, Spring Data can obtain the default schema from `NamingStrategy.getSchema()`.

### 8.1. Customizing Table Names with NamingStrategy

Besides `schema`, `NamingStrategy` can customize how table/column names are derived. Example:

```java
@Configuration
class RelationalNamingConfiguration {

    @Bean
    NamingStrategy namingStrategy() {
        return new NamingStrategy() {

            @Override
            public String getSchema() {
                return "app";
            }

            @Override
            public String getTableName(Class<?> type) {
                return NamingStrategy.super.getTableName(type);
            }
        };
    }
}
```

The example above keeps the default table naming rule and only sets the default schema. You can override `getTableName` to apply a prefix or custom convention, while ensuring the naming strategy is deterministic and does not cause conflicts between entities.

### 8.2. How NamingStrategy and @Table Work Together

This can be summarized as:

- `NamingStrategy` provides default rules for the mapping context.
- `@Table(value = ...)` overrides the table name for a single entity.
- `@Table(schema = ...)` overrides the schema for a single entity.
- If an attribute is not specified, the framework can fall back to default metadata/naming strategy.

Avoid creating arbitrary inconsistent naming rules. Keep naming conventions consistent across entities, DDL, and migrations.

## 9. Identifier Quoting and Case Sensitivity

An identifier is a table, schema, or column name. Databases may fold unquoted identifiers to uppercase or lowercase, or treat quoted identifiers as case-sensitive.

Spring Data R2DBC uses `R2dbcDialect` and identifier processing to render identifiers. Quote characters vary by database:

| Database | Common Identifier Quote Character |
| --- | --- |
| PostgreSQL | Double quote `"` |
| MySQL | Backtick |
| SQL Server | Square brackets or double quotes when configured appropriately |
| H2 | Double quote |

Table name examples:

```sql
-- PostgreSQL
SELECT * FROM "purchase_order";

-- MySQL: identifier enclosed in backticks
SELECT * FROM `purchase_order`;

-- SQL Server
SELECT * FROM [purchase_order];
```

This is illustrative native syntax. Applications using Spring Data typically let the dialect render identifiers when the framework generates SQL.

### 9.1. Quoting Behavior Depends on Version

Do not assume every version of Spring Data Relational has the same default identifier quoting:

- Spring Data Relational 3.5 documentation notes that `forceQuote` for R2DBC is disabled by default in the `@Column` section.
- Spring Data Relational 4.1 mapping documentation describes table/column names derived from classes/properties as being rendered quoted according to the default database; this can be disabled via `R2dbcMappingContext.setForceQuote(false)` or by using `R2dbcMappingContext.forPlainIdentifiers()`.

Therefore, when upgrading versions, read the mapping reference for the exact release train managed by the Spring Boot BOM and verify the actual generated SQL. Do not rely on an older version's quoting behavior when designing schemas for a new version.

### 9.2. Disabling Quotes for Plain Identifiers

Current Spring Data Relational documentation describes creating a mapping context using plain identifiers:

```java
R2dbcMappingContext.forPlainIdentifiers(...);
```

Or configuring the context with:

```java
context.setForceQuote(false);
```

These are mapping context configuration APIs; the exact way to override the bean/context depends on the Spring Data R2DBC version and application configuration. Only disable quoting when the schema follows the database's unquoted identifier rules and does not rely on reserved keywords or special characters.

### 9.3. Avoiding Names That Require Quoting

Prefer:

- Lowercase.
- Simple names.
- `snake_case`.
- No spaces or special punctuation.
- No collisions with reserved keywords.

For example, use `purchase_order` instead of `order`. Simple names keep DDL, native queries, migrations, and administration tools more consistent.

## 10. Table Names Colliding with SQL Keywords

If a legacy schema has a table named `order`, identifier quoting depends on the dialect and mapping configuration.

PostgreSQL example:

```sql
CREATE TABLE sales."order" (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
```

Entity:

```java
@Table(value = "order", schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
    private String status;
}
```

You must verify how Spring Data renders the name `order` in the version you are using. If identifier processing does not quote it in line with the DDL, queries may fail with syntax errors.

A better long-term solution is to rename the physical table to `purchase_order` via migration when possible. Do not rely on quoting to justify table names that are awkward across tools.

## 11. Combining @Table and @Column

`@Table` selects the table/schema; `@Column` selects column names. Example:

```java
@Table(value = "customer_profile", schema = "crm")
public class CustomerProfile {

    @Id
    private Long id;

    @Column("first_name")
    private String firstName;

    @Column("last_name")
    private String lastName;

    @Column("email_addr")
    private String email;
}
```

Mapping:

| Java property | Database object |
| --- | --- |
| Entity `CustomerProfile` | `crm.customer_profile` |
| `id` | `id` |
| `firstName` | `first_name` |
| `lastName` | `last_name` |
| `email` | `email_addr` |

The `@Column` annotation lets the column name differ from the property name. Column name quoting rules also depend on `R2dbcMappingContext` and the dialect.

## 12. @Table with Aggregates and Child Tables

Spring Data Relational organizes mapping around aggregates. The aggregate root is the entry point for persistence operations; child objects or collections can be stored in separate tables according to mapping metadata.

Example:

```java
@Table(value = "purchase_order", schema = "sales")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}

public class OrderLine {
    private String productCode;
    private Integer quantity;
}
```

`@Table` identifies the aggregate root table. `@MappedCollection` controls how the collection is mapped and which column references the root's ID. It does not replace `@Table` on the root.

If you need to customize the table or column names of child structures, check the mapping metadata and naming rules of the Spring Data Relational version in use. `@Table` does not automatically create foreign keys or DDL for these relationships.

### 12.1. Do Not Confuse with JPA Relationships

Spring Data Relational is not JPA/Hibernate. You cannot assume that putting `@Table` on two classes and adding `@OneToMany` will make R2DBC generate joins or lazy loading like an ORM.

Spring Data Relational uses its own aggregate model and mapping. You must design the schema, foreign keys, and load/save operations according to relational mapping rules.

## 13. @Table and Repository Scanning

`@Table` marks a class as a candidate for relational mapping. The annotation also helps metadata scanning discover and preprocess domain types.

Example:

```java
@Table("invoice")
public class Invoice {
    @Id
    private Long id;
}
```

Repository:

```java
public interface InvoiceRepository
        extends ReactiveCrudRepository<Invoice, Long> {
}
```

In some mapping configurations, a POJO can be mapped by convention even without `@Table`. However, annotating entities keeps mapping metadata explicit and aids classpath scanning. Especially when an application uses multiple Spring Data modules, ensure repositories are recognized by the right store.

If a repository is not created:

- Check the scanned packages.
- Check R2DBC repository configuration annotations if using manual configuration.
- Check that the domain type has appropriate metadata.
- Check that the Spring Data R2DBC dependency is on the classpath.

## 14. @Table Does Not Automatically Rewrite Native SQL

An important point: `@Table` is used by mapping metadata when Spring Data generates persistence operations. It does not rewrite every SQL statement written by developers.

Repository native query example:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("SELECT * FROM crm.customer WHERE email_address = :email")
    Mono<Customer> findByEmail(String email);
}
```

In the `@Query` above, the table name `crm.customer` is hardcoded. If you change the annotation to:

```java
@Table(value = "client", schema = "crm")
public class Customer {
    @Id
    private Long id;
}
```

the native query does not automatically change to `crm.client`. You must update the SQL manually or use an appropriate mapping API.

Similarly, `DatabaseClient.sql("SELECT ... FROM ...")` executes the SQL provided by the application. `@Table` does not replace table names in raw SQL.

## 15. Schemas Across Multiple Environments

An application may run in local, test, staging, and production environments with different schemas:

| Environment | Example Schema |
| --- | --- |
| Local | `app_dev` |
| Test | `app_test` |
| Staging | `app_staging` |
| Production | `app` |

If the schema differs by environment, you can configure migrations and `NamingStrategy` appropriately per profile.

Example:

```java
@Configuration
class MappingConfiguration {

    @Bean
    NamingStrategy namingStrategy(
            @Value("#{environment.getProperty('app.database.schema', 'app')}") String schema) {

        return new NamingStrategy() {
            @Override
            public String getSchema() {
                return schema;
            }
        };
    }
}
```

This example obtains the default schema from configuration. Make sure the `NamingStrategy` bean is picked up by Spring Data R2DBC auto-configuration and that the corresponding schema has been created by migrations before the application runs.

Never set the schema from an arbitrary request value. A schema is an identifier, not an ordinary bind parameter. For multi-tenancy, use an explicitly designed tenant routing/connection strategy with allowlist checks and database permissions.

## 16. Schema-per-Tenant and Limits of Static Annotations

Some systems store each tenant in a separate schema, for example:

- `tenant_a.customer`.
- `tenant_b.customer`.

If the schema is fixed per entity, `@Table(schema = ...)` works well. However, if the schema changes per request/tenant, a static annotation on the class is not enough to automatically select the schema for the current user.

Design approaches to consider:

1. Give each tenant or tenant group its own `ConnectionFactory`/mapping context.
2. Route connections to select a validated database/schema before querying.
3. Have the database session set the schema/search path per connection safely.
4. Use dynamic expression/schema features only when the Spring Data version in use explicitly supports them and context resolution is tightly controlled.

Some versions of `@Table` support value expressions for table/schema names. Capabilities, caching behavior, and sanitization mechanisms vary by version. If an expression returns a `SqlIdentifier`, the current Javadoc notes that the identifier is used directly without further sanitization. Therefore, never construct a `SqlIdentifier` from a user-supplied string.

For multi-tenancy, inspect connection pools and transaction contexts: a connection assigned to tenant A must not be reused for tenant B without resetting the session schema/search path.

## 17. Schema Access Permissions

Even when mapping is correct, queries can still fail if the database user lacks permission to access the schema or table.

PostgreSQL example:

```sql
GRANT USAGE ON SCHEMA crm TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE crm.customer
TO app_user;
```

If using sequences or identity sequences that have separate permissions depending on the database, verify those permissions as well. DDL migrations often run as a migration user with higher privileges than the runtime user; do not assume the runtime user has permission to create schemas/tables.

Common errors:

- Schema does not exist.
- Table does not exist in the selected schema.
- User lacks USAGE/SELECT/INSERT privileges.
- Connection points to a different database.
- Default schema or search path differs from the local environment.

When troubleshooting, check both the rendered SQL and the actual database user/connection.

## 18. Using Migrations to Synchronize @Table with the Schema

When changing mapping:

```java
@Table(value = "customer", schema = "crm")
public class Customer {
    @Id
    private Long id;
}
```

the migration must create the matching table:

```sql
CREATE SCHEMA IF NOT EXISTS crm;

CREATE TABLE IF NOT EXISTS crm.customer (
    id BIGINT PRIMARY KEY
);
```

When moving from `public.customer` to `crm.customer`, the migration needs to:

- Create the `crm` schema.
- Create or migrate data to the new table.
- Create indexes/constraints.
- Grant permissions to the runtime user.
- Check dependent views, triggers, foreign keys, and jobs.
- Switch application mapping.
- Have a rollback or compatibility plan during rollout.

Do not merely change the annotation and expect existing data to move on its own.

### 18.1. Schema Names in Migrations and Mapping Must Match

Typos or casing mismatches can cause hard-to-diagnose errors:

```text
@Table(schema = "CRM", value = "customer")
Migration: CREATE TABLE crm.customer ...
```

If the database is case-sensitive when identifiers are quoted, `CRM` and `crm` may be two different schemas. Use lowercase and stay consistent.

## 19. Testing @Table Mapping

An integration test should verify that Spring Data actually accesses the intended schema/table.

Repository example:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);
}
```

Illustrative test:

```java
@DataR2dbcTest
class CustomerMappingTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void savesCustomerInConfiguredSchema() {
        Customer customer = new Customer(
                "person@example.com",
                "Example Person");

        StepVerifier.create(repository.save(customer))
                .assertNext(saved -> assertThat(saved.getId()).isNotNull())
                .verifyComplete();

        StepVerifier.create(repository.findByEmail("person@example.com"))
                .assertNext(found ->
                        assertThat(found.getDisplayName())
                                .isEqualTo("Example Person"))
                .verifyComplete();
    }
}
```

This is a test skeleton; entity constructors/getters, schema initialization, test database, and test dependencies must be configured for your specific project. Use the exact R2DBC driver and database supported by the application.

### 19.1. Testing a Dedicated Schema

If using a specific schema, the test setup must create the schema before the repository runs:

```sql
CREATE SCHEMA crm;
CREATE TABLE crm.customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL,
    display_name VARCHAR(150)
);
```

The test must verify that data appears in the right schema. You can query the qualified table directly to verify:

```sql
SELECT COUNT(*) FROM crm.customer;
```

### 19.2. Testing Multiple Schemas with the Same Table Name

If you have `crm.customer` and `archive.customer`, write one record via each repository and verify no data is written to the wrong schema.

### 19.3. Testing Naming Strategy

If using a custom `NamingStrategy`, test that table/column names are rendered according to the convention. Whenever possible, run integration tests against a real database to verify quoting/case folding.

## 20. Common Errors with @Table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Relation/table not found | Wrong table name or schema | Check `value`, `schema`, and DDL |
| Query runs against default schema | Annotation lacks `schema` or naming strategy is not applied | Check metadata and default schema |
| Table has an unexpected name | `NamingStrategy` derived the name from the class | Use explicit `@Table(value = ...)` |
| Table name matching keyword causes syntax error | Identifier was not quoted for the dialect | Check `forceQuote`/dialect or rename the table |
| Uppercase table name not found | Case folding vs. quoted identifier mismatch | Use exact casing or standardize schema |
| Repository is not created | Incorrect domain type/repository scan | Check scanned packages and mapping metadata |
| Native query still hits the old table | `@Table` does not rewrite native SQL | Update the SQL or use a mapping API |
| Works locally, fails in production | Different default schema, permissions, or search path | Check connection user and schema permissions |
| Two entities accidentally write to the same table | Derived names collided | Specify explicit names with `@Table` |
| Multi-tenant reads wrong data | Schema/connection context shared improperly | Design routing and reset connection state |
| Changed annotation but new table does not appear | `@Table` does not run DDL/migrations | Create the corresponding migration |

## 21. Table and Schema Naming Guidelines

To keep mapping maintainable:

- Use table names with business meaning.
- Use `snake_case` and lowercase.
- Avoid reserved keywords like `order`, `user`, or `group`.
- Do not use spaces or special characters in new identifiers.
- Use schemas by bounded context or module when namespace separation is needed.
- Keep annotation names aligned with migrations.
- Do not embed the schema name into `value` when the `schema` attribute exists.
- Never use a schema from a request without validation/allowlisting.

Example:

```java
@Table(value = "purchase_order", schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

This reads more clearly than `@Table("order")` and avoids keyword conflicts.

## 22. When to Use @Table vs. NamingStrategy?

| Situation | Appropriate Approach |
| --- | --- |
| One entity has a special table name | `@Table(value = ...)` |
| One entity lives in a separate schema | `@Table(schema = ...)` |
| Most entities share the same schema | `NamingStrategy.getSchema()` |
| Whole project needs custom table naming rules | Custom `NamingStrategy` |
| Hand-written native SQL | Write the exact table/schema name in SQL |
| Schema varies per tenant | Tenant-aware routing or supported, controlled dynamic mechanism |
| Need to create tables/indexes/constraints | Migration tool/DDL |

Do not create a custom naming strategy just to rename one table. Annotating directly is easier to read and has less impact on other entities.

## 23. Checking APIs by Spring Data Version

`@Table` belongs to Spring Data Relational and is used by Spring Data R2DBC. However, mapping, naming, identifier quoting, and expression support can change between release trains.

When consulting documentation:

1. Identify the application's Spring Boot version.
2. Check the BOM to find the Spring Data release train.
3. Open the `Table` Javadoc for that exact version.
4. Check `value`, `name`, and `schema` in the annotation.
5. Read the R2DBC mapping reference for the same release.
6. Confirm `NamingStrategy` and `R2dbcMappingContext` behavior.
7. Run integration tests to see SQL working against the real driver.

Current Javadoc describes `value` and `name` as aliases and `schema` as the schema prefix. Recent versions also describe expression support for table/schema names; if using this feature, read the exact Javadoc for the running version.

## 24. Checklist When Adding @Table to an Entity

When mapping a new entity, verify:

1. Imported the right `org.springframework.data.relational.core.mapping.Table`.
2. Selected a table name matching the real schema.
3. Specified `schema` when you do not want to rely on the connection's default schema.
4. Used `@Column` for columns whose names differ from property names.
5. Table/column names match the dialect's casing and quoting rules.
6. Avoided identifiers colliding with reserved keywords whenever possible.
7. Migrations have created the corresponding schema/table/indexes/constraints.
8. The runtime user has permissions to access the schema/table.
9. The repository or `R2dbcEntityTemplate` uses the right mapping context.
10. Native SQL has been updated separately if table/schema names changed.
11. Integration tests run on the target driver/database.
12. With multi-tenancy, connection/schema routing cannot leak across tenants.

## 25. Official References

- [Spring Data Relational R2DBC Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html) — convention mapping, `@Table`, `NamingStrategy`, and identifier quoting.
- [Javadoc @Table — Spring Data Relational 4.1](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/Table.html) — `value`, `name`, and `schema` attributes.
- [Javadoc @Table — Spring Data Relational 3.5](https://docs.spring.io/spring-data/jdbc/docs/3.5.x/api/org/springframework/data/relational/core/mapping/Table.html) — API of the 3.5 release train.
- [Javadoc NamingStrategy](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/NamingStrategy.html) — how table names, column names, and default schemas are derived.
- [Spring Data R2DBC Reference](https://docs.spring.io/spring-data/relational/reference/r2dbc/) — repositories and persistence with R2DBC.

`@Table` is the declaration point for mapping between an entity and a relational table in Spring Data R2DBC. Use `value` or `name` to specify the table name, `schema` to specify the namespace, and `NamingStrategy` for application-wide default rules. Keep annotations synchronized with DDL/migrations, database permissions, identifier quoting, and native queries. Because naming/quoting behavior can change across release trains, always check documentation for the right version and verify mapping with integration tests against a real R2DBC driver.
