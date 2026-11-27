# Distinguishing SQL Joins from Combining Multiple Publishers

In Spring Data Relational R2DBC, there are two common ways to fetch data from multiple sources: asking the database to combine tables with a SQL `JOIN`, or running multiple reactive operations and combining results using Reactor operators. Both approaches can produce an object or response containing data from multiple sources, but they solve two different problems.

A SQL join combines rows according to key relationships and predicates directly inside the database. The database can optimize filtering, joining, sorting, and sending only the needed columns back to the application. Combining Publishers happens in the application layer: each Publisher emits data independently, and then Reactor merges, maps, sequences, or zips them according to operator rules. Reactor does not inherently know that two objects sharing the same `customerId` are rows meant to be joined.

Choosing the right approach reduces round trips, avoids N+1 queries, keeps data consistency clear, and controls concurrency. SQL joins typically fit when data resides in the same database with clear relational keys. Publisher composition fits when combining independent results, data across multiple databases or external services, or when each source has its own lifecycle.

## 1. What Is a SQL JOIN?

A SQL join combines rows from two or more tables based on a join condition. For example, a `customer` table stores customers and an `orders` table stores orders:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

`orders.customer_id` references `customer.id`. If we need a list of orders along with customer names, the database can execute a join:

```sql
SELECT
    o.id AS order_id,
    o.total_amount,
    o.status,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = 'PAID'
ORDER BY o.id;
```

The database finds rows matching the join condition, filters by status, and returns the selected projection. The application receives only the needed result instead of loading both full tables and matching them manually.

### 1.1. Common JOIN Types

| JOIN Type | Meaning |
|---|---|
| `INNER JOIN` | Returns only rows with matching pairs on both sides |
| `LEFT JOIN` | Returns all left-side rows; right columns are NULL if no match exists |
| `RIGHT JOIN` | Returns all right-side rows; left columns are NULL if no match exists |
| `FULL OUTER JOIN` | Returns matching rows plus unmatched rows from both sides, if supported by the database |
| `CROSS JOIN` | Produces the Cartesian product of two row sets |

Example `INNER JOIN` returning only customers with orders:

```sql
SELECT c.id, c.name, o.id AS order_id
FROM customer c
INNER JOIN orders o ON o.customer_id = c.id;
```

`LEFT JOIN` retains customers who have no orders yet:

```sql
SELECT c.id, c.name, o.id AS order_id
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id;
```

If a customer has multiple orders, `LEFT JOIN` returns multiple rows for that customer. This is a property of a one-to-many relationship, not duplicate-data corruption.

## 2. Using JOIN in Spring Data R2DBC

Spring Data Relational R2DBC provides entity-oriented abstractions such as repositories and `R2dbcEntityTemplate`, alongside the lower-level SQL API `DatabaseClient`. For multi-table join queries needing custom projections, `DatabaseClient` is often the most direct, explicit way to write SQL and map results.

Example DTO:

```java
public record OrderSummary(
    Long orderId,
    BigDecimal totalAmount,
    String status,
    Long customerId,
    String customerName
) {}
```

A repository or service can use `DatabaseClient`:

```java
Flux<OrderSummary> findPaidOrderSummaries(DatabaseClient databaseClient) {
    return databaseClient.sql("""
            SELECT
                o.id AS order_id,
                o.total_amount AS total_amount,
                o.status AS order_status,
                c.id AS customer_id,
                c.name AS customer_name
            FROM orders o
            JOIN customer c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.id
            """)
        .bind("status", "PAID")
        .map((row, metadata) -> new OrderSummary(
            row.get("order_id", Long.class),
            row.get("total_amount", BigDecimal.class),
            row.get("order_status", String.class),
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class)
        ))
        .all();
}
```

Column aliases prevent confusion when tables share column names like `id`, `status`, or `created_at`. The mapper converts each `Row` into a DTO inside the callback; never retain `Row` for use after the callback ends.

### 2.1. Using @Query for Fixed SQL JOINs

If the query is stable and belongs to a specific repository, you can declare the SQL with `@Query`:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT o.id, o.total_amount, o.status,
               c.id AS customer_id, c.name AS customer_name
        FROM orders o
        JOIN customer c ON c.id = o.customer_id
        WHERE o.status = :status
        ORDER BY o.id
        """)
    Flux<OrderSummary> findSummariesByStatus(String status);
}
```

Projection mapping depends on the projection type and mapping capabilities of your Spring Data R2DBC version. If the DTO has a complex structure or needs explicit mapper control, `DatabaseClient` is easier to trace.

### 2.2. JOINs Are Not Inferred Solely from Reference Fields

Spring Data Relational does not behave like a JPA ORM with automatic lazy loading of relationships. A property holding a customer ID does not mean Spring Data automatically joins the `customer` table when reading an `Order` entity.

For example, an entity may hold a foreign key:

```java
@Table("orders")
public class Order {

    @Id
    private Long id;

    private Long customerId;

    private BigDecimal totalAmount;
}
```

`customerId` is simply reference data mapped from a column. If you need the customer's name, write an explicit join, run a second query, or call another data source and compose Publishers. Do not assume accessing `order.getCustomer()` will trigger a query like a JPA lazy association.

## 3. Cardinality: One-to-Many Changes Result Shape

When joining one customer with multiple orders, a single customer can appear across multiple result rows:

```text
customer
+----+----------+
| id | name     |
+----+----------+
| 10 | An       |
+----+----------+

orders
+----+-------------+--------+
| id | customer_id | total  |
+----+-------------+--------+
| 1  | 10          | 100.00 |
| 2  | 10          | 250.00 |
+----+-------------+--------+

JOIN result
+----------+-------------+--------+
| cust_name| order_id    | total  |
+----------+-------------+--------+
| An       | 1           | 100.00 |
| An       | 2           | 250.00 |
+----------+-------------+--------+
```

If each row is mapped into a `Customer`, the application may receive multiple `Customer` objects with the same ID. If you need one `Customer` containing a list of orders, you must group the rows or use an appropriate query/aggregate.

With `LEFT JOIN`, columns from the child table may be null:

```java
Long orderId = row.get("order_id", Long.class);
```

`orderId == null` can indicate a customer without orders. DTOs and mappers must allow null for right-side columns. Never use primitive `long` when a column can be null.

## 4. What Is Publisher Composition?

In Reactor, `Mono<T>` and `Flux<T>` are Publishers. They can be combined with operators to form new streams. Each source still executes its own work; Reactor coordinates signals and values between Publishers.

For example, a customer detail screen needs customer info and a list of orders. You can run two independent queries and combine the results:

```java
public record CustomerDetail(
    Customer customer,
    List<Order> orders
) {}

Mono<CustomerDetail> findCustomerDetail(Long customerId) {
    Mono<Customer> customerMono = customerRepository.findById(customerId);

    Mono<List<Order>> ordersMono = orderRepository
        .findByCustomerIdOrderByCreatedAtDesc(customerId)
        .collectList();

    return Mono.zip(customerMono, ordersMono)
        .map(tuple -> new CustomerDetail(
            tuple.getT1(),
            tuple.getT2()
        ));
}
```

`Mono.zip` waits for both Monos to emit a value and produces a tuple. Then `map` turns the tuple into `CustomerDetail`. Both queries can be subscribed to as independent sources coordinated by Reactor.

Key point: `zip` pairs results by emission position, not by `customerId` or a relational key. In the example above, both Monos represent one specific customer, so positional pairing makes sense. If two Fluxes contain many customers and many orders, `zip` does not perform a relational join.

## 5. Common Reactor Operators When Combining Publishers

Composition operators have distinct semantics. Choosing the wrong operator can drop data, pair wrong elements, or create excessive concurrency.

| Operator | How It Works | Is It a Key-Based SQL-Style Join? |
|---|---|---|
| `Mono.zip(a, b)` | Waits for each source to emit one value then builds a tuple | No; pairs values by position |
| `Flux.zip(a, b)` | Pairs 1st element with 1st, 2nd with 2nd, etc. | No; pairs by emission index |
| `combineLatest` | Once all sources have emitted, emits a new combination whenever any source updates | No; combines latest state |
| `flatMap` | Maps each element to an inner Publisher and merges results | No; runs async work per element |
| `concatMap` | Like `flatMap`, but processes inner Publishers sequentially preserving order | No; serializes work |
| `merge` | Interleaves signals from multiple sources by emission time | No; does not pair by key |
| `concat` | Consumes one source completely before the next, concatenating results | No; concatenates streams |
| `collectMap` / `collectMultimap` | Collects data into an in-memory map by key | Can assist application-level matching, but requires manual key definition and memory management |

### 5.1. Mono.zip: Pairing Single Results

`Mono.zip` fits when each source returns at most one value and those values must be used together:

```java
Mono<CustomerProfile> profileMono = profileRepository.findByCustomerId(id);
Mono<CreditScore> scoreMono = creditClient.findScore(id);

return Mono.zip(profileMono, scoreMono)
    .map(tuple -> new CustomerRiskView(
        tuple.getT1(),
        tuple.getT2()
    ));
```

This combines a database profile with a credit score from an external service. No SQL join can directly join a local table with a Publisher from an HTTP service; application-level composition is appropriate here.

If either Mono completes empty, a standard `Mono.zip` also completes empty because it cannot form a full tuple. If one source may have no data yet a response is still required, provide an explicit fallback:

```java
Mono<CreditScore> score = creditClient.findScore(id)
    .defaultIfEmpty(CreditScore.unknown());

return Mono.zip(profileMono, score)
    .map(tuple -> new CustomerRiskView(tuple.getT1(), tuple.getT2()));
```

Only supply default values when business rules allow it. Do not turn service failures into "unknown" data if that hides an incident that should be reported.

### 5.2. Flux.zip: Pairing by Emission Position

`Flux.zip` pairs elements by emission order, not by ID:

```java
Flux<Tuple2<Customer, Order>> pairs = Flux.zip(
    customerRepository.findAll(),
    orderRepository.findAll()
);
```

This is generally not how to combine two related entity sets. If the customer stream emits 10 elements and the order stream emits 25 elements, `zip` can only pair until one stream runs out of elements. The first customer will be paired with the first order even if they do not share a foreign key.

Only use `zip` when two streams are designed to align positionally, such as two sample series generated at matching indices. Never use it as a substitute for `JOIN ... ON customer.id = orders.customer_id`.

### 5.3. combineLatest: Combining Latest State

`combineLatest` is useful when sources are state update streams:

```java
Flux<DashboardState> dashboard = Flux.combineLatest(
    inventoryPublisher,
    pricePublisher,
    (inventory, price) -> new DashboardState(inventory, price)
);
```

Once every source has emitted at least one value, each update from any source produces a new result from the latest values of all sources. This is a state-combination pattern suited to dashboards or event streams. It does not join rows by key and may re-emit the same value from one source when another source changes.

### 5.4. merge and concat Only Combine Streams

`merge` interleaves elements from multiple sources as they emit:

```java
Flux<Event> events = Flux.merge(orderEvents, paymentEvents);
```

The result is a shared event stream; there are no tuples or join relationships between events from the two sources.

`concat` consumes the first source completely before moving to the next:

```java
Flux<AuditEntry> history = Flux.concat(currentEntries, archivedEntries);
```

It appends two streams without pairing corresponding rows. Choose based on ordering requirements and data semantics.

### 5.5. flatMap and concatMap: Calling a Dependent Publisher Per Element

If each customer requires a query to load an auxiliary profile, you can use `flatMap`:

```java
Flux<CustomerView> views = customerRepository.findByActiveTrue()
    .flatMap(customer -> profileRepository.findByCustomerId(customer.getId())
        .map(profile -> new CustomerView(customer, profile)));
```

Each customer triggers a secondary query. This is valid reactive composition, but it can cause N+1 queries: one query to fetch the customer list, plus one query per customer.

`flatMap` can run inner Publishers concurrently. Bound concurrency when the customer count is large:

```java
Flux<CustomerView> views = customerRepository.findByActiveTrue()
    .flatMap(customer -> profileRepository.findByCustomerId(customer.getId())
        .map(profile -> new CustomerView(customer, profile)), 8);
```

The limit `8` means at most eight inner Publishers are subscribed concurrently in this stage. It helps control load, though it does not eliminate the total N+1 query count.

If input order must be preserved and queries must execute one at a time, use `concatMap`:

```java
Flux<CustomerView> views = customerRepository.findByActiveTrue()
    .concatMap(customer -> profileRepository.findByCustomerId(customer.getId())
        .map(profile -> new CustomerView(customer, profile)));
```

`concatMap` preserves order but usually lowers throughput because each inner Publisher must complete before processing the next element.

## 6. How Database JOIN Differs from Application-Layer Composition

| Criterion | SQL JOIN | Publisher Composition |
|---|---|---|
| Where combining happens | Database engine | Application / Reactor pipeline |
| Matching mechanism | SQL predicates like foreign keys, primary keys, or expressions | Positional, emission timing, dependent stream, or application-managed keys |
| Round trips | Usually one query for the join | Usually multiple operations/sources, unless sources batch |
| Optimization | Database chooses join algorithms and uses indexes/statistics | Application coordinates, holds maps/buffers, and limits concurrency |
| Heterogeneous sources | Cannot directly join across database boundaries in one query | Can combine databases, HTTP services, caches, and message streams |
| Consistency | A single SQL statement evaluates under database snapshot/statement semantics | Multiple operations may observe data at different points in time |
| Application memory | Receives only needed result projection | May need to hold multiple result sets or lookup maps in memory |
| Handling 1-N relationships | Database returns multiple rows; grouping needed for nested objects | Application groups by key or emits per-item views |

SQL joins usually win when tables reside in the same database. Databases are built to execute joins using indexes, statistics, and server-side memory/temp space. The application avoids pulling two large datasets over the wire to join manually.

Publisher composition shines when sources cannot be queried in a single SQL statement, or when independent operations can run in parallel. However, composition does not provide relational semantics automatically. The application must explicitly define join keys, cardinality, missing-data behavior, and resource limits.

## 7. Avoiding N+1 Queries When Combining Publishers

A common mistake is fetching a list of entities and calling a repository inside `flatMap` for every row:

```java
Flux<CustomerView> views = customerRepository.findAll()
    .flatMap(customer -> orderRepository
        .findByCustomerId(customer.getId())
        .collectList()
        .map(orders -> new CustomerView(customer, orders)));
```

With 500 customers, this can issue one initial query and 500 queries fetching orders. That is an N+1 query pattern. Even though each query is non-blocking, round trips and database pressure still grow.

### 7.1. Batch Fetching with IN

If the customer set is bounded to a reasonable size, you can fetch customers once, fetch all orders for those IDs in one query, and group in the application:

```java
Flux<CustomerView> findCustomerViews() {
    return customerRepository.findTop100ByActiveTrueOrderByIdAsc()
        .collectList()
        .flatMapMany(customers -> {
            if (customers.isEmpty()) {
                return Flux.empty();
            }

            List<Long> customerIds = customers.stream()
                .map(Customer::getId)
                .toList();

            return orderRepository.findByCustomerIdIn(customerIds)
                .collectMultimap(Order::getCustomerId)
                .flatMapMany(ordersByCustomer ->
                    Flux.fromIterable(customers)
                        .map(customer -> new CustomerView(
                            customer,
                            List.copyOf(ordersByCustomer.getOrDefault(
                                customer.getId(), List.of()))
                        ))
                );
        });
}
```

How this example works:

1. Fetch up to 100 customers in a stable order.
2. Extract the list of IDs.
3. Run one `IN` query to fetch orders for all customers in the batch.
4. Group orders by `customerId` via `collectMultimap`.
5. Iterate customers and build `CustomerView`, using an empty list if a customer has no orders.

This is application-level batch composition, not a SQL join. It reduces query count to two in this case, while holding the customer and order lists in memory. Bound batch sizes and respect database bind-parameter limits. For large datasets, process across multiple batches instead of `findAll().collectList()`.

### 7.2. When Does Batch Composition Fit?

This approach fits well when:

- You need to keep the customer entity and order list together in a response structure.
- The repository already offers a convenient `findByCustomerIdIn` API.
- Each batch size has a clear upper bound.
- Additional application-level merging is needed where SQL join is awkward.
- Combined data comes from multiple sources or multiple databases.

If both tables live in the same database and only a projection is needed, a SQL join is usually simpler and often more efficient.

## 8. Matching Multiple Data Sources by Key

Reactor has no built-in operator that understands relational keys across two Fluxes and performs a hash join automatically. If you want key-based matching in the application, build a lookup structure or process in batches.

For example, given two streams emitting `Customer` and `Profile`, collect profiles into a map by customer ID and look them up:

```java
Mono<List<CustomerView>> combineCustomersAndProfiles(
        Flux<Customer> customers,
        Flux<Profile> profiles) {

    Mono<List<Customer>> customerList = customers.collectList();
    Mono<Map<Long, Profile>> profileMap = profiles
        .collectMap(Profile::getCustomerId);

    return Mono.zip(customerList, profileMap)
        .map(tuple -> tuple.getT1().stream()
            .map(customer -> new CustomerView(
                customer,
                tuple.getT2().get(customer.getId())
            ))
            .toList());
}
```

This snippet illustrates key-based matching via a map. Define behavior for missing profiles, multiple profiles per customer, or duplicate IDs. `collectMap` keeps only one value per key according to the operator's rules; if a key can have multiple values, use `collectMultimap` or define explicit conflict selection.

This example also materializes both entire streams. Use it only when sizes are bounded. For large sets, batch, use cursors, or push the join to the database.

## 9. When Combining Data Across Multiple Databases or Services

A SQL join cannot directly combine a PostgreSQL table with an HTTP service response or a message broker Publisher. Publisher composition is the natural choice in the application layer.

Example fetching an order from the database and shipping tracking from an external service:

```java
Mono<OrderTrackingView> findTracking(Long orderId) {
    Mono<Order> order = orderRepository.findById(orderId);

    return order.flatMap(value ->
        shippingClient.findTracking(value.getId())
            .map(tracking -> new OrderTrackingView(value, tracking))
    );
}
```

Here the tracking request depends on the order ID, so `flatMap` is the logical composition operator. If the shipping service finds no data, decide whether to return an empty response, an untracked status, or a business error.

With many orders, calling an external service per row creates N+1 HTTP calls. Prefer the external service's batch API if available, or bound concurrency and configure timeouts:

```java
Flux<OrderTrackingView> findTrackings() {
    return orderRepository.findByStatus("SHIPPED")
        .flatMap(order -> shippingClient.findTracking(order.getId())
            .map(tracking -> new OrderTrackingView(order, tracking)), 8);
}
```

Bounded concurrency limits simultaneous requests, though there is still one request per order. If the service supports batch tracking by ID list, a batch API reduces round trips much more effectively.

## 10. Consistency When Running Multiple Publishers

A SQL join usually runs as a single database statement. Its result set follows the database's snapshot/isolation semantics for that statement. By contrast, running two independent queries and composing Publishers can observe data at different points in time.

For example:

1. First query reads customer info.
2. Another transaction updates the customer or adds an order.
3. Second query reads the order list.
4. Application combines the two results into one response.

The response may contain pre-update customer state alongside post-update orders. That may be acceptable for an overview screen, but unsuitable for business workflows requiring a consistent snapshot.

### 10.1. Use Reactive Transactions When Needed

If all Publishers access the same database and require the same transaction, compose them inside a Spring-managed reactive transaction:

```java
@Transactional(readOnly = true)
public Mono<CustomerDetail> findConsistentDetail(Long customerId) {
    Mono<Customer> customer = customerRepository.findById(customerId);

    Mono<List<Order>> orders = orderRepository
        .findByCustomerId(customerId)
        .collectList();

    return Mono.zip(customer, orders)
        .map(tuple -> new CustomerDetail(tuple.getT1(), tuple.getT2()));
}
```

The transaction manager and repositories must share the same `ConnectionFactory` to participate in the same reactive transaction. The database isolation level determines actual consistency; `readOnly = true` does not automatically imply snapshot isolation.

Parallel execution in `Mono.zip` is not always suitable for every transaction manager or driver. If ordering must be guaranteed or the driver restricts single-connection usage within a transaction, consider sequential composition using `flatMap`/`then` and test against the real driver.

### 10.2. You Cannot Create a Shared ACID Transaction Across HTTP Services

An R2DBC reactive transaction does not span an HTTP request to another service. If a use case updates the database and then calls an external service, design consistency using patterns such as outbox, saga, or compensating workflows as needed by the business. `Mono.zip` only combines reactive signals; it does not create a distributed transaction.

## 11. Backpressure, Concurrency, and Resource Hold Time

Publisher composition still obeys Reactive Streams demand, though operators can introduce buffering or concurrent work.

- `zip` coordinates demand across sources to build tuples; overall speed is bounded by the slowest source.
- `flatMap` can subscribe to many inner Publishers simultaneously. Set concurrency limits to control load.
- `concatMap` processes sequentially, lowering concurrency at the cost of potential latency increases.
- `collectList`, `collectMap`, and `collectMultimap` buffer data in memory until sources complete.
- `merge` can emit results from faster sources ahead of slower ones.

If a Publisher holds a database connection, slow downstream consumption can extend connection hold times. If a large Flux triggers many inner queries, the connection pool can saturate. Bound row counts, batch sizes, concurrency, and processing durations.

Example bounded concurrency:

```java
customerRepository.findByActiveTrue()
    .flatMap(this::enrichCustomer, 8);
```

The limit `8` applies to concurrent inner Publishers in this operator. It does not cap the total number of customers emitted. If you need to cap total rows, add SQL conditions/limits or use a paginated API.

## 12. Cancellation and Error Handling When Composing Publishers

When one Publisher in a composition emits an error, operators like `zip` or `flatMap` normally propagate the error downstream and cancel sibling subscriptions per Reactor semantics. When downstream cancels the pipeline, cancellation propagates upstream across supporting components.

Implications for database queries:

- Do not swallow database errors into empty results if the failure should be reported.
- Configure timeouts for external sources that could hang.
- When falling back, only supply default values if business rules permit.
- Ensure resources are released on completion, error, or cancellation.
- Do not call `subscribe()` manually inside a service to launch a detached branch; doing so makes cancellation and error handling harder for callers.

Example intentional fallback for an optional profile:

```java
Mono<Profile> profile = profileClient.findByCustomerId(customerId)
    .onErrorResume(ProfileNotFoundException.class, error -> Mono.empty());

return Mono.zip(customerRepository.findById(customerId),
                profile.defaultIfEmpty(Profile.empty()))
    .map(tuple -> new CustomerView(tuple.getT1(), tuple.getT2()));
```

This example converts only "profile not found" into a default value. Timeouts or database unavailability still propagate to be handled at the appropriate layer.

## 13. Which Approach to Choose for Each Scenario?

| Scenario | Approach to Consider | Reason |
|---|---|---|
| Two tables in the same database with join keys | SQL `JOIN` | Database optimizes the join and reduces round trips |
| Reporting projection across multiple tables | `DatabaseClient` or `@Query` with JOIN | Fetches only needed columns and maps to DTO |
| One customer and their list of orders | JOIN then group, or two queries + `Mono.zip` | Choose based on cardinality, size, and consistency needs |
| Combining database data with an HTTP service | Publisher composition | Sources cannot be queried in a single SQL statement |
| Combining two independent Monos, one value each | `Mono.zip` | Builds a tuple from two single results |
| Pairing two Fluxes by emission index | `Flux.zip` | Only fits when streams align positionally |
| Tracking latest state from multiple sources | `combineLatest` | Emits new state whenever any source updates |
| Calling a dependent Publisher per element | `flatMap` or `concatMap` | Choose concurrency vs. ordering appropriately |
| Combining events from multiple sources | `merge` | Interleaves streams, does not join by key |
| Large datasets requiring key-based linking | SQL JOIN or bounded batch queries | Avoids materializing both full sets in heap |

## 14. Common Mistakes

| Mistake | Consequence | How to Handle |
|---|---|---|
| Using `Flux.zip` to combine customers and orders | Pairs by position, causing mismatched keys | Use SQL JOIN or match explicitly by key |
| Assuming Reactor understands entity relationships | Related data is not auto-loaded | Write explicit JOINs or additional queries |
| Using `flatMap` to run a sub-query for every row | N+1 queries or N+1 HTTP calls | Use JOIN, batch fetch, or batch APIs |
| Unbounded `flatMap` on a large stream | Too many concurrent queries | Set concurrency aligned with pool and downstream |
| Using `collectList()` on unbounded data | Heap grows with entire result set | Paginate or use bounded batches |
| Omitting `ORDER BY` in "first" queries | Selected row is non-deterministic | Add stable ordering and tie-breaker key |
| Using `INNER JOIN` when unmatched rows must be kept | Left rows without matches are dropped | Use `LEFT JOIN` |
| Mapping `LEFT JOIN` right-side columns to primitives | Cannot represent SQL NULL | Use wrapper types or nullable DTOs |
| Missing aliases when tables share column names | Mapper reads the wrong column | Give each column a unique alias |
| Assuming two separate queries share a snapshot | Response may reflect data from two points in time | Use appropriate transactions/isolation when needed |
| Thinking `Mono.zip` creates a shared transaction | `zip` provides no transaction guarantee | Configure reactive transaction manager and shared `ConnectionFactory` |
| Calling `subscribe()` inside a service | Loses control of errors and cancellation | Return the Publisher and compose in the pipeline |
| Using `merge`/`concat` as joins | Results are only interleaved or appended | Pick operators with matching semantics |

## 15. Testing SQL JOINs and Publisher Composition

Both approaches should be tested along different dimensions.

### 15.1. Testing JOINs

Prepare test data covering:

- Customers with multiple orders.
- Customers without orders.
- Orders with different statuses.
- Nullable values on the `LEFT JOIN` side.
- Multiple tables sharing column names such as `id` and `status`.

Verify returned row counts, aliases, DTO mapping, `INNER`/`LEFT JOIN` behavior, and result ordering. For 1-N relationships, confirm the application does not accidentally treat every join row as a distinct customer.

### 15.2. Testing Composition

For `Mono.zip`, verify:

- Both sources emit values.
- One source completes empty.
- One source emits an error.
- One source is slow or times out.
- Fallbacks apply only to permitted error types.

For `flatMap`, verify concurrency, emission ordering where required, inner Publisher errors, and cancellation. For batch composition, verify empty sets, missing IDs, duplicate IDs, and size limits.

Example testing a `Mono.zip` result:

```java
StepVerifier.create(customerService.findCustomerDetail(10L))
    .assertNext(detail -> {
        assertEquals(10L, detail.customer().getId());
        assertNotNull(detail.orders());
    })
    .verifyComplete();
```

### 15.3. Testing Consistency and Performance

If business rules require a consistent snapshot, test transactions on the real database or a compatible database with the deployed isolation level. Measure SQL statement count, round trips, query latency, connection hold time, heap usage, and pending acquire metrics to compare JOINs against batch composition.

Do not benchmark solely with a single run over a few rows. Use realistic data volumes and simulate concurrent requests.

## 16. Decision Workflow

When data from multiple sources is needed, evaluate in order:

1. Are all sources in the same database and accessible from a single SQL statement?
2. Are there clear keys or relational conditions to JOIN on?
3. Do you need a flat projection per row pair or a parent object with a child list?
4. If using multiple Publishers, does each source return one value or many values?
5. Do you need key-based matching, or positional/latest-state pairing?
6. Is there a risk of N+1 queries or N+1 HTTP calls?
7. Is a consistent snapshot required across sources?
8. What limits are needed on batch size, concurrency, timeouts, and memory?
9. Does behavior when one source is empty or errors match business rules?
10. Have cancellation and resource cleanup been tested?

## 17. Principles to Remember

- SQL `JOIN` matches rows by relational predicates in the database; Reactor composition combines Publishers in the application layer.
- `Mono.zip` and `Flux.zip` pair by emission position, never automatically by foreign keys.
- `combineLatest` combines latest states; `merge` interleaves streams; `concat` appends streams.
- `flatMap` invokes a dependent Publisher per element; configure concurrency to control load and watch for N+1.
- `concatMap` preserves sequential processing order, usually trading off lower throughput.
- For tables in the same database, prefer SQL JOIN when it represents a natural relational link that the database can optimize.
- Use Publisher composition when sources are independent, across databases or external services, or when workflows orchestrate multiple operations.
- For one-to-many relationships, define clearly how rows are grouped and how nullable sides are handled.
- Batch fetching reduces N+1, but batch sizes and memory usage must be bounded.
- Multiple separate queries can observe data at different times; use reactive transactions/isolation when consistency is needed.
- `Mono.zip` does not create distributed transactions and cannot span HTTP services.
- Return Publishers to callers; never call `subscribe()` or `block()` arbitrarily inside services.
- Test round trips, cardinality, errors, cancellation, ordering, and resource usage on the real driver and database.

SQL joins and Publisher composition both play essential roles in Spring Data Relational R2DBC, but they are not interchangeable. Use joins to let the database combine related rows within a single data source; use Publisher composition to let the application orchestrate independent results and heterogeneous sources. By choosing the right semantics and controlling N+1 queries, cardinality, transactions, and concurrency, the data access layer stays clearer and avoids unnecessary overhead.
