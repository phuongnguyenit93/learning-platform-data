# Identifying and Resolving N+1 Queries

In Spring Data Relational R2DBC applications, an N+1 query issue occurs when the application fetches a set of parent records in one SQL query, and then executes one additional SQL query per parent record to fetch related data. Given N parent records, the total number of queries is typically 1 + N.

For example, an application fetches a list of 100 customers and then queries orders for each customer one by one. The database receives one `SELECT` for customers and 100 more `SELECT`s for orders. Even though operations are written with `Mono` or `Flux` and do not block threads under R2DBC, the number of database round trips is still 101.

**Reactive programming does not automatically eliminate N+1.** R2DBC organizes I/O in a non-blocking model, whereas N+1 is a problem of query count and round trips. Fixing it requires changing how data is fetched: `JOIN`s and projections, `IN` batch queries, aggregate queries, or dedicated read models.

## 1. What Is N+1?

N+1 is a query pattern consisting of:

1. One query fetching N root records, commonly called parent records.
2. Each parent record triggering one extra query to fetch related data.

For example, given `customer` and `purchase_order` tables:

~~~sql
SELECT id, name
FROM customer
WHERE active = true;
~~~

Then, for each customer, the application runs:

~~~sql
SELECT id, customer_id, total
FROM purchase_order
WHERE customer_id = :customerId;
~~~

If the first query returns 100 customers, the second `SELECT` runs 100 times.

| Component | Query Count |
|---|---:|
| Fetch customer list | 1 |
| Fetch purchase_order for each customer | N |
| Total | 1 + N |

With N = 100, total queries equal 101. If N grows to 1,000, query count rises to 1,001 even though the screen only displays one list.

The name N+1 describes query count scaling with the number of parent records. It is not a SQL syntax error or a bug specific to R2DBC; it is a data access flow design issue.

## 2. How Does N+1 Arise in R2DBC?

In Spring Data R2DBC, N+1 typically happens when a service calls a repository inside a reactive operator per element:

~~~java
public Flux<CustomerWithOrders> findCustomersWithOrders() {
    return customerRepository.findByActiveTrue()
        .flatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerWithOrders(customer, orders)
                )
        );
}
~~~

Execution flow:

1. `findByActiveTrue()` emits customers.
2. For each customer, `flatMap` calls `findByCustomerId()`.
3. Each repository call triggers a query fetching orders.
4. Order results are collected into a list and paired with the customer.

If the first query returns N customers, the child query is invoked N times. Query count is 1 + N.

Replacing `flatMap` with `concatMap` does not solve N+1:

~~~java
return customerRepository.findByActiveTrue()
    .concatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders ->
                new CustomerWithOrders(customer, orders)
            )
    );
~~~

`concatMap` runs child queries sequentially in element order. It lowers concurrency and preserves order, but still fires one query per customer. `flatMap` can run multiple child queries concurrently, yet the query count remains N.

## 3. Why Does N+1 Cause Problems?

Every database query incurs fixed overhead beyond SQL execution time:

- Sending the request over a connection.
- Database parsing and planning the statement.
- Executing and reading results.
- Transmitting data back to the application.
- Driver decoding results and emitting rows into the reactive pipeline.

As round trips increase, this fixed overhead repeats many times. Even if each SQL query runs fast, total latency can become large.

Illustrative table:

| Customers | Parent Queries | Child Queries | Total Queries |
|---:|---:|---:|---:|
| 10 | 1 | 10 | 11 |
| 100 | 1 | 100 | 101 |
| 500 | 1 | 500 | 501 |
| 1,000 | 1 | 1,000 | 1,001 |

Actual timings also depend on connection pools, network latency, database load, indexes, and result sizes. However, query count growing linearly with parent count is a clear warning sign to investigate.

### Reactive Does Not Erase Round-Trip Overhead

R2DBC prevents threads from blocking on I/O the way JDBC does. While the database works, the event loop can serve other tasks. Yet the database still has to receive each statement and return each result.

N+1 in a reactive pipeline can:

- Increase total request completion time.
- Increase connection acquisitions or connection usage.
- Generate many statements and reactive signals.
- Increase processing load on the database.
- Keep pool connections busy longer under concurrent queries.
- Create heavy pressure as the number of customers in results grows.

If `flatMap` runs many queries concurrently, peak load on the database can spike sharply. If `concatMap` runs sequentially, completion latency can grow from waiting on each query in turn.

## 4. Distinguishing N+1 from a Multi-Row Query

Having many rows or multiple SQL statements is not automatically N+1.

- One `JOIN` query returning 1,000 rows is still a single query.
- Two fixed queries—one fetching customers and one batch-fetching all orders—remain two queries even with hundreds of customers.
- One query per customer is the N+1 pattern.
- Multiple independent queries for distinct business steps are not necessarily N+1.

What matters is whether query execution count scales with the number of items in the parent set.

## 5. How N+1 in R2DBC Differs from ORM Lazy Loading

In JPA/Hibernate, N+1 is often encountered when loading a list of entities and then accessing a lazy relationship. The ORM may emit an extra `SELECT` per entity when the association is accessed.

Spring Data Relational and Spring Data R2DBC do not provide a persistence context or JPA/Hibernate-style lazy-loading proxies. As a result, N+1 is usually more explicit in application code:

- A service calling a child repository inside `flatMap`/`concatMap`.
- A mapper calling a repository to enrich each DTO.
- A loop executing a `DatabaseClient` query per ID.
- Multiple components invoked per item, each hitting the database independently.

Example of a mapper inadvertently causing N+1:

~~~java
return customerRepository.findAll()
    .flatMap(customer ->
        ownerRepository.findById(customer.getOwnerId())
            .map(owner ->
                new CustomerView(
                    customer.getId(),
                    customer.getName(),
                    owner.getDisplayName()
                )
            )
    );
~~~

With 200 customers where each customer's owner is queried individually, the application runs 1 customer query plus 200 owner queries. If many customers share the same owner, it may even query the exact same owner repeatedly.

## 6. How to Identify N+1

Do not guess from code inspection alone. Observe the actual SQL statements executed during a request or use case.

### 6.1. Enable Query Logging in Development

Configure logging for Spring Data R2DBC, Spring R2DBC, and driver packages according to your version. Aim to observe:

- The parent `SELECT`.
- Repeated child `SELECT`s.
- Bind values changing per customer ID.
- How many times similar SQL statements run.
- Timing intervals between executions.

Logs reveal repeating patterns, though SQL logging with sensitive data should not be enabled in production without parameter masking or redaction policies.

### 6.2. Look for Repeated Statement Patterns

A telltale sign:

~~~text
SELECT id, name FROM customer WHERE active = ?
SELECT id, customer_id, total FROM purchase_order WHERE customer_id = ?
SELECT id, customer_id, total FROM purchase_order WHERE customer_id = ?
SELECT id, customer_id, total FROM purchase_order WHERE customer_id = ?
...
~~~

If the exact same SQL structure executes repeatedly differing only by `customer_id`, check whether it sits inside a loop or per-customer reactive operator.

### 6.3. Count Queries per Request

Track:

- Total SQL statements executed per request.
- Execution counts grouped by SQL fingerprint.
- Connection acquisition counts.
- Average and p95/p99 query durations.
- Returned row counts.
- Requests whose query count scales with page size.

If a page of 20 customers executes ~21 queries and a page of 100 customers executes ~101 queries, that is strong evidence of N+1.

### 6.4. Distributed Tracing and Database Monitoring

Tracing reveals numerous database spans inside a single request. If an HTTP request shows a long chain of identical SQL spans, each handling one ID, check for N+1.

Database monitoring can group statements by query fingerprint, showing how many times a SQL shape executed and total time spent. Combining that with application traces helps pinpoint the call site issuing the queries.

### 6.5. Testing Query Counts

An integration test can seed a known set of customers and orders, execute the use case, and count queries. With a batched solution, query count should remain roughly constant by batch count rather than growing by one per customer.

You can use an R2DBC proxy or `ConnectionFactory` wrapper in tests to count statement executions. Measure only queries triggered by the use case itself, excluding schema setup and test data seeding.

Avoid overly brittle exact-number assertions if the framework may issue extra metadata or version-specific statements. Assert bounds reflecting the architectural goal—such as verifying query count does not grow linearly with customer count.

## 7. Solution 1: JOIN and Projection

If a screen needs customer data alongside order data, fetch them in a single `JOIN` query:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       o.id AS order_id,
       o.total AS order_total
FROM customer c
LEFT JOIN purchase_order o
       ON o.customer_id = c.id
WHERE c.active = true
ORDER BY c.id, o.id;
~~~

Instead of one parent query and N child queries, the database runs one `JOIN` query.

Map the flat result:

~~~java
public record CustomerOrderRow(
    Long customerId,
    String customerName,
    Long orderId,
    BigDecimal orderTotal
) {
}
~~~

~~~java
Flux<CustomerOrderRow> rows =
    databaseClient.sql(sql)
        .map((row, metadata) -> new CustomerOrderRow(
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class),
            row.get("order_id", Long.class),
            row.get("order_total", BigDecimal.class)
        ))
        .all();
~~~

Because a one-to-many `JOIN` produces one row per order, customer details repeat across rows. The application can group rows by customer ID to construct nested responses.

~~~java
Mono<List<CustomerWithOrders>> result =
    rows.collectList()
        .map(this::groupCustomerOrderRows);
~~~

`groupCustomerOrderRows` groups all rows sharing the same `customerId`, building one customer and its corresponding order list.

### Advantages of JOIN

- Reduces database round trips.
- Lets the database optimize joins and filters.
- Selects only the exact columns needed.
- Convenient for projections, reports, and read models.

### Considerations

- A customer with multiple orders appears multiple times in the flat result.
- Joining multiple one-to-many relationships at once can create a Cartesian product or blow up row counts.
- Must handle null columns from `LEFT JOIN` when a customer has no orders.
- Collecting everything with `collectList()` grows memory usage with result size.
- Paginating directly over a one-to-many `JOIN` result paginates by row rather than by customer.

`JOIN` works well when relationships are clear and result sizes are controllable. Do not join every table just to minimize SQL count if intermediate results grow excessively large.

## 8. Solution 2: Batch Query with IN

To keep the two datasets separate and avoid repeating parent columns across rows, you can:

1. Query the customer list.
2. Collect the customer IDs.
3. Query all orders belonging to those IDs in a single `IN` query.
4. Group orders by customer ID.
5. Attach each order list to its customer.

Example repository:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    Flux<PurchaseOrder> findByCustomerIdIn(
        Collection<Long> customerIds
    );
}
~~~

Service:

~~~java
public Flux<CustomerWithOrders> findCustomersWithOrders() {
    return customerRepository.findByActiveTrue()
        .collectList()
        .flatMapMany(customers -> {
            if (customers.isEmpty()) {
                return Flux.empty();
            }

            List<Long> customerIds = customers.stream()
                .map(Customer::getId)
                .toList();

            return orderRepository.findByCustomerIdIn(customerIds)
                .collectMultimap(PurchaseOrder::getCustomerId)
                .flatMapMany(ordersByCustomer ->
                    Flux.fromIterable(customers)
                        .map(customer -> {
                            Collection<PurchaseOrder> orders =
                                ordersByCustomer.getOrDefault(
                                    customer.getId(),
                                    List.of()
                                );

                            return new CustomerWithOrders(
                                customer,
                                List.copyOf(orders)
                            );
                        })
                );
        });
}
~~~

For N customers in one batch, this typically executes:

- One query to fetch customers.
- One query to fetch all orders for those customers.

Around two queries total instead of 1 + N.

### Why Check for an Empty List?

If there are no customers, there is no reason to query orders. Some databases reject `IN ()` with an empty list; expansion behavior also depends on the API and framework version. Returning `Flux.empty()` avoids unnecessary queries.

### Bounding Batch Size

An oversized `IN` list can exceed bind-parameter limits or produce huge SQL statements. When there are many customers, split IDs into reasonably sized batches:

~~~text
Customer IDs: 1 ... 2,500
       |
       +-- Batch 1: 1 ... 500
       +-- Batch 2: 501 ... 1,000
       +-- Batch 3: 1,001 ... 1,500
       +-- Batch 4: 1,501 ... 2,000
       +-- Batch 5: 2,001 ... 2,500
~~~

Each batch runs one query fetching orders. Query count then scales with batch count rather than customer count.

If using `DatabaseClient` and building an `IN` clause manually, generate individual placeholders for each ID and bind values. Never concatenate user IDs into a SQL string. Verify collection expansion support for your specific abstraction and driver rather than assuming all R2DBC drivers accept a collection in a single bind marker.

## 9. Batching Page by Page

Do not always collect all customers into memory. For large datasets, paginate the parent list and batch-query child records for the current page's IDs.

Example flow:

~~~text
Read a page of customers (e.g., 100 records)
              |
              v
Collect 100 customer IDs
              |
              v
One query fetching orders for 100 IDs
              |
              v
Group orders by customer ID
              |
              v
Build response for current page
              |
              v
Read next page of customers
~~~

With P pages, each page requires one parent query and one batched child query—roughly 2P queries total. That remains bounded by page count rather than firing one query per customer.

When paginating:

- Use a deterministic sort order, such as `created_at` with ID as a tie-breaker.
- Select only the ID and columns needed for batching.
- Cap elements per page to keep `IN` list sizes bounded.
- Handle empty pages.
- Do not paginate directly on a one-to-many `JOIN` result if the goal is paginating by customer.

## 10. Solution 3: Using SQL Aggregates When Only Metrics Are Needed

Sometimes the application only needs the order count per customer, not the full orders. In that case, do not load order lists just to count them in Java.

Use `GROUP BY`:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o
       ON o.customer_id = c.id
WHERE c.active = true
GROUP BY c.id, c.name
ORDER BY c.id;
~~~

DTO:

~~~java
public record CustomerOrderCount(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
~~~

Mapping:

~~~java
Flux<CustomerOrderCount> counts =
    databaseClient.sql(sql)
        .map((row, metadata) -> new CustomerOrderCount(
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class),
            row.get("order_count", Long.class)
        ))
        .all();
~~~

The database computes `COUNT` and returns only the required metrics. This is usually efficient for dashboards or lists displaying related counts.

Be sure to use `COUNT(o.id)` instead of `COUNT(*)` in a `LEFT JOIN` query. When a customer has no orders, `LEFT JOIN` still emits one row with NULL order columns; `COUNT(*)` would count that row as 1, whereas `COUNT(o.id)` returns 0.

## 11. Solution 4: Controlled Read Models or Caching

If a screen frequently needs combined data from multiple tables, you can build a read model tailored to display needs:

- A database view.
- A summary table updated as part of business workflows.
- A dedicated read model for dashboard queries.
- Caching shared, infrequently changing reference data.

These options reduce repeated `JOIN`s or batch queries, though they add synchronization and data consistency requirements.

Caching helps only when queries repeatedly hit the same keys and clear invalidation policies exist. Caching individual orders by customer is not a general solution for N+1 if every request still checks or loads hundreds of uncached keys.

Do not create denormalized tables or caches solely to fix an unmeasured query. First identify the actual use case and query pattern.

## 12. Bounding Concurrency Does Not Eliminate N+1

If you cannot change the query pattern immediately, you can bound how many child queries run concurrently:

~~~java
return customerRepository.findByActiveTrue()
    .flatMap(
        customer -> orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders ->
                new CustomerWithOrders(customer, orders)
            ),
        8
    );
~~~

The concurrency parameter limits how many inner publishers are active at once. It avoids firing too many simultaneous queries and eases pressure on the connection pool.

However, with 100 customers there will still be 100 child queries. Total query count remains 101. This is a temporary load-control measure, not a fix for N+1.

Similarly:

- `concatMap` runs sequentially but still issues N queries.
- `flatMap` with bounded concurrency still issues N queries.
- `zip` or `merge` across multiple publishers does not combine SQL statements.
- Wrapping queries in a transaction does not merge them into one query.

To reduce query count, you must change how data is fetched or group IDs into a batch query.

## 13. Do Indexes Fix N+1?

An index on `purchase_order.customer_id` can make each individual child query faster:

~~~sql
CREATE INDEX idx_purchase_order_customer_id
ON purchase_order(customer_id);
~~~

However, an index does not reduce query count from 1 + N down to 2. It only helps the database locate orders faster on each query.

Indexes are a useful complementary optimization after choosing the right query strategy. Inspect execution plans and workload before adding indexes rather than indexing columns blindly.

## 14. Mistakes to Avoid When Addressing N+1

### 14.1. Using flatMap and Assuming It Batches

~~~java
customers.flatMap(customer ->
    orderRepository.findByCustomerId(customer.getId())
);
~~~

`flatMap` only composes publishers. It does not automatically merge multiple repository calls into one SQL `IN` query.

### 14.2. Using concatMap and Thinking Query Count Dropped

`concatMap` merely serializes child queries. It can make requests slower by waiting on each query sequentially.

### 14.3. Caching Without Invalidation

Caching relational data without TTL or invalidation rules can serve stale data. Caching also fails to help with cold or uncached keys.

### 14.4. Joining Too Many One-to-Many Relationships

If a customer has many orders and each order has many lines, joining both relationships can produce rows equal to the product of element counts. The result set can dwarf the actual business data.

In that scenario, two separate batch queries can be more efficient and easier to group than one massive `JOIN`.

### 14.5. Paginating After a One-to-Many JOIN

`LIMIT`/`OFFSET` on a `JOIN` result can slice across a customer's orders or repeat a customer across pages. If the requirement is to paginate customers, paginate the `customer` table first and then fetch child data for that page.

### 14.6. Unbounded collectList()

`collectList()` is convenient for grouping data, but holds the entire result set in memory. For large datasets, paginate or process in bounded batches.

## 15. Testing to Prevent N+1 Regressions

After optimizing, write integration tests that verify query counts or query-count scaling.

Example dataset:

- 5 customers.
- 3 orders per customer.
- Use case returns customers with their order lists.

Comparison:

| Implementation | Expected Query Count |
|---|---:|
| Fetch customers then query orders per customer | 1 + 5 = 6 |
| JOIN customers and orders | 1 |
| Fetch customers then batch orders with IN | 2 |
| Page-by-page batching, one page of 5 customers | 2 |

Actual counts may include setup, transaction, or auxiliary framework queries. Tests should measure only the use case's data-access portion.

Beyond query count, verify:

- Are all customers included?
- Are customers without orders retained?
- Is each order attached to the right customer?
- Are orders duplicated by a JOIN?
- Does pagination align with parent entities?
- Is data filtered by tenant and permissions?
- Is result order deterministic?

An optimization that reduces query count while returning wrong results is not a valid optimization.

## 16. Choosing a Strategy by Use Case

| Requirement | Appropriate Strategy |
|---|---|
| Parent list with a few child fields | JOIN and DTO/projection |
| List of parent objects and child collections | Batch query with `IN` then group by parent ID |
| Only related counts or totals needed | `GROUP BY` and aggregate functions |
| Large dataset requiring pagination | Paginate parents first, batch children per page |
| Repeated queries for rarely changing reference data | Cache with explicit invalidation policy |
| Unable to refactor N+1 immediately | Bound concurrency for temporary load relief |
| Multiple screens sharing one read shape | Consider a read model or database view |

No single strategy fits every relationship. `JOIN` works well for a bounded read query; batch `IN` fits when keeping collections separate; aggregate queries fit when only metrics are needed.

## 17. Workflow for Finding and Fixing N+1

Follow this sequence:

1. Pick a request or use case showing slowness.
2. Count total SQL statements executed during the request.
3. Group statements by query fingerprint and check which ones repeat.
4. Inspect parameters to spot the pattern of one parent query plus one child query per ID.
5. Locate the call site inside reactive chains, mappers, or repository loops.
6. Determine what data is actually needed: full object graph, a projection, or just metrics.
7. Choose `JOIN`, batch `IN`, aggregate query, or read model.
8. If needed, paginate parents and split batches to bound memory and bind parameters.
9. Test both correctness and query count across varying parent counts.
10. Monitor latency, query count, pool usage, and database load after the change.

When parent count increases from 10 to 100, query count for a sound solution should not increase by 90 just because each parent invokes a repository method. With page-based batching, query count should scale only with page or batch count.

## 18. Key Takeaways

- N+1 is one query fetching N parent records plus N child queries, typically totaling 1 + N.
- In R2DBC, N+1 usually comes from calling a repository or `DatabaseClient` inside `flatMap`, `concatMap`, or per-entity loops.
- Reactive execution does not eliminate database round trips; `flatMap` only controls composition and concurrency.
- Identify it using SQL logs, query fingerprints, tracing, metrics, and statement-counting integration tests.
- `JOIN`s and projections can fetch related data in one query, but require handling repeated rows and pagination.
- Batch `IN` typically reduces 1 + N queries to one parent query and one child query per batch.
- When only metrics are needed, use `COUNT`/`GROUP BY` instead of loading full collections to the application.
- Paginate parents first and batch child data per page on large datasets.
- Bounding concurrency only caps simultaneous queries, not total query count.
- Indexes speed up individual queries without removing N+1.
- Choose strategies based on desired output shape and test both correctness and query count.
