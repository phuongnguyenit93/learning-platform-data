# Reducing Round Trips, Repeated Queries, and the N+1 Pattern from Applications

An application may execute each individual SQL statement very quickly yet still have slow overall requests because it sends too many SQL statements over the network to Oracle. Every time an application sends a command and the database processes and returns results, there is overhead: network latency, protocol work, parse/execute/fetch, cursor management, and coordination between the application tier and database tier. When an application issues hundreds or thousands of small queries for a single screen, round-trip overhead can exceed the database's execution time for each statement.

The **N+1 query** pattern is a common culprit: the application runs one query to fetch N parent records, then runs another query for each parent record to fetch related data. A page showing 100 orders can generate 101 round trips even though the data could be fetched with one JOIN or a few batch queries.

This lesson focuses on identifying and reducing round trips in applications using Oracle Database:
- Understand round-trip cost and distinguish round trips from operations inside an execution plan.
- Identify N+1 patterns in code, ORMs, APIs, and SQL logs.
- Convert repeated queries into JOINs, EXISTS, aggregations, or set-based queries.
- Batch reads and writes, array binding, collection binding, and staging tables.
- Distinguish JDBC fetch size from solutions that actually eliminate N+1.
- Design pagination, caching, and data APIs appropriately.
- Measure execute, fetch, and parse counts, latency, and database work.
- Practice tuning an order screen with parent/child relationships.

Examples use Oracle Database 19c and Java/JDBC conceptually. Specific ORM API names vary by framework and version. The goal is reducing exchanges between the application and the database while preserving exact results, transaction semantics, and scalability.

## 1. What is a round trip?

A round trip is a single request/response exchange between the application and the database over a connection. With JDBC, a statement typically goes through sending an execute request, database processing, and returning status/results; queries returning many rows also require fetch calls to transfer rows to the client in chunks.

One round trip is not synonymous with one operation in an execution plan. A single SQL statement can execute many internal operations in the database while the application sends only one execute request. Conversely, a Java loop can send the exact same SELECT 500 times, creating many round trips even if each statement performs a tiny index lookup.

### 1.1. Components of latency

Total request time can be pictured as:

~~~text
Application request
    |
    | 1. Prepare SQL and bind values
    v
Network request --------------------+
    |                                |
    v                                |
Oracle parse / execute               |
    |                                |
    v                                |
Database work                        |
    |                                |
    v                                |
Network response <-------------------+
    |
    v
Application processes results
    |
    +-- May send the next query
~~~

User-perceived latency includes:
- Processing time in the application tier.
- Network wait time per exchange.
- Parse/execute time in Oracle.
- Block reads, joins, sorts, and SQL processing time.
- Time transferring result rows back to the client.
- ORM time mapping rows to objects and running application logic.

When round trips are numerous, network latency and coordination overhead accumulate. For example, illustratively, if each exchange averages 4 ms and the application performs 300 sequential round trips, round-trip waiting alone takes about 1.2 seconds, before counting database work and mapping. This calculation illustrates the cumulative effect, not an actual latency promise for every system.

### 1.2. Sequential vs. parallel round trips

If the application issues the second query only after receiving the first query's result, wait times add up sequentially. Running multiple queries in parallel can cut wall-clock time in some cases, but still consumes many database sessions/cursors, CPU, I/O, and connections; it does not eliminate N+1 overhead.

Do not fix N+1 by firing hundreds of concurrent queries. Reduce the number of SQL statements and fetch the needed dataset directly.

### 1.3. Parse, execute, and fetch

A SQL SELECT typically has these phases:
- Parse: Oracle analyzes syntax, checks objects/privileges, and finds or creates an appropriate cursor.
- Execute: runs the statement with bind values.
- Fetch: retrieves batches of result rows from the cursor to the application.

Prepared statements and cursor reuse can reduce parse overhead. Fetch size can reduce the number of fetch round trips for large result sets. However, neither technique turns 101 SELECT statements into one SELECT statement; they address different kinds of overhead.

## 2. The N+1 query pattern

N+1 happens when an application fetches a list of N entities, and then for each entity queries related data via a separate SQL statement.

### 2.1. Order and order lines example

Suppose we need to display a list of orders along with customer name and total line count.

Code prone to N+1:

~~~java
List<Order> orders = orderRepository.findRecentOrders();

for (Order order : orders) {
    Customer customer =
        customerRepository.findById(order.getCustomerId());

    List<OrderLine> lines =
        orderLineRepository.findByOrderId(order.getId());

    render(order, customer, lines);
}
~~~

If the list has 100 orders:
- 1 query fetches the orders.
- 100 queries fetch customers if not cached.
- 100 queries fetch order lines.

That can total 201 SQL statements. If each order only needs a line count or total amount, loading every OrderLine for each order also inflates transferred data and object allocations.

A variant that only fetches customer inside the loop issues 1 + N queries. That is the most common origin of the name N+1.

### 2.2. N+1 timeline

~~~text
List screen request
  |
  +-- Q1: SELECT 100 orders
  |
  +-- Q2: SELECT customer WHERE id = 1
  +-- Q3: SELECT customer WHERE id = 2
  +-- Q4: SELECT customer WHERE id = 3
  |      ...
  +-- Q101: SELECT customer WHERE id = 100
  |
  v
Render response
~~~

Even if each query takes only 1 ms on the database, sequential round trips costing a few milliseconds each still push total request time up sharply.

### 2.3. N+1 does not only live in for loops

N+1 can arise indirectly:
- An ORM lazy-loading a relationship when a getter is called.
- A JSON serializer accessing a lazy collection.
- A template engine calling getters for each row.
- A mapper or DTO assembler calling a repository inside a loop.
- A GraphQL resolver loading a relation separately per parent object.
- A service calling another API/database for every element of a list.
- A stored procedure calling a subroutine repeatedly, where each call executes its own SQL.

So scanning controllers for loops is not enough. Trace SQL generated during response serialization/rendering and association traversal.

### 2.4. N+1 vs. multiple operations inside one query

A single SQL statement with a HASH JOIN, TABLE ACCESS FULL, and SORT is still just one SQL statement sent by the application. Multiple internal operations can be far more efficient than hundreds of tiny round trips. Tuning must examine both execution plans and SQL call counts.

## 3. Identifying N+1 in applications

### 3.1. Counting executions per request

A strong indicator is the exact same SQL shape executing many times within one request, binding a different ID each time.

Example log:

~~~text
SELECT * FROM customers WHERE customer_id = :1
  bind :1 = 101
SELECT * FROM customers WHERE customer_id = :1
  bind :1 = 102
SELECT * FROM customers WHERE customer_id = :1
  bind :1 = 103
...
~~~

The SQL text is identical and only the bind value changes. PreparedStatement can reuse the cursor, yet every execute is still an exchange with the database.

### 3.2. Signs in APM and application tracing

In an HTTP request trace, look for:
- Number of JDBC/SQL spans.
- Duration of each database span.
- Same SQL fingerprint repeating.
- Bind keys changing sequentially.
- One parent query followed by N child queries.
- Database wait time dominating request duration.

Attach a request ID/correlation ID to logs to group SQL statements belonging to the same request. Oracle module/action tags can also categorize workload from the database side.

### 3.3. Signs in Oracle

`V$SQL` provides metrics such as `SQL_ID`, `EXECUTIONS`, `PARSE_CALLS`, `FETCHES`, `ROWS_PROCESSED`, `ELAPSED_TIME`, and `BUFFER_GETS`. Counters are typically cumulative per cursor in the shared pool, not automatically broken down by HTTP request. Combine `SQL_ID`, module/action, client identifier, timestamps, and tracing to attribute queries to specific requests.

Example finding frequently executed SQL:

~~~sql
SELECT
    sql_id,
    executions,
    parse_calls,
    fetches,
    rows_processed,
    elapsed_time,
    buffer_gets,
    module,
    action,
    SUBSTR(sql_text, 1, 1000) AS sql_text
FROM v$sql
WHERE executions > 100
ORDER BY executions DESC
FETCH FIRST 30 ROWS ONLY;
~~~

A SQL with high `EXECUTIONS` is not automatically N+1; it may be a legitimate query run across many independent requests. Compare against request counts, module/action, and SQL traces.

### 3.4. Counting SQL at the application tier

Use a datasource proxy, JDBC instrumentation, ORM statistics, or APM to count:
- Statement executions.
- Prepared statement calls.
- Result set fetches.
- Batch executions.
- Total database time.
- Rows returned.

Set budgets per endpoint. For example, a 20-order list endpoint should not jump from 5 queries to 45 queries just because 20 orders exist. Specific budgets must reflect endpoint design and workload.

## 4. Replacing N+1 with JOIN

When related data can be retrieved in a single SQL statement, JOIN is usually the first option.

### 4.1. Repeated queries

~~~sql
SELECT order_id, customer_id, order_date
FROM orders
WHERE order_date >= :p_from_date;
~~~

Then the application loops over each order and calls:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id = :p_customer_id;
~~~

### 4.2. JOIN in a single statement

~~~sql
SELECT
    o.order_id,
    o.order_date,
    o.status,
    c.customer_id,
    c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_date >= :p_from_date
ORDER BY o.order_date DESC, o.order_id DESC;
~~~

The application receives both order and customer in one result set. The database optimizes the join and runs internal operations without a round trip per customer.

### 4.3. When to use LEFT JOIN?

If an order may not have a customer attached or you want to keep orders even when no matching customer row exists, use LEFT JOIN:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name
FROM orders o
LEFT JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_date >= :p_from_date;
~~~

Misplacing a filter on the right-side table can accidentally turn LEFT JOIN into INNER JOIN. For example, `c.active_flag = 'Y'` in WHERE will eliminate rows without a customer. If you want to keep orders while joining only active customers, put the condition in ON or handle the logic accordingly.

### 4.4. JOIN can multiply rows

If an order has 5 order lines, joining `orders` with `order_lines` returns 5 rows for that order. That is the right relational result, though the application must group rows into an object graph if the API expects one order containing a list of lines.

Do not use DISTINCT to hide join row multiplication without understanding the relationship. DISTINCT can require sorting/hashing and discard genuinely distinct rows.

## 5. Replacing N+1 with aggregation

If a screen only needs line counts, total quantities, or total amounts, aggregate in the database instead of loading all child rows.

### 5.1. Scalar subquery aggregation

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM order_lines l
        WHERE l.order_id = o.order_id
    ) AS line_count,
    (
        SELECT SUM(l.quantity * l.unit_price)
        FROM order_lines l
        WHERE l.order_id = o.order_id
    ) AS order_total
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_date >= :p_from_date;
~~~

This is still one SQL statement sent by the application. The optimizer can transform subqueries or pick suitable access paths. Do not assume scalar subqueries always run independently once per row; inspect the plan and runtime statistics.

### 5.2. GROUP BY and JOIN

Another clear approach:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    NVL(x.line_count, 0) AS line_count,
    x.order_total
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
LEFT JOIN (
    SELECT
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity * unit_price) AS order_total
    FROM order_lines
    GROUP BY order_id
) x
  ON x.order_id = o.order_id
WHERE o.order_date >= :p_from_date;
~~~

The subquery aggregates child rows first and then joins the result with the parent. If only a small set of orders is of interest, consider limiting the parent before aggregating to avoid scanning too many child rows; optimizer and statistics decide the plan, so measure on real data.

### 5.3. EXISTS when only checking if a child row exists

No JOIN is needed if you only want to check for at least one detail row:

~~~sql
SELECT o.order_id, o.order_date
FROM orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.order_id
      AND l.quantity > 0
);
~~~

EXISTS expresses semi-join semantics cleanly: only match existence matters. JOIN can multiply parent rows when multiple child rows exist, forcing the application to use DISTINCT or GROUP BY.

## 6. Fetching object graphs in one or a few queries

A screen may need a list of parents along with child collections. Two common strategies exist: join fetch or batch fetch.

### 6.1. JOIN fetch

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    l.line_id,
    l.product_id,
    l.quantity,
    l.unit_price
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
LEFT JOIN order_lines l
  ON l.order_id = o.order_id
WHERE o.order_id IN (:order_ids)
ORDER BY o.order_id, l.line_id;
~~~

One query fetches all needed data. The application groups rows by `order_id` to assemble the object graph.

Pros:
- Few round trips.
- A single consistent statement snapshot under Oracle read consistency.
- Can leverage database joins and indexes.

Cons:
- Parent rows repeat per child row.
- Joining multiple to-many collections at once can cause Cartesian multiplication.
- Network result payload can become huge.
- Parent pagination is harder when joining directly to a collection.

### 6.2. Two batch queries

A balanced strategy is:
1. Fetch the parent and customer list in one query.
2. Fetch all child rows for that parent list in one query.

~~~sql
SELECT
    order_id,
    order_date,
    customer_id
FROM orders
WHERE order_date >= :p_from_date
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Then fetch lines for those 50 orders:

~~~sql
SELECT
    order_id,
    line_id,
    product_id,
    quantity,
    unit_price
FROM order_lines
WHERE order_id IN (
    :p_id_1, :p_id_2, :p_id_3
    -- bind the remaining IDs
)
ORDER BY order_id, line_id;
~~~

In practice, the application generates bind placeholders matching the batch ID count or uses collection/table-valued inputs. For very large lists, never concatenate literals into SQL; use collection binding, staging tables, or split into appropriate batches.

This keeps query count fixed by the number of association types rather than growing linearly with parent count. It also avoids massive row multiplication from joining multiple collections.

### 6.3. Grouping child rows in the application tier

After the second query, build a map from `order_id` to its list of lines:

~~~java
Map<Long, List<OrderLine>> linesByOrder = new HashMap<>();

for (OrderLine line : fetchedLines) {
    linesByOrder
        .computeIfAbsent(line.getOrderId(), key -> new ArrayList<>())
        .add(line);
}

for (Order order : orders) {
    order.setLines(
        linesByOrder.getOrDefault(order.getId(), List.of())
    );
}
~~~

This runs in memory with zero extra queries. Complexity is typically close to O(number of parents + number of child rows).

### 6.4. When to pick JOIN vs. batch?

| Need | Approach |
| --- | --- |
| Parent + one many-to-one relationship | JOIN |
| Parent + one small child collection | JOIN fetch or batch fetch |
| Parent + multiple to-many collections | Multiple batch queries usually prevent row explosion |
| Only need count/sum/exists | Aggregation or EXISTS |
| Paginated parent list | Page parents first, then batch fetch children |
| Details of a single parent | JOIN or one parent query + one child query depending on payload |

There is no rule that everything must always be crammed into one query. The goal is a reasonable round-trip count and minimal data transfer while keeping logic simple.

## 7. Batch fetching in ORMs

ORMs usually support lazy/eager loading and batch fetching. Configuration names vary across frameworks, but the core idea is grouping multiple foreign keys into a single query.

### 7.1. Lazy loading

Lazy loading loads an association only when code accesses it. It saves data when an association goes unused. However, when a loop accesses an association for each parent, lazy loading can trigger N+1.

~~~java
for (Order order : orders) {
    // May trigger a separate SELECT for each order.
    render(order.getCustomer().getName());
}
~~~

### 7.2. Eager loading

Eager loading requests fetching the association upfront. Depending on the ORM, the framework may use a JOIN or secondary queries. Eager does not guarantee a single SQL statement; inspect the actual SQL generated.

### 7.3. Batch loading

Batch loading collects unloaded entities/associations into one query using multiple IDs:

~~~sql
SELECT *
FROM customers
WHERE customer_id IN (:id1, :id2, :id3, ...);
~~~

If 100 orders reference 70 distinct customers, batch loading can fetch all 70 customers in one or a few queries instead of 70 separate queries.

### 7.4. Fetch join and pagination

Fetch joining a to-many collection causes a parent to appear in multiple rows. Applying OFFSET/FETCH or pagination directly to the joined result can limit SQL rows before the ORM reconstructs complete parent/child objects, or force the ORM to paginate in memory depending on the framework.

A safer strategy is usually:
1. Query the page of parent IDs with a deterministic ORDER BY.
2. Query parent/customer data for that page.
3. Query child rows using the set of parent IDs.
4. Assemble the object graph in the application.

### 7.5. Checking actual ORM SQL

Do not rely on annotation names like EAGER, LAZY, or FETCH to guess query counts. Enable SQL logging in dev/test, count statements per request, and check during response serialization as well. Pay special attention to N+1 triggered by getters or serializers.

## 8. Batch reads and large ID lists

A common way to eliminate N+1 is collecting IDs into a set and querying once. However, how that ID list is passed to Oracle should be chosen carefully.

### 8.1. IN lists with bind variables

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id IN (:id1, :id2, :id3);
~~~

Bind variables avoid literal concatenation and enable cursor reuse. In Oracle 19c, an IN list expression has an expression count limit (commonly hitting ORA-01795 above 1000). For large lists, split into batches or use collections/staging tables.

Avoid generating distinct SQL text for every value by binding; note that varying placeholder counts can still produce distinct SQL text across different batch sizes.

### 8.2. Splitting into batches

If 5,000 IDs must be fetched, split into appropriate chunks, e.g., a few hundred IDs per batch. Round trips become the number of batches rather than the number of parents. Batch sizing should consider:
- IN list limits.
- Bind and payload size.
- PGA/SQL memory.
- Result row count.
- Network packets and latency.
- Cursor/transaction hold duration.

There is no single optimal batch size for all applications. Measure and pick based on real sizes.

### 8.3. Global temporary tables

When an ID set is large or reused across multiple SQL statements, load the IDs into a global temporary table (GTT) and join:

~~~sql
CREATE GLOBAL TEMPORARY TABLE request_order_ids (
    order_id NUMBER PRIMARY KEY
) ON COMMIT DELETE ROWS;
~~~

Load IDs via batch insert, then query:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    l.line_id,
    l.quantity
FROM request_order_ids r
JOIN orders o
  ON o.order_id = r.order_id
LEFT JOIN order_lines l
  ON l.order_id = o.order_id;
~~~

A GTT stores its definition permanently while data is temporary per session or transaction depending on `ON COMMIT DELETE ROWS`/`PRESERVE ROWS`. With connection pools, understand session affinity and cleanup to avoid reading stale data left in the same session.

### 8.4. SQL collections and TABLE()

You can define a SQL collection type and bind a collection to join as a row source. SQL-level type example:

~~~sql
CREATE TYPE number_list_t AS TABLE OF NUMBER;
/
~~~

Query:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN TABLE(:p_customer_ids) ids
  ON ids.COLUMN_VALUE = c.customer_id;
~~~

How collections are bound depends on the Oracle JDBC driver and created SQL type. In Oracle JDBC, Oracle-specific APIs like `createOracleArray` are typically used with the SQL type name; check driver documentation for your release. Do not confuse PL/SQL associative arrays with SQL nested table types usable directly in SQL.

### 8.5. JSON_TABLE for JSON inputs

If an API already receives an ID list as JSON and needs to turn it into SQL rows, `JSON_TABLE` can project an array as a row source:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN JSON_TABLE(
    :p_ids_json,
    '$[*]'
    COLUMNS (
        customer_id NUMBER PATH '$'
    )
) ids
  ON ids.customer_id = c.customer_id;
~~~

This is an option when the input is already JSON. Validate the JSON and bound the element count. Do not choose JSON merely because it works; a SQL collection or GTT may fit better when internal data is already an ID list.

## 9. Reducing round trips when writing data

N+1 also appears in writes: the application inserts/updates rows one by one in a loop, executing a separate statement on each iteration.

### 9.1. Many single-row executes

~~~java
for (OrderLine line : lines) {
    try (PreparedStatement ps = connection.prepareStatement(
            "insert into order_lines(order_id, product_id, quantity) values (?, ?, ?)")) {
        ps.setLong(1, line.getOrderId());
        ps.setLong(2, line.getProductId());
        ps.setInt(3, line.getQuantity());
        ps.executeUpdate();
    }
}
~~~

With 1,000 lines, the application may perform 1,000 executes and multiple parses/round trips. Creating and closing PreparedStatement inside the loop also adds statement-management overhead.

### 9.2. Reusing PreparedStatement and JDBC batching

~~~java
String sql =
    "insert into order_lines(order_id, product_id, quantity) values (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderLine line : lines) {
        ps.setLong(1, line.getOrderId());
        ps.setLong(2, line.getProductId());
        ps.setInt(3, line.getQuantity());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

JDBC batching allows the driver to send multiple DML operations together rather than executing each statement independently. The driver may chunk batches or use array binding depending on statement type, driver, and configuration; do not assume a single `executeBatch` always equals one network packet/round trip.

### 9.3. Batch size

You do not have to push millions of rows into one batch. Chunking helps:
- Keep application memory bounded.
- Reduce how long a batch holds transactions/locks.
- Make retrying failed chunks easier.
- Avoid oversized payloads.
- Commit in well-defined business units.

Batch size must match transaction semantics. If the entire import must be atomic, do not commit per chunk arbitrarily; if each chunk is an independent unit, design explicit idempotency and restartability.

### 9.4. Array binding and bulk DML

Oracle JDBC can optimize batch DML via array binding. PL/SQL offers `FORALL` for bulk DML over collections inside the database. Both cut overhead compared to calling a procedure or executing one row at a time.

If the application can pass a dataset to a stored procedure and the procedure uses `FORALL`, round trips can drop from many calls to one call plus in-database bulk processing. Still, manage SQL collection types, payload size, exceptions, and transaction boundaries carefully.

### 9.5. Set-based DML is often better than batching

When every row undergoes the same transformation, a single UPDATE can replace a batch:

~~~sql
UPDATE order_lines
SET status = 'ARCHIVED'
WHERE order_date < :p_cutoff;
~~~

When updating from a staging table:

~~~sql
MERGE INTO inventory target
USING inventory_stage source
ON (target.product_id = source.product_id)
WHEN MATCHED THEN
    UPDATE SET target.quantity = source.quantity
WHEN NOT MATCHED THEN
    INSERT (product_id, quantity)
    VALUES (source.product_id, source.quantity);
~~~

Set-based DML lets the optimizer inspect the full dataset and choose an appropriate plan. Use batching when each row carries distinct inputs or the operation cannot be expressed cleanly as a set-based SQL statement.

## 10. Fetch size and large result sets

Fetch size is the number of rows the driver tries to retrieve per fetch from the database. It can reduce fetch round trips when result sets are large.

### 10.1. JDBC setFetchSize

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "select order_id, order_date from orders order by order_id")) {

    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            process(rs.getLong("ORDER_ID"), rs.getDate("ORDER_DATE"));
        }
    }
}
~~~

A fetch size of 500 hints to the driver to retrieve rows in batches of around 500. Exact behavior depends on the driver and result set type.

### 10.2. Fetch size does not cure N+1

If the application still runs 100 customer SELECTs per order, `setFetchSize` does not merge them into one query. It only governs how rows are fetched from each result set. N+1 must be solved with JOINs, batch loading, collection inputs, or appropriate caching.

### 10.3. Excessively large fetch size

A huge fetch size can:
- Reduce fetch counts.
- Increase client memory usage.
- Cause the application to pull more data than needed.
- Increase latency before processing begins on a large batch.
- Create GC or memory pressure in the application.

Choose fetch size based on row width, row count, memory budget, and how the application consumes rows. Do not set an enormous value globally for all queries.

### 10.4. Streaming and row-by-row processing

If exporting large datasets, stream rows so the entire result set is not materialized in memory. Ensure `ResultSet`, `Statement`, and `Connection` are properly closed across their lifecycles; do not keep cursors open longer than necessary.

## 11. Pagination to avoid over-fetching

One reason applications emit many queries is APIs lacking clear pagination, forcing clients to make many small calls or load everything at once.

### 11.1. OFFSET/FETCH

~~~sql
SELECT order_id, order_date, status
FROM orders
ORDER BY order_date DESC, order_id DESC
OFFSET :p_offset ROWS
FETCH NEXT :p_page_size ROWS ONLY;
~~~

OFFSET/FETCH is simple for pagination. However, at large offsets, Oracle may have to read and discard many rows before returning the page. `ORDER BY` must specify a deterministic order, usually adding the primary key as a tie-breaker.

### 11.2. Keyset pagination

For data sorted descending by `order_date` and `order_id`, use keyset pagination:

~~~sql
SELECT order_id, order_date, status
FROM orders
WHERE order_date < :p_last_order_date
   OR (
       order_date = :p_last_order_date
       AND order_id < :p_last_order_id
   )
ORDER BY order_date DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

The next request passes the last row's values from the previous page as a cursor. Keyset pagination is typically more efficient for deep pages when an appropriate index exists and avoids large OFFSET overhead.

### 11.3. Page parents first, load children after

If a screen needs order lines, paginate the parent orders first, then fetch child rows for those page IDs in a batch query. Do not join all child rows and paginate over the multiplied result if the goal is parent-level pagination.

## 12. Caching and reducing repeated queries

Caching can eliminate repeated queries for infrequently changing data, but requires clear invalidation and consistency policies.

### 12.1. Request-scoped cache

Within a single request, if multiple orders share the same `customer_id`, keep loaded customers in a Map so the same customer is not queried repeatedly. This is a simple fix for duplicate lookups, though it does not replace batch loading when every order belongs to a different customer.

### 12.2. Application cache

Caching can fit:
- Product catalogs.
- Country/province codes.
- Infrequently changing configuration.
- Shared metadata.

Do not arbitrarily cache balances, inventory, or transaction statuses needing strong consistency. Define TTL, invalidation, versioning, and data authorization.

### 12.3. Oracle result cache

Oracle provides SQL query result cache and PL/SQL function result cache for suitable scenarios. Result cache stores results for reuse when dependencies remain unchanged per cache rules. It is not a universal cache for every query and does not replace batch/join design.

Inspect the execution plan and notes to see whether result cache is used. Evaluate invalidation, memory, and data suitability before enabling.

### 12.4. Caching does not fix structural N+1

If cache hits occur for some IDs, query count may drop. Yet whenever per-entity cache misses occur, N+1 persists. Fix the query structure first; use caching as a complementary layer for data with matching semantics.

## 13. Designing APIs to reduce chattiness

Round trips do not only happen between an application and Oracle. One service may call another service repeatedly per item, causing that downstream service to hit the database repeatedly.

### 13.1. Set-based APIs

Replace APIs like:

~~~text
GET /customers/101
GET /customers/102
GET /customers/103
~~~

with a batch API:

~~~text
POST /customers:batchGet
{
  "ids": [101, 102, 103]
}
~~~

The service receives a list of IDs, queries once or in a few batches, and returns a map of results. This cuts chattiness between services and between services and the database.

### 13.2. Screen-specific DTO/projection

Do not load an entire entity graph if the screen only needs order ID, date, customer name, and total. Build a projection/DTO with just the required columns:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    SUM(l.quantity * l.unit_price) AS total_amount
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
LEFT JOIN order_lines l
  ON l.order_id = o.order_id
WHERE o.order_date >= :p_from_date
GROUP BY
    o.order_id,
    o.order_date,
    c.customer_name;
~~~

DTOs reduce data transfer, mapping overhead, and unnecessary association loading. Ensure aggregates behave accurately when an order has no lines.

### 13.3. GraphQL DataLoader pattern

In GraphQL, resolvers can trigger N+1 when each parent resolver loads a relation individually. The DataLoader pattern collects keys within an execution window, invokes a batch loader, and maps results back to the corresponding keys.

Batch loaders must preserve stable key/result mapping and handle missing keys. DataLoader caches are usually request-scoped to prevent data leaks across users or tenants.

## 14. Stored procedures and database API boundaries

Some workloads can cut round trips by sending one PL/SQL call instead of multiple separate SQL statements:

~~~sql
BEGIN
    order_api.create_order(
        p_customer_id => :p_customer_id,
        p_items_json  => :p_items_json,
        p_order_id    => :p_order_id
    );
END;
/
~~~

The procedure can validate input, insert header and lines with `FORALL`, and return the order ID. The application makes a single database API call for the entire operation.

### 14.1. Benefits
- Reduces application-to-database call count.
- Keeps data-intensive logic close to the database.
- Leverages `FORALL`/set-based SQL.
- Can reduce back-and-forth payloads.
- Establishes clear transaction boundaries when contracts are well designed.

### 14.2. Trade-offs
- Business logic may split between Java and PL/SQL.
- Package versioning and deployment require coordination.
- Testing and observability require appropriate tooling.
- Overly generic procedures can be hard to tune.
- Do not push all business logic into the database just to save a couple of round trips.

Choose stored APIs when data operations are atomic, DML volume is large, or a stable contract is needed. Clarify who owns COMMIT/ROLLBACK: typically the application/service manages transactions, and procedures do not self-commit unless explicitly required by contract.

## 15. Transaction consistency when combining queries

Reducing round trips by replacing multiple queries with one query can change snapshot semantics.

Oracle provides statement-level read consistency under READ COMMITTED: each SELECT sees data committed as of the moment that statement began. If an application runs 100 separate queries, those queries can see snapshots from different points in time if other transactions commit in between.

A single JOIN reads all tables in the same statement snapshot, usually giving a more consistent view across parent and child as of statement start.

With two batch queries (parent then child), under READ COMMITTED the two statements can see different snapshots. In some workflows, a parent might change or child rows might be added/deleted between the two queries. If cross-statement consistency is required, consider an appropriate transaction/isolation level such as SERIALIZABLE or a read-only transaction, while accounting for overhead, retries, and `ORA-08177` that can arise in SERIALIZABLE.

Do not enable SERIALIZABLE merely to fix N+1. Optimize query count first, then choose the consistency model required by business rules.

## 16. Anti-patterns to avoid

### 16.1. Querying inside getters

A getter like `getCustomerName()` should not silently query the database. It obscures data-access cost and lets serializers trigger N+1.

### 16.2. Repository calls inside loops

Do not call `findById` or `findChildren` inside a loop when batching is possible. If each iteration needs distinct criteria, gather the keys first and load them as a set.

### 16.3. Creating a new PreparedStatement per row

Reuse statements and use JDBC batching. PreparedStatement caching reduces parse overhead but does not replace batch execution.

### 16.4. SELECT * for large object graphs

Select only required columns. `SELECT *` inflates bytes, network transfer, and mapping cost, especially with CLOB/BLOB columns.

### 16.5. Joining every to-many collection

Joining multiple independent collections multiplies rows by the product of their sizes. For example, an order with 4 lines and 3 payments yields 12 rows for the same order. Use separate batch queries per collection or aggregate before joining.

### 16.6. Building IN lists by string concatenation

Never concatenate IDs into SQL text. Use bind variables, collection binding, or staging tables. Concatenating literals creates varying SQL text, defeats cursor reuse, and opens SQL injection risks.

### 16.7. Unbounded parallelization of N+1

Spawning many futures/threads to fire hundreds of queries concurrently can exhaust pools, spike concurrent sessions, and overload Oracle. Batch and use set-based SQL first; if parallelism is still needed, bound concurrency explicitly.

### 16.8. Caching transactional data without invalidation

Stale caches can serve wrong balances or inventory. Define consistency contracts before caching and never treat caches as a substitute for transactions.

## 17. Measuring before and after tuning

Do not just count queries. Measure round trips, data transferred, database work, and request latency.

### 17.1. Application-tier metrics

- SQL execute count per request.
- Driver prepare/parse count.
- Fetch count and fetched row count.
- Total database span duration.
- Request p50/p95/p99.
- Bytes sent/received if instrumentation supports it.
- Borrowed connection count and pool wait time.
- Duplicate queries grouped by fingerprint.

### 17.2. Oracle-side metrics

`V$SQL` provides cumulative per-cursor counters:

~~~sql
SELECT
    sql_id,
    executions,
    parse_calls,
    fetches,
    rows_processed,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads,
    module,
    action
FROM v$sql
WHERE parsing_schema_name = 'APP'
ORDER BY elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Counters are totals per cursor in the shared pool since load/reset; they do not map directly to a single HTTP request. Dividing `elapsed_time` by `executions` only gives an approximate average and can be skewed by executions of varying sizes.

### 17.3. Setting module/action

Applications can set session module/action so DBAs can classify SQL:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'OrderService',
        action_name => 'ListOrders'
    );
END;
/
~~~

With connection pools, reset module/action when returning connections to the pool or starting a new request. Otherwise, subsequent SQL can be misattributed to the prior request's module/action.

### 17.4. SQL trace and TKPROF

SQL trace records parse, execute, fetch, waits, and session statistics. TKPROF formats traces for analysis:
- Parse/execute/fetch counts.
- CPU and elapsed time.
- Logical/physical reads.
- Rows processed.
- Wait events.

DBAs can enable tracing by session/module/service via `DBMS_MONITOR` per privileges. Traces can contain sensitive SQL text and bind values; protect trace files and keep tracing enabled only as long as needed.

### 17.5. Comparing equivalent workloads

Before/after comparisons must use the same:
- Dataset and data state.
- Bind values or representative bind distribution.
- Request volume/concurrency.
- Documented warm/cold cache conditions.
- Transaction boundaries.
- Environment and execution plans.

An optimization that cuts query count yet returns 100x more data may not improve latency. Compare total bytes, CPU, buffers, p95, and concurrent load.

## 18. Lab: fixing N+1 for an order screen

The lab creates three small tables and sample data to compare query strategies.

### 18.1. Create tables

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);

CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR2(20),
    CONSTRAINT lab_orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers(customer_id)
);

CREATE TABLE lab_order_lines (
    line_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    product_name VARCHAR2(100),
    quantity NUMBER NOT NULL,
    unit_price NUMBER(12, 2) NOT NULL,
    CONSTRAINT lab_lines_order_fk
        FOREIGN KEY (order_id)
        REFERENCES lab_orders(order_id)
);

CREATE INDEX lab_orders_customer_ix
ON lab_orders(customer_id);

CREATE INDEX lab_lines_order_ix
ON lab_order_lines(order_id);
~~~

### 18.2. Load sample data

~~~sql
BEGIN
    FOR i IN 1 .. 20 LOOP
        INSERT INTO lab_customers(customer_id, customer_name)
        VALUES (i, 'Customer ' || i);
    END LOOP;

    FOR i IN 1 .. 100 LOOP
        INSERT INTO lab_orders(
            order_id,
            customer_id,
            order_date,
            status
        )
        VALUES (
            i,
            MOD(i - 1, 20) + 1,
            DATE '2025-01-01' + MOD(i, 30),
            CASE WHEN MOD(i, 3) = 0 THEN 'PAID' ELSE 'OPEN' END
        );

        FOR j IN 1 .. MOD(i, 4) + 1 LOOP
            INSERT INTO lab_order_lines(
                line_id,
                order_id,
                product_name,
                quantity,
                unit_price
            )
            VALUES (
                i * 10 + j,
                i,
                'Product ' || j,
                j,
                100 + j * 10
            );
        END LOOP;
    END LOOP;

    COMMIT;
END;
/
~~~

### 18.3. Simulate N+1

Parent query:

~~~sql
SELECT order_id, customer_id, order_date, status
FROM lab_orders
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

For each order, the application runs:

~~~sql
SELECT customer_id, customer_name
FROM lab_customers
WHERE customer_id = :p_customer_id;
~~~

If also fetching lines, each order triggers:

~~~sql
SELECT line_id, product_name, quantity, unit_price
FROM lab_order_lines
WHERE order_id = :p_order_id;
~~~

Count actual SQL statements in the application. This yields 1 + 20 or 1 + 20 + 20 queries depending on association loading.

### 18.4. Optimize with JOIN and aggregation

~~~sql
SELECT
    o.order_id,
    o.order_date,
    o.status,
    c.customer_name,
    COUNT(l.line_id) AS line_count,
    NVL(SUM(l.quantity * l.unit_price), 0) AS order_total
FROM (
    SELECT order_id, customer_id, order_date, status
    FROM lab_orders
    ORDER BY order_date DESC, order_id DESC
    FETCH FIRST 20 ROWS ONLY
) o
JOIN lab_customers c
  ON c.customer_id = o.customer_id
LEFT JOIN lab_order_lines l
  ON l.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_date,
    o.status,
    c.customer_name
ORDER BY o.order_date DESC, o.order_id DESC;
~~~

Parents are limited first, then joined to customer/lines and aggregated. The application needs only one query to render the summary list. If full line details are required, use one additional batch query for the 20 order IDs.

### 18.5. Optimize with two batch queries

Query 1:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.status,
    c.customer_name
FROM (
    SELECT order_id, customer_id, order_date, status
    FROM lab_orders
    ORDER BY order_date DESC, order_id DESC
    FETCH FIRST 20 ROWS ONLY
) o
JOIN lab_customers c
  ON c.customer_id = o.customer_id
ORDER BY o.order_date DESC, o.order_id DESC;
~~~

Query 2: fetch lines for the page's order IDs. For small ID counts, bind placeholders; for large ID counts, consider SQL collections or GTTs.

~~~sql
SELECT
    order_id,
    line_id,
    product_name,
    quantity,
    unit_price
FROM lab_order_lines
WHERE order_id IN (
    :id1, :id2, :id3
    -- bind the remaining IDs for the page
)
ORDER BY order_id, line_id;
~~~

The application groups lines by `order_id`. Query count stays at two for the whole page instead of scaling with order count.

### 18.6. Measure and compare

Record:
- Query/execute count per request.
- Total database span duration.
- Total rows returned.
- Bytes transferred if available.
- Request elapsed time.
- Buffers/Reads and execution plans of batch queries.

Expected outcome is a sharp drop in query count. However, JOIN can return more rows if loading child collections; pick summary aggregation or batch detail based on the payload actually needed.

## 19. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Screen slow even though each SQL is fast | N+1 or many sequential round trips | Count SQL per request, batch or JOIN |
| Increased fetch size yet still many SQLs | Fetch size only tunes result set fetching | Fix the N+1 query structure |
| Eager loading still emits many queries | ORM uses secondary selects | Enable SQL logging, batch fetch, or projections |
| JOIN duplicates parent rows | One-to-many relationship produces multiple rows | Group/aggregate or batch fetch |
| Joining multiple collections causes row explosion | Cartesian product of to-many relations | Split batch queries per collection |
| Huge IN list fails with ORA-01795 | Exceeds IN list expression limit | Split batches, collection binding, or GTT |
| Batch insert still slow | Batch too large/small, indexes/triggers, or commit frequency | Tune batch size and use set-based DML if possible |
| PreparedStatement still N+1 | Reuse cuts parse, does not remove repeated executes | Batch IDs or combine into one query |
| Parallelizing queries overloads DB | Unbounded concurrency | Cut query count and bound workers |
| Pagination missing child rows | Paginating directly over to-many JOIN | Page parent IDs first, fetch children afterward |
| Cache returns stale data | Improper invalidation/TTL | Define consistency contract |
| Batch query reads too much | Overly wide ID batch or projection | Bound ID set and select needed columns |
| Combining queries alters consistency | Separate statements previously saw different snapshots | Choose transaction/isolation per business rules |
| High V$SQL executions mistaken for N+1 | Counter accumulates across many requests | Correlate with tracing and module/action |
| Stored procedure still incurs many round trips | Procedure queries over DB link or client loops | Measure full call chain and design batch API |

## 20. Design checklist

Before releasing a data read/write endpoint:

1. Count SQL executions for a representative-sized request.
2. Look for repeating query fingerprints with varying ID binds.
3. Verify lazy associations are not triggered inside loops/serializers.
4. Choose JOIN when related data is needed together and row counts are reasonable.
5. Choose EXISTS/aggregation when only boolean/count/sum is needed.
6. Choose batch fetching when multiple to-many collections exist.
7. Paginate parents before fetching child rows.
8. Use bind variables, collection inputs, or GTTs for ID lists.
9. Use JDBC batching/array binding for repeated DML.
10. Use fetch size to tune large result set fetching, not as an N+1 cure.
11. Bound concurrency and batch sizes.
12. Define transaction consistency when splitting across multiple queries.
13. Measure query count, bytes, buffers, latency, and p95 before/after.
14. Check connection pooling and reset module/action when using pools.
15. Evaluate caches for consistency and invalidation.
16. Verify privileges, SQL trace, and sensitive data handling before enabling instrumentation.

## 21. Practice exercises

Use `LAB_CUSTOMERS`, `LAB_ORDERS`, and `LAB_ORDER_LINES` from section 18.

### Exercise 1 — Count N+1

Write a program that fetches 20 orders and queries customer for each order. Count total executions. Try adding the lines query and record the new query count.

### Exercise 2 — JOIN

Replace the repeated customer queries with a JOIN. Compare query count, rows returned, and request duration.

### Exercise 3 — Aggregation

Write one query returning `line_count` and `order_total` per order. Compare with loading all lines and summing in Java.

### Exercise 4 — Batch fetch

Fetch 20 orders in the first query and all lines in the second query. Group lines by `order_id` in Java. Confirm query count does not grow with order count.

### Exercise 5 — Pagination

Build two pages with OFFSET/FETCH, then switch to keyset pagination. Verify deterministic ordering when multiple orders share the same `order_date`.

### Exercise 6 — JDBC batch

Insert many order lines using single-row `executeUpdate`, then using `addBatch`/`executeBatch`. Compare execution counts, timing, and transaction behavior.

### Exercise 7 — Fetch size

Query a large row set and test fetch sizes 50, 200, and 500. Observe timing, memory, and fetch counts if driver instrumentation supports it. Explain why this does not solve N+1 queries.

### Exercise 8 — GTT or collection binding

Create a large set of order IDs, load them into a GTT or SQL collection, and JOIN to fetch data. Compare against an IN list with many bind placeholders.

### Exercise 9 — Transaction consistency

Across two sessions, run two parent/child batch queries while the other session modifies data. Observe READ COMMITTED behavior and evaluate whether another transaction/isolation level is needed for the screen's requirements.

### Exercise 10 — Instrumentation

Tag MODULE/ACTION for the lab endpoint. Use `V$SQL` or tracing to count executes/fetches. Write a before/after report including query count, rows, buffers, and p95 latency.

## 22. Cleaning up lab data

Run only in the lab schema you created, after completing the exercises:

~~~sql
DROP TABLE lab_order_lines PURGE;
DROP TABLE lab_orders PURGE;
DROP TABLE lab_customers PURGE;
~~~

If you created additional GTTs, SQL collection types, or other objects during the exercises, drop only your lab objects. Never drop business objects or shared tables.

## Summary

N+1 arises when an application fetches a set of parents and then queries related data separately for each parent. The cost lies not only in SQL execution but also in network round trips, parse/execute/fetch, ORM mapping, and sequential waits. Reusing PreparedStatement reduces parse overhead; fetch size reduces fetch round trips for large result sets; neither eliminates N+1.

Prefer set-based SQL, JOIN, EXISTS, and aggregation where appropriate. For object graphs with multiple to-many collections, paginate parents first and batch-fetch each collection using an ID set, SQL collection, or GTT. For repeated DML, use JDBC batching/array binding or PL/SQL `FORALL`; if an operation can be expressed as a single set-based UPDATE/MERGE, evaluate that first. Tune batch size, fetch size, pagination, and caching to the actual workload.

Reducing query counts must go hand in hand with controlling transferred data volume, transaction consistency, connection pooling, and runtime plans. Use application tracing, SQL fingerprints, module/action, `V$SQL`, and SQL trace to measure before and after. A good optimization cuts round trips while still returning exact data, preserving transaction semantics, and improving latency under real concurrency.

## Oracle and JDBC references

- [Oracle Database JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC statements, result sets, batching, and LOB/array APIs.
- [Oracle Database JDBC Developer's Guide — Performance Extensions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/performance-extensions.html) — statement caching, batching, and fetch behavior.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — optimizer, execution plans, and SQL performance.
- [Oracle Database PL/SQL Language Reference — FORALL Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/FORALL-statement.html) — bulk DML in PL/SQL.
- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — joins, subqueries, row limiting, and query syntax.
- [Oracle Database SQL Language Reference — CREATE TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html) — global temporary tables.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html) — tagging session module/action.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_MONITOR (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_MONITOR.html) — SQL trace by session, client identifier, service, and module.
- [Oracle Database Reference — V$SQL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html) — executions, fetches, elapsed time, and buffer gets.

When deploying on an Oracle release or JDBC driver other than 19c, check the exact version's driver documentation, especially regarding batch execution, array binding, collection binding, fetch size, and SQL/IN list limits.
