# Keyword Scope Supported by JDBC and Limits on Traversing Nested Relationships

In **Spring Data Relational JDBC**, repositories can generate queries from method names via **derived queries**. You write conditions using keywords such as `IsNull`, `IsNotNull`, `Between`, `Like`, `In`, `True`, `False`, `And`, and `Or`; Spring Data parses the method name and builds SQL suited to your database.

However, Spring Data JDBC's query derivation scope has an important boundary: **derived query conditions focus on properties of the aggregate root and do not automatically traverse nested relationships like an ORM that auto-generates joins**. For instance, just because an order has a list of order lines or references a customer does not mean you can freely write `findByLinesSku(...)` or `findByCustomerName(...)`.

This lesson covers commonly used keyword groups, how to read method names, limitations when querying embedded objects, child collections, and aggregate references, and options when you need SQL joins or queries over nested data.

## 1. How Do Derived Queries Work?

A derived query is a query inferred from a repository method name. Spring Data reads the method name, identifies properties in the domain type, recognizes operators, and builds an SQL statement.

Example:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByLastName(String lastName);

    List<Customer> findByActiveTrue();

    List<Customer> findByEmailIsNull();
}
```

A method name can be broken down into parts:

- **Subject:** describes the operation or result type, such as `find`, `count`, `exists`, `delete`.
- **`By`:** marks the beginning of the predicate.
- **Property path:** the property name in the domain model.
- **Keyword/operator:** conditions such as `IsNull`, `Between`, `Like`, `In`, `True`.
- **Combining/sorting/limiting:** `And`, `Or`, `OrderBy`, `First`, `Top`, and parameters such as `Sort`/`Pageable` when supported by the module.

For example, `findByLastName(String lastName)` finds aggregate roots whose `lastName` property equals the passed value. The property in the method is the Java property name; it does not have to match the SQL column name.

If the domain has:

```java
@Column("last_name")
private String lastName;
```

the method is still written as `findByLastName(...)`, not `findByLast_name(...)`.

### 1.1. Derived queries are not abbreviated SQL

Method names are a convention-based declarative language defined by Spring Data. They do not let you embed arbitrary SQL clauses into method names.

```java
List<Customer> findByLastName(String lastName);
```

is valid if `lastName` is a persistent property and the query type is supported.

By contrast, a name like `findByLastNameAndJoinOrders(...)` does not tell Spring to automatically infer `JOIN orders`. `JoinOrders` is not a general join directive in query derivation.

**Only use properties and keywords that Spring Data JDBC can resolve from the domain model.** When requirements exceed that scope, move to explicit SQL or a custom repository.

## 2. Common Subjects

The part before `By` usually indicates the result or operation type:

| Subject | Example | Meaning |
|---|---|---|
| `find…By` | `findByLastName(...)` | Find one or more aggregates |
| `read…By` | `readByActiveTrue()` | Read aggregates matching condition |
| `get…By` | `getByEmail(...)` | Read matching condition |
| `query…By` | `queryByStatus(...)` | Query matching condition |
| `count…By` | `countByActiveTrue()` | Count matching rows |
| `exists…By` | `existsByEmail(...)` | Check if matching rows exist |
| `delete…By` | `deleteByExpiredTrue()` | Delete matching rows per repository mechanism |
| `remove…By` | `removeByStatus(...)` | Alternative name for delete operations |

These are common patterns across the Spring Data ecosystem. Exact supported subjects and return type handling must match your Spring Data JDBC version. For delete operations, check the return type and repository method semantics carefully; do not treat a derived delete as arbitrary SQL capable of cascading across every relationship.

`find`, `read`, `get`, and `query` are often interchangeable for read queries. Choose one consistent naming convention in your codebase.

## 3. Common Predicate Groups in Spring Data JDBC

The keywords below represent common groups when creating derived queries for aggregate root properties. Exact syntax and detailed support can vary by module version; do not extrapolate keywords specific to JPA, MongoDB, or Elasticsearch.

### 3.1. Equality and inequality comparisons

| Keyword | Example | Meaning |
|---|---|---|
| No keyword | `findByStatus(status)` | Equality comparison |
| `Is` | `findByStatusIs(status)` | Equality comparison |
| `Equals` | `findByStatusEquals(status)` | Equality comparison |
| `Not` | `findByStatusNot(status)` | Differs from passed value |

Example:

```java
List<Order> findByStatus(OrderStatus status);

List<Order> findByStatusIs(OrderStatus status);

List<Order> findByStatusNot(OrderStatus status);
```

Illustrative SQL semantics:

```sql
SELECT *
FROM orders
WHERE status = ?;
```

and:

```sql
SELECT *
FROM orders
WHERE status <> ?;
```

For nullable properties, remember SQL uses three-valued logic. `status <> 'CANCELLED'` does not automatically include rows with `status IS NULL`, because comparing against NULL yields UNKNOWN. If you want to include nulls, express that condition separately using `Or...IsNull`.

### 3.2. Range and ordering comparisons

| Keyword | Example | Meaning |
|---|---|---|
| `Between` | `findByPriceBetween(min, max)` | Within range |
| `LessThan` | `findByPriceLessThan(max)` | Less than |
| `LessThanEqual` | `findByPriceLessThanEqual(max)` | Less than or equal to |
| `GreaterThan` | `findByPriceGreaterThan(min)` | Greater than |
| `GreaterThanEqual` | `findByPriceGreaterThanEqual(min)` | Greater than or equal to |
| `Before` | `findByCreatedAtBefore(time)` | Before timestamp |
| `After` | `findByCreatedAtAfter(time)` | After timestamp |

Example:

```java
List<Product> findByPriceBetween(long minimum, long maximum);

List<Order> findByCreatedAtAfter(LocalDateTime start);

List<Order> findByCreatedAtBefore(LocalDateTime end);
```

Semantically equivalent SQL:

```sql
SELECT *
FROM products
WHERE price BETWEEN ? AND ?;
```

`BETWEEN` typically includes both endpoints. If business rules require a half-open interval such as `[start, end)`, write two conditions `GreaterThanEqual` and `LessThan`, or use `@Query` when that reads more clearly.

`Before` and `After` are generally suited to dates/times or ordered types. Choose a Java type compatible with the SQL column and your application's time zone rules.

### 3.3. NULL checks

| Keyword | Example | SQL |
|---|---|---|
| `IsNull` / `Null` | `findByDeletedAtIsNull()` | `deleted_at IS NULL` |
| `IsNotNull` / `NotNull` | `findByDeletedAtIsNotNull()` | `deleted_at IS NOT NULL` |

Example:

```java
List<Order> findByDeletedAtIsNull();

List<Order> findByDeletedAtIsNotNull();
```

These methods take no parameters because the predicate only checks the column's null state.

### 3.4. Boolean conditions

| Keyword | Example | Meaning |
|---|---|---|
| `True` / `IsTrue` | `findByEnabledTrue()` | Boolean property is true |
| `False` / `IsFalse` | `findByEnabledFalse()` | Boolean property is false |

Example:

```java
List<UserAccount> findByEnabledTrue();

List<UserAccount> findByEnabledFalse();
```

If a property uses `Boolean` and the database permits NULL, there are three states: `TRUE`, `FALSE`, and `NULL`. `findByEnabledFalse()` finds only FALSE; to include FALSE or NULL, write a combined condition.

### 3.5. String conditions

| Keyword | Example | Meaning |
|---|---|---|
| `Like` | `findByNameLike(pattern)` | Uses caller-supplied LIKE pattern |
| `NotLike` | `findByNameNotLike(pattern)` | Negates LIKE condition |
| `StartingWith` | `findByNameStartingWith(prefix)` | String starts with value |
| `EndingWith` | `findByNameEndingWith(suffix)` | String ends with value |
| `Containing` | `findByNameContaining(part)` | String contains substring |
| `IgnoreCase` | `findByNameIgnoreCase(name)` | Case-insensitive comparison when supported |

Example:

```java
List<Customer> findByNameStartingWith(String prefix);

List<Customer> findByNameEndingWith(String suffix);

List<Customer> findByNameContaining(String fragment);

List<Customer> findByNameLike(String pattern);
```

`Like` generally accepts a pattern with SQL wildcards such as `%` and `_`. `StartingWith`, `EndingWith`, and `Containing` state more specific goals; Spring Data constructs the corresponding pattern based on the keyword.

Semantically equivalent SQL:

```sql
-- Starts with "An"
WHERE name LIKE 'An%'

-- Ends with "son"
WHERE name LIKE '%son'

-- Contains "min"
WHERE name LIKE '%min%'
```

Case-sensitivity behavior depends on the keyword, dialect, generated expression, and database collation. `IgnoreCase` is not a promise that all databases share identical Unicode/collation rules. For Vietnamese text searches, test against your actual collation and data.

### 3.6. Value sets

| Keyword | Example | Meaning |
|---|---|---|
| `In` | `findByStatusIn(statuses)` | Value is in set |
| `NotIn` | `findByStatusNotIn(statuses)` | Value is not in set |

Example:

```java
List<Order> findByStatusIn(Collection<OrderStatus> statuses);

List<Order> findByStatusNotIn(Collection<OrderStatus> statuses);
```

Semantically equivalent SQL:

```sql
SELECT *
FROM orders
WHERE status IN (?, ?, ?);
```

`In`/`NotIn` inputs are typically compatible collections or arrays. Handle empty collections explicitly in business logic; SQL `IN ()` is not portable syntax, and how the framework handles empty collections can depend on version and dialect.

Also be careful when a collection contains NULL: `IN`/`NOT IN` logic is subject to SQL three-valued logic. If nulls need to be included, add an explicit `IsNull` predicate.

### 3.7. Combining predicates

`And` and `Or` combine conditions:

```java
List<Order> findByStatusAndCustomerId(
        OrderStatus status,
        Long customerId
);

List<Order> findByStatusOrPriority(
        OrderStatus status,
        int priority
);
```

Semantically equivalent SQL:

```sql
WHERE status = ?
  AND customer_id = ?;
```

or:

```sql
WHERE status = ?
   OR priority = ?;
```

For methods combining both AND and OR, pay close attention to how the parser groups predicates. If an expression requires multiple parenthesized groups, prefer `@Query` so the SQL structure is directly visible rather than building a very long, hard-to-verify method name.

### 3.8. Sorting and limiting results

You can specify ordering in the method:

```java
List<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);

List<Product> findTop10ByActiveTrueOrderByNameAsc();

Optional<Order> findFirstByOrderCode(String orderCode);
```

- `OrderBy...Asc` sorts ascending.
- `OrderBy...Desc` sorts descending.
- `First` and `Top` limit the number of results per method syntax.
- `Sort` or `Pageable` can be used on query methods and repository APIs supported by your Spring Data JDBC version.

If pagination is needed, choose return types and method signatures supported by your version's API. Not every query with `Pageable` has identical cost or the same count-query behavior. For complex queries, inspect the SQL and database execution plan.

## 4. Repository Example Using Keyword Groups

Suppose we have an aggregate root `Order`:

```java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("order_code")
    private String orderCode;

    private OrderStatus status;

    @Column("customer_id")
    private Long customerId;

    private Integer priority;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("deleted_at")
    private LocalDateTime deletedAt;

    // Constructor, getters, and domain methods...
}
```

Repository:

```java
public interface OrderRepository
        extends CrudRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    List<Order> findByStatusNot(OrderStatus status);

    List<Order> findByPriorityGreaterThanEqual(Integer priority);

    List<Order> findByCreatedAtBetween(
            LocalDateTime start,
            LocalDateTime end
    );

    List<Order> findByDeletedAtIsNull();

    List<Order> findByDeletedAtIsNotNull();

    List<Order> findByStatusIn(Collection<OrderStatus> statuses);

    List<Order> findByStatusAndCustomerId(
            OrderStatus status,
            Long customerId
    );

    List<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);

    List<Order> findTop20ByDeletedAtIsNullOrderByCreatedAtDesc();

    long countByStatus(OrderStatus status);

    boolean existsByOrderCode(String orderCode);
}
```

All of these methods query properties of the `Order` aggregate root. They do not traverse related objects or generate joins automatically.

Method names should reflect domain meaning. Once a method name becomes so long you must read it multiple times to understand it, switching complex conditions to `@Query` or a custom repository is usually easier to maintain.

## 5. Key Limitation: No Automatic Traversal of Nested Relationships

Spring Data JDBC centers on aggregate roots and does not provide automatic object-graph traversal to generate joins the way users may be accustomed to in JPA.

Suppose the model is:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;

    @Embedded(prefix = "shipping_")
    private ShippingAddress shippingAddress;
}
```

The properties `customerId`, `lines`, and `shippingAddress` represent distinct things:

- `customerId` is a scalar value stored directly on the root row.
- `lines` is a child collection belonging to the aggregate, stored in another table.
- `shippingAddress` is a value object flattened into columns on the root table.

Do not assume that because Java code can call `order.getLines()` or `order.getShippingAddress()`, a derived query can automatically reach deep into nested properties.

### 5.1. Do not rely on findByLinesSku(...)

The following example expresses a common query intent that lies outside Spring Data JDBC's simple derived-query scope:

```java
// Do not rely on this working in Spring Data JDBC:
List<PurchaseOrder> findByLinesSku(String sku);
```

Reason: `lines` is a child collection within the aggregate. To find roots having at least one line item with a specific SKU, the database must query the `order_lines` table and relate it to `orders`.

That is a join or `EXISTS` check on a child table, not a comparison against a direct scalar property of the root.

When you need this query, use explicit SQL or a custom repository.

### 5.2. Do not rely on findByCustomerName(...)

If the aggregate only stores a reference ID:

```java
@Column("customer_id")
private Long customerId;
```

then `Customer` is a separate aggregate root. Derived queries on `PurchaseOrderRepository` do not automatically traverse to `Customer.name` just because the domain models the relationship with an ID or `AggregateReference`.

A method like:

```java
// Not a general join traversal in Spring Data JDBC:
List<PurchaseOrder> findByCustomerName(String name);
```

requires joining `orders.customer_id = customers.id` and then filtering `customers.name`. Write explicit SQL or query `Customer` separately and then use the resulting IDs.

### 5.3. Do not assume findByShippingAddressCity(...) is always supported

An embedded object is flattened into columns on the same root table. In SQL terms, filtering on `shipping_city` is simple. Still, nested property paths in derived queries are not a capability you should blindly assume in Spring Data JDBC.

If you need to filter on an embedded column, the explicit approach is `@Query` using the mapped column name:

```java
@Query("""
    SELECT *
    FROM orders
    WHERE shipping_city = :city
    """)
List<PurchaseOrder> findOrdersByShippingCity(@Param("city") String city);
```

This is SQL against the root table. Verify the exact column names, prefix, and embedded mapping naming strategy.

**Distinguish two things:** object mapping can reconstruct nested objects from root columns; query derivation does not automatically support arbitrary nested property paths because of that.

## 6. Why Does the Nested Path Limitation Matter?

Spring Data JDBC designs persistence around aggregates, does not maintain a persistence context, and does not auto-generate graph joins for every relationship.

A simple derived query maps directly:

```java
findByStatus(OrderStatus status)
```

into a condition on a root column:

```sql
SELECT *
FROM orders
WHERE status = ?;
```

By contrast, a nested query needs to know much more:

- Which table holds the filtered property?
- Which foreign key joins the relationship?
- Is it one-to-many or many-to-one?
- Can one root match multiple child rows?
- Will the join duplicate root rows in results?
- Are `DISTINCT`, `EXISTS`, `GROUP BY`, or pagination needed?
- If returning the aggregate root, must child collections still be loaded and mapped afterward?

An ORM with its own query model may provide syntax to express those relationships. Spring Data JDBC's derived queries keep a smaller scope; when joins are needed, you specify the SQL and result shape explicitly.

## 7. Querying Nested Relationships with @Query

Spring Data JDBC allows declaring SQL directly with `@Query`. This is the right option when joins or child-table conditions are required.

### 7.1. Finding orders with a line item by SKU

Example:

```java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT DISTINCT o.*
        FROM orders o
        JOIN order_lines l ON l.order_id = o.id
        WHERE l.sku = :sku
        """)
    List<PurchaseOrder> findOrdersContainingSku(
            @Param("sku") String sku
    );
}
```

SQL:

```sql
SELECT DISTINCT o.*
FROM orders o
JOIN order_lines l
    ON l.order_id = o.id
WHERE l.sku = ?;
```

`DISTINCT` avoids returning the same root multiple times if multiple child rows on the same order match. Table and column names in SQL must match the actual schema.

### 7.2. Using EXISTS when you only need to test child existence

You can express the same intent with `EXISTS`:

```java
@Query("""
    SELECT o.*
    FROM orders o
    WHERE EXISTS (
        SELECT 1
        FROM order_lines l
        WHERE l.order_id = o.id
          AND l.sku = :sku
    )
    """)
List<PurchaseOrder> findOrdersHavingSku(@Param("sku") String sku);
```

`EXISTS` clearly states that at least one matching child is sufficient. Depending on the database and data, the optimizer may choose a different execution plan than a join; inspect the execution plan when performance matters.

### 7.3. A join query does not automatically populate a full aggregate graph

If `@Query` returns `PurchaseOrder`, Spring Data JDBC must map the SQL result to that return type. A join query selecting columns of `orders` does not mean the framework automatically uses joined columns to assemble the entire `lines` collection like an ORM fetch join.

Choose your goal clearly:

- Return the aggregate root using the required root columns.
- Return a projection/DTO containing only the columns needed by the screen.
- Return child DTOs via a dedicated repository or custom JDBC call.
- Run intentional queries to retrieve root and child rows when business logic needs both.

Avoid `SELECT *` across multiple tables while expecting every column to be wired automatically into nested objects. Overlapping column names, mapping metadata, and joined row multiplication can make results ambiguous.

### 7.4. SQL must be database SQL

`@Query` in Spring Data JDBC takes native SQL, not JPQL. Do not use JPA-style entity names or association paths.

JPQL examples are invalid syntax for Spring Data JDBC:

```text
SELECT o FROM PurchaseOrder o JOIN o.lines l WHERE l.sku = :sku
```

In JDBC, write actual table names and join conditions:

```sql
SELECT DISTINCT o.*
FROM orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku = :sku;
```

This lets you use any SQL your database supports, but it also means queries can depend on dialect and schema and should be tested against a real database.

## 8. When to Use a Custom Repository or JdbcTemplate?

`@Query` works well for explicit SQL queries whose results map cleanly. When you need more complex queries, multiple tables, specialized projections, or controlled SQL commands, a custom repository is a good choice.

Example custom repository returning a DTO:

```java
public record OrderLineSummary(
        Long orderId,
        String orderCode,
        String sku,
        int quantity
) {
}
```

Implementation using `NamedParameterJdbcTemplate`:

```java
@Repository
public class OrderSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderLineSummary> findLineSummaries(String sku) {
        String sql = """
            SELECT o.id AS order_id,
                   o.order_code,
                   l.sku,
                   l.quantity
            FROM orders o
            JOIN order_lines l ON l.order_id = o.id
            WHERE l.sku = :sku
            ORDER BY o.id
            """;

        var parameters = new MapSqlParameterSource("sku", sku);

        return jdbc.query(sql, parameters, (rs, rowNum) ->
                new OrderLineSummary(
                        rs.getLong("order_id"),
                        rs.getString("order_code"),
                        rs.getString("sku"),
                        rs.getInt("quantity")
                )
        );
    }
}
```

This is a projection example: each result row maps to an `OrderLineSummary`. It does not try to reconstruct the `PurchaseOrder` aggregate from a joined result set that may repeat root columns.

### 8.1. Choosing between derived queries, @Query, and JdbcTemplate

| Approach | Best suited when | Points to watch |
|---|---|---|
| Derived query | Simple conditions on root properties | Keyword and property path limitations |
| `@Query` | Specific SQL joins/exists/aggregate expressions whose result maps to return type | Must manage SQL, schema, and mapping |
| Custom repository + `JdbcTemplate` | Complex DTOs/projections, multiple queries, custom data-access logic | Manage `RowMapper` and transaction participation |
| Multiple repository calls | Data comes from independent aggregates that can be read separately | Consider query count and consistency |
| Database view | Complex read reused repeatedly | View belongs to schema/database; mapping still must be clear |

## 9. Querying Each Relationship Type

### 9.1. Embedded objects

Embedded properties are stored as columns on the root table. If query derivation does not handle a nested property as needed, use `@Query` with the flattened column.

Example:

```java
@Query("""
    SELECT *
    FROM orders
    WHERE shipping_city = :city
    """)
List<PurchaseOrder> findByShippingCity(@Param("city") String city);
```

No join is needed because the address columns live on the `orders` table itself.

### 9.2. Child collections

With `@MappedCollection`, child rows live in a separate table. To filter roots by a child property, write a join or `EXISTS`:

```sql
SELECT o.*
FROM orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
      AND l.quantity > 5
);
```

If you want the child rows themselves, return a DTO or child projection rather than assuming a derived query on the root can return an arbitrary child path.

### 9.3. Aggregate references

If an order stores `customer_id`, querying by ID queries a scalar property on the root:

```java
List<PurchaseOrder> findByCustomerId(Long customerId);
```

However, querying by customer name requires a join:

```sql
SELECT o.*
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.display_name = ?;
```

You can write this SQL using `@Query` or a custom repository. When only customer IDs are needed first, querying `CustomerRepository` separately can be simpler, then passing the IDs to find orders if the ID count is reasonable.

### 9.4. Multiple nested relationships

A query such as "find all orders for customers in city X that have a line item with SKU Y" combines `orders`, `customers`, and `order_lines`. This is a multi-table query and should not be squeezed into a long method name.

The SQL can be written as:

```sql
SELECT DISTINCT o.*
FROM orders o
JOIN customers c
    ON c.id = o.customer_id
JOIN order_lines l
    ON l.order_id = o.id
WHERE c.city = ?
  AND l.sku = ?;
```

If pagination, sorting, or projections are also needed, design the query and return type explicitly and inspect the execution plan.

## 10. Distinguishing Relationship Queries from Aggregate Persistence

A query derivation limitation does not mean Spring Data JDBC cannot save or load aggregates containing nested objects.

For example:

- `@Embedded` allows value objects to be flattened into root columns.
- `@MappedCollection` allows saving and loading child collections belonging to an aggregate.
- `AggregateReference` represents a reference to another aggregate root.

These annotations control **object mapping and aggregate persistence**. They do not expand the derived-query language into a query builder capable of joining every relationship.

| Need | Mapping/persistence | Querying |
|---|---|---|
| Save address with order | `@Embedded` | Query root columns; use `@Query` if nested paths are unsupported |
| Save order lines | `@MappedCollection` | Join/`EXISTS` or custom query to filter by lines |
| Reference Customer | ID/`AggregateReference` | Query by ID on root; join when filtering by Customer attributes |
| Load aggregate | Aggregate repository | Repository loads aggregate per mapping |
| Multi-table reports | Not necessarily an aggregate | DTO/projection, SQL, or view |

Do not confuse the ability to assemble objects when loading an aggregate with the ability to query arbitrarily deep properties across the object graph.

## 11. Which Keywords Should Not Be Carried Over from Other Modules to JDBC?

Spring Data Commons provides shared query method infrastructure, yet each Spring Data module has distinct capabilities. Not every keyword from one store makes sense in Spring Data JDBC.

Examples you should not assume work in JDBC:

| Feature common in other modules | Why not to assume JDBC support |
|---|---|
| JPA association traversal/fetch joins | JDBC derived queries do not auto-generate joins from object relationships |
| JPQL entity paths | JDBC `@Query` expects SQL, not JPQL |
| MongoDB `Regex`/document operators | Syntax and semantics belong to the MongoDB query model |
| Geospatial `Near`/`Within` | Depends on whether the store supports geographic types and operators |
| Elasticsearch full-text/search operators | Belongs to search engines, not standard relational query derivation |
| JPA `EntityGraph`/fetch strategies | Spring Data JDBC has no JPA persistence context or fetch graph semantics |
| Store-specific collection association operators | You cannot infer that child collections can be queried like scalar properties |

Even if a keyword appears in Spring Data's general keyword table, check whether your Spring Data JDBC version and dialect support translating it. Never conclude a query works at runtime merely because IDE autocomplete suggests it or the method name compiles.

## 12. Method Names and Property Paths: Common Mistakes

### 12.1. Using column names instead of property names

Domain:

```java
@Column("created_at")
private LocalDateTime createdAt;
```

Correct:

```java
List<Order> findByCreatedAtAfter(LocalDateTime time);
```

Wrong property-parsing intent:

```java
List<Order> findByCreated_atAfter(LocalDateTime time);
```

### 12.2. Querying non-persistent properties

If a property is annotated with `@Transient`, or is merely a computed value with no mapped column, derived queries cannot generate standard SQL conditions for it.

Example:

```java
@Transient
private String displayLabel;
```

You cannot expect `findByDisplayLabel(...)` to work as a column query if `displayLabel` is not persisted. Query the underlying persistent properties that compose it, or use a projection or application-layer computation.

### 12.3. Using nested property names

Methods like `findByAddressCity(...)`, `findByLinesSku(...)`, or `findByCustomerName(...)` represent nested property paths. Do not assume Spring Data JDBC will automatically traverse and join those relationships.

Move to `@Query` or a custom repository when conditions lie in another table or inside a nested object that derived queries do not support.

### 12.4. Overly long method names

Example:

```java
findByStatusAndCustomerIdAndCreatedAtAfterAndDeletedAtIsNullOrderByPriorityDesc(...)
```

Long methods are not inherently invalid, but when there are many `And`/`Or` branches, they become hard to read and prone to logic errors. When a query needs expression grouping, joins, subqueries, or projections, explicit SQL is usually easier to review.

## 13. Query Performance and Correctness

Derived queries generate SQL conveniently, but do not automatically make queries fast. Consider database factors:

- **Indexes:** columns used in predicates, joins, and sorts may need indexes.
- **Selectivity:** an `IS NOT NULL` condition on a column where nearly all rows have values may filter out very little.
- **LIKE patterns:** `Containing` usually generates leading-wildcard patterns that cannot use standard B-tree indexes effectively.
- **IN lists:** very large collections can bloat SQL statements and hurt execution plans.
- **Join duplicates:** one-to-many joins can return multiple rows per root; consider `DISTINCT` or `EXISTS`.
- **Pagination:** joining one-to-many data can paginate over joined rows instead of roots if the query is not designed carefully.
- **Null semantics:** `Not`, `NotIn`, and ordinary comparisons do not automatically include SQL NULL.

Index examples:

```sql
CREATE INDEX idx_orders_status
    ON orders(status);

CREATE INDEX idx_orders_customer_id
    ON orders(customer_id);

CREATE INDEX idx_order_lines_order_id_sku
    ON order_lines(order_id, sku);
```

Appropriate indexes depend on query frequency, data distribution, and the database engine. Do not create indexes mechanically on every column; indexes also increase INSERT/UPDATE/DELETE overhead.

### 13.1. Inspecting execution plans

In PostgreSQL you can use:

```sql
EXPLAIN
SELECT DISTINCT o.*
FROM orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku = 'BOOK-01';
```

Use `EXPLAIN ANALYZE` in an appropriate environment when you want to measure actual execution; that statement runs the query and can have load impact if the query is heavy. Optimization plans should be grounded in real data and the target database, not just method names.

## 14. Testing Derived Queries and Nested Queries

### 14.1. Testing derived queries on root properties

```java
@DataJdbcTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orders;

    @Test
    void findsOrdersByStatus() {
        assertThat(orders.findByStatus(OrderStatus.NEW))
                .allMatch(order -> order.getStatus() == OrderStatus.NEW);
    }
}
```

Tests require matching fixtures and schema. This verifies that the derived query is parsed and executed properly on the test database.

### 14.2. Testing custom join queries

For a query finding orders containing an SKU:

```java
@Test
void findsOrdersContainingSku() {
    List<PurchaseOrder> result =
            orders.findOrdersContainingSku("BOOK-01");

    assertThat(result)
            .extracting(PurchaseOrder::getId)
            .contains(orderId);
}
```

Include a case where one order has multiple lines with the same SKU to confirm the root is not duplicated if the method uses `DISTINCT` or `EXISTS`.

### 14.3. Testing projections for child rows

If the repository returns `OrderLineSummary`, tests should verify that SQL aliases map cleanly to the DTO:

- `order_id` → `orderId`
- `order_code` → `orderCode`
- `sku` → `sku`
- `quantity` → `quantity`

With a custom `RowMapper`, alias names and JDBC types must match the mapping you wrote.

### 14.4. Testing NULL and empty collections

If a query uses `Not`, `NotIn`, `IsNull`, or `In`, test NULL data and empty collections. These are the cases most likely to reveal differences between Java expectations and SQL logic.

## 15. Decision Table: Which Query Tool to Choose?

| Requirement | Recommended approach |
|---|---|
| Compare a scalar property of the aggregate root | Derived query |
| `IS NULL`, boolean, range, string, `IN` on root | Derived query with appropriate keyword |
| Simple sorting/limiting | `OrderBy`, `First`/`Top`, `Sort`/`Pageable` if supported by version |
| Filter root by a child collection property | `@Query` with `EXISTS`/join or custom repository |
| Filter root by an attribute of a referenced aggregate | SQL join or separate query by ID |
| Filter by an embedded column | `@Query` using flattened column name if derived nested path is unsuitable |
| Return data from multiple tables as a DTO | Custom query/projection/`RowMapper` |
| Reports with complex aggregations | Explicit SQL, view, or reporting repository |
| Update/delete rows with specialized SQL commands | Custom repository/`JdbcTemplate` with clear transactions and invariants |

## 16. Principles to Remember

- Spring Data JDBC derived queries use Java property names and module-supported keywords to generate SQL.
- Common predicate groups include equality/inequality, ranges, NULL, booleans, strings, `IN`/`NOT IN`, `And`/`Or`, sorting, and result limits.
- Do not assume query capabilities from JPA, MongoDB, or search engines carry straight over to Spring Data JDBC.
- Spring Data JDBC focuses on aggregate root properties; do not assume method names automatically traverse `@MappedCollection`, `AggregateReference`, or nested objects to generate joins.
- Embedded, child, and reference constructs are mapping and aggregate-persistence concepts; they do not automatically extend query derivation.
- When you need to query child tables or other aggregates, use `@Query` SQL, custom repositories, `JdbcTemplate`, projections, or views.
- With one-to-many joins, watch out for duplicate roots, `DISTINCT`/`EXISTS`, pagination, and result mapping.
- Test SQL, dialects, indexes, and NULL data against a real database whenever correctness or performance matters.

Use derived queries for simple, readable conditions on aggregate roots. When conditions must reach into nested relationships, specify the tables, join keys, and result shape explicitly with SQL or a custom repository. This separation keeps repositories easy to understand and prevents confusing Spring Data JDBC's object-mapping capabilities with automatic querying across the entire object graph.
