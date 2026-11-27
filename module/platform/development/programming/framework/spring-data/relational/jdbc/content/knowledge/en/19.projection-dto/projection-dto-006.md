# Column Aliases, Parameter Names, and Data Types on Projections

In **Spring Data Relational JDBC**, projections allow a query to return a data shape suited to the use case instead of always constructing the entire aggregate root. A list screen may only need order number, customer name, and total amount; a report may need order counts by status. Projections represent these results via interfaces, DTOs, or records.

For projections to work reliably, the contract between SQL and Java must be clear. **Column names in the result set, property or constructor parameter names, input parameter names, and data types must align according to the mapping rules of Spring Data JDBC and the JDBC driver.** A query that executes cleanly in the database can still fail when the framework maps results if aliases are wrong, the constructor does not match, or Java types cannot receive SQL values.

This lesson focuses on three areas directly tied to projections:

- **Column aliases:** naming result columns for unambiguous mapping to projection properties.
- **Parameter names:** binding SQL placeholders to repository method parameters.
- **Data types:** ensuring SQL, JDBC, and Java types are compatible, including nulls, arithmetic, and aggregate values.

## 1. What Is a Projection?

An entity typically describes the state of a persisted aggregate. A projection describes **a data view** required for a specific query.

Example order entity:

~~~java
@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        String status,
        Long customerId,
        BigDecimal totalAmount,
        LocalDateTime createdAt
) {
}
~~~

A list screen only needs:

~~~java
public record OrderListItem(
        Long orderId,
        String orderNumber,
        String customerName,
        BigDecimal totalAmount
) {
}
~~~

The query can join the order table with the customer table and return OrderListItem. This result is not the full PurchaseOrder aggregate; it is a read structure combining data from multiple tables.

### 1.1. Why Not Always Return Entities?

If a screen only needs four fields, loading the full aggregate can be wasteful:

- Extra columns that are never displayed may be read.
- The aggregate may contain child collections that must be queried and materialized.
- A reporting join query may return results that do not correspond to a single entity.
- Persistence entities can expose write-model details to read APIs.

Projections help select the exact data for the use case. They are especially useful for lists, reports, dashboards, searches, and aggregate queries.

### 1.2. A Projection Is Not an Aggregate for Updates

A projection usually holds partial data and may combine multiple tables. Do not take a slim projection and treat it as a complete aggregate to invoke domain behavior or save back through the root repository.

When business mutations are needed:

1. Load the aggregate root via the repository.
2. Invoke domain behavior on the root.
3. Save the aggregate via the repository.

When only reading is needed:

1. Write a query selecting the exact columns.
2. Map into a projection/DTO.
3. Return the result to the caller.

## 2. Three Common Forms of Projections

Spring Data supports projections in several forms. Specific details can depend on the module and Spring Data JDBC version in use; always verify the release contract in your project.

### 2.1. Interface-Based Projections

An interface describes the accessors the caller needs:

~~~java
public interface CustomerSummary {
    Long getId();
    String getName();
    String getCity();
}
~~~

The repository can declare a method returning the projection:

~~~java
List<CustomerSummary> findByActiveTrue();
~~~

Spring Data generates an appropriate implementation/proxy to supply values from the query result. With closed projections, the interface declares only properties determinable in advance. This lets the framework know what properties the caller needs in query types where the module supports optimization.

JavaBean accessors typically use the getName() form. When using records or DTO classes, accessors may be name(); those are two distinct API styles.

### 2.2. Class-Based Projections (DTOs)

A DTO class represents returned data via a constructor:

~~~java
public class CustomerSummary {
    private final Long id;
    private final String name;
    private final String city;

    public CustomerSummary(Long id, String name, String city) {
        this.id = id;
        this.name = name;
        this.city = city;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCity() {
        return city;
    }
}
~~~

Class-based projections do not need interface proxies. Spring Data must know how to instantiate the DTO and map query values to the corresponding constructor/properties.

If a DTO has multiple constructors, clarify the persistence constructor selected under Spring Data rules, using @PersistenceCreator when appropriate. Constructor parameter names and compiler metadata can also affect mapping.

### 2.3. Record Projections

Java records fit read DTOs nicely because components and the constructor are declared concisely:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        String city
) {
}
~~~

Records provide a canonical constructor and component-named accessors:

~~~java
CustomerSummary summary = ...;
summary.name();
summary.city();
~~~

Records fit well when projection data is treated as immutable values. However, records do not automatically solve alias or type-conversion issues; result columns must still map cleanly to components.

## 3. Column Aliases: Connecting SQL Names to Java Property Names

When a query has expressions, joins, or column names differing from Java properties, use aliases to assign explicit names to each result column.

Example:

~~~sql
SELECT
    po.id AS order_id,
    po.order_number AS order_number,
    c.name AS customer_name,
    po.total_amount AS total_amount
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.status = :status;
~~~

Projection:

~~~java
public record OrderListItem(
        Long orderId,
        String orderNumber,
        String customerName,
        BigDecimal totalAmount
) {
}
~~~

With Spring Data Relational's common default naming strategy, camelCase Java property names correspond to snake_case column names. Thus aliases order_id, order_number, customer_name, and total_amount supply result column names matching those properties. If your application uses a different naming strategy or custom mapping, aliases must match the column names expected by mapping metadata.

### 3.1. Why Aliases Matter

A join query can contain multiple columns sharing the same name:

~~~sql
SELECT
    po.id,
    c.id,
    po.status,
    c.name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id;
~~~

The result set has two columns with the label id. That causes ambiguity when mapping into a DTO containing both orderId and customerId. Alias them:

~~~sql
SELECT
    po.id AS order_id,
    c.id AS customer_id,
    po.status AS order_status,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id;
~~~

DTO:

~~~java
public record OrderCustomerView(
        Long orderId,
        Long customerId,
        String orderStatus,
        String customerName
) {
}
~~~

Aliases clarify the origin and meaning of each value while reducing the risk of the driver returning duplicate labels or overwriting values during mapping.

### 3.2. Aliases for Computed Expressions

A computed column has no natural property name:

~~~sql
SELECT
    id AS product_id,
    price_minor_units * stock_quantity AS inventory_value_minor_units
FROM product;
~~~

Projection:

~~~java
public record InventoryValue(
        Long productId,
        Long inventoryValueMinorUnits
) {
}
~~~

Expressions must have aliases matching mapping properties. Never rely on database-generated expression labels, as those labels are hard to map and vary across drivers.

### 3.3. Aliases for Aggregate Functions

~~~sql
SELECT
    status AS order_status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM purchase_order
GROUP BY status;
~~~

Projection:

~~~java
public record OrderStatistics(
        String orderStatus,
        Long orderCount,
        BigDecimal totalRevenue
) {
}
~~~

The aliases order_status, order_count, and total_revenue describe the result column names. Java types must match the types returned by the database/driver for COUNT and SUM; do not assume every database returns the same type for an aggregate expression.

### 3.4. Rules for Maintainable Aliases

- Use stable, business-meaningful aliases.
- Avoid two result columns sharing an alias.
- Use lowercase and snake_case consistently if that is your project's naming strategy.
- Alias every expression, function, and potentially colliding column in joins.
- Avoid SQL keywords or names with spaces/special characters as aliases.
- Select result columns matching the projection; avoid SELECT *.
- Whenever the schema changes, re-verify aliases and DTO mappings.

## 4. Must Aliases Always Match Java Component Names?

Not necessarily. Distinguish between:

- **Java property/component name:** e.g., customerName.
- **Schema column name:** e.g., customer_name.
- **Result set label:** the name returned by SQL after aliasing.

Spring Data Relational uses mapping metadata and a naming strategy to link properties to columns. With the default snake_case naming strategy, the customerName property maps to the customer_name column. Therefore, aliasing to the mapped column name is usually the clearest option:

~~~sql
SELECT c.name AS customer_name
~~~

If a property is annotated with custom mapping or the application uses a custom naming strategy, follow the configured column name. Do not infer solely from getter names.

### 4.1. Using `@Column` When Column Names Differ from Convention

On entities, `@Column` lets you specify an explicit column name:

~~~java
@Column("display_label")
private String displayLabel;
~~~

If a projection DTO has corresponding mapping metadata supported by Spring Data, the alias must match the declared column name. For plain projection classes/records, the safest practice is to keep aliases aligned with mapping conventions and verify with integration tests on your exact version.

Do not mechanically slap `@Column` onto DTOs assuming every projection type processes annotations identically to entities. Annotation reading and constructor resolution depend on the projection type and mapping path.

### 4.2. Watch Casing and Quoting

Some databases automatically fold unquoted identifiers to lowercase or uppercase. Drivers may return column labels in that normalized casing. To reduce discrepancies:

- Prefer simple aliases like customer_name.
- Avoid aliases containing spaces.
- Avoid relying on mixed case unless truly necessary.
- If quoting aliases is required, verify the quoting rules of the target database.

For example:

~~~sql
SELECT c.name AS customer_name
~~~

is far more portable than an alias with spaces such as AS "Customer Name".

## 5. Projections with `@Query`

When writing explicit SQL, the author controls the exact column list and aliases:

~~~java
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface OrderReadRepository {

    @Query("""
           SELECT
               po.id AS order_id,
               po.order_number AS order_number,
               c.name AS customer_name,
               po.total_amount AS total_amount
           FROM purchase_order po
           JOIN customer c ON c.id = po.customer_id
           WHERE po.status = :status
           ORDER BY po.id DESC
           """)
    List<OrderListItem> findOrderItems(
            @Param("status") String status
    );
}
~~~

OrderListItem is the record projection from the previous section. In real applications, the repository interface may extend a root repository or be organized as a fragment depending on architecture. The example focuses on the SQL/result mapping contract.

With `@Query`:

- SQL must use database table and column names.
- Aliases must be compatible with projection properties/components.
- Column types must be convertible to Java types.
- The result set must supply enough data to construct the projection.
- Cardinality must match the return type: List for multiple rows, Optional for at most one row.

### 5.1. SQL Determines Selected Columns

With explicit queries, never assume Spring Data automatically rewrites the column list to match the projection. Select the exact columns in SELECT. If a projection has four components but SQL returns only three columns, constructor mapping may fail or miss data depending on the mapping path.

### 5.2. Projections Do Not Create Joins Automatically

Declaring a DTO with a customerName component does not cause Spring Data JDBC to join the customer table automatically. The SQL must contain the join and select the corresponding column. Projections describe the result shape; SQL describes how data is retrieved.

## 6. Method Parameter Names and Named Parameters in SQL

Input parameter names form a separate contract from column aliases. SQL placeholders receive values from Java parameters via parameter binding.

Example:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE status = :status
         AND price_minor_units >= :minimumPrice
       """)
List<ProductSummary> search(
        @Param("status") String productStatus,
        @Param("minimumPrice") long minPrice
);
~~~

Bindings:

| SQL placeholder | Java parameter | Role |
| --- | --- | --- |
| :status | @Param("status") String productStatus | Status filter value |
| :minimumPrice | @Param("minimumPrice") long minPrice | Minimum price threshold |

The Java variable name productStatus does not need to match status because @Param("status") specifies the binding name. What matters is that the string in @Param matches the SQL placeholder exactly.

### 6.1. Why Declare `@Param` Explicitly?

Without @Param, the framework may have to rely on parameter name metadata preserved at compile time. This depends on compiler configuration, such as the -parameters flag.

With Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += "-parameters"
}
~~~

Declaring @Param makes the method contract explicit and reduces reliance on metadata. It is especially helpful when:

- Java variable names differ from placeholder names.
- A query has multiple parameters.
- Method parameter variables are refactored.
- A project spans multiple modules or differing compiler settings.

### 6.2. Distinguishing Three Kinds of Names

~~~text
SQL column alias         Java projection property
-----------------        -----------------------
customer_name     -----> customerName
total_revenue     -----> totalRevenue

SQL named parameter      Java method parameter
-------------------      ---------------------
:status            <---- @Param("status") String productStatus
:minimumPrice      <---- @Param("minimumPrice") long minPrice
~~~

Aliases describe **returned data**; named parameters describe **input values**. Never use a column alias in place of @Param or assume a Java parameter name determines a result set column name.

### 6.3. Do Not Bind Table Names, Column Names, or ORDER BY

Bind parameters substitute values only:

~~~sql
WHERE status = :status
~~~

You cannot use:

~~~sql
ORDER BY :sortColumn
~~~

expecting sortColumn to become a column name. The database treats the placeholder as a literal value, not an SQL identifier.

If dynamic sorting is required, use a whitelist:

~~~java
String orderBy = switch (sort) {
    case NEWEST -> "created_at DESC, id DESC";
    case NAME -> "name ASC, id ASC";
    case PRICE -> "price_minor_units DESC, id DESC";
};
~~~

Only append strings from an application-controlled set of constants; never concatenate raw column names sent from a request.

### 6.4. Collection Parameters and IN Clauses

A query can filter by a collection of IDs:

~~~java
@Query("""
       SELECT id, name, status
       FROM customer
       WHERE id IN (:ids)
       """)
List<CustomerSummary> findByIds(@Param("ids") Collection<Long> ids);
~~~

When binding a collection, Spring JDBC's named parameter mechanism can expand the placeholder list to match the element count. Check the behavior of your framework version and explicitly define handling for empty collections:

- Return an empty list immediately in the service if there are no IDs to look up.
- Or pick another suitable query.
- Never let an empty list produce invalid SQL or accidentally drop the filter condition.

Check for null elements and bound collection size if inputs come from an API.

## 7. Data Types: SQL, JDBC, and Java Must Be Compatible

Projections only work reliably when column/expression data types can convert to the corresponding Java types. Three layers must be considered:

1. **SQL type:** the type declared in the schema or produced by an SQL expression.
2. **JDBC type:** the type returned by the driver from the ResultSet or metadata.
3. **Java type:** the type of the component, constructor parameter, or accessor in the projection.

Not every database returns the same type for an expression. For instance, SUM(INTEGER) may return a wider type than the base column; division may return decimal; COUNT(*) usually returns a large integer.

### 7.1. Common Type Mapping Reference

| Common SQL type | Typical Java type | Notes |
| --- | --- | --- |
| BIGINT | Long / long | Use Long if column can be null; long cannot represent null |
| INTEGER | Integer / int | Watch for overflow when expressions yield larger results |
| SMALLINT | Short / Integer | Can use a wider type after checking range |
| DECIMAL, NUMERIC | BigDecimal | Suitable for money and decimals requiring precision |
| REAL, FLOAT, DOUBLE | Float, Double | Do not use floating point for money needing decimal accuracy |
| VARCHAR, CHAR, TEXT | String | Mind length, collation, and encoding |
| BOOLEAN | Boolean / boolean | Boolean allows null; mapping depends on driver/database |
| DATE | LocalDate | Represents a date only, no time of day |
| TIME | LocalTime | Contains no date or timezone |
| TIMESTAMP without timezone | LocalDateTime | Local date-time, does not itself represent a global instant |
| Timestamp with timezone/offset | OffsetDateTime, Instant, or converter-supported type | Check driver and database rules |
| UUID | UUID | Support and representation can vary across databases |
| Binary/BLOB | byte[] or suitable stream type | Consider size and loading strategy |

The table above is a general guide, not a guarantee of identical conversions across every JDBC driver. Verify actual data types against your production database and driver.

### 7.2. Use Wrappers When Columns Can Be NULL

If a query can return SQL NULL, primitives are unsuitable:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        Integer loyaltyPoints,
        Boolean marketingOptIn
) {
}
~~~

long, int, and boolean cannot represent null. If the database can return null for the column, use wrappers (Long, Integer, Boolean) or use COALESCE to define a default value.

Example:

~~~sql
SELECT
    id AS id,
    name AS name,
    COALESCE(loyalty_points, 0) AS loyalty_points,
    COALESCE(marketing_opt_in, FALSE) AS marketing_opt_in
FROM customer;
~~~

Only supply a default value if it carries accurate business meaning. Null can mean “unknown,” which differs from 0 or false.

### 7.3. COUNT and SUM Have Different Return Types

Example:

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM purchase_order
WHERE status = :status;
~~~

Projection:

~~~java
public record RevenueSummary(
        Long orderCount,
        BigDecimal totalRevenue
) {
}
~~~

COUNT(*) typically returns a large integer type, fitting Long. SUM(total_amount) returns a type dependent on the column type and database; if total_amount is DECIMAL/NUMERIC, BigDecimal usually fits.

If no rows match:

- COUNT(*) typically returns 0 in one result row.
- SUM(...) can return SQL NULL.

If you want a default sum of 0:

~~~sql
COALESCE(SUM(total_amount), 0) AS total_revenue
~~~

The type of the literal 0 may be inferred as a different numeric type by the database. If specific precision/scale is required, cast appropriately for the database or verify the expression's actual type.

### 7.4. Avoid Unsafe Narrowing Conversions

Suppose the database returns BIGINT while the projection declares Integer. Values exceeding Integer limits can cause conversion errors or data loss if coerced improperly.

Similarly, never map DECIMAL to double just for convenience. For money:

~~~java
public record PaymentSummary(
        Long paymentCount,
        BigDecimal totalAmount
) {
}
~~~

BigDecimal preserves decimal precision. When rounding is needed, scale and rounding mode rules must be defined by business requirements.

## 8. Data Types for Expressions and Calculations

The type of the underlying column is not necessarily the type of the resulting expression.

### 8.1. Multiplication

~~~sql
SELECT
    quantity * unit_price AS line_total
FROM order_line;
~~~

If quantity is INTEGER and unit_price is DECIMAL, the resulting type follows the database's type-promotion rules. The projection should use a sufficiently wide and accurate type, typically BigDecimal for monetary amounts.

### 8.2. Division

~~~sql
SELECT
    CAST(total_amount AS DECIMAL(19, 4))
        / NULLIF(item_count, 0) AS average_item_amount
FROM order_summary;
~~~

Integer division in some databases truncates fractional parts. If a decimal result is needed, cast the operand or expression using your database's syntax. NULLIF prevents division by zero by returning NULL when the denominator is 0. Adjust DECIMAL precision and cast syntax for the target database.

### 8.3. CASE Expressions

~~~sql
SELECT
    id AS id,
    CASE
        WHEN active = TRUE THEN 'ACTIVE'
        ELSE 'INACTIVE'
    END AS display_status
FROM customer;
~~~

Projection:

~~~java
public record CustomerStatusView(
        Long id,
        String displayStatus
) {
}
~~~

The component's Java type must be compatible with the result types of the CASE branches. Branches should have compatible types; if any branch returns NULL, consider a wrapper/nullable type.

## 9. Constructor Parameter Names and Record Components

Class-based projections are usually instantiated via a constructor. Spring Data needs to know which value maps to which parameter.

Record:

~~~java
public record CustomerContact(
        Long customerId,
        String customerName,
        String emailAddress
) {
}
~~~

The canonical constructor has explicit component names. Query:

~~~sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    c.email AS email_address
FROM customer c
WHERE c.active = TRUE;
~~~

With the snake_case naming strategy, the aliases match the camelCase component names. Ensure your application's mapping metadata uses the same convention.

### 9.1. DTO Class with One Constructor

~~~java
public final class CustomerContact {
    private final Long customerId;
    private final String customerName;
    private final String emailAddress;

    public CustomerContact(
            Long customerId,
            String customerName,
            String emailAddress
    ) {
        this.customerId = customerId;
        this.customerName = customerName;
        this.emailAddress = emailAddress;
    }
}
~~~

Constructor parameter names are a key part of mapping when the framework uses constructor binding. For regular classes, enable parameter name metadata with -parameters when needed and check the rules of your Spring Data version. A single constructor makes constructor resolution unambiguous.

### 9.2. DTO with Multiple Constructors

If a class has multiple constructors, Spring Data needs to identify which constructor creates the projection. You can use the `@PersistenceCreator` annotation where supported by the mapping API:

~~~java
@PersistenceCreator
public CustomerContact(
        Long customerId,
        String customerName,
        String emailAddress
) {
    // ...
}
~~~

Do not assume a constructor is chosen simply because it has the most parameters. Verify the constructor discovery rules of the release in use.

### 9.3. Column Order Should Not Be the Sole Contract

Do not design projections assuming “the first column always goes into the first parameter, the second column into the second parameter” when the mapping framework matches by property/column name. Use explicit aliases and ensure constructor parameters have matching names.

This makes changing SELECT column order less error-prone and makes SQL self-describing. When using a custom RowMapper, the mapper code explicitly decides which column goes into which constructor argument.

## 10. Interface Projections and Accessors

An interface projection can declare:

~~~java
public interface ProductCard {
    Long getId();
    String getSku();
    String getName();
    BigDecimal getPrice();
}
~~~

With a query method, results must supply the properties required by the interface. With custom SQL, column aliases must be compatible with projection mapping:

~~~sql
SELECT
    p.id AS id,
    p.sku AS sku,
    p.name AS name,
    p.price_amount AS price
FROM product p
WHERE p.active = TRUE;
~~~

If mapping relies on Java property names and a naming strategy, aliases may need to match the corresponding column names. Use integration tests to verify exact interface projection behavior with your project's Spring Data JDBC version.

### 10.1. Getters Must Match Properties

The accessor getCustomerName() expresses the property customerName. If SQL returns an unrelated alias such as client_label, mapping may fail to locate the value unless metadata/custom mapping provides the link.

### 10.2. Closed Projections and Computed Data

Closed projections declare only the specific properties needed for reading. Some query types can optimize the column set based on those properties. With `@Query` using explicit SQL, the SELECT list itself decides which columns the database returns.

If a projection needs a property derived from multiple fields or an SQL expression, consider:

- Computing it in SQL with a clear alias.
- Using a default method if simply combining already-selected properties.
- Using a DTO projection when explicit constructors and data types are preferred.

Never assume an extra getter makes Spring Data automatically generate a JOIN or run another query.

## 11. Null, Optional, and Default Values in Projections

SQL NULL can appear in a result set regardless of whether the base table is nullable—for example, due to a LEFT JOIN or an aggregate function.

Example:

~~~sql
SELECT
    po.id AS order_id,
    c.name AS customer_name
FROM purchase_order po
LEFT JOIN customer c ON c.id = po.customer_id;
~~~

If there is no matching customer, customer_name is SQL NULL. The projection should use a nullable type:

~~~java
public record OrderCustomerSummary(
        Long orderId,
        String customerName
) {
}
~~~

Do not use primitives for nullable components:

~~~java
// Risky if LEFT JOIN has no customer:
public record OrderCustomerSummary(
        long orderId,
        String customerName
) {
}
~~~

### 11.1. COALESCE or Wrapper?

The two choices have different meanings:

- Use wrappers (Long, Integer, Boolean) to preserve SQL NULL information.
- Use COALESCE to replace NULL with a default value per business rules.

Example:

~~~sql
SELECT
    id AS id,
    COALESCE(nickname, name) AS display_name
FROM customer;
~~~

Here display name is defined as nickname if present, otherwise name. That is an explicit display rule.

Do not mechanically replace every NULL with an empty string or 0. NULL can represent “unknown,” “not applicable,” or “no relationship,” which differs from empty/0.

### 11.2. Zero Rows vs. One Row Containing NULL

A projection query returns:

- Zero rows: empty collection or Optional.empty depending on method type.
- One row with customer_name = NULL: the projection exists, and the customerName property is null if mapping permits.
- One row with customer_name = empty string: the projection exists, and the name is an empty string.

Do not use an Optional wrapping the entire projection to represent a single component being null.

## 12. Aliases and Data Types in JOINs

JOINs are where aliases and type mapping cause errors most frequently:

~~~sql
SELECT
    po.id AS order_id,
    po.created_at AS order_created_at,
    c.id AS customer_id,
    c.name AS customer_name,
    c.active AS customer_active
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.id = :orderId;
~~~

Projection:

~~~java
public record OrderCustomerDetail(
        Long orderId,
        LocalDateTime orderCreatedAt,
        Long customerId,
        String customerName,
        Boolean customerActive
) {
}
~~~

Prefixed aliases disambiguate two aggregates that both have id, name, or createdAt properties. If the alias were simply id, a projection needing both order ID and customer ID could not map unambiguously.

### 12.1. LEFT JOIN and Nullable Types

If you switch to LEFT JOIN, components sourced from customer can be null. Use appropriate nullable wrappers/references and decide how the DTO represents an absent customer.

### 12.2. ID Types Between Two Tables

If purchase_order.customer_id is BIGINT while customer.id is UUID or another type, the join may require a cast or a schema fix. The projection must use types matching the result columns, not merely copy the ID type from another entity.

## 13. Date-Time and Timezone Mapping

Date-time values require special attention because Java type names do not automatically dictate timezone semantics.

| SQL column | Common Java type | Meaning |
| --- | --- | --- |
| DATE | LocalDate | Calendar date |
| TIME | LocalTime | Time of day |
| TIMESTAMP without timezone | LocalDateTime | Local date-time, no offset |
| Timestamp with timezone/offset | OffsetDateTime or Instant per driver/converter | Instant in time with offset or UTC instant info |

Example:

~~~sql
SELECT
    id AS id,
    created_at AS created_at
FROM purchase_order
WHERE created_at >= :fromTime;
~~~

Projection:

~~~java
public record OrderCreatedView(
        Long id,
        LocalDateTime createdAt
) {
}
~~~

If the database stores timestamps without timezone, LocalDateTime usually reflects the data accurately. If the business requires a global instant, define timezone semantics at the domain/database layer and use the corresponding type/converter. Do not arbitrarily interpret LocalDateTime as UTC if the schema does not guarantee it.

## 14. Projections for Monetary Calculations and Quantities

Money should be stored and read using exact decimal types or a smallest-unit integer model according to system policy.

DECIMAL column example:

~~~sql
SELECT
    order_id AS order_id,
    SUM(quantity * unit_price) AS line_total
FROM order_line
GROUP BY order_id;
~~~

Projection:

~~~java
public record OrderLineTotal(
        Long orderId,
        BigDecimal lineTotal
) {
}
~~~

If the schema stores money as integer minor units, the calculation may return BIGINT:

~~~sql
SELECT
    order_id AS order_id,
    SUM(quantity * unit_price_minor_units) AS line_total_minor_units
FROM order_line
GROUP BY order_id;
~~~

Projection:

~~~java
public record OrderLineTotalMinorUnits(
        Long orderId,
        Long lineTotalMinorUnits
) {
}
~~~

Do not switch between the two models without defining scale, rounding, and currency. A monetary amount is not merely a number; if results can span multiple currencies, the projection should also carry the currency code or group by currency.

## 15. Custom `RowMapper` When Standard Projection Mapping Is Insufficient

For SQL with complex result shapes, you can use a custom repository fragment with JdbcClient or NamedParameterJdbcTemplate to map each column explicitly.

Example:

~~~java
public record CustomerSpend(
        Long customerId,
        String customerName,
        Long orderCount,
        BigDecimal totalSpend
) {
}
~~~

Custom query:

~~~java
public List<CustomerSpend> findCustomerSpend(String status) {
    return jdbcClient.sql("""
            SELECT
                c.id AS customer_id,
                c.name AS customer_name,
                COUNT(po.id) AS order_count,
                COALESCE(SUM(po.total_amount), 0) AS total_spend
            FROM customer c
            LEFT JOIN purchase_order po
                ON po.customer_id = c.id
               AND po.status = :status
            GROUP BY c.id, c.name
            ORDER BY total_spend DESC, c.id
            """)
        .param("status", status)
        .query((rs, rowNum) -> new CustomerSpend(
                rs.getLong("customer_id"),
                rs.getString("customer_name"),
                rs.getLong("order_count"),
                rs.getBigDecimal("total_spend")
        ))
        .list();
}
~~~

An explicit RowMapper offers several benefits:

- The author decides exactly which column goes into which component.
- Appropriate JDBC getters can be called for each type.
- Nulls can be handled via wasNull() or object getters.
- Data can be transformed/normalized during mapping.
- No reliance on automatic projection mechanisms for complex result shapes.

The example above assumes JdbcClient from Spring Framework 6.1+ and matching schema columns. For older versions, use NamedParameterJdbcTemplate or JdbcTemplate.

### 15.1. Checking NULLs in a `RowMapper`

With primitive getters like getLong, JDBC returns 0 when the SQL value is NULL; call wasNull() immediately after the getter if you need to distinguish them:

~~~java
long raw = rs.getLong("customer_id");
Long customerId = rs.wasNull() ? null : raw;
~~~

Or use an object-returning getter if the driver supports the target type:

~~~java
Long customerId = rs.getObject("customer_id", Long.class);
~~~

Never allow NULL to silently become 0 unintentionally.

### 15.2. When Is a Custom `RowMapper` Unnecessary?

If a projection has only a few simple columns and Spring Data JDBC's standard mapping works cleanly, a DTO/record projection requires less code. Custom mappers should appear only when solving specific needs such as specialized types, complex expressions, JSON, multiple nullable branches, or multi-table mappings.

## 16. Common Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Projection property receives no value | Alias mismatches column mapping/property | Align alias with naming strategy and verify result-set labels |
| Two tables both have an id column | JOIN produces duplicate column labels | Use distinct aliases like order_id, customer_id |
| DTO constructor not called properly | Ambiguous constructor or missing parameter metadata | Use record/clear constructor, -parameters, @PersistenceCreator when needed |
| Record component not mapped | Alias or data type mismatches component | Verify each component and column label |
| Primitive receives SQL NULL | Primitives cannot represent null | Use wrappers or intentional COALESCE |
| COUNT/SUM mismatches Java type | Aggregate result type differs from source column type | Check DB/driver types, use suitable Long/BigDecimal |
| Monetary precision loss | Using double or integer division | Use BigDecimal, casts, and explicit rounding rules |
| Timezone shift in timestamps | Confusing TIMESTAMP with timezone-aware instants | Define schema semantics and Java types |
| @Param mismatches placeholder | Typo or reliance on parameter metadata | Use @Param explicitly |
| Using placeholder for column name | Bind parameters are for values only | Whitelist identifiers and build SQL safely |
| LEFT JOIN breaks constructor | Right-side column can be null while DTO uses primitive | Use wrappers or default rules |
| SELECT * makes mapping fragile | Result set has duplicate/extra columns or shifts with schema | List columns and aliases explicitly |
| Projection used to update aggregate | DTO lacks full invariants/state | Load full root for command paths |
| RowMapper turns NULL into 0 | Calling getLong/getInt without wasNull() | Use getObject or check wasNull() |

## 17. Projection Design Workflow

When creating a new projection, follow this sequence:

1. **Identify the read use case.** Does the caller need display, reporting, search, or business processing?
2. **Choose the result shape.** Interface projection, DTO class, record, or RowMapper.
3. **List components.** Each component needs an explicit name and Java type.
4. **Write an intentional SELECT.** Fetch only needed columns; avoid SELECT * in join projections.
5. **Assign unique aliases.** Alias according to column names expected by mapping metadata; use prefixes to disambiguate columns from multiple tables.
6. **Bind parameters.** Use named placeholders and explicit @Param.
7. **Check types.** Compare SQL type, JDBC type, and Java type; consider nullability, overflow, scale, and timezone.
8. **Determine cardinality.** Optional for at most one row; List/Iterable for multiple rows; scalar for a single value.
9. **Check version/module.** Verify that the projection type and mapping are supported by your project's Spring Data JDBC version.
10. **Integration test.** Verify present/absent data, aliases, nulls, aggregate expressions, joins, and the real database dialect.

## 18. End-to-End Projection Testing Example

Suppose a repository has the query:

~~~java
@Query("""
       SELECT
           po.id AS order_id,
           po.order_number AS order_number,
           c.name AS customer_name,
           po.total_amount AS total_amount
       FROM purchase_order po
       JOIN customer c ON c.id = po.customer_id
       WHERE po.status = :status
       ORDER BY po.id
       """)
List<OrderListItem> findOrderItems(@Param("status") String status);
~~~

Tests should verify:

~~~java
@Test
void mapsAliasesAndTypesToProjection() {
    List<OrderListItem> result =
            repository.findOrderItems("CONFIRMED");

    assertThat(result).hasSize(1);
    OrderListItem item = result.get(0);
    assertThat(item.orderId()).isEqualTo(1001L);
    assertThat(item.orderNumber()).isEqualTo("ORD-1001");
    assertThat(item.customerName()).isEqualTo("Lan");
    assertThat(item.totalAmount())
            .isEqualByComparingTo("125000.00");
}
~~~

This is an illustrative skeleton; real tests must set up matching schema and fixtures, imports, repository beans, and a suitable database. Beyond the happy path, verify:

- When no orders match, an empty list is returned.
- LEFT JOIN with no customer handles nullable components properly.
- Aggregate functions return compatible types.
- Alias names are not unexpectedly normalized by the driver.
- Parameters with special characters are bound safely.

For SQL tied to PostgreSQL, MySQL, or SQL Server, run integration tests against that real database or corresponding Testcontainers. H2 is not sufficient proof for every dialect.

## Key Takeaways

A projection is a contract between SQL and Java. **Column aliases** define returned data labels; **parameter names** link SQL placeholders to method parameters; **data types** determine whether JDBC values map accurately into components.

Always alias columns clearly, especially in JOINs or expressions; use `@Param` to declare placeholder names explicitly; pick wrappers for nullable data, `BigDecimal` for exact decimals, and date-time types matching schema semantics. When standard mapping falls short, a custom `RowMapper` gives column-by-column control. Finally, test projections against the target database to confirm aliases, constructors, data types, and null cases actually work as designed.
