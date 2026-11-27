# Detecting Repeated Queries When Loading Aggregate Lists in Spring Data JDBC

## 1. Why Observe Query Counts When Loading Aggregates?

A list screen often loads multiple aggregate roots at once. For example, an orders page displays a list of orders along with each order's line items. At the Java layer, the repository call can look very simple:

~~~java
List<Order> orders = orderRepository.findAll();
~~~

However, a single repository call does not necessarily generate a single SELECT statement. Spring Data JDBC loads aggregates according to its mapping. If an aggregate root references child collections, the framework may execute additional queries to fetch data for those collections.

With traditional loading, the process can be:

1. SELECT the list of aggregate roots.
2. For each root, SELECT the entities belonging to the first collection.
3. For each root, SELECT the entities belonging to the second collection, if present.
4. Assemble the results into complete aggregates.

As the number of aggregates grows, the number of SQL statements can grow linearly with the number of roots. This pattern is commonly called an **N+1 query**.

It is important to identify this query pattern from SQL logs, query metrics, and processing time. Looking only at `findAll()` in code is not enough to conclude how many SQL statements the application is executing.

## 2. Traditional Aggregate Loading in Spring Data JDBC

Suppose we have an order aggregate:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String orderNumber;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;

    // constructors, getters...
}
~~~

Child entity:

~~~java
@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    private String sku;

    private int quantity;

    // constructors, getters...
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends CrudRepository<Order, Long> {
}
~~~

When calling `orderRepository.findAll()` under traditional loading, the SQL may look like:

~~~sql
SELECT id, order_number, status
FROM orders
ORDER BY id;
~~~

Then, for each order, the framework fetches the order lines:

~~~sql
SELECT id, order_id, sku, quantity
FROM order_lines
WHERE order_id = ?;
~~~

If there are 3 orders, the log may show:

~~~text
SELECT ... FROM orders;

SELECT ... FROM order_lines WHERE order_id = 101;
SELECT ... FROM order_lines WHERE order_id = 102;
SELECT ... FROM order_lines WHERE order_id = 103;
~~~

This is the pattern of one query fetching roots plus one collection query per root.

### 2.1. Query Count Formula

Let:

- N be the number of aggregate roots loaded.
- K be the number of direct collection paths loaded separately per aggregate.
- Qroot be the number of queries fetching aggregate roots, typically 1 for a single list load.

In the simple case, the approximate number of queries is:

\[
Q = Q_{root} + N \times K
\]

If there is only one collection:

\[
Q = 1 + N
\]

If there are two collections loaded separately:

\[
Q = 1 + 2N
\]

For example:

| Aggregate roots | One collection | Two collections |
|---:|---:|---:|
| 1 | 2 | 3 |
| 10 | 11 | 21 |
| 50 | 51 | 101 |
| 100 | 101 | 201 |

This is a model for recognizing trends, not a guarantee of exact statement counts for every mapping. Nested aggregates, additional application queries, and other loading paths can alter the count. Confirm using SQL logs against the actual aggregate and running version.

## 3. N+1 in Spring Data JDBC Differs from ORM Lazy Loading

Spring Data JDBC manages aggregates by aggregate boundaries. When loading an aggregate, the framework builds the required object graph according to the mapping. Repeated queries can happen during the materialization of the aggregate list itself, because referenced entities are loaded with separate statements.

Do not assume that a child query only runs when code calls a collection getter as in some ORMs with lazy-loading proxies. Observe when statements appear during the request and inspect the corresponding call stack.

Also distinguish two patterns:

**Pattern A — Traditional aggregate loading**

~~~java
List<Order> orders = orderRepository.findAll();
~~~

One query loads roots, then the framework loads collections for each root.

**Pattern B — Application calling a repository inside a loop**

~~~java
List<Long> ids = findOrderIds();

List<Order> orders = new ArrayList<>();

for (Long id : ids) {
    orders.add(orderRepository.findById(id).orElseThrow());
}
~~~

Here, the application explicitly calls `findById` multiple times. Even if the aggregate has no child collections, the root query count still scales with the number of IDs.

Both patterns can appear together in the same request. So when you see many similar SELECTs, determine whether they come from relation loading or from a loop in a service/controller.

## 4. Signs of N+1 in SQL Logs

A strong indicator is the same SQL template executing many times, differing only by the bound parent aggregate ID parameter.

Example log:

~~~text
Executing SQL:
SELECT id, order_number, status FROM orders

Executing SQL:
SELECT id, order_id, sku, quantity
FROM order_lines WHERE order_id = ?
Parameters: [101]

Executing SQL:
SELECT id, order_id, sku, quantity
FROM order_lines WHERE order_id = ?
Parameters: [102]

Executing SQL:
SELECT id, order_id, sku, quantity
FROM order_lines WHERE order_id = ?
Parameters: [103]
~~~

Watch for three characteristics:

1. There is a SELECT fetching the list of roots.
2. Another SELECT repeats with the exact same SQL structure.
3. Bound parameter values vary by each root's ID.

If the number of child SELECT executions scales roughly with the number of roots, that is an N+1 signal.

### 4.1. Comparing Query Counts Across Page Sizes

A useful test is loading the same endpoint with different page sizes:

| Page size | Observed queries | Notes |
|---:|---:|---|
| 1 | 2 | One root query and one child query |
| 10 | 11 | Child query repeats per root |
| 50 | 51 | Statement count grows with page size |

If the query count scales nearly linearly like this, inspect how collections are loaded.

You do not need to use the exact numbers in the table. The goal is to compare query growth as N increases while keeping filters and aggregate structure constant.

### 4.2. Distinguishing Repeated Queries from Valid Queries

Not every repeated or similar SQL statement is N+1:

- One root query and one count query to construct a `Page` can be expected behavior.
- One data query and one permission-check query may be two distinct parts of a use case.
- A batch may execute the same SQL template multiple times by design.
- A loop calling `findById` produces N queries caused by application code, not collection loading.

Group statements by SQL fingerprint/template, count executions, record bind values, and correlate with traces/requests. Do not just count total log lines.

## 5. Enabling SQL Logging to Observe Queries

With Spring JDBC, you can enable SQL logging at DEBUG level:

~~~properties
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
~~~

To observe bound parameters, you can enable TRACE:

~~~properties
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
~~~

Example logging configuration:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

The `JdbcTemplate` logger reveals SQL executed through Spring JDBC. The parameter logger helps inspect bind values during diagnosis.

Do not leave bind parameter logging broadly enabled in production if values may contain sensitive information. Use it briefly in test environments or under controlled logging policies, and turn it off once investigation is complete.

If default logs are not detailed enough, you can use JDBC observability tools such as P6Spy or datasource-proxy to record:

- SQL statements and parameters.
- Execution time.
- Statement invocation count.
- Connection/request context.
- Total query count within a use case.

A DataSource proxy tool is especially useful when counting queries per request or writing assertions in integration tests.

## 6. Measuring Query Count for a Single Use Case

Do not measure the entire application and extrapolate to a single endpoint. Pick one concrete use case, such as an API listing orders.

Measurement steps:

1. Create test data with a known number of aggregates.
2. Call the exact service/controller method under observation.
3. Count SELECTs by SQL fingerprint.
4. Separate root queries, child queries, count queries, and other queries.
5. Repeat with different numbers of roots.
6. Compare query count, total SQL time, and total request time.

Example data:

~~~text
orders:
  id 101
  id 102
  id 103

order_lines:
  order_id 101 -> 2 rows
  order_id 102 -> 3 rows
  order_id 103 -> 1 row
~~~

With traditional loading, the number of child rows does not directly determine the number of child queries. A SELECT loading one root's collection may return 0, 1, or many rows, yet the statement still executes for that root.

This is why query count and row count should be tracked separately. One query can return many rows; many queries can each return only one row.

## 7. Tracing the Source of Repeated Queries

Once you observe repeated SQL, trace back to the source generating the statements.

### 7.1. Collection Queries During Aggregate Assembly

Signs:

- One SELECT fetches aggregate roots.
- Collection SELECTs repeat with different parent IDs.
- There is no obvious repository loop in the service.
- Query count grows as the root list grows.

This is the traditional aggregate loading pattern.

### 7.2. Repository Methods Called Inside a Loop

Example:

~~~java
for (Long customerId : customerIds) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow();
    // Process customer.
}
~~~

If you only need to load customers for a list of IDs, use the batch-lookup API:

~~~java
Iterable<Customer> customers =
        customerRepository.findAllById(customerIds);
~~~

`findAllById` sends a set of IDs in a single repository operation. Actual SQL still depends on store strategy, bind parameter limits, and how aggregates with collections are loaded, but it avoids the application-layer anti-pattern of calling a repository method per ID.

### 7.3. Services Calling Repositories Inside Mappers or Serializers

A DTO mapper or getter might call a service/repository to enrich each item. When converting a list to a response, the query count can scale with the item count.

Example to avoid:

~~~java
List<OrderResponse> responses = orders.stream()
        .map(order -> new OrderResponse(
                order.getId(),
                customerRepository.findById(order.getCustomerId())
                        .orElseThrow()
                        .getName()
        ))
        .toList();
~~~

Identify queries emitted during response mapping. You can batch-load the customer IDs upfront, build a map by ID, and construct DTOs from that map.

### 7.4. Listeners or Callbacks Querying Additional Data

Lifecycle event listeners may run when an aggregate is loaded and may invoke additional repositories. If logs show queries appearing after aggregates are assembled, check listeners, callbacks, and beans observing entities.

A listener that only logs will not necessarily emit extra SQL. However, a listener that queries extra information can create another chain of queries.

## 8. Single Query Loading in Spring Data JDBC

Since Spring Data JDBC 3.2, the framework provides **Single Query Loading** to load multiple aggregates along with their collections in a single SQL statement in supported scenarios.

Instead of:

~~~text
SELECT orders
SELECT order_lines WHERE order_id = 101
SELECT order_lines WHERE order_id = 102
SELECT order_lines WHERE order_id = 103
~~~

Single Query Loading can construct the aggregate results using a single SQL query. The implementation uses window functions such as `row_number()` and `count(*)` to represent child collections in one result set without creating unnecessary cross products between collections.

Reference: https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/

### 8.1. Enabling Single Query Loading

The property is configured on `JdbcMappingContext`/`RelationalMappingContext`:

~~~java
mappingContext.setSingleQueryLoadingEnabled(true);
~~~

If the application uses explicit Java-based JDBC configuration extending `AbstractJdbcConfiguration`, you can customize the existing mapping context bean:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.core.convert.JdbcCustomConversions;
import org.springframework.data.jdbc.core.mapping.JdbcMappingContext;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.relational.core.mapping.NamingStrategy;
import org.springframework.data.relational.core.mapping.RelationalManagedTypes;

@Configuration
@EnableJdbcRepositories
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    @Bean
    public JdbcMappingContext jdbcMappingContext(
            Optional<NamingStrategy> namingStrategy,
            JdbcCustomConversions customConversions,
            RelationalManagedTypes jdbcManagedTypes
    ) {
        JdbcMappingContext context = super.jdbcMappingContext(
                namingStrategy,
                customConversions,
                jdbcManagedTypes
        );

        context.setSingleQueryLoadingEnabled(true);

        return context;
    }
}
~~~

This example applies when the application owns its JDBC configuration via Java configuration. If Spring Boot auto-creates the mapping context or the project already has a configuration class extending `AbstractJdbcConfiguration`, customize the existing bean in line with your application structure. Do not register a second `JdbcMappingContext` just to enable the flag, because converters and aggregate operations must share the same mapping context.

### 8.2. Support Conditions

Single Query Loading has limitations to check before expecting query counts to drop:

| Condition | Limitation |
|---|---|
| Version | Available since Spring Data JDBC 3.2 |
| Collections | Aggregate has no nested collections; this restriction includes Map |
| Embedded/references | Aggregate does not use AggregateReference or embedded entities |
| Database dialect | Dialect must support analytic/window functions; Spring Data JDBC built-in dialects except H2 and HSQL support them |
| Repository methods | Applies only to CrudRepository find methods; derived queries and annotated queries are currently outside its scope |
| Configuration | `setSingleQueryLoadingEnabled(true)` must be enabled |

If any condition is not met, Spring Data JDBC falls back to the default aggregate loading strategy. Therefore, enabling the flag alone is not proof that an endpoint uses Single Query Loading.

The Spring Data Relational documentation still describes this feature as experimental. Test against your actual database/dialect and inspect SQL logs after enabling it.

Documentation: https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html

### 8.3. H2 and HSQL in Tests

H2 and HSQL do not support the analytic/window functions needed by this mechanism under the dialects provided by Spring Data JDBC. As a result, tests running on these two databases may fall back to default loading.

If your goal is to verify that Single Query Loading works, run integration tests against a database with a supported dialect, such as PostgreSQL, MySQL, or another DBMS supported by your project's Spring Data JDBC version.

Do not conclude the feature does not work solely from test results on H2/HSQL. Likewise, do not conclude it is active merely because setting the flag produces no error.

## 9. Reducing Costs When Single Query Loading Cannot Be Used

Not every aggregate satisfies Single Query Loading requirements. Other options include:

### 9.1. Limiting the Number of Aggregates Loaded at Once

Use pagination to load only a subset of roots per request:

~~~java
public interface OrderRepository
        extends CrudRepository<Order, Long>,
                PagingAndSortingRepository<Order, Long> {
}

Page<Order> page = orderRepository.findAll(
        PageRequest.of(0, 20, Sort.by("id").descending())
);
~~~

Pagination does not eliminate N+1 under traditional loading. However, it bounds N per request and keeps collection query costs more manageable.

Do not load an entire table to serve a list screen if users only view one page of data.

### 9.2. Loading Only the Data the Screen Needs

A list screen might only need order ID, order number, status, created date, and total amount. If it does not need every `OrderLine`, you do not necessarily have to load full aggregates for the list view. You can create a custom repository query returning a DTO/read model with just the required columns.

Example projection:

~~~java
public record OrderListItem(
        Long id,
        String orderNumber,
        String status,
        BigDecimal totalAmount
) {}
~~~

A custom query can compute the total amount in the database and return `OrderListItem` directly. This avoids constructing an entire object graph just to render a table.

Keep the boundary clear: custom queries serve read models/list views; business operations requiring full aggregates can continue using aggregate repositories.

### 9.3. Batch-Loading Child Data by Parent ID List

When child data is needed for display but Single Query Loading does not fit, you can load roots first and then fetch all child rows in a single query using the list of parent IDs.

Illustrative SQL:

~~~sql
SELECT id, order_id, sku, quantity
FROM order_lines
WHERE order_id IN (:orderIds)
ORDER BY order_id, id;
~~~

Then group results by `order_id` in Java:

~~~java
Map<Long, List<OrderLineView>> linesByOrderId =
        lineViews.stream().collect(
                Collectors.groupingBy(OrderLineView::orderId)
        );
~~~

This turns N child queries into one batch query for the whole page. It fits read models or custom repository fragments. If assembling full aggregates manually, you must handle mapping, collection ordering, transaction consistency, and property paths properly; do not bypass Spring Data JDBC aggregate semantics carelessly.

For very large ID lists, check the database/driver bind parameter limit and split into appropriate batches.

### 9.4. Avoiding Per-Aggregate Queries in Loops

If you already have a list of IDs, prefer a single `findAllById` operation over calling `findById` repeatedly.

If related data belongs to a different aggregate, you can batch-load those aggregates by ID set and build a lookup map. Only do this when they are truly independent aggregates; do not split child entities belonging to the same aggregate into separate aggregates just to dodge query counts.

### 9.5. Being Careful When Joining Multiple Collections

A query joining a root with one collection can reduce round-trips. However, joining multiple one-to-many collections can produce a cross product.

For example, an order has 4 order lines and 3 status history entries. Joining both collections can return 12 rows for that single order. As child data grows, intermediate row counts and duplicated data can become huge.

Single Query Loading uses a result-set strategy with window functions to avoid this naive cross-product multiplication. If you write JOINs manually, measure returned row counts and network data volume, not just statement count.

## 10. Query Count Is Not the Only Performance Metric

Reducing SQL counts usually lowers round-trips and overhead, yet a single query can still be very slow.

Track at least these metrics:

| Metric | Question to answer |
|---|---|
| Query count | How many statements does one request emit? |
| SQL fingerprint frequency | Which statements are executed repeatedly? |
| Total database time | How long is spent waiting on the database in total? |
| Slowest statement | Which statement has the highest latency? |
| Rows returned | How many rows does each query return? |
| Rows scanned | How many rows must the database read to find results? |
| Payload size | Is too much duplicate data transferred over the network? |
| Request latency | How long does the user actually wait? |
| Connection usage | How long does the request hold a connection? |

For example:

- 100 very fast queries still incur round-trip overhead per query.
- 1 JOIN query returning 100,000 rows can also be slow and memory-intensive.
- 1 query with a non-indexed predicate can scan an entire table.
- Low query count paired with heavy Java work in entity callbacks/listeners can still make a request slow.

Use query plans such as `EXPLAIN` or your database's equivalent tool to evaluate slow statements. Check indexes on collection foreign keys, such as `order_lines(order_id)`, when queries frequently filter by parent ID.

## 11. Lifecycle Events Can Also Affect Load Time

Spring Data JDBC publishes lifecycle events for aggregates. The official documentation notes that lifecycle events can be expensive and affect performance when loading large result sets.

If query counts are already good yet aggregate materialization time remains high, check:

- Does a listener perform heavy processing?
- Does a listener invoke a repository to load extra data?
- Does a listener log full entities or serialize large objects?
- Does a callback perform expensive computations or access external resources?

`JdbcAggregateTemplate` provides `setEntityLifecycleEventsEnabled(false)` to disable publishing lifecycle events when appropriate. This choice affects application event semantics, so only use it after confirming listeners do not need to run on that read path.

Do not confuse lifecycle events with entity callbacks. Spring Data JDBC uses callbacks for features like auditing; disabling event publication does not mean disabling all entity callbacks.

Documentation: https://docs.spring.io/spring-data/relational/reference/jdbc/events.html

## 12. Designing Tests to Catch N+1

An integration test can verify query count trends as aggregate counts increase. Use a DataSource proxy or statement-counting tool to capture query counts within a repository call scope.

Example test cases to include:

1. Create 1 aggregate root with a child collection.
2. Count queries when calling `findAll`.
3. Create 10 aggregate roots with the same structure.
4. Count queries when calling `findAll` again.
5. Compare query counts and identify which statements repeat.

Illustrative results with traditional loading and one collection:

| Data | Root SELECT | Child SELECT | Total |
|---|---:|---:|---:|
| 1 root | 1 | 1 | 2 |
| 10 roots | 1 | 10 | 11 |
| 50 roots | 1 | 50 | 51 |

If Single Query Loading is enabled and the aggregate meets the conditions, re-check statement counts. Do not assert only an absolute total query count if the test framework also runs setup, cleanup, or count SQL. Filter by the SQL fingerprint of the use case.

### 12.1. Testing on the Target Database

Factors that can differ between H2 and a production database:

- Window function support.
- SQL dialect and query generation.
- Query planner and indexes.
- Driver behavior.
- Data types and collations.

Use Testcontainers or a database integration environment using the same DBMS as production when testing performance and Single Query Loading.

### 12.2. Do Not Let Tests Depend on Absolute Wall-Clock Time

Avoid tests such as "request must finish under 50 ms" across all machines. Elapsed time depends on CPU, database, container, and CI environment.

For detecting N+1, checking statement counts per SQL fingerprint and scaling trends with N is much more stable than checking a hard latency threshold. Performance benchmarks can measure latency separately in controlled environments.

## 13. Workflow for Investigating a Slow Endpoint

When an endpoint loading a list of aggregates is slow, proceed in order:

1. Identify the repository/service method generating the list.
2. Enable SQL logging or DataSource query tracing in a test environment.
3. Group SQL statements by fingerprint and count executions.
4. Check which SELECT repeats per parent ID.
5. Try increasing page size while keeping filters unchanged.
6. Distinguish relation loading from repository calls inside loops.
7. Measure total database time, per-statement latency, and returned row counts.
8. Inspect `JdbcMappingContext` and Single Query Loading conditions.
9. If the feature does not apply, consider pagination, projections, or batch-loading child rows.
10. Re-measure with the same dataset and scenario to confirm the change actually reduces query count/latency.

Do not optimize based on query count alone. Also review returned rows, indexes, query plans, and object graph construction cost.

## 14. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| `findAll` is one line of code yet emits many SELECTs | Aggregate has collections loaded separately per root | Group SQL by fingerprint and check for N+1 |
| Same child SELECT repeats with different parent IDs | Traditional collection loading mechanism | Evaluate Single Query Loading or batch loading |
| Query count grows with page size | Statements are executed per aggregate | Identify relation paths and bound root count |
| Calling `findById` many times | Service or mapper calls repository inside a loop | Use `findAllById` or a batch query |
| Single Query Loading enabled yet queries still repeat | Aggregate/method/dialect does not meet conditions | Check limitations and verify SQL logs |
| H2 test still shows N+1 | H2 lacks analytic functions required by Single Query Loading | Test on a supported database dialect |
| Low query count yet slow request | Heavy query, too many rows returned, or slow Java mapping/listeners | Measure DB time, rows, payload, and lifecycle listeners |
| JOIN reduces queries yet returns huge row count | Cross product across multiple collections | Measure intermediate rows; consider Single Query Loading or batch fetch |
| Pagination enabled yet N+1 persists | Pagination only bounds N, does not change load strategy | Combine pagination with an appropriate loading strategy |
| DTO mapping emits extra SELECTs | Mapper calls repository per item | Batch-load referenced data before building DTOs |
| SQL log omits full parameters | Appropriate logger not enabled or different proxy needed | Use JDBC logging/DataSource proxy |
| Flaky query count tests | Counting setup/cleanup SQL or auxiliary test queries | Scope counting and filter by SQL fingerprint |
| Disabled lifecycle events yet callbacks still run | Confusing event publication with entity callbacks | Distinguish the two mechanisms and keep required callbacks |

## 15. Practice Exercises

### Exercise 1 — Observing Aggregate Loading

Create `Order` with `List<OrderLine>`. Call `findAll()` with 1, 10, and 50 roots. Enable SQL logging and record how many times the `order_lines` SELECT executes.

### Exercise 2 — Computing Query Growth

Create an aggregate with two independent collections. Compare query counts for 1, 10, and 20 aggregates. Compare measurements against the approximate formula 1 + N × K.

### Exercise 3 — Distinguishing Two Sources of N+1

Write a service calling `findById` in a loop. Then replace it with `findAllById`. Compare the logs against a single `findAll` loading an aggregate with a child collection.

### Exercise 4 — Enabling Single Query Loading

Use Spring Data JDBC 3.2+ and a database supporting window functions. Enable `setSingleQueryLoadingEnabled(true)`, call `CrudRepository.findAll()`, and inspect the SQL. Verify that the exercise aggregate satisfies the constraints.

### Exercise 5 — Checking Fallback

Add a nested collection or use a derived query. Observe default loading when Single Query Loading cannot be applied. Record which condition triggers the fallback.

### Exercise 6 — Batch-Loading for List Views

Create a DTO containing only the order info and line items needed for display. Run one query fetching child rows for the list of order IDs, group results by parent ID, and compare against traditional aggregate loading.

### Exercise 7 — Evaluating Multi-Collection JOINs

Write a query joining `orders`, `order_lines`, and `order_events`. Create data with multiple order lines and multiple events per order. Measure result-set row counts to identify the cross product.

### Exercise 8 — Measuring Lifecycle Listeners

Add an `AfterConvertEvent` listener with light processing, then simulate a listener executing an auxiliary query. Measure query count and latency. Determine the listener's impact on the aggregate loading path.

## 16. Key Takeaways

- Loading a list of aggregates with child collections can produce N+1 queries under Spring Data JDBC's traditional loading.
- The common pattern is one root SELECT followed by the same collection SELECT repeated with different parent IDs.
- With one collection, query count is roughly 1 + N; with K separately loaded collection paths, it can approach 1 + N × K.
- Spring Data JDBC builds the aggregate during loading; do not automatically attribute this to lazy-loading proxies as in some ORMs.
- Enable SQL logging or DataSource query tracing to group statements by fingerprint and count executions.
- Distinguish relation loading from loops calling `findById`, DTO mappers, or listeners issuing their own queries.
- Single Query Loading is available from Spring Data JDBC 3.2, must be enabled on the mapping context, and only applies when the aggregate, repository method, and database meet its constraints.
- Single Query Loading is currently documented as experimental; if conditions are not met, the framework falls back to default loading.
- Pagination bounds aggregate count but does not eliminate N+1 by itself; projections and batch-loading can suit list views.
- Query count does not replace latency, query plans, returned rows, payload size, and object-graph materialization cost.
- Lifecycle events can add overhead when loading large result sets; distinguish event publication from entity callbacks before changing configuration.

## References

- [Spring Data Relational — Persisting Entities and Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Blog — Introducing Single Query Loading](https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/)
- [RelationalMappingContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/RelationalMappingContext.html)
- [JdbcMappingContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/JdbcMappingContext.html)
- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html)
- [JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html)
