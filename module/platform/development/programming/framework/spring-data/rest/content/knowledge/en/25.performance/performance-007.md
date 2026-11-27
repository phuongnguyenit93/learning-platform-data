# Designing Indexes for Search Queries Exposed in Spring Data REST

Spring Data REST can expose repository query methods as search endpoints. Clients call these endpoints with query parameters, and Spring Data translates those calls into queries at the persistence layer. As data grows, search queries can slow down if the database must scan too many rows, sort large datasets, or join across columns lacking suitable indexes.

Index design should start from the **actual queries exposed by the API**: filter predicates, sort orders, joins, pagination, and read/write frequency. Spring Data REST does not automatically create indexes just because a repository defines a finder method. Indexes must be designed and deployed in the database via migrations or the application's schema management mechanism.

## 1. Search Endpoints and Database Queries

Suppose the application has a repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    List<Order> findByCustomerIdAndStatus(
        Long customerId,
        OrderStatus status
    );

    List<Order> findByStatusAndCreatedAtAfterOrderByCreatedAtDesc(
        OrderStatus status,
        Instant createdAt
    );
}
~~~

Spring Data REST can expose exported query methods under the search resource. Clients discover search links and call the corresponding endpoint, for example:

~~~http
GET /orders/search/findByStatus?status=PAID
~~~

Or:

~~~http
GET /orders/search/findByCustomerIdAndStatus?customerId=42&status=PAID
~~~

The request is ultimately translated into a database query based on the query method. The database may need to:

- Filter on one or more columns.
- Join related tables.
- Sort on one or more columns.
- Count results for pagination.
- Read the columns required to build the representation.

Indexes should serve the operations that actually appear in query plans. Do not create an index on every entity property merely because it can be passed as a query parameter.

## 2. Start from the API Workload

Before creating indexes, inventory the query methods and how clients call them. For each search endpoint, document:

| Component | Question to answer |
|---|---|
| Predicate | Which columns appear in WHERE? |
| Join | Does the query join tables or filter on associations? |
| Sort | Which columns do clients typically sort by? |
| Pagination | Are page, size, and sort used? |
| Selectivity | Do filter conditions typically match few or many rows? |
| Frequency | How often is the endpoint called? |
| Data volume | How many rows does the table have and how fast does it grow? |
| Write rate | Do inserts/updates/deletes occur frequently? |

Example of an endpoint searching orders by status and creation time:

~~~http
GET /orders/search/findByStatusAndCreatedAtAfterOrderByCreatedAtDesc
    ?status=PAID
    &createdAt=2026-11-01T00:00:00Z
    &page=0
    &size=20
~~~

The query can be semantically equivalent to:

~~~sql
SELECT *
FROM orders
WHERE status = ?
  AND created_at > ?
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
~~~

An index on `status` and `created_at` can support both filtering and sort order. Whether the database uses that index depends on cardinality, statistics, actual data, query shape, and the optimizer.

## 3. Single-Column Indexes for Common Filter Conditions

A single-column index is helpful when one column is frequently used in a predicate with sufficient selectivity.

Example:

~~~sql
CREATE INDEX idx_orders_status
    ON orders (status);
~~~

This index can support:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID';
~~~

Suitable cases include:

- Looking up by a unique identifier or business code.
- Filtering by email or username.
- Searching by foreign key.
- Filtering by a frequently queried property with many distinct values.

An index does not guarantee a query will always be faster. If a condition matches most rows in a table, the database may choose a sequential scan or table scan because reading sequentially is cheaper than repeated index and table lookups.

### Low-Selectivity Columns

A boolean column like `active` has only two values. A single-column index on it is often unhelpful if most records share the same value.

Example:

~~~sql
CREATE INDEX idx_people_active
    ON people (active);
~~~

The index above may offer little help if 95% of users are active. If the application primarily searches active users alongside another condition, a composite index or partial index may be more appropriate, depending on the database and workload.

## 4. Composite Indexes for Multiple Conditions

When a query method filters on multiple columns, a composite index can serve the predicates together.

Example:

~~~java
List<Order> findByCustomerIdAndStatus(
    Long customerId,
    OrderStatus status
);
~~~

Corresponding query:

~~~sql
SELECT *
FROM orders
WHERE customer_id = ?
  AND status = ?;
~~~

A suitable index could be:

~~~sql
CREATE INDEX idx_orders_customer_status
    ON orders (customer_id, status);
~~~

Column order in a composite B-tree index matters. In many databases, an index is most effectively utilized when the query filters on leading columns of the index. Therefore, consider other queries that share the same prefix.

For example, the index:

~~~sql
CREATE INDEX idx_orders_customer_status_created
    ON orders (customer_id, status, created_at);
~~~

can support queries filtering by:

- `customer_id`.
- `customer_id` and `status`.
- `customer_id`, `status`, and a `created_at` range.

However, it is not the default optimal choice for a query filtering only by `status`, because `status` is not the leading column.

### Choosing Column Order

A common starting point is placing equality filter columns first in the index, then considering range and sort columns. Still, the final ordering must reflect the workload:

- Which columns frequently appear together?
- Are there queries using only a leading prefix?
- What are the value cardinalities and distributions?
- Does the query need range conditions or ordering?
- How can the database optimizer leverage the index?

Do not apply a mechanical column-ordering rule across all databases. Read execution plans and the index documentation for the database engine in use.

## 5. Combining Filters with ORDER BY

Spring Data REST lets clients request sorting via the `sort` query parameter when the repository and configuration allow it.

Example:

~~~http
GET /orders/search/findByStatus
    ?status=PAID
    &sort=createdAt,desc
    &page=0
    &size=20
~~~

Equivalent query:

~~~sql
SELECT *
FROM orders
WHERE status = ?
ORDER BY created_at DESC
LIMIT 20;
~~~

Index:

~~~sql
CREATE INDEX idx_orders_status_created_desc
    ON orders (status, created_at DESC);
~~~

can help the database locate rows with the matching status and read them in created_at order. Whether ASC/DESC direction is leveraged depends on the database, index structure, and query sort order.

If an endpoint frequently sorts by multiple columns, inspect the actual sort order. An index serving `ORDER BY created_at DESC` may not serve `ORDER BY total ASC, created_at DESC` well.

Include a deterministic secondary order, typically ID, when paginating across datasets with many duplicate sort values. Example:

~~~http
GET /orders?sort=createdAt,desc&sort=id,desc&page=0&size=20
~~~

The index can be aligned to that ordering if this query is an important workload.

## 6. Indexes for Range and Time-Based Queries

Derived queries can use comparison operators such as `After`, `Before`, `GreaterThan`, `LessThan`, and `Between`.

Example:

~~~java
List<Order> findByCreatedAtBetween(
    Instant start,
    Instant end
);
~~~

Query:

~~~sql
SELECT *
FROM orders
WHERE created_at BETWEEN ? AND ?;
~~~

A single index on `created_at` can support range scans:

~~~sql
CREATE INDEX idx_orders_created_at
    ON orders (created_at);
~~~

If the query also filters by status:

~~~sql
SELECT *
FROM orders
WHERE status = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC;
~~~

you can try a composite index:

~~~sql
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at DESC);
~~~

Using half-open intervals `[start, end)` is often convenient for contiguous time ranges, avoiding boundary overlap between consecutive days or windows.

Keep time zones and temporal types consistent between the application and the database. Indexes cannot fix timezone conversion bugs or semantically incorrect predicates.

## 7. Indexes for Associations and Foreign Keys

A query method can filter on properties of a related entity or traverse associations:

~~~java
List<Order> findByCustomerEmail(String email);
~~~

Depending on mappings, Spring Data may generate a join from orders to customers:

~~~sql
SELECT o.*
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.email = ?;
~~~

Indexes to consider:

~~~sql
CREATE INDEX idx_customers_email
    ON customers (email);

CREATE INDEX idx_orders_customer_id
    ON orders (customer_id);
~~~

An index on `customers.email` supports finding customers by email; an index on `orders.customer_id` can support joins and querying a customer's orders.

Many databases do not automatically create indexes for every foreign key. Check the actual schema and the conventions of the database you are using.

If email is business-unique, consider a unique constraint/index both to enforce uniqueness and to support lookups. Do not create a unique index if valid data can contain duplicate emails.

## 8. Indexes for Prefix, Substring, and Full-Text Queries

Not every string search uses a B-tree index the same way.

### Exact Match

~~~sql
WHERE email = ?
~~~

A B-tree index on email is usually appropriate.

### Prefix Search

~~~sql
WHERE last_name LIKE 'Ngu%'
~~~

Some databases and collations can leverage a B-tree index for prefix searches. This capability depends on collation, operator class, and database engine.

### Substring Search

~~~sql
WHERE description LIKE '%spring%'
~~~

A standard B-tree index is typically ineffective because the pattern starts with a wildcard. If substring searches are frequent, consider full-text indexes, trigram indexes, or an appropriate search engine.

### Full-Text Search

If an API needs to search words or phrases within long text, use the database's full-text capabilities instead of adding multiple B-tree indexes per string. For example, PostgreSQL can use tsvector and GIN indexes; MySQL has FULLTEXT indexes. Syntax and semantics vary by database.

Derived query methods such as `Containing`, `StartingWith`, or `EndingWith` can generate corresponding LIKE predicates. Inspect the generated SQL before choosing an index.

## 9. Pagination and Count Query Cost

When a search endpoint returns `Page<T>`, Spring Data typically executes a data query and may execute an additional count query to determine the total number of pages.

Example:

~~~java
Page<Order> findByStatus(
    OrderStatus status,
    Pageable pageable
);
~~~

Client:

~~~http
GET /orders/search/findByStatus?status=PAID&page=0&size=20
~~~

The database may need to execute both:

~~~sql
SELECT *
FROM orders
WHERE status = ?
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
~~~

and:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = ?;
~~~

An index suited to the predicate can assist both the data query and the count query, though counting is not always cheap on large tables.

Large OFFSET values can force the database to read and discard many rows before returning the next page. For workloads traversing deep into large datasets, consider keyset pagination or an appropriate cursor-based API. Spring Data REST and repository abstractions must be configured or extended accordingly; do not assume every endpoint supports cursor pagination by default.

## 10. Using JPA @Index and Database Migrations

JPA lets you describe indexes in entity mappings with `@Table(indexes = ...)`:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(
    name = "orders",
    indexes = {
        @Index(
            name = "idx_orders_status_created",
            columnList = "status, created_at"
        )
    }
)
public class Order {
    // fields
}
~~~

`columnList` must match database column names, not necessarily Java field names. If custom naming strategies, schema naming, or column mappings are used, verify the actual generated column names.

JPA annotations describe the schema for schema-generation tools when enabled. In production, it is generally better to manage indexes through controlled migrations such as Flyway or Liquibase so creating, altering, and rolling back indexes can be reviewed and deployed consistently.

SQL migration example:

~~~sql
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at DESC);
~~~

Do not rely on `ddl-auto=update` to manage all production index changes without verification. Confirm that migrations target the exact database engine and version in use.

## 11. Reading Execution Plans Before Adding Indexes

Never evaluate an index by its name or by guessing from the query method. Inspect how the database actually executes the query.

With PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE status = 'PAID'
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
~~~

With MySQL, use `EXPLAIN` or `EXPLAIN ANALYZE` depending on version support.

What to inspect:

- Whether a sequential scan/table scan or an index scan was chosen.
- Estimated row count versus actual row count.
- Number of rows the database had to read to return the requested rows.
- Whether sorting required an extra step or was satisfied by index order.
- Join strategies and indexes on join columns.
- Buffer/page reads and execution time.
- Discrepancies between estimated rows and actual rows.

Run plans against data and predicates representative of production. A query returning very few rows in development may get a completely different plan when the production table is much larger.

`EXPLAIN ANALYZE` actually executes the query. For queries with side effects or sensitive production systems, check safety and run in an appropriate environment.

## 12. Indexes Increase Write Cost and Storage Usage

Indexes speed up reads in certain workloads, but every index must also be updated when data changes.

Costs to weigh:

- INSERT must add entries to relevant indexes.
- UPDATE on indexed columns may have to update index entries.
- DELETE must remove corresponding entries.
- Indexes consume disk storage and cache memory.
- Many similar indexes increase maintenance overhead and may offer little real benefit.

Do not create duplicate composite indexes or single-column indexes already covered by another index unless the workload proves it necessary. Check index usage and query performance before keeping indexes long term.

On write-heavy tables, retain only indexes serving critical queries or required constraints.

## 13. Partial Indexes and Covering Indexes

Some databases support **partial indexes**, indexing only rows matching a condition. PostgreSQL example:

~~~sql
CREATE INDEX idx_orders_open_created
    ON orders (created_at DESC)
    WHERE status = 'OPEN';
~~~

This index can be smaller than a full-table index if only a fraction of rows have status OPEN and queries frequently target that subset. The query predicate must be compatible with the partial index condition for the optimizer to use it.

A **covering index** contains enough columns for a query so the database can satisfy part or all of the query from the index without reading table rows, depending on the engine.

For example, a query needing only id and created_at:

~~~sql
SELECT id, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Some databases allow declaring included columns:

~~~sql
CREATE INDEX idx_orders_status_created_cover
    ON orders (status, created_at DESC)
    INCLUDE (id);
~~~

INCLUDE syntax is not available in every database. Do not pack many columns into an index just to force a covering index; larger indexes increase storage and write overhead.

## 14. Controlling Which Sorts Clients May Request

Spring Data REST can let clients pick sorting via query parameters. If clients are permitted to sort by every property, the number of query combinations grows and effective indexing becomes difficult.

Example:

~~~http
GET /orders?sort=createdAt,desc&page=0&size=20
~~~

The application should define which sort orders are genuinely supported and needed. You can use repositories/services or custom controllers to constrain sorting per the API contract.

Do not create indexes for every arbitrary sort combination. Prioritize common, stable cases with meaningful performance impact.

For combined filtering and sorting, evaluate indexes against the entire query. An index covering only the sort column without supporting the predicate may still force the database to read many rows.

## 15. Index Design Workflow for Search Endpoints

1. List exported query methods and actual client requests.
2. Identify predicates, joins, sorts, pagination, and count queries.
3. Gather metrics on cardinality, data distribution, read frequency, and write rate.
4. Run execution plans on representative data.
5. Propose single-column or composite indexes based on query workload.
6. Verify column order, range predicates, sort order, and leftmost prefix usage.
7. Deploy indexes through reviewed migrations.
8. Re-measure execution plans, latency, and write cost after index creation.
9. Monitor index usage and remove redundant indexes in separate migrations when backed by evidence.
10. Verify pagination, association joins, and other query methods affected by the change.

## 16. Key Points to Remember

- Spring Data REST exposes query methods as search endpoints, but does not automatically create database indexes.
- Design indexes from actual SQL and workload: WHERE, JOIN, ORDER BY, pagination, and count.
- Column order in composite indexes matters; inspect query prefixes and real predicates.
- Equality filters are commonly considered before range/sort columns, though final choices must rest on execution plans.
- Indexing foreign keys and join columns can accelerate association queries.
- B-trees suit many exact-match and range queries; substring/full-text queries require other index mechanisms.
- Pagination can trigger count queries; large OFFSET values can be expensive.
- JPA @Index describes schema metadata, while migrations provide controlled production index changes.
- Indexes increase write cost and storage; avoid duplicate or unused indexes.
- Use EXPLAIN/EXPLAIN ANALYZE and real measurements to confirm benefits.

## References

- [Spring Data REST — Repository resources and query method resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Jakarta Persistence — @Index API](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/index)
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html)
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)
- [MySQL — Optimization and Indexes](https://dev.mysql.com/doc/refman/8.4/en/optimization-indexes.html)
