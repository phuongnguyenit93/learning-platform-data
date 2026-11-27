# Mapping Column Names, Aliases, and Result Properties

When using Spring Data Relational R2DBC, a SQL query returns a set of rows with named or aliased columns. Spring Data needs to convert each value in a row into a property of a Java entity or DTO. That process depends on mapping metadata, the naming strategy, and the column labels returned by the database.

Column names in the database can differ from Java property names. For example, an entity uses `customerName`, the schema uses `customer_name`, while a join query may need an alias `customer_name` to avoid colliding with a column from another table. If a column name or alias does not match the mapping expected by Spring Data, the property may not be assigned properly or mapping may fail depending on the entity type and constructor.

This lesson explains how Spring Data R2DBC maps query results, the difference between column names and aliases, how to use `@Column`, how to define aliases for entities and projections, how to handle SQL expressions, joins, null values, and how to perform explicit mapping with `DatabaseClient`.

## 1. From SQL results to Java properties

A SQL query returns a result set. Each row has values; each column has a label provided by the R2DBC driver through metadata. That label is usually the selected column name or an alias declared with `AS`.

Schema example:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(200)
);
~~~

Java entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("customer_name")
    private String name;

    @Column("email_address")
    private String email;
}
~~~

When reading rows from the `customer` table, Spring Data uses the entity's mapping metadata to determine which column corresponds to which property:

| Java property | Mapped column name |
|---|---|
| `id` | `id` |
| `name` | `customer_name` |
| `email` | `email_address` |

Query example:

~~~sql
SELECT id, customer_name, email_address
FROM customer
WHERE id = :id;
~~~

The column labels in the result match the entity's mapping. Spring Data can convert the row into a `Customer` without writing a per-column mapper manually.

General flow:

~~~text
SQL query
   |
   v
Database result set
   |
   v
R2DBC Row + RowMetadata
   |
   v
Spring Data mapping metadata
   |
   v
Entity / DTO
~~~

For repository methods, Spring Data typically performs this conversion step based on the return type. When using `DatabaseClient`, the application can either request Spring mapping or read individual columns manually from `Row`.

## 2. Distinguishing column names, property names, and aliases

These three names serve different roles:

- **Java property name:** the attribute name in an entity or DTO, such as `customerName`.
- **Physical column name:** the name declared in the schema, such as `customer_name`.
- **SQL alias:** an alternative label for a column in a result set, such as `customer_name AS display_name`.

Example table:

| Component | Example | Where it is used |
|---|---|---|
| Java property | `customerName` | Entity/DTO source code |
| Column in schema | `customer_name` | DDL and SQL |
| Alias in SELECT | `customer_name AS display_name` | Query result labels |
| Mapping annotation | `@Column("display_name")` | Entity property metadata |

An alias does not rename a column in the database. It only changes the column label returned by the current query.

Example:

~~~sql
SELECT customer_name AS display_name
FROM customer;
~~~

The table still has the column `customer_name`. The query result has the label `display_name`. To map this label into an entity with property `name`, the mapping metadata must map `name` to `display_name`, for example:

~~~java
@Column("display_name")
private String name;
~~~

If the entity still declares `@Column("customer_name")`, the alias `display_name` no longer matches the column name expected by metadata. Choose an alias matching the target mapping or adjust the metadata accordingly.

## 3. Naming strategy and @Column determine mapping names

When a property does not declare `@Column`, Spring Data Relational uses a naming strategy to infer the column name from the property. The default rule usually converts camelCase to snake_case:

| Java property | Column name via naming strategy |
|---|---|
| `firstName` | `first_name` |
| `createdAt` | `created_at` |
| `orderNumber` | `order_number` |
| `totalAmount` | `total_amount` |

Example:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private LocalDateTime createdAt;
}
~~~

The default mapping corresponds to `order_number` and `created_at`, assuming the project uses the default naming strategy.

When a column name differs from the convention, use Spring Data Relational's `@Column`:

~~~java
@Column("ORDER_NO")
private String orderNumber;
~~~

In a custom query, the SELECT must return a column label matching the active mapping metadata. For the property above, the column label must match `ORDER_NO` according to the identifier rules of the database and driver.

`@Column` is metadata mapping a property to a column. It does not rewrite hand-written SQL and does not automatically generate aliases in the result set.

### 3.1. Use the correct annotation package

For Spring Data Relational R2DBC, import:

~~~java
import org.springframework.data.relational.core.mapping.Column;
~~~

Do not confuse it with JPA's `jakarta.persistence.Column`. The two annotations belong to two different persistence mechanisms.

When a project has both JPA and R2DBC, check the actual imports on your entities. JPA annotations do not replace the mapping metadata used by Spring Data Relational.

## 4. Mapping @Query results to entities

When a repository method returns an entity, the columns in SELECT must provide data corresponding to the properties the entity needs to map.

Example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, customer_name, email_address
        FROM customer
        WHERE id = :id
        """)
    Mono<Customer> findCustomerById(Long id);
}
~~~

Entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("customer_name")
    private String name;

    @Column("email_address")
    private String email;
}
~~~

Here the column names in SELECT match the entity's mapping. Spring Data puts the `customer_name` value into the `name` property and `email_address` into the `email` property.

If a query reads data from a legacy table with different column names, you can use aliases so the result set has labels matching the entity:

~~~sql
SELECT
    legacy_cust_nm AS customer_name,
    email_addr AS email_address
FROM legacy_customer
WHERE customer_id = :id;
~~~

The entity still uses `@Column("customer_name")` and `@Column("email_address")`. Aliases make the result labels match the target metadata.

Do not assume any arbitrary alias will automatically convert to a Java property name. Rely on the naming strategy or the property's `@Column` value, then verify with integration tests on the real driver and database.

## 5. Using aliases for DTOs and projections

Not every query needs to return a full entity. For reports, summary screens, or lists displaying only a few fields, DTO projections are usually more suitable.

DTO example:

~~~java
public record CustomerOrderSummary(
        Long customerId,
        String customerName,
        Long orderCount) {
}
~~~

Query:

~~~java
@Query("""
    SELECT
        c.id AS customer_id,
        c.customer_name AS customer_name,
        COUNT(o.id) AS order_count
    FROM customer c
    LEFT JOIN purchase_order o
        ON o.customer_id = c.id
    GROUP BY c.id, c.customer_name
    ORDER BY c.customer_name
    """)
Flux<CustomerOrderSummary> findOrderSummary();
~~~

The aliases follow the naming convention corresponding to the DTO component names: `customer_id`, `customer_name`, and `order_count`. When using class-based projections, ensure the DTO's constructor/components and result labels map cleanly under your project's Spring Data configuration.

A DTO contains only the data the query needs to return. This avoids creating an entity with many unselected properties and makes clear that the result is read-only data serving a specific use case.

### 5.1. Interface projections

When using an interface projection, accessor names represent the properties the projection requires:

~~~java
public interface CustomerNameView {
    Long getId();
    String getCustomerName();
}
~~~

The query must provide labels compatible with the projection's mapping:

~~~java
@Query("""
    SELECT
        c.id AS id,
        c.customer_name AS customer_name
    FROM customer c
    WHERE c.active = TRUE
    """)
Flux<CustomerNameView> findActiveCustomerNames();
~~~

With projections, clearer aliases make queries easier to understand and avoid depending on unstable column names. Verify mapping in your Spring Data R2DBC version, especially when projections have nested properties or property names differing significantly from the schema.

### 5.2. When to use an entity vs. a DTO?

| Scenario | Suitable result type |
|---|---|
| Reading an aggregate for business processing or updating | Entity |
| Reading the full state of an object | Entity |
| Screen needing only a few columns | DTO or projection |
| Report with `COUNT`, `SUM`, `AVG` | DTO or projection |
| Multi-table join results with colliding column names | DTO with clear aliases |
| Computed results not corresponding to a stored entity | DTO or specialized result type |

Avoid mapping a partial result set into a full entity if unselected properties might be mistaken for null or default state. Using a DTO for partial read-only results generally makes the contract clearer.

## 6. Aliases for expressions and aggregate functions

A SQL expression rarely has a default label suitable for a Java property. Give it a meaningful alias.

Example:

~~~sql
SELECT
    c.id AS customer_id,
    COALESCE(c.nickname, c.customer_name) AS display_name,
    COUNT(o.id) AS order_count,
    SUM(o.total_amount) AS total_spent
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
GROUP BY c.id, c.nickname, c.customer_name;
~~~

DTO:

~~~java
public record CustomerStatistics(
        Long customerId,
        String displayName,
        Long orderCount,
        BigDecimal totalSpent) {
}
~~~

The aliases clearly describe each expression's result. Do not rely on default names generated by the database for `COUNT(...)` or `COALESCE(...)`; such names can be unreadable, vary across databases, or fail to match properties.

Notes on data types:

- `COUNT` typically returns a wide integer type, though the exact Java type must be compatible with the driver and database.
- `SUM` has a result type depending on the input column type and database engine.
- `AVG` can return a decimal type different from the original column type.
- `COALESCE` must have arguments with compatible data types.
- Values can be null if the expression or aggregation permits it.

Check actual return types and choose appropriate Java types, such as `Long` for counts and `BigDecimal` for monetary amounts.

## 7. Aliases when joining multiple tables

A join query can return multiple columns with the same name. For example, both `customer` and `purchase_order` have `id`, `created_at`, or `status` columns.

Avoid relying on `SELECT *`:

~~~sql
SELECT *
FROM customer c
JOIN purchase_order o ON o.customer_id = c.id;
~~~

The result set may contain duplicate labels. When a mapper reads by name, determining which column belongs to which entity can be ambiguous or driver-dependent.

Select columns explicitly and assign clear aliases:

~~~sql
SELECT
    c.id AS customer_id,
    c.customer_name AS customer_name,
    o.id AS order_id,
    o.status AS order_status,
    o.created_at AS order_created_at
FROM customer c
JOIN purchase_order o
    ON o.customer_id = c.id;
~~~

Corresponding DTO:

~~~java
public record CustomerOrderRow(
        Long customerId,
        String customerName,
        Long orderId,
        String orderStatus,
        LocalDateTime orderCreatedAt) {
}
~~~

This aliasing avoids collisions between `customer.id` and `purchase_order.id`, while making the origin of each field clear.

If the goal is to return a `Customer` containing a list of `Order`s, do not assume an arbitrary join will automatically assemble an aggregate graph like a JPA ORM. Spring Data Relational has its own aggregate model. Decide how to load and assemble related data using repositories, custom queries, or DTOs consistent with aggregate boundaries.

## 8. Distinguishing column aliases from table names and property names in derived queries

An alias exists only in the SELECT result set. It does not rename tables, alter the schema, or change property names in the domain model.

Example:

~~~sql
SELECT customer_name AS display_name
FROM customer;
~~~

This query does not create a `display_name` column in the `customer` table. To rename a physical column, use a schema migration.

Similarly, derived query methods use the entity's Java properties:

~~~java
Flux<Customer> findByName(String name);
~~~

If the entity has a `name` property and `@Column("customer_name")`, Spring Data uses metadata to generate the condition on the `customer_name` column. Do not rename the method to `findByCustomerName` merely because the physical column is `customer_name`, unless the Java property is actually named `customerName`.

For hand-written SQL in `@Query`, use physical table/column names or aliases matching the query itself. Mapping metadata does not automatically rewrite names inside raw SQL strings.

## 9. Explicit mapping with DatabaseClient

When full control over reading results is needed, `DatabaseClient` lets you extract values from `Row` by column label.

Example:

~~~java
Flux<CustomerOrderRow> findCustomerOrders() {
    return databaseClient.sql("""
            SELECT
                c.id AS customer_id,
                c.customer_name AS customer_name,
                o.id AS order_id,
                o.status AS order_status
            FROM customer c
            JOIN purchase_order o
                ON o.customer_id = c.id
            """)
            .map((row, metadata) -> new CustomerOrderRow(
                    row.get("customer_id", Long.class),
                    row.get("customer_name", String.class),
                    row.get("order_id", Long.class),
                    row.get("order_status", String.class)))
            .all();
}
~~~

Here, the strings passed to `row.get(...)` must match the column labels provided by the driver. Thus, aliases in SQL and names used in the mapper must stay consistent.

You can use `RowMetadata` to inspect column information provided by the driver:

~~~java
.map((row, metadata) -> {
    ColumnMetadata idColumn =
            metadata.getColumnMetadata("customer_id");

    Long id = row.get("customer_id", Long.class);

    return new CustomerIdView(id);
})
~~~

Metadata APIs and name-based lookup behavior depend on the R2DBC SPI and driver. If you encounter case-sensitivity differences, check the actual labels returned and use stable names in SQL.

### 9.1. Reading nullable columns

A nullable column can return Java `null` when read with `Row.get`:

~~~java
String phoneNumber =
        row.get("phone_number", String.class);
~~~

If `phone_number` is SQL NULL, `phoneNumber` can be `null`. Use wrapper types like `Long`, `Integer`, or `Boolean` when a column can be null; Java primitive types such as `long` or `int` cannot hold null.

Do not confuse two cases:

- No rows: the publisher emits no row.
- A row exists but a nullable column is SQL NULL: the publisher emits a row and the column value is null.

### 9.2. Explicit data type conversion

`Row.get(label, type)` requires a Java type compatible with the value the driver can provide. For numeric types, date/time types, UUIDs, or database-specific types, check the driver's type mapping.

If a conversion is not supported directly, use Spring Data conversions when mapping entities/DTOs, or convert explicitly inside the mapper. Avoid arbitrary casts that could trigger `ClassCastException` at runtime.

## 10. Alias names and identifier case sensitivity

Case-sensitivity rules for column names and aliases depend on the database management system.

For example, PostgreSQL folds unquoted identifiers to lowercase. Some other engines fold to uppercase or apply their own rules. Quoted identifiers generally preserve exact casing according to dialect rules.

PostgreSQL example:

~~~sql
SELECT customer_name AS display_name
FROM customer;
~~~

The unquoted alias is normalized to `display_name`.

If written as:

~~~sql
SELECT customer_name AS "displayName"
FROM customer;
~~~

PostgreSQL preserves the casing of the quoted alias. The mapper must then look up the exact label reported by the driver.

To minimize cross-database differences:

- Prefer lowercase `snake_case` aliases.
- Avoid aliases containing spaces or special characters unless necessary.
- Avoid using SQL keywords as aliases.
- If quoting identifiers is unavoidable, use dialect-appropriate quoting syntax and test on the target database.
- Do not rely on drivers normalizing names the same way across all database engines.

## 11. Missing columns, extra columns, and partial entity mapping

An entity may have more persistent properties than the columns selected in a SQL query. For example, the entity has `id`, `name`, `email`, `phoneNumber`, while the query selects only `id` and `name`.

~~~sql
SELECT id, customer_name
FROM customer;
~~~

This is a partial result set. Properties absent from the result set cannot be populated from the row. Exact behavior depends on the entity type, constructor, and mapping converters; do not rely on missing properties always defaulting to null or a default value automatically.

If a use case only needs two fields, create a dedicated projection/DTO:

~~~java
public record CustomerNameView(
        Long id,
        String customerName) {
}
~~~

If the query needs to return a full entity, select all required persistent columns:

~~~sql
SELECT
    id,
    customer_name,
    email_address,
    phone_number
FROM customer;
~~~

Extra columns in the result set do not automatically become entity properties. If a query includes `COUNT`, expressions, or columns from joined tables, map them into an appropriate DTO instead of expecting the entity to hold unmapped columns.

## 12. Aliases for nested projections and value objects

When results need to represent nested data, check DTO styles supported by your Spring Data version's mapping rules. Do not assume that dots in an alias like `address.city` automatically construct a nested object.

A safe approach is to use flat aliases:

~~~sql
SELECT
    c.id AS customer_id,
    c.customer_name AS customer_name,
    a.city AS address_city,
    a.postal_code AS address_postal_code
FROM customer c
LEFT JOIN customer_address a
    ON a.customer_id = c.id;
~~~

Flat DTO:

~~~java
public record CustomerAddressRow(
        Long customerId,
        String customerName,
        String addressCity,
        String addressPostalCode) {
}
~~~

The service layer can transform the flat DTO into a nested response structure. This makes missing-address cases explicit and avoids relying on unsupported nested-alias mapping behavior.

If an entity uses `@Embedded` or a value object, choose aliases matching the embedded property's column mapping and configured prefix. Inspect Spring Data Relational's mapping metadata to confirm effective column names.

## 13. Common errors when mapping column names and aliases

| Error | Cause | Resolution |
|---|---|---|
| Alias differs from column name expected by entity mapping | Result set label does not match mapping metadata | Use an alias matching the naming strategy or `@Column` |
| Using Java property names instead of physical columns in SQL | Hand-written SQL is not rewritten by mapping metadata | Write exact column names or aliases in SELECT |
| Using `SELECT *` in joins | Multiple tables share column names | Select columns explicitly and assign distinct aliases |
| Omitting aliases for `COUNT`, `SUM`, or expressions | Unpredictable result labels that fail to match DTO | Assign stable, meaningful aliases |
| Selecting too few columns when returning a full entity | Entity lacks required mapping data | Select all required columns or use a projection/DTO |
| Using camelCase aliases when naming strategy expects snake_case | Labels do not follow mapping convention | Use snake_case aliases or explicit mapping |
| Confusing JPA `@Column` with Spring Data `@Column` | Annotation belongs to a different framework | Import `org.springframework.data.relational.core.mapping.Column` |
| Duplicate aliases in joins | Mapper cannot disambiguate target columns | Assign distinct aliases such as `customer_id`, `order_id` |
| Wrong casing on quoted aliases | Database preserves exact casing of quoted identifiers | Check actual labels returned by the driver |
| Wrong cast on `COUNT` or `SUM` values | SQL/driver type differs from assumed Java type | Choose a compatible type or convert explicitly |
| Treating an alias as a schema change | Aliases only rename query result labels | Use migrations to rename physical columns |

## 14. Workflow for designing SELECT queries and result mapping

When writing a declared query, follow these steps:

1. Decide whether the result type is an entity, DTO, or projection.
2. List the properties required in the result type.
3. Determine effective mapped column names from the naming strategy and `@Column`.
4. Write explicit SELECT lists, avoiding `SELECT *` for joins or projections.
5. Add aliases for expressions, aggregates, and colliding column names.
6. Ensure aliases align with mapping metadata or explicit mappers.
7. Check case sensitivity and quoting rules for your database.
8. Verify Java types match the types returned by the driver.
9. Account for nullable columns and potentially absent properties.
10. Run integration tests on the target database/driver to confirm the entity or DTO builds as expected.

Creating a mapping table before writing SQL helps prevent errors:

| Result label | Target property | Notes |
|---|---|---|
| `id` | `id` | Primary key |
| `customer_name` | `name` | Entity uses `@Column("customer_name")` |
| `email_address` | `email` | Entity uses `@Column("email_address")` |
| `order_count` | `orderCount` | Alias for `COUNT` expression |
| `order_id` | `orderId` | Alias disambiguated from `customer_id` |

## 15. Testing result mapping

A query can execute successfully yet still map into the wrong properties or types. Therefore, integration tests should assert the actual values of important properties.

Repository example:

~~~java
StepVerifier.create(customerRepository.findCustomerById(existingId))
        .assertNext(customer -> {
            assertThat(customer.getId()).isEqualTo(existingId);
            assertThat(customer.getName()).isEqualTo("Nguyen An");
            assertThat(customer.getEmail()).isEqualTo("an@example.com");
        })
        .verifyComplete();
~~~

Projection example:

~~~java
StepVerifier.create(customerRepository.findOrderSummary())
        .assertNext(summary -> {
            assertThat(summary.customerId()).isEqualTo(10L);
            assertThat(summary.customerName()).isEqualTo("Nguyen An");
            assertThat(summary.orderCount()).isEqualTo(2L);
        })
        .verifyComplete();
~~~

With `DatabaseClient`, verify the mapper returns expected values by alias. Prepare test data covering:

- Column names differing from Java property names.
- Aliases for computed expressions.
- Two tables sharing identical column names.
- Nullable columns.
- Zero matching rows.
- Large numeric values or specialized types when the query includes aggregates.

Unit tests on a mapper can validate pure Java conversion logic, while integration tests against the target database confirm that aliases, metadata, driver, and mapping all work together.

## 16. Key takeaways

- Spring Data R2DBC maps result sets using mapping metadata and column labels provided by the driver.
- Java property names, physical column names, and SQL aliases are three distinct concepts.
- Naming strategies typically convert camelCase to snake_case; `@Column` overrides the column name for a specific property.
- An alias in SELECT only changes the result label; it does not alter the schema or Java property names.
- For entities, result labels must align with effective column names in mapping metadata.
- For DTOs/projections, set clear aliases matching properties and the active mapping naming convention.
- Always alias expressions, aggregates, and colliding column names in JOINs.
- Avoid `SELECT *` when joining multiple tables or selecting a small projection.
- `DatabaseClient` allows reading explicitly by alias via `Row.get`; names must match labels emitted by the driver.
- Distinguish having no rows from having a row with SQL NULL columns.
- When SELECT retrieves only partial data, use a DTO/projection rather than assuming a full entity will be constructed properly.
- Verify aliases, data types, and identifier casing with integration tests on a real database.
