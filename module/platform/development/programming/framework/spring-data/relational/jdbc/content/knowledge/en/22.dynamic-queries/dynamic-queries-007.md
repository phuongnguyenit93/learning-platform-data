# Criteria Limitations with JOINs and Aggregate Relationships

In **Spring Data Relational JDBC**, `Criteria` and `Query` provide a Java API for building dynamic query conditions. You can build predicates on properties, combine `AND`/`OR`, check `NULL`, compare ranges, filter by sets of values, and add sorting or result limits.

However, this API has a narrower scope than a general-purpose SQL query builder or the JPA Criteria API. **Criteria does not automatically infer JOINs simply because an aggregate has `@MappedCollection` or `AggregateReference`.** When conditions live on a child table or on properties of another aggregate root, you need to write explicit SQL relationships via `@Query`, a custom repository, or `JdbcTemplate`.

To use Criteria properly, distinguish three kinds of data:

- **Aggregate root properties:** reside on the root table and are the natural target of Criteria.
- **Embedded value objects:** fields flattened into the root table itself; they do not create a JOIN to another table.
- **Child collections or aggregate references:** data resides in another table; filtering on those fields generally requires an explicit JOIN or `EXISTS`.

This lesson explains how to build dynamic queries with Criteria, its limitations with nested relationships, SQL alternatives, and important considerations for result mapping.

## 1. What Is Criteria in Spring Data JDBC?

`Criteria` belongs to Spring Data Relational and describes filter predicates over relational data. `Query` combines predicates with query options such as sort, limit, and offset supported by the API.

Common types:

- `org.springframework.data.relational.core.query.Criteria`
- `org.springframework.data.relational.core.query.Query`
- `org.springframework.data.jdbc.core.JdbcAggregateTemplate`
- `org.springframework.data.domain.Sort`

For example, instead of declaring many repository methods for each combination of conditions, a service can build Criteria from search parameters:

```java
Criteria criteria = Criteria.where("status").is(OrderStatus.NEW)
        .and("createdAt").greaterThanOrEquals(from)
        .and("deletedAt").isNull();

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")))
        .limit(50);

List<PurchaseOrder> orders =
        aggregateTemplate.findAll(query, PurchaseOrder.class);
```

This example illustrates a query over aggregate root properties. Property names in Criteria are mapped Java property names such as `createdAt`, not necessarily physical column names like `created_at`.

Package names, method overloads, and exact API details may vary across Spring Data Relational versions. Follow your project's exact dependency version when implementing.

### 1.1. Criteria Is Not the JPA Criteria API

Both APIs share similar names, but their goals and capabilities differ.

| Aspect | Spring Data Relational `Criteria` | JPA Criteria API |
|---|---|---|
| Typical package | `org.springframework.data.relational.core.query` | `jakarta.persistence.criteria` |
| Query object | Relational predicates used with `Query`/template | JPA query model |
| Root/path/join graph | Does not provide a general association join model like JPA | Has `Root`, `Path`, `Join` |
| Entity relationships | Follows Spring Data JDBC aggregate mapping | Follows JPA association mapping |
| Persistence context | No managed-entity session like JPA | Has a persistence context |
| Purpose | Builds SQL conditions matching relational mapping | Builds queries over entity models and associations |

You cannot copy a JPA Criteria snippet using `root.join("lines")` into Spring Data JDBC and expect it to work. Spring Data JDBC models aggregates and queries differently.

### 1.2. Criteria Fits Dynamic Queries

Criteria is especially useful when the number of conditions depends on input:

- Users may filter by status or leave that filter blank.
- The screen has an optional date range.
- One or more enum values may be selected.
- Certain conditions apply only when a checkbox is enabled.
- Predicates must be combined with sort/limit.

For example, a service adds conditions only when the user provides values:

```java
List<Criteria> predicates = new ArrayList<>();

if (status != null) {
    predicates.add(Criteria.where("status").is(status));
}

if (createdAfter != null) {
    predicates.add(Criteria.where("createdAt").greaterThanOrEquals(createdAfter));
}

if (includeDeleted == false) {
    predicates.add(Criteria.where("deletedAt").isNull());
}
```

These predicates can be combined into a final condition using the `Criteria` API of the version in use. Combining conditions must preserve `AND`/`OR` semantics; avoid a single flat expression when conditions require complex logical grouping.

## 2. Common Criteria Predicates

Criteria offers familiar comparison operators for relational properties. Examples:

| Group | Expression | Meaning |
|---|---|---|
| Equal | `.is(value)` | Equals value |
| Not equal | `.not(value)` | Not equal to value |
| Null | `.isNull()` | Column is SQL NULL |
| Not null | `.isNotNull()` | Column is not SQL NULL |
| Greater than | `.greaterThan(value)` | `>` |
| Greater than or equal | `.greaterThanOrEquals(value)` | `>=` |
| Less than | `.lessThan(value)` | `<` |
| Less than or equal | `.lessThanOrEquals(value)` | `<=` |
| Within range | `.between(from, to)` | Within range |
| In set | `.in(values)` | Value is in set |
| Not in set | `.notIn(values)` | Value is not in set |
| LIKE string | `.like(pattern)` | Pattern matching |
| Boolean | `.isTrue()` / `.isFalse()` | Boolean true/false values |

Exact method names may vary by version. Consult the Javadoc of the Spring Data Relational version your project uses when you need a less common operator.

Example:

```java
Criteria criteria = Criteria.where("totalAmount")
        .greaterThanOrEquals(minimum)
        .and("status")
        .in(List.of(OrderStatus.NEW, OrderStatus.PAID));
```

Predicates can be chained further:

```java
Criteria criteria = Criteria.where("status").is(OrderStatus.PAID)
        .and("createdAt").between(start, end)
        .and("deletedAt").isNull();
```

Intended SQL semantics:

```sql
SELECT *
FROM orders
WHERE status = ?
  AND created_at BETWEEN ? AND ?
  AND deleted_at IS NULL;
```

Criteria describes conditions; the template translates those conditions into SQL according to mapping and dialect.

## 3. Using Query to Add Sort and Limits

`Query` wraps Criteria and can carry sorting, offset, or limit options depending on the API version.

Example:

```java
Criteria criteria = Criteria.where("status").is(OrderStatus.NEW);

Query query = Query.query(criteria)
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("orderCode")
        ))
        .limit(25)
        .offset(0);

List<PurchaseOrder> result =
        aggregateTemplate.findAll(query, PurchaseOrder.class);
```

Points to remember:

- Sort uses mapped property names such as `createdAt`.
- Limit caps the number of root rows selected by the query.
- Offset skips leading rows according to the sort order.
- Always use a stable sort when paginating, typically adding a unique key like ID to avoid nondeterministic order across pages.

For example, sorting only by timestamp can produce unstable ordering if multiple orders share the same `createdAt`. Adding `id` as a secondary criterion keeps ordering consistent:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);
```

`Query` is not a place to express arbitrary JOINs. Adding `.sort(...)` or `.limit(...)` does not turn Criteria into a query builder capable of joining any table.

## 4. Criteria Querying Aggregate Root Properties

Suppose aggregate root `PurchaseOrder` has scalar properties:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_code")
    private String orderCode;

    private OrderStatus status;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("deleted_at")
    private LocalDateTime deletedAt;

    // Constructors, getters, and domain methods...
}
```

These properties are stored in the `orders` table, so they work cleanly with root-level Criteria conditions:

```java
Criteria criteria = Criteria.where("status").is(OrderStatus.NEW)
        .and("createdAt").greaterThanEqual(from)
        .and("createdAt").lessThan(to)
        .and("deletedAt").isNull();

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")));
```

Semantically equivalent SQL:

```sql
SELECT *
FROM orders
WHERE status = ?
  AND created_at >= ?
  AND created_at < ?
  AND deleted_at IS NULL
ORDER BY created_at DESC;
```

### 4.1. Building Criteria from Optional Filters

A search filter may have several optional fields:

```java
public record OrderFilter(
        OrderStatus status,
        LocalDateTime createdFrom,
        LocalDateTime createdTo,
        String orderCode
) {
}
```

The service can build predicates for each supplied field. A clean style is initializing an empty Criteria and chaining remaining conditions:

```java
Criteria criteria = Criteria.empty();

if (filter.status() != null) {
    criteria = criteria.and("status").is(filter.status());
}

if (filter.createdFrom() != null) {
    criteria = criteria.and("createdAt")
            .greaterThanOrEquals(filter.createdFrom());
}

if (filter.createdTo() != null) {
    criteria = criteria.and("createdAt")
            .lessThan(filter.createdTo());
}

if (filter.orderCode() != null && !filter.orderCode().isBlank()) {
    criteria = criteria.and("orderCode").like("%" + filter.orderCode() + "%");
}

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")))
        .limit(100);
```

How empty Criteria and `and(...)` calls work depends on the API version; if your version lacks the corresponding factory, collect predicates in a list and combine them. The goal is adding only conditions that were provided, without passing null values into equality checks.

For user-entered search strings, check how the API handles wildcards and escaping `%`/`_`. If searching for a literal string instead of a pattern, escape wildcards according to database rules.

### 4.2. Do Not Confuse SQL NULL with Empty Values

`isNull()` tests for SQL NULL. It is not equivalent to an empty string, zero, or Boolean false.

For example:

- `orderCode IS NULL`: no code assigned yet.
- `orderCode = ''`: has a string, and it is empty.
- `deletedAt IS NULL`: no deletion timestamp yet.
- `enabled = FALSE`: flag has value false.

If the domain needs to combine multiple states, add explicit predicates and account for SQL three-valued logic.

## 5. Why Doesn't Criteria Automatically Generate JOINs?

Criteria describes predicates over a mapping scope that Spring Data JDBC can resolve. It does not expose a full `Root`/`Join` model for navigating entity associations like the JPA Criteria API.

Suppose an aggregate has these components:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();

    @Embedded(prefix = "shipping_")
    private ShippingAddress shippingAddress;
}
```

The three properties have different mappings:

| Property | How Stored | Involved Table |
|---|---|---|
| `customerId` | Scalar ID on root | `orders` |
| `lines` | Child collection | `order_lines` |
| `shippingAddress` | Flattened fields | `shipping_*` columns in `orders` |

Criteria on `customerId` is a root-level predicate:

```java
Criteria.where("customerId").is(customerId);
```

However, querying `lines.sku` requires inspecting `order_lines` and joining `order_lines.order_id` to `orders.id`. Querying `customer.displayName` requires joining `orders.customer_id` to `customers.id`.

A nested property name alone is insufficient to specify:

- Which table to JOIN.
- Which columns form the join key.
- Whether to use INNER or LEFT JOIN.
- Whether duplicate roots must be eliminated.
- Whether EXISTS or aggregate functions are needed.
- Whether the result should be root, child, or DTO.

Therefore, do not assume Criteria automatically constructs JOINs merely because the domain model has object or collection fields.

## 6. Limitations with @MappedCollection and Child Entities

`@MappedCollection` represents a collection of child entities owned by the aggregate root. Children are stored in a separate table with a foreign-key column pointing back to the root.

Example:

```java
@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    private String sku;
    private int quantity;

    // Constructors and getters...
}
```

Aggregate root:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "line_index")
private List<OrderLine> lines = new ArrayList<>();
```

DDL:

```sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    line_index INTEGER NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL
);
```

To find orders containing at least one line with `sku = 'BOOK-01'`, the condition is on the child table. You cannot treat `lines` like a scalar column of the `orders` table.

Do not rely on Criteria such as:

```java
// Not a general JOIN syntax for child collections.
Criteria.where("lines.sku").is("BOOK-01");
```

This is not a reliable way to request joining `orders` with `order_lines`. Write SQL with JOIN/EXISTS or use a custom repository.

### 6.1. Using EXISTS to Filter Roots by Children

SQL:

```sql
SELECT o.*
FROM orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
      AND l.sku = ?
);
```

`EXISTS` works well when the goal is retrieving each root once if at least one child matches the condition.

In Spring Data JDBC, you can use `@Query` or a custom repository. If the result is only for display, a DTO projection is often cleaner than returning the aggregate root:

```java
public record OrderMatch(
        Long orderId,
        String orderCode,
        String status
) {
}
```

### 6.2. Using JOIN When Data from Both Root and Child Is Needed

If a screen needs each line item along with its order code:

```sql
SELECT
    o.id AS order_id,
    o.order_code AS order_code,
    l.id AS line_id,
    l.sku AS sku,
    l.quantity AS quantity
FROM orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku = ?
ORDER BY o.id, l.line_index;
```

Each result-set row represents an order/line pair. Suitable DTO:

```java
public record OrderLineResult(
        Long orderId,
        String orderCode,
        Long lineId,
        String sku,
        Integer quantity
) {
}
```

Do not try to map this multi-row result set into a single aggregate root without grouping logic for child rows. Each joined row repeats root information.

## 7. Limitations with AggregateReference and Other Aggregate Roots

An aggregate can reference another root via an ID or `AggregateReference`.

Example:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;
}
```

The reference holds the `Customer` ID; it is not a loaded customer object. Criteria can filter by the ID stored on the root if the mapping/property path supports it:

```java
Criteria.where("customer").is(AggregateReference.to(customerId));
```

Or the application can store a scalar `customerId` property and filter directly by ID.

But if the requirement is "find orders by customer name", the condition is in the `customers` table:

```sql
SELECT o.*
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.display_name = ?;
```

Criteria on `PurchaseOrder` does not automatically load `Customer` and does not automatically generate a join simply because `AggregateReference<Customer, Long>` exists.

### 7.1. When to Query Customer Separately?

If the query is simple and the ID set is small, you can:

1. Find matching customers in `CustomerRepository`.
2. Extract the list of customer IDs.
3. Find orders by `customerId` or `customerId IN (...)`.

This uses multiple repository queries but can be easy to understand. Consider the size of the ID set, number of round trips, and database limits on `IN` parameters.

If the query needs pagination over orders filtered by customer name, a JOIN/EXISTS in a single SQL statement is usually better because the database filters and paginates the exact same result set.

## 8. Embedded Objects Differ from JOIN Relationships

`@Embedded` flattens a value object's properties into columns in the root table. Thus, embedded objects do not require a JOIN to a separate table.

Example:

```java
public record ShippingAddress(
        String street,
        String city,
        String postalCode
) {
}
```

In the aggregate:

```java
@Embedded(prefix = "shipping_")
private ShippingAddress shippingAddress;
```

The schema might contain:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    order_code VARCHAR(40) NOT NULL,
    shipping_street VARCHAR(180),
    shipping_city VARCHAR(100),
    shipping_postal_code VARCHAR(20)
);
```

The condition `shipping_city = ?` is on the `orders` table itself; there is no `shipping_addresses` table to JOIN.

Still, whether Criteria resolves a nested property like `shippingAddress.city` depends on mapping and API version. Do not assume nested Java property paths are always supported. For stable queries on flattened columns, use explicit SQL:

```sql
SELECT *
FROM orders
WHERE shipping_city = ?;
```

Or use a property path supported by your application's mapping version and verify it with an integration test.

**Embedded maps multiple fields onto the same row; `@MappedCollection` and `AggregateReference` involve other tables/aggregates.** Only the latter two cases require considering JOIN or EXISTS when filtering on another table's data.

## 9. Using @Query When JOINs Are Needed

Spring Data JDBC supports declaring explicit SQL with `@Query`. This is the right option when a query needs joins or subqueries.

Example repository returning a DTO:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT
            o.id AS order_id,
            o.order_code AS order_code,
            o.status AS status
        FROM orders o
        WHERE EXISTS (
            SELECT 1
            FROM order_lines l
            WHERE l.order_id = o.id
              AND l.sku = :sku
        )
        """)
    List<OrderMatch> findOrdersContainingSku(
            @Param("sku") String sku
    );
}
```

The example assumes constructor/record DTO mapping and aliases supported by your project's version. If your current module or version does not directly support that DTO mapping, use a custom repository with `JdbcTemplate` and a `RowMapper`.

### 9.1. Do Not Use JPQL

`@Query` in Spring Data JDBC accepts SQL, not JPQL.

JPQL describes entities and associations:

```text
SELECT o FROM PurchaseOrder o JOIN o.lines l WHERE l.sku = :sku
```

JDBC SQL describes tables and columns:

```sql
SELECT DISTINCT o.id, o.order_code, o.status
FROM orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku = :sku;
```

Use actual table and column names, including any prefixes and naming strategies used by the schema.

### 9.2. Select Explicit Columns with Clear Aliases

When joining, multiple tables often share column names like `id`, `status`, and `created_at`. Avoid `SELECT *` because column labels can collide and DTO mapping becomes unpredictable.

Write:

```sql
SELECT
    o.id AS order_id,
    c.id AS customer_id,
    o.status AS order_status,
    c.display_name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id;
```

Then map into a DTO with matching component names:

```java
public record OrderCustomerView(
        Long orderId,
        Long customerId,
        String orderStatus,
        String customerName
) {
}
```

Aliases must be compatible with your application's naming strategy/constructor mapping. Check actual column labels if the database normalizes casing.

## 10. Using a Custom Repository and JdbcTemplate

For multi-table queries, specialized DTOs, or results needing explicit conversions, a custom repository gives strong control.

Example DTO:

```java
public record OrderLineSearchResult(
        Long orderId,
        String orderCode,
        String customerName,
        String sku,
        Integer quantity
) {
}
```

Custom repository:

```java
@Repository
public class OrderSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderLineSearchResult> searchByCustomerAndSku(
            String customerName,
            String sku
    ) {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_code AS order_code,
                c.display_name AS customer_name,
                l.sku AS sku,
                l.quantity AS quantity
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            JOIN order_lines l ON l.order_id = o.id
            WHERE c.display_name = :customerName
              AND l.sku = :sku
            ORDER BY o.id, l.line_index
            """;

        var parameters = new MapSqlParameterSource()
                .addValue("customerName", customerName)
                .addValue("sku", sku);

        return jdbc.query(sql, parameters, (rs, rowNum) ->
                new OrderLineSearchResult(
                        rs.getLong("order_id"),
                        rs.getString("order_code"),
                        rs.getString("customer_name"),
                        rs.getString("sku"),
                        rs.getObject("quantity", Integer.class)
                )
        );
    }
}
```

This approach lets you:

- Use JOINs across multiple tables.
- Select the exact output columns.
- Return DTOs per result-set row.
- Control type conversions and NULL handling.
- Avoid constructing aggregate graphs when a use case only needs reporting data.

`NamedParameterJdbcTemplate` still participates in Spring transactions when sharing the same DataSource and transaction manager. However, it does not automatically apply aggregate lifecycles or load child collections.

## 11. Beware of One-to-Many JOIN Results

Joining root and child tables can return multiple rows for a single root.

For example, one order with three order lines:

| order_id | order_code | line_id | sku |
|---:|---|---:|---|
| 101 | PO-101 | 1001 | BOOK-01 |
| 101 | PO-101 | 1002 | PEN-02 |
| 101 | PO-101 | 1003 | BAG-03 |

If the query only aims to list orders, a join result can repeat `PO-101` three times. Two common fixes:

- `SELECT DISTINCT` on the returned root columns.
- `WHERE EXISTS (...)` to check for a matching child without multiplying root rows.

If each child is needed, repeating root details in each row's DTO may be intentional.

### 11.1. Pagination Over JOINs

Paginating a one-to-many join query paginates joined rows, not aggregate roots. For example, limit 20 may return 20 line rows belonging to 3 orders instead of 20 orders.

If the goal is paginating roots:

1. Write a query selecting matching root IDs using `EXISTS` or a subquery.
2. Sort and paginate the ID list.
3. Fetch root/DTO data for those IDs.
4. If child collections are needed, load them in a separate controlled query.

Or use SQL with a CTE/subquery to paginate roots before joining children. Syntax depends on the database.

PostgreSQL example:

```sql
WITH page_of_orders AS (
    SELECT o.id
    FROM orders o
    WHERE EXISTS (
        SELECT 1
        FROM order_lines l
        WHERE l.order_id = o.id
          AND l.sku = :sku
    )
    ORDER BY o.created_at DESC, o.id DESC
    LIMIT :limit OFFSET :offset
)
SELECT o.id, o.order_code, l.sku, l.quantity
FROM page_of_orders p
JOIN orders o ON o.id = p.id
LEFT JOIN order_lines l ON l.order_id = o.id
ORDER BY o.created_at DESC, o.id DESC, l.line_index;
```

This is a concrete reporting query. It demonstrates why the unit of pagination must be established before joining collections.

## 12. Do JOIN Queries Load Aggregate Children Automatically?

Do not assume a `@Query` join returning an aggregate root automatically builds the full object graph like a JPA fetch join.

Spring Data JDBC manages aggregates through repository/template mapping. A custom SQL query must be designed to return the exact result shape the mapper can process. Extra joined columns do not automatically turn into child objects just because table foreign keys exist.

When reporting DTOs are needed, returning DTOs/projections directly is usually better. When a full aggregate is needed to execute domain behavior:

- Find matching root IDs using a dedicated query.
- Load the aggregate via repository/template mapping.
- Execute domain methods.
- Persist the aggregate through the corresponding persistence path.

Loading many roots and then calling the repository once per root can cause N+1 queries. Consider batch loading, dedicated read queries, or a DTO read model.

## 13. Why You Should Not Use Criteria to Emulate Every Kind of JOIN

You might try to write a method or Criteria property path that looks like a relationship:

```java
// Not a general JOIN model:
Criteria.where("customer.displayName").is("Lan");

// Not a reliable way to query child collections:
Criteria.where("lines.sku").is("BOOK-01");
```

These expressions do not specify join tables, join conditions, multiplicity, or how results map. Even if a particular property path happens to resolve under some mapping, that does not turn Criteria into a general relational join builder.

When filtering across tables is needed, write the SQL relationship explicitly. That lets readers see:

- Foreign-key join conditions.
- Join type.
- Filter predicates.
- Potential duplicates.
- Unit of pagination.
- Result data shape.

## 14. Choosing the Right Query Approach

| Need | Suitable Tool | Reason |
|---|---|---|
| Dynamic predicates on root scalar properties | `Criteria` + `Query` | Flexible conditions driven by input |
| Root query needing sort/limit | `Query` + `Sort` | Attaches ordering and bounds to query |
| Filter by flattened embedded columns | Criteria if mapping/version supports it; or `@Query` | Same root table, no JOIN needed |
| Filter roots by child collection | SQL `EXISTS` or JOIN | Requires accessing child table |
| Filter roots by aggregate reference properties | SQL JOIN or separate query by ID | Requires accessing target aggregate table |
| Return multi-table data for UI | DTO/record projection | Read output has a dedicated shape |
| Report one row per child | JOIN + DTO/RowMapper | Each result row represents one child |
| Complex or vendor-specific SQL | Custom repository + `JdbcTemplate` | Full control of SQL and mapping |
| Modify aggregates | Repository/`JdbcAggregateTemplate` | Preserves aggregate lifecycle and invariants |

### 14.1. A Quick Decision Rule

Ask yourself: **which table holds the column being filtered?**

- If it is on the aggregate root table, consider Criteria.
- If it is in a flattened embedded value object on the root, check the physical column and mapping support; explicit SQL is a clear choice when stability matters.
- If it is on a child table or another aggregate root, use JOIN/EXISTS in SQL.
- If results combine columns from multiple tables, return a DTO/projection rather than forcing an aggregate.
- If domain state needs modification, load the aggregate and save via repository/template.

## 15. Testing Criteria and JOINs

Criteria and SQL joins must be tested against a real database or a test database with the same dialect/schema.

### 15.1. Testing Criteria on the Root

```java
@DataJdbcTest
class PurchaseOrderCriteriaTest {

    @Autowired
    JdbcAggregateTemplate template;

    @Test
    void findsNewOrdersCreatedInRange() {
        Criteria criteria = Criteria.where("status").is(OrderStatus.NEW)
                .and("createdAt").greaterThanOrEquals(
                        LocalDateTime.parse("2026-01-01T00:00:00")
                );

        Query query = Query.query(criteria);

        List<PurchaseOrder> result =
                template.findAll(query, PurchaseOrder.class);

        assertThat(result)
                .allMatch(order -> order.getStatus() == OrderStatus.NEW);
    }
}
```

The test needs matching fixtures and schema. It verifies predicates on root properties, not JOINs across children.

### 15.2. Testing EXISTS by Child

Create two orders:

- Order A has line `BOOK-01`.
- Order B only has line `PEN-02`.

Run the `EXISTS` query for `sku = BOOK-01` and verify only Order A is returned. Add a case where Order A has two `BOOK-01` lines to verify the root is not duplicated.

### 15.3. Testing DTOs for JOINs

If the query returns `OrderLineSearchResult`, verify:

- Every column alias matches DTO mapping.
- Result row count matches the number of matching children.
- A root with multiple children produces multiple DTOs if that is intended.
- Nullable values map into wrapper types.
- Sorting includes a stable tie-breaker.

### 15.4. Testing Pagination

If a query paginates roots over a one-to-many JOIN, create one root with multiple children alongside other roots. Verify each page contains the expected number of roots, not joined child rows. If pagination is applying to child rows, fix the query to paginate roots first.

## 16. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Criteria cannot find property | Using SQL column name instead of Java property, or non-persistent property | Check mapping and use property name |
| `Criteria.where("lines.sku")` fails | Child collection lives in another table; Criteria does not auto-JOIN | Use `EXISTS`/JOIN in SQL |
| Criteria cannot filter by Customer name | Root only stores customer ID/reference | JOIN `customers` or query Customer separately |
| Treating Criteria like JPA `root.join(...)` | Confusing the two APIs | Use SQL or a custom repository |
| JOIN returns the same order multiple times | One root matches multiple child rows | Use `EXISTS`, `DISTINCT`, or per-child DTOs |
| Pagination returns fewer orders than expected | Limit applied to joined rows | Paginate roots first, then JOIN |
| `@Query` returns root with empty/unexpected child collection | Custom SQL does not automatically assemble the full aggregate graph | Load aggregate via repository or return DTO |
| DTO aliases fail to map | Column labels do not match naming strategy | Set explicit aliases and inspect ResultSet metadata |
| Nested embedded path fails to resolve | Mapping/version differences or unsupported property path | Use flattened column name in SQL with integration tests |
| Query slows down after adding JOIN | Missing indexes or high join cardinality | Inspect execution plan and index FKs/filters |
| `SELECT *` causes duplicate column labels | Multiple tables share column names | Select specific columns with unique aliases |

## 17. Key Principles

- Spring Data Relational `Criteria` and `Query` build predicates and query options; they are not the JPA Criteria API.
- Criteria works best for conditions on mapped properties within the aggregate root's scope.
- `@MappedCollection` stores children in a separate table; Criteria does not automatically JOIN child tables merely because a Java collection exists.
- `AggregateReference` stores a target ID; Criteria does not automatically load the target aggregate or join on its attributes.
- `@Embedded` flattens a value object into root columns; that is same-row mapping, not a JOIN relationship.
- When filtering by children or other aggregates, write `JOIN`/`EXISTS` using SQL `@Query` or a custom repository.
- On one-to-many JOINs, decide explicitly whether you want one row per root or one row per child; use `EXISTS`, `DISTINCT`, or the corresponding DTO.
- Pagination must target the right data unit; paginate roots before joining collections when listing aggregates.
- Join queries returning DTOs are usually easier to control than expecting custom SQL to materialize full aggregate graphs.
- Verify mappings, aliases, SQL dialects, indexes, and pagination with integration tests.

Criteria keeps dynamic queries concise when filters sit on aggregate root properties. When conditions cross into child tables or other aggregate roots, switch to explicit SQL to specify join keys, cardinality, and result shape. Clearly separating object mapping from query planning leads to sound query designs and avoids false expectations about automatic JOINs in Spring Data JDBC.
