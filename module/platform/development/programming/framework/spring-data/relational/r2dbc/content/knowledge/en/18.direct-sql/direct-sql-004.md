# Distinguishing one, first, all, and Empty Results

When using Spring Framework DatabaseClient to execute direct SQL in a Spring Data R2DBC application, you must choose the right way to retrieve results according to the number of rows the query can return. The three common options are one(), first(), and all(). They read data from the same SQL query but carry different cardinality contracts:

- one(): accepts at most one row; if there are no rows, the Mono completes empty; if there is more than one row, it emits a result-size error.
- first(): takes the first emitted row; if there are no rows, the Mono completes empty. If the query returns multiple rows, subsequent rows are not returned to the caller.
- all(): retrieves all rows as a Flux; if there are no rows, the Flux completes without emitting any elements.

**Choose the API based on the cardinality expected by business logic, not merely because you want a Mono or Flux.** one() helps catch queries that should return a single row but return multiple rows. first() fits when business logic genuinely wants the first row under a defined order. all() is for lists or multi-row streams.

Another key point: an empty result is not a database error. Mono.empty() and Flux.empty() represent a successful query with no matching rows. They differ from SQL NULL, from SQL errors, and from DML updating 0 rows.

## 1. DatabaseClient and FetchSpec

DatabaseClient provides a reactive API for running direct SQL without declaring a repository method for every statement. After binding parameters and mapping Row, the application chooses how to retrieve data via methods on RowsFetchSpec/FetchSpec.

Example querying a single customer:

~~~java
Mono<CustomerView> customer = databaseClient
        .sql("""
             SELECT id, display_name, email_address
             FROM customers
             WHERE id = :id
             """)
        .bind("id", customerId)
        .map((row, metadata) -> new CustomerView(
                row.get("id", Long.class),
                row.get("display_name", String.class),
                row.get("email_address", String.class)))
        .one();
~~~

This code creates a publisher; the query executes only upon subscription. one() determines how the returned rows are handled.

### 1.1. Basic Options

| Method | Return Type | No Rows | Multiple Rows |
| --- | --- | --- | --- |
| one() | Mono<T> | Mono completes empty | Emits result-size error |
| first() | Mono<T> | Mono completes empty | Returns only the first row |
| all() | Flux<T> | Flux completes empty | Returns all rows |

Here T is the type produced by the mapper. Without map(), FetchSpec can return data as Map<String, Object>.

### 1.2. FetchSpec Does Not Modify SQL

one(), first(), and all() are API-side result-consumption choices. They do not rewrite the SQL statement to add WHERE, ORDER BY, or LIMIT clauses.

If a query can return millions of rows, calling first() does not replace proper SQL design. If only the single latest row is needed, put ORDER BY and LIMIT into SQL so the database selects the right row and reduces work.

## 2. one(): Requiring at Most One Row

one() fits when the query has an at-most-one-row contract. For example:

- Looking up by primary key.
- Looking up by a column with a unique constraint.
- Reading a single configuration entry by tenant and key.
- Fetching a record by ID and tenant.

Example:

~~~java
public Mono<CustomerView> findCustomer(Long id) {
    return databaseClient
            .sql("""
                 SELECT id, display_name, email_address
                 FROM customers
                 WHERE id = :id
                 """)
            .bind("id", id)
            .map((row, metadata) -> new CustomerView(
                    row.get("id", Long.class),
                    row.get("display_name", String.class),
                    row.get("email_address", String.class)))
            .one();
}
~~~

Because id is the primary key, the database guarantees the query cannot return more than one row. If that ID does not exist, the publisher completes empty.

### 2.1. one() Errors When More Than One Row Is Returned

Suppose a query looks up by email, but the database lacks a unique constraint:

~~~sql
SELECT id, email_address
FROM customers
WHERE email_address = :email
~~~

If the data currently has two customers with the same email, one() does not silently pick one row. It emits a result-size error, typically translated by Spring into IncorrectResultSizeDataAccessException.

This is a useful signal: the query or data violates the at-most-one-row contract required by the code.

Do not catch this error and turn it into Mono.empty(), because doing so hides duplicate-data bugs.

### 2.2. one() Does Not Mean Exactly One Row Must Exist

In DatabaseClient's FetchSpec, one() allows zero rows and represents that case with Mono.empty(). It enforces the upper bound on multiple rows with an error.

If the use case requires a customer to exist, handle empty explicitly:

~~~java
public Mono<CustomerView> requireCustomer(Long id) {
    return findCustomer(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

This gives two independent rules:

- one() guards the at-most-one-row cardinality.
- switchIfEmpty() turns the zero-row case into a business error when the use case requires the resource to exist.

### 2.3. Enforcing Uniqueness in the Database

If business rules require emails to be globally unique:

~~~sql
CREATE UNIQUE INDEX uk_customers_email
ON customers (email_address);
~~~

If emails only need to be unique within each tenant:

~~~sql
CREATE UNIQUE INDEX uk_customers_tenant_email
ON customers (tenant_id, email_address);
~~~

one() is a cardinality check on read. A unique constraint is the database mechanism that protects uniqueness against concurrent requests and writes from multiple sources.

## 3. first(): Taking the First Row of the Result

first() fits when a query may return multiple rows, yet the use case only needs the first row under a deterministic ordering.

Example fetching the most recent event for a customer:

~~~java
public Mono<CustomerEvent> findLatestEvent(Long customerId) {
    return databaseClient
            .sql("""
                 SELECT id, customer_id, event_type, created_at
                 FROM customer_events
                 WHERE customer_id = :customerId
                 ORDER BY created_at DESC, id DESC
                 LIMIT 1
                 """)
            .bind("customerId", customerId)
            .map((row, metadata) -> new CustomerEvent(
                    row.get("id", Long.class),
                    row.get("customer_id", Long.class),
                    row.get("event_type", String.class),
                    row.get("created_at", LocalDateTime.class)))
            .first();
}
~~~

ORDER BY created_at DESC selects the latest event. id DESC acts as a tie-breaker so the order remains deterministic when two events share the same timestamp. LIMIT 1 tells the database it only needs to return at most one row.

### 3.1. first() Does Not Guarantee Business Order

If a query has no ORDER BY, the database does not guarantee which row appears first. Results can shift depending on execution plans, indexes, data layout, vacuuming, partitioning, or database version.

Do not write:

~~~sql
SELECT id, status
FROM orders
WHERE customer_id = :customerId
~~~

and then use first() intending to get the latest order. The query does not define what "latest" means.

Write:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT 1
~~~

### 3.2. first() Does Not Replace LIMIT

first() selects the first element from the result publisher. It does not automatically inject LIMIT 1 into the SQL statement. The driver may cancel reading the rest after receiving the first row, but that does not mean the database avoided the full work of producing the result.

For queries that can return many rows, add LIMIT/FETCH FIRST/TOP per the dialect when business logic only needs one row. Row-limiting syntax varies across databases.

### 3.3. first() Can Hide Duplicate Data

If a query is supposed to return only one row, but duplicates exist due to a missing constraint, first() still returns one row and ignores the rest. This can mask data bugs.

For example, looking up a configuration by tenant and key:

~~~sql
SELECT config_value
FROM tenant_settings
WHERE tenant_id = :tenantId
  AND setting_key = :key
~~~

If each tenant may have only one setting for a given key, use one() and a unique constraint on (tenant_id, setting_key). Using first() here could let the application keep running with an arbitrary value.

## 4. all(): Retrieving All Rows as a Flux

all() is appropriate for list queries:

~~~java
public Flux<CustomerView> findActiveCustomers() {
    return databaseClient
            .sql("""
                 SELECT id, display_name, email_address
                 FROM customers
                 WHERE active = :active
                 ORDER BY display_name, id
                 """)
            .bind("active", true)
            .map((row, metadata) -> new CustomerView(
                    row.get("id", Long.class),
                    row.get("display_name", String.class),
                    row.get("email_address", String.class)))
            .all();
}
~~~

all() emits each row along the reactive stream. If the query finds no rows, the Flux completes empty.

### 4.1. An Empty Flux Is a Valid List Result

An endpoint listing active customers may return an empty collection when no customer matches the criteria. That is normally a successful result, not a 404.

Example:

~~~java
return customerService.findActiveCustomers()
        .collectList()
        .map(ResponseEntity::ok);
~~~

If the Flux has no elements, collectList() emits a Mono containing an empty List. That Mono still emits a List value and completes—it is not Mono.empty().

### 4.2. Do Not Arbitrarily Collect Large Datasets

The snippet:

~~~java
return databaseClient.sql("SELECT * FROM audit_events")
        .map((row, metadata) -> mapEvent(row))
        .all()
        .collectList();
~~~

holds the entire result in memory. For large tables, heap usage can spike, triggering heavy garbage collection and slowing down the entire system.

Consider:

- Pagination with a deterministic ORDER BY.
- Time/scope bounds on the data.
- Streaming responses if the API and client support them.
- Batch processing.
- Backpressure and bounded concurrency.

all() produces a Flux, but it does not guarantee bounded memory usage if downstream calls collectList() or retains every item.

### 4.3. all() Has No Order Unless Specified in SQL

Flux emits rows in the order of the database result stream. If business logic requires a specific order, add ORDER BY. Never rely on physical table order or insertion order.

## 5. Empty Results: Mono.empty() and Flux.empty()

In reactive programming, a publisher can terminate in three main ways:

- Emit one or more values and complete.
- Complete without emitting any value.
- Emit an error.

For SQL queries:

| SQL Result | Typical API Representation |
| --- | --- |
| one() query finds one row | Mono emits one object and completes |
| one() query finds no rows | Mono.empty() |
| one() query returns more than one row | Error due to cardinality mismatch |
| first() query finds rows | Mono emits the first row |
| first() query finds no rows | Mono.empty() |
| all() query has multiple rows | Flux emits each row |
| all() query has no rows | Flux.empty() |
| Database/SQL error | Publisher emits error |

### 5.1. Empty Is Not Null

Reactor does not allow a Mono to emit a Java null value. Mono.empty() is a publisher that emits no value.

A database row may exist while a nullable column holds SQL NULL. In that case, the mapper should construct an object whose corresponding property is null:

~~~java
public record CustomerView(
        Long id,
        String displayName,
        String nickname) {
}

Mono<CustomerView> result = databaseClient
        .sql("""
             SELECT id, display_name, nickname
             FROM customers
             WHERE id = :id
             """)
        .bind("id", id)
        .map((row, metadata) -> new CustomerView(
                row.get("id", Long.class),
                row.get("display_name", String.class),
                row.get("nickname", String.class)))
        .one();
~~~

If the row exists but nickname is SQL NULL, the Mono still emits CustomerView; the object's nickname field is null. If no row exists, the Mono completes empty.

### 5.2. Do Not Accidentally Turn SQL NULL into Empty

Avoid mapping a nullable column directly into an empty publisher:

~~~java
.flatMap(row -> Mono.justOrEmpty(
        row.get("nickname", String.class)))
~~~

If nickname is SQL NULL, Mono.justOrEmpty() produces Mono.empty(). That erases the distinction between "no row found" and "row exists with a null nickname column."

If you need to preserve both meanings, map to a DTO or record with a nullable field:

~~~java
.map((row, metadata) -> new CustomerNickname(
        row.get("id", Long.class),
        row.get("nickname", String.class)))
~~~

The mapper must return a non-null object. Fields inside the object may be nullable according to the schema/domain.

### 5.3. Empty Does Not Trigger onErrorResume

The code:

~~~java
return findCustomer(id)
        .onErrorResume(error -> Mono.just(fallbackCustomer));
~~~

runs the fallback only when the publisher emits an error. If the query finds no row and returns Mono.empty(), onErrorResume does not run.

Use switchIfEmpty() or defaultIfEmpty() for the missing-value case.

## 6. Handling Empty with switchIfEmpty and defaultIfEmpty

switchIfEmpty() substitutes an empty publisher with another publisher:

~~~java
public Mono<CustomerView> requireCustomer(Long id) {
    return findCustomer(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

defaultIfEmpty() emits a default value:

~~~java
public Mono<CustomerView> findOrFallback(Long id) {
    return findCustomer(id)
            .defaultIfEmpty(CustomerView.notFound());
}
~~~

Which one to choose depends on the contract:

- Resource must exist: usually use switchIfEmpty(Mono.error(...)).
- Valid business fallback value exists: use defaultIfEmpty(...).
- List APIs: usually keep the empty Flux or collectList() into an empty list.

### 6.1. Using switchIfEmpty for Flux

~~~java
public Flux<CustomerView> findActiveOrDefaults() {
    return findActiveCustomers()
            .switchIfEmpty(Flux.just(defaultCustomer()));
}
~~~

This snippet emits defaultCustomer only when there are no rows at all. If there are one or more rows, the fallback does not run.

Do not automatically inject a dummy element into every empty list if the API has a clear empty-collection convention.

### 6.2. Using defer When Creating Fallbacks with Side Effects

If the fallback calls another service or records a metric, use a lazy publisher:

~~~java
return findCustomer(id)
        .switchIfEmpty(Mono.defer(() -> {
            metrics.incrementCustomerNotFound();
            return Mono.error(new CustomerNotFoundException(id));
        }));
~~~

Mono.defer() ensures the fallback publisher is created only when the source actually completes empty. Avoid invoking services or side effects at pipeline assembly time if they should only happen in the empty case.

## 7. Choosing one(), first(), or all() by Data Contract

A decision guide:

| Business Need | Choice | SQL/Schema Requirement |
| --- | --- | --- |
| Read by primary key | one() | Predicate on PK |
| Read by unique business key | one() | Unique constraint ensures at most one row |
| Read latest record | first() | Explicit ORDER BY and LIMIT 1 |
| Take a deliberate sample row | first() | Acceptable selection rule and ORDER BY if stability needed |
| Search list | all() | Appropriate filters, sorting, and pagination/limit |
| Multi-row report | all() | Streaming or batching; avoid unbounded collect |
| Read a required resource | one() + switchIfEmpty(error) | PK/unique predicate and not-found contract |
| Only check whether a record exists | EXISTS query or one() | Choose lightweight query per database |

### 7.1. Reading by ID

~~~java
Mono<Order> findById(Long id) {
    return databaseClient.sql("""
            SELECT id, status, total_amount
            FROM orders
            WHERE id = :id
            """)
            .bind("id", id)
            .map((row, metadata) -> mapOrder(row))
            .one();
}
~~~

The primary key guarantees the query has at most one row. If the ID does not exist, the publisher is empty; the service or controller decides whether to return 404 or an absence result per the API contract.

### 7.2. Reading the Latest Record

~~~java
Mono<OrderEvent> latestEvent(Long orderId) {
    return databaseClient.sql("""
            SELECT id, event_type, created_at
            FROM order_events
            WHERE order_id = :orderId
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """)
            .bind("orderId", orderId)
            .map((row, metadata) -> mapOrderEvent(row))
            .first();
}
~~~

This query can return 0 or 1 row due to LIMIT. first() expresses the intent of taking the first row. one() can also be used when SQL already guarantees at most one row; pick one style and stay consistent.

### 7.3. Fetching a Bounded List

~~~java
Flux<OrderSummary> findRecentOrders(Long customerId, int pageSize) {
    return databaseClient.sql("""
            SELECT id, status, created_at
            FROM orders
            WHERE customer_id = :customerId
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
            .bind("customerId", customerId)
            .bind("pageSize", pageSize)
            .map((row, metadata) -> mapOrderSummary(row))
            .all();
}
~~~

pageSize must be validated at the application layer so clients cannot request an excessively large limit. For multi-page pagination, prefer cursor/keyset pagination if offsets grow large or data changes continuously.

## 8. Behavior When a Query Unexpectedly Returns Multiple Rows

This is the key difference between one() and first():

~~~text
Query result: [row A, row B, row C]

one():
  emits a cardinality error because more than one row exists

first():
  emits row A and completes

all():
  emits row A, row B, row C and completes
~~~

### 8.1. one() Catches Data/Query Bugs

If a query looks up a user by email where email is expected to be unique, one() detects duplicates in the database. Handle the error as an integrity/query-contract failure and investigate constraints/migrations.

Do not switch to first() just to make the error disappear. Doing so can cause the application to pick the wrong user, configuration, or resource.

### 8.2. first() Is an Intentional Choice

first() makes sense when business logic asks for one representative item from multiple results, such as the latest event, best price, or top candidate by priority order.

The order must be defined in SQL. If two rows can tie on the sort column, add a tie-breaker for deterministic results.

### 8.3. all() Preserves Full Cardinality

all() fits when the caller needs the entire result set of the query. If you only need an existence check, do not fetch all rows and count them. Use EXISTS or COUNT depending on the goal.

## 9. DML and 0-Row Results: rowsUpdated() vs. all()/one()

INSERT, UPDATE, and DELETE normally do not return row data. For DML statements without a result set, use rowsUpdated() to obtain the number of affected rows:

~~~java
Mono<Integer> updateOrderStatus(Long id, String status) {
    return databaseClient.sql("""
            UPDATE orders
            SET status = :status
            WHERE id = :id
            """)
            .bind("status", status)
            .bind("id", id)
            .fetch()
            .rowsUpdated();
}
~~~

If no rows are updated, the publisher still emits 0 and completes. This is not Mono.empty().

### 9.1. Distinguishing Three Outcomes

| Situation | Publisher |
| --- | --- |
| UPDATE affects 3 rows | Mono emits 3 |
| UPDATE matches no rows | Mono emits 0 |
| Database emits constraint/connection error | Mono emits error |

The service can interpret the row count:

~~~java
return updateOrderStatus(id, status)
        .flatMap(rows -> {
            if (rows == 1) {
                return Mono.just(UpdateResult.updated());
            }
            if (rows == 0) {
                return Mono.just(UpdateResult.notFound());
            }
            return Mono.error(new UnexpectedUpdateCountException(rows));
        });
~~~

If the UPDATE is designed to affect multiple rows, set appropriate thresholds and semantics rather than assuming it is always 1.

### 9.2. Conditional UPDATE

A statement may include version or state predicates:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND status = 'DRAFT'
~~~

rowsUpdated() returning 0 can mean the order does not exist, the version changed, or the status is no longer DRAFT. Decide whether the API distinguishes these cases or returns a general conflict result.

### 9.3. SQL with RETURNING

Some databases support row-returning DML, such as PostgreSQL INSERT/UPDATE ... RETURNING. In that case, use row mapping and one()/first()/all() matching the result set's cardinality:

~~~java
Mono<Order> updateAndReturn(Long id, String status) {
    return databaseClient.sql("""
            UPDATE orders
            SET status = :status
            WHERE id = :id
            RETURNING id, status
            """)
            .bind("status", status)
            .bind("id", id)
            .map((row, metadata) -> mapOrder(row))
            .one();
}
~~~

If no row matches, the result publisher is empty. RETURNING syntax and support depend on the database/driver; do not assume every DBMS shares the same syntax.

## 10. Counting Rows and Checking Existence

If you only need to know whether matching rows exist, you can use EXISTS:

~~~java
Mono<Boolean> customerExists(Long id) {
    return databaseClient.sql("""
            SELECT EXISTS (
                SELECT 1
                FROM customers
                WHERE id = :id
            ) AS present
            """)
            .bind("id", id)
            .map((row, metadata) -> Boolean.TRUE.equals(
                    row.get("present", Boolean.class)))
            .one();
}
~~~

With an aggregate without GROUP BY, COUNT usually returns exactly one row even when there are no matching records:

~~~sql
SELECT COUNT(*) AS total
FROM orders
WHERE status = :status
~~~

When no orders match, the aggregate row still exists and total is 0. Thus, one() emits an object/count with value 0, not Mono.empty().

### 10.1. EXISTS and COUNT Have Different Purposes

- EXISTS answers whether at least one row exists; the database can stop as soon as a match is found.
- COUNT returns the total number of rows; the database generally needs to determine the full matching count according to the query plan.

If only a boolean is needed, EXISTS expresses intent better than COUNT > 0. However, actual performance depends on the optimizer, indexes, and database.

## 11. Mapping Rows and Handling Nullable Columns

DatabaseClient can return a Map or map Row into a DTO/domain object. Explicit mapping prevents confusing empty results with SQL NULL.

### 11.1. Mapping to a DTO

~~~java
public record ProductView(
        Long id,
        String name,
        BigDecimal price,
        String description) {
}

Mono<ProductView> findProduct(Long id) {
    return databaseClient.sql("""
            SELECT id, name, price, description
            FROM products
            WHERE id = :id
            """)
            .bind("id", id)
            .map((row, metadata) -> new ProductView(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("price", BigDecimal.class),
                    row.get("description", String.class)))
            .one();
}
~~~

description may be null if the schema allows it. ProductView remains a valid object.

### 11.2. Missing Column vs. Null Value

If SQL SELECT omits a column from the projection, the mapper should not try to read it. If the column is in the result set with SQL NULL, row.get() returns null for that property. Distinguish mapping errors caused by wrong column names from nullable data.

### 11.3. Column Names and Aliases

When using aggregates, expressions, or duplicate column names in JOINs, assign explicit aliases:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.id = :id
GROUP BY c.id, c.name
~~~

The mapper reads using the exact alias. Column labels can depend on the database/dialect if no explicit alias is set.

## 12. Pagination and Stable Ordering with all()

all() emits every row returned by SQL. For list APIs, the SQL should have an explicit limit and deterministic ordering.

### 12.1. Offset Pagination

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset
~~~

This is straightforward, but large offsets force the database to skip many rows. Data changes between pages can also cause duplicates or skipped items.

### 12.2. Keyset Pagination

For descending order by created_at and id:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenantId
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize
~~~

The client sends the cursor of the last row from the previous page. The sort-key pair must provide a deterministic order and have an appropriate index.

### 12.3. Do Not Use first() to Simulate Pagination

first() only returns the single first row. It does not provide cursors, page boundaries, or total counts. If the business need is a paginated list, use all() with SQL limit/cursor and return pagination metadata separately.

## 13. Combining one()/first()/all() with HTTP APIs

Typical HTTP contract mappings:

| Endpoint | Query Type | Common Empty Outcome |
| --- | --- | --- |
| GET /customers/{id} | one() | 404 if the resource must exist |
| GET /customers?active=true | all() | 200 with an empty array |
| GET /orders/latest | first() | 404 or 204 per API contract |
| GET /customers/exists/{id} | EXISTS + one() | 200 with false |
| PATCH /orders/{id} | DML + rowsUpdated() or RETURNING | 404/409 depending on update conditions |

### 13.1. Single Resource

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<CustomerView>> getCustomer(
        @PathVariable Long id) {

    return customerService.findCustomer(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

### 13.2. Collection

~~~java
@GetMapping
public Mono<ResponseEntity<List<CustomerView>>> listCustomers() {
    return customerService.findActiveCustomers()
            .collectList()
            .map(ResponseEntity::ok);
}
~~~

If there are no rows, the endpoint returns 200 with an empty list. For very large collections, do not collect everything; use appropriate pagination or streaming responses.

### 13.3. 204 No Content

204 can be appropriate when an endpoint succeeds without needing a response body, such as a successful DELETE command. Do not return 204 simply because a SELECT found no rows when the API contract specifies 404.

## 14. Common Mistakes When Choosing the Wrong Method

| Symptom | Cause | Fix |
| --- | --- | --- |
| Query returns duplicates without error | Using first() for a query needing uniqueness | Use one() and a unique constraint |
| one() emits IncorrectResultSizeDataAccessException | Query returns more than one row | Check predicates, JOINs, and constraints |
| Resource not found but API misses onErrorResume | Empty is not an error | Use switchIfEmpty/defaultIfEmpty |
| SQL NULL treated as missing row | Mapping nullable column to Mono.empty() | Map to a DTO with a nullable field |
| Empty list returns 404 | Confusing Flux.empty() with a single resource | Return 200 and an empty collection |
| first() returns different rows across runs | Query lacks deterministic ORDER BY | Add ORDER BY and a tie-breaker |
| first() still runs an expensive query | Assuming first() adds LIMIT automatically | Add LIMIT/FETCH FIRST/TOP in SQL |
| all() spikes heap usage | Calling collectList() on unbounded data | Use pagination, batching, or streaming |
| UPDATE matching 0 rows treated as empty | Using row fetch instead of rowsUpdated | Check the affected row count |
| COUNT is 0 but publisher is not empty | Aggregate still returns one row | Read count = 0 as a valid result |
| JOIN causes one() to fail on multiple rows | One entity has multiple child rows | Use aggregation, right projection, or all() |
| Unstable list order | Relying on database physical order | Add an explicit ORDER BY |

## 15. Testing Cardinality and Empty Results with StepVerifier

StepVerifier lets you assert how many elements a publisher emits and whether it completes or errors.

### 15.1. one() Finding No Rows

~~~java
StepVerifier.create(repositoryClient.findCustomer(999L))
        .verifyComplete();
~~~

The test confirms the Mono completes without emitting any elements.

### 15.2. one() With One Row

~~~java
StepVerifier.create(repositoryClient.findCustomer(10L))
        .assertNext(customer ->
                assertThat(customer.id()).isEqualTo(10L))
        .verifyComplete();
~~~

### 15.3. one() With Multiple Rows

Prepare data causing the query to return two rows and verify the publisher emits a cardinality error. Depending on the Spring version and exception translation path, verify the exact exception contract exposed by the application—commonly IncorrectResultSizeDataAccessException.

Do not write a test that only asserts "any error" if the goal is to protect duplicate-row behavior.

### 15.4. first() Returning Rows in Order

Prepare three rows with different timestamps. Invoke the query with ORDER BY created_at DESC, id DESC and first(). Verify the latest row is emitted.

Then add two rows sharing the same timestamp to verify that the id tie-breaker makes the result deterministic.

### 15.5. Empty all()

~~~java
StepVerifier.create(repositoryClient.findCustomersByStatus("UNKNOWN"))
        .verifyComplete();
~~~

An empty Flux completes immediately without emitting elements.

### 15.6. collectList() on an Empty Flux

~~~java
StepVerifier.create(repositoryClient
                .findCustomersByStatus("UNKNOWN")
                .collectList())
        .assertNext(list -> assertThat(list).isEmpty())
        .verifyComplete();
~~~

This test proves collectList() emits an empty List, not Mono.empty().

### 15.7. SQL NULL vs. No Row

Create two test cases:

1. A row exists with nickname set to SQL NULL.
2. No row matches the ID.

For the first case, verify the Mono emits a DTO and DTO.nickname is null. For the second case, verify the Mono completes empty.

### 15.8. rowsUpdated() Equal to 0

~~~java
StepVerifier.create(repositoryClient.updateStatus(999L, "CLOSED"))
        .expectNext(0)
        .verifyComplete();
~~~

The exact numeric type depends on the API/version; what matters is asserting that the publisher emits an affected row count of 0.

## 16. Integration Tests Should Run Against a Real Database

Mocking DatabaseClient can test how a service chains publishers, but it cannot verify:

- That the driver actually returns the expected row count.
- That the database handles LIMIT/ORDER BY correctly.
- That JOINs produce the expected cardinality.
- That unique constraints prevent duplicates.
- That SQL NULL maps properly.
- That DML returns the expected rows updated.

For critical queries, use Testcontainers or a test database matching production. Set up clear fixture data, execute real queries, and verify publishers with StepVerifier.

### 16.1. Verifying Duplicates with a Unique Constraint

Attempt to insert two customers with the same email. Verify the database rejects the second insert. Afterward, querying with one() continues to return at most one row.

### 16.2. Testing JOINs

One customer with multiple orders produces multiple rows when joining customer and order. Using one() to map CustomerView can trigger a cardinality error even though there is only one customer.

Options:

- Query customer and orders separately.
- Use aggregates to combine orders.
- Use all() and group/assemble results in a bounded manner.
- Select only a single representative row if business logic truly needs one row.

Do not use first() to hide a JOIN unexpectedly generating multiple rows.

## 17. JOINs and Cardinality: One Entity Can Produce Multiple Rows

Example:

~~~sql
SELECT c.id AS customer_id,
       c.display_name,
       o.id AS order_id
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE c.id = :customerId
~~~

If the customer has three orders, the result set has three rows. one() will see three rows and emit an error, even if the developer's goal was to fetch one customer.

### 17.1. Read Only the Parent If Children Are Not Needed

~~~sql
SELECT c.id, c.display_name
FROM customers c
WHERE c.id = :customerId
~~~

Querying without joining the child table preserves primary-key cardinality.

### 17.2. Use Aggregation for Child Collections

Depending on the database, you can use JSON/array aggregation or a separate query for child collections. Verify native type mapping and avoid making queries hard to maintain when two simple queries suffice.

### 17.3. Use all() When Each Row Is a Result to Process

If the goal is listing a customer's orders, all() matches the semantics:

~~~java
Flux<OrderView> findOrders(Long customerId) {
    return databaseClient.sql("""
            SELECT id, status, total_amount
            FROM orders
            WHERE customer_id = :customerId
            ORDER BY id
            """)
            .bind("customerId", customerId)
            .map((row, metadata) -> mapOrderView(row))
            .all();
}
~~~

## 18. Notes When Combining with Optional and Service Return Types

Mono.empty() and Optional.empty() express absence at two different layers. There is no need to wrap Optional inside Mono when the service already uses Mono to represent no result.

Example:

~~~java
Mono<CustomerView> findCustomer(Long id);
~~~

is sufficient to represent one or no customer. If you want to turn absence into an explicit value:

~~~java
Mono<Optional<CustomerView>> findCustomerOptional(Long id) {
    return findCustomer(id)
            .map(Optional::of)
            .defaultIfEmpty(Optional.empty());
}
~~~

This can be useful at internal imperative API boundaries, but is usually unnecessary inside reactive services because it creates two layers representing absence.

Never emit null via Mono.just(null). Use Mono.empty() when a publisher has no value, or emit a valid object with nullable fields.

## 19. Method Selection Checklist

- [ ] Can the query return at most one row? Use one().
- [ ] Does the database have a primary key or unique constraint guaranteeing cardinality?
- [ ] If returning multiple rows is an error, is one() kept to detect it?
- [ ] Do you only need the first row under a business order? Use first().
- [ ] Does the SQL have a deterministic ORDER BY and tie-breaker?
- [ ] Was LIMIT/FETCH FIRST/TOP added to bound database work?
- [ ] Do you need the entire result set? Use all().
- [ ] Does the list have appropriate bounds/pagination or streaming?
- [ ] Are empty Mono/Flux handled according to the API contract?
- [ ] Is SQL NULL distinguished from no row?
- [ ] Is onErrorResume accidentally used to handle empty?
- [ ] Does DML use rowsUpdated() when only the affected row count is needed?
- [ ] Is an UPDATE affecting 0 rows distinguished from an empty query?
- [ ] Can a JOIN unexpectedly multiply cardinality?
- [ ] Have integration tests verified behavior on a real database?

## 20. Selection Diagram

~~~mermaid
flowchart TD
    A[Run SQL and receive result set] --> B{How many rows does business logic need?}
    B -->|At most one row| C[one()]
    C --> D{Any row?}
    D -->|No| E[Mono.empty()]
    D -->|One row| F[Mono emits object]
    D -->|Multiple rows| G[Cardinality error]
    B -->|Intentional first row| H[ORDER BY + LIMIT 1 + first()]
    H --> I{Any row?}
    I -->|No| E
    I -->|Yes| F
    B -->|All rows| J[all()]
    J --> K{Any row?}
    K -->|No| L[Flux.empty()]
    K -->|Yes| M[Flux emits each row]
    N[DML returning no rows] --> O[rowsUpdated()]
    O --> P[Mono emits affected row count, including 0]
~~~

## 21. Conclusion

one(), first(), and all() describe three distinct cardinality contracts when reading SQL with DatabaseClient. one() fits at-most-one-row queries and helps catch duplicates; first() takes the first row in result order, so it requires a deterministic ORDER BY and usually LIMIT 1 in SQL; all() returns all rows as a Flux and needs pagination or streaming appropriate for large datasets.

Zero-row results are represented by Mono.empty() or Flux.empty(), not SQL errors. SQL NULL is a value inside an existing row; map it to a nullable field in an object rather than turning it into an empty publisher. switchIfEmpty/defaultIfEmpty handle absence, whereas onErrorResume handles error signals. For DML, rowsUpdated() emits the number of affected rows, and 0 is a concrete result rather than empty.

Let SQL queries and schemas enforce cardinality: primary keys/unique constraints for one(), ORDER BY/LIMIT for first(), and filters/pagination for all(). Test missing rows, rows with NULL columns, duplicates, multi-row JOINs, and 0-row UPDATEs using StepVerifier with a real database. When the data contract is chosen correctly, the reactive pipeline cleanly expresses success, absence, and errors.
