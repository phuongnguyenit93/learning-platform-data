# Identifying N+1 Queries from SQL Counts and Query Shapes

## 1. What Is an N+1 Query?

N+1 is a performance problem that occurs when an application executes one query to fetch a list of parent entities, and then issues a similar additional query for each entity to load related data.

For example: a customer list page displays each customer's order count. The application fetches 100 customers with one SELECT statement, and then when calling `customer.getOrders().size()`, Hibernate loads the order collection separately for each customer.

Without caching or a batching mechanism, the number of SELECT statements can be:

- 1 query to fetch the customer list.
- N queries to fetch orders for N customers.
- Total: 1 + N queries.

With N = 100, the application may issue 101 SELECT statements just to display one page. If the database resides on another server, the network round-trip cost is often much larger than the Java processing time.

N+1 does not happen only with `OneToMany` relationships. It can also occur when accessing a lazy `ManyToOne` or `OneToOne` on each entity, or when a loop calls a repository method for each element.

Key point: N+1 is an execution pattern recognizable by **the number of SQL statements growing with entity count** and **a repeating SQL shape**, rather than merely "having many queries".

## 2. Example Producing N+1 with JPA

### 2.1. Entity Mapping

Suppose each customer has multiple orders:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }
}
```

Order entity:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
```

The `orders` collection is configured as LAZY. Hibernate typically does not load orders when querying `Customer`. When the code accesses the collection for the first time, Hibernate issues SQL to load the related data.

### 2.2. Code Prone to N+1

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Service:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<String> customerOrderCounts() {
        List<Customer> customers = repository.findAll();

        return customers.stream()
            .map(customer ->
                customer.getName() + ": " + customer.getOrders().size()
            )
            .toList();
    }
}
```

If there are N customers and each collection is not yet loaded, the query flow is typically:

1. `findAll()` fetches the list of `Customer`s.
2. First call to `getOrders()` for the 1st `Customer`: loads orders for that customer.
3. First call to `getOrders()` for the 2nd `Customer`: runs another SELECT.
4. Continues for each remaining `Customer`.

With N customers, there can be 1 + N SELECT statements. How many orders each person has does not change the number of collection loads in this manner; each collection is loaded by a separate query, whether it has 0 or many elements.

A lazy collection must be accessed within a transaction; if the persistence context has already closed, Hibernate may throw `LazyInitializationException` at this point.

## 3. Identifying via SQL Query Counts

### 3.1. Counting Queries per Use Case

Start by identifying a specific operation, for example:

- Opening the customer list page.
- Viewing details of a single order.
- Loading a product list along with category names.
- Building a response DTO with fields from lazy relationships.

Then measure the number of SQL statements issued within the scope of that operation. If the query count grows nearly linearly with the number of parent entities, investigate for N+1.

Example measurement results:

| Customer Count | Queries for Customer | Queries for Orders | Total SELECTs |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 2 |
| 10 | 1 | 10 | 11 |
| 50 | 1 | 50 | 51 |
| 100 | 1 | 100 | 101 |

This table is an example for an uncached lazy collection accessed on every `Customer`. These are not fixed numbers for every mapping or provider.

A strong indicator is when increasing entity count from 10 to 100 increases secondary queries from 10 to 100. A well-designed consolidated query usually keeps the SQL count roughly constant as returned rows increase, even though data volume and read time may still grow.

### 3.2. Do Not Look Only at Total Query Count

A single request can legitimately run multiple different queries: fetching the current user, permissions, configuration, primary data, and secondary data. A high total query count alone is not enough to conclude N+1.

Ask:

- Is there an initial query fetching a list of root entities?
- Does the same SQL statement then run repeatedly?
- Does each repetition change only a bind parameter such as `customer_id`?
- Is the repetition count close to the number of loaded entities?
- Which property/association access triggers the queries?

If there is 1 query for the `Customer` list and 100 nearly identical queries filtering by different `customer_id` values, that is a classic sign.

### 3.3. Distinguish Query Count from Returned Row Count

One query can return thousands of rows and still be a single statement. Conversely, 100 queries each returning a few rows can cause many round-trips.

Measure at least:
- Number of SQL executions.
- Total database time.
- Connection acquisition wait time.
- Returned row count and data size.
- Entity/DTO mapping time.
- Number of queries repeating the same pattern.

N+1 is usually an issue of round-trip count and repeated execution overhead, not just total row count.

## 4. Identifying via SQL Shape

### 4.1. First Query Fetching Root Entities

The initial SQL might look like:

```sql
select
    c.id,
    c.name
from customer c
where c.name is not null;
```

This query fetches N customers. Looking at this SQL alone reveals no problem.

### 4.2. Repeated Queries Fetching the Association

Hibernate may then issue many similar statements:

```sql
select
    o.id,
    o.order_number,
    o.customer_id
from purchase_order o
where o.customer_id = ?;
```

In the logs, the same SQL appears multiple times with different bind parameters:

```text
/* illustrative query */
where o.customer_id = 10

/* same SQL shape */
where o.customer_id = 11

/* same SQL shape */
where o.customer_id = 12

/* ... continues for each customer */
```

Identifying characteristics:
- Same table and same column list.
- Same WHERE condition.
- Only bind parameter values change.
- SQL statement executes repeatedly within the same request/use case.
- Repetition count increases with the number of parent entities iterated.

SQL logs may show `?` placeholders every time while bind values are written to a separate logger. Therefore, inspect both SQL statements and bind parameters when you need to confirm which entity's association each query is loading.

### 4.3. Identifying N+1 with ManyToOne

Suppose an `Order` list needs to display `Customer` names. A `@ManyToOne(fetch = LAZY)` mapping might generate:

```sql
select
    o.id,
    o.order_number,
    o.customer_id
from purchase_order o;
```

Then, when the code calls `order.getCustomer().getName()`, Hibernate may load each `Customer` by ID:

```sql
select c.id, c.name
from customer c
where c.id = ?;
```

If the list contains many `Order`s referencing different `Customer`s and proxies are uninitialized, additional SELECTs may repeat per accessed `Customer`. If many `Order`s reference the same `Customer` within the same persistence context, the first-level cache can reduce queries for already-loaded IDs; thus, actual query counts depend on foreign key distribution and caching.

### 4.4. SQL Shapes Can Vary

Not all N+1 queries produce identical character-for-character SQL. SQL may differ due to:
- Different associations.
- Entity inheritance or discriminators.
- Filter/tenant conditions.
- Batch fetching or fetch modes.
- Provider/dialect and Hibernate version.
- Queries generated from repositories, lazy proxies, or serialization.

Compare normalized SQL shapes: tables, joins, predicates, placeholder counts, and data intent. Do not search only for exact string matches.

## 5. Enabling SQL Logging in Spring Boot and Hibernate

### 5.1. Displaying SQL

With Spring Boot:

```yaml
spring:
  jpa:
    show-sql: false

logging:
  level:
    org.hibernate.SQL: DEBUG
```

Using a logger instead of `show-sql` lets you control output via the logging framework, filter by package, and send logs to observability systems. Avoid enabling multiple SQL logging mechanisms simultaneously if they print the same statement twice.

### 5.2. Displaying Bind Parameters with Hibernate 6

To see which ID each repeated query passes:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Hibernate 6 uses the `org.hibernate.orm.jdbc.bind` category to log bind values. With Hibernate 5, the commonly used logger is `org.hibernate.type.descriptor.sql.BasicBinder`. Logger names depend on version, so use the category matching your actual dependency.

Bind logs may contain names, emails, identifiers, or sensitive data. Enable TRACE only in development/test environments or during controlled investigations; do not expose bind values in production logs without proper data protection policies.

### 5.3. SQL Logs Are Not the Only Measurement Tool

SQL logs are useful for seeing query shapes, but they do not always provide:
- Exact database execution time.
- Connection wait time.
- Actual rows read/written.
- Execution plans.
- Normalized query fingerprints.

Combine logs with a datasource proxy, APM, Hibernate statistics, and database monitoring tools for fuller evidence.

## 6. Using Hibernate Statistics to Count Statements

### 6.1. Enabling Statistics

In Spring Boot configuration:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

Hibernate statistics can report prepared statement counts, entity loads, collection fetches, and other metrics.

You can obtain `Statistics` from `SessionFactory`:

```java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();

long statements = statistics.getPrepareStatementCount();
long entityLoads = statistics.getEntityLoadCount();
long collectionFetches = statistics.getCollectionFetchCount();
```

Key Hibernate imports:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
```

`getPrepareStatementCount()` is the number of prepared statements recorded by Hibernate within the statistics scope. It is a useful before/after comparison metric, though it does not necessarily equal the number of network round-trips or queries observed by every database tool. Understand the metric and reset timing accurately.

### 6.2. Measuring a Use Case in Tests

Integration test example:

```java
@SpringBootTest
class CustomerQueryTest {

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Autowired
    private CustomerService customerService;

    @Test
    void measuresStatementsForCustomerOrderCounts() {
        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();

        // Fixtures must be created and committed before measuring.
        statistics.clear();

        List<String> result =
            customerService.customerOrderCounts();

        assertThat(result).isNotEmpty();

        long statementCount =
            statistics.getPrepareStatementCount();

        System.out.println("Prepared statements: " + statementCount);
    }
}
```

This is an illustrative skeleton; the test needs to prepare fixture data before resetting statistics and ensure the service runs through a transaction/persistence context like production.

`SessionFactory` statistics are shared across threads. If multiple tests or requests run concurrently, other queries may increment the counter during measurement. For accurate measurement, run tests in isolation or use a request/connection-scoped capture tool rather than relying on a global counter under concurrency.

### 6.3. Measuring Before and After Fixing

A valid measurement must keep constant:
- Same dataset and entity count.
- Same use case and inputs.
- Same transaction boundaries.
- Same cache state.
- Same provider, dialect, and fetch configuration.
- Same statement-counting method.

For example, before the fix there were 1 + 100 statements; after the fix there are 2 statements. That is strong evidence that query fan-out has been reduced for that dataset. Still, verify result contents, returned row counts, and actual latency.

## 7. Caching Can Hide N+1

### 7.1. First-Level Cache

Each persistence context/`EntityManager` has a first-level cache. When an entity with the same ID is already managed, accessing that entity again within the same context typically does not need a new SELECT.

Therefore, if many `Order`s reference the same `Customer`, the first access may query `Customer`, while subsequent accesses in the same persistence context reuse the managed instance.

This can make the query count smaller than the number of entities iterated, but it does not prove the design is free of N+1. When real data has many distinct foreign keys or a fresh persistence context per request, the issue becomes much clearer.

### 7.2. Second-Level Cache and Query Cache

If the application enables second-level caching, some entities/associations may be served from cache instead of the database. The query cache can also affect how queries execute depending on configuration and provider.

When measuring N+1:
- Check whether caching is enabled.
- Run tests with a controlled cache state.
- Distinguish a cache hit from a well-designed query.
- Measure both cold-cache and warm-cache scenarios if production experiences both.

Do not disable caching system-wide just to investigate. Use an isolated test/profile or evict specific cache regions when possible.

### 7.3. Tests Should Flush and Clear Fixtures

If fixtures are persisted in the same persistence context, entities may already be managed or collections already initialized. This prevents the test from reproducing N+1.

In a JPA test, you can:
1. Persist fixtures.
2. Flush to write fixture SQL to the database.
3. Clear the persistence context to evict currently managed entities.
4. Reset statistics.
5. Invoke the use case being measured.

Example:

```java
entityManager.flush();
entityManager.clear();
statistics.clear();

List<String> result =
    customerService.customerOrderCounts();
```

If the test uses `@DataJpaTest`'s transaction, pay attention to the fixture transaction versus the service call transaction. The goal is to ensure measured queries actually read from the database instead of using objects still sitting in the persistence context.

## 8. Where Does N+1 Appear in the Request Lifecycle?

### 8.1. Inside a Service Loop

Common form:

```java
for (Customer customer : customers) {
    int count = customer.getOrders().size();
}
```

Each access to an uninitialized lazy collection can trigger a query. Similarly, calling `repository.findByCustomerId(id)` inside a loop creates application-level N+1, even without lazy associations.

### 8.2. Inside a DTO Mapper

A mapper can unintentionally access relationships:

```java
CustomerResponse toResponse(Customer customer) {
    return new CustomerResponse(
        customer.getId(),
        customer.getName(),
        customer.getOrders().stream()
            .map(PurchaseOrder::getOrderNumber)
            .toList()
    );
}
```

If the mapper runs for each `Customer` after querying the list, reading `orders` can produce N queries. Do not inspect only the service; check mappers, getters, computed properties, and serializers.

### 8.3. During JSON Serialization

If a controller returns an entity, Jackson may call getters and access lazy associations while serializing the response. When Open EntityManager in View is enabled, the persistence context may remain open until response rendering, causing queries to fire after the service has returned.

Consequently, counting queries only inside the service can miss N+1 occurring during serialization. Measure the entire request or use explicitly materialized DTOs within the transaction to control response data.

Returning entities directly can also cause JSON reference cycles, unexpected data loading, or exposure of internal fields. DTO projections help define the exact data an API needs to return.

### 8.4. In Nested Loops or Multi-Level Relationships

A page might load `Customer`, then each `Order`, and then each `OrderItem`. If each level is lazy and accessed in loops, query counts can become N+1 or multi-level such as 1 + N + M.

Read logs chronologically and group queries by association. Repeating queries after loading `Order` may be a separate issue on `OrderItem`, even after the `Customer`-`Order` query has been optimized.

## 9. Distinguishing N+1 from Legitimate Queries

Not every repeated query is a bug. Some valid cases:
- Each operation needs to read distinct data that cannot be combined.
- Queries are intentionally run per partition/batch.
- Data requires independent permissions or transactions.
- Batch size is capped because a single large query would exceed parameter limits.
- Each query genuinely has different conditions or results.

To conclude N+1, establish the link between the initial query, the repeated queries, and the data access loop. Ask whether the data can be loaded in batches or fetched via a tailored projection in a small fixed number of queries.

An endpoint running 5 fixed SQL statements for 5 different pieces of data is not necessarily N+1. An endpoint running 1 parent query followed by 500 child queries of the same shape varying only by foreign key is a very clear sign.

## 10. Fixes and Verification

### 10.1. JOIN FETCH for Needed Relationships

You can request loading `Customer` and `Orders` in the same query:

```java
@Query("""
    select distinct c
    from Customer c
    left join fetch c.orders
    where c.name is not null
    order by c.name, c.id
    """)
List<Customer> findNamedWithOrders();
```

Fetch join loads the association in the query. The SQL typically joins `customer` and `purchase_order` instead of issuing an extra SELECT per customer.

Notes:
- Use `LEFT JOIN FETCH` if you still need `Customer`s without any `Order`.
- `JOIN FETCH` (inner) excludes `Customer`s that have no related elements.
- Joining a collection increases SQL row count according to the number of child elements.
- Do not fetch too many large collections at once.
- Queries returning entities may use `distinct` to express the intent of unique root entities; deduplication behavior also depends on provider/version.

After fixing, logs should show a join query instead of the 1 + N pattern. However, SQL row count can rise significantly; measure transferred data and mapping time.

### 10.2. EntityGraph

Spring Data JPA supports `@EntityGraph` to specify associations to fetch for a repository method:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @EntityGraph(attributePaths = "orders")
    List<Customer> findByNameNotNull();
}
```

`EntityGraph` expresses a fetch plan at the repository level. The provider decides how to execute it, using joins or supplementary queries depending on mapping and dialect. Therefore, do not assume `EntityGraph` always generates a single SQL statement; verify statement counts and query shapes in logs.

`EntityGraph` fits well when the same entity has multiple use cases with different association loading needs. Avoid setting all relationships to global EAGER just to fix one screen; that can cause other use cases to over-fetch data.

### 10.3. DTO Projections Fetching Only Needed Data

If a screen only needs customer names and order counts, you can use an aggregate query:

```java
public record CustomerOrderCount(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
```

```java
@Query("""
    select new com.example.CustomerOrderCount(
        c.id,
        c.name,
        count(o)
    )
    from Customer c
    left join c.orders o
    where c.name is not null
    group by c.id, c.name
    order by c.name, c.id
    """)
List<CustomerOrderCount> findNamedOrderCounts();
```

This query returns aggregated results directly without loading `orders` collections just to call `size()` per `Customer`. Constructor expressions must match the DTO package, parameter order, and types; the result type of `count()` is `Long`.

Projections are especially suitable for read APIs and reports because they avoid hydrating unnecessary entities/associations.

### 10.4. Batch Fetching

If you cannot join all associations, Hibernate can group multiple lazy loads into a query using `IN`.

Global configuration:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 25
```

Or annotate an association/entity with `@BatchSize`:

```java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
@BatchSize(size = 25)
private List<PurchaseOrder> orders = new ArrayList<>();
```

Instead of one SELECT per customer, Hibernate can load collections for a group of customers with a condition similar to:

```sql
select ...
from purchase_order
where customer_id in (?, ?, ..., ?);
```

Batch fetching typically reduces query count from 1 + N to roughly 1 + the number of batches needed, depending on uninitialized collections, batch size, cache, and provider. It reduces round-trips but does not necessarily eliminate secondary queries completely; still measure the actual SQL.

This is a Hibernate-specific feature, not a general Jakarta Persistence guarantee.

### 10.5. Subselect Fetching

Hibernate can use `@Fetch(FetchMode.SUBSELECT)` on a collection to load collections for a group of parents using a subselect query after the parent query:

```java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<PurchaseOrder> orders = new ArrayList<>();
```

This mechanism can be helpful when a use case loads a group of `Customer`s and then needs the collection for all of them. However, it depends on Hibernate, query context, and how collections are accessed. Inspect SQL, parent set size, and memory before applying broadly.

### 10.6. Choosing a Fetch Strategy by Use Case

| Approach | When Suitable | What to Measure |
|---|---|---|
| JOIN FETCH | Need association for a use case with moderate dataset | Joined row count, duplicate data, pagination |
| EntityGraph | Want to declare fetch plan per repository method | Actual SQL emitted by provider |
| DTO projection | Need only a specific set of fields/aggregates | Column count, grouping/aggregates, mapping |
| Batch fetching | Need lazy associations but want grouped loading | Batch count and IN list size |
| SUBSELECT fetching | Need the same collection for a group of parents | Parent scope and subselect query |

No single strategy is optimal for every association. Choose based on data, endpoint, parent count, collection size, and response requirements.

## 11. N+1 and Collection Pagination

A common mistake is adding a collection `JOIN FETCH` to a repository method returning `Page<Customer>`. The database paginates over joined rows while the application wants pagination over `Customer`s. One `Customer` with many `Order`s occupies multiple SQL rows and skews pagination results.

Hibernate may log a warning or apply pagination in memory depending on query/provider/version. This can load far too many rows.

Solutions:

1. Paginate `Customer` first with a query returning only IDs or root DTOs.
2. Run a second query loading associations for the page's ID list via `where c.id in :ids`.
3. Re-order the association-loaded results to match the page's ID order because `IN` does not preserve order.
4. Or use a DTO projection/aggregate query if the response only needs read data.

Two-step example:

```java
Page<Long> pageIds =
    customerRepository.findNamedIds(PageRequest.of(0, 20));

List<Customer> customers =
    customerRepository.findWithOrdersByIdIn(pageIds.getContent());
```

Repository:

```java
@Query("""
    select c.id
    from Customer c
    where c.name is not null
    order by c.name, c.id
    """)
Page<Long> findNamedIds(Pageable pageable);

@Query("""
    select distinct c
    from Customer c
    left join fetch c.orders
    where c.id in :ids
    """)
List<Customer> findWithOrdersByIdIn(@Param("ids") Collection<Long> ids);
```

This example should handle an empty page separately to avoid querying with an empty ID list; it must also preserve original page order when building the response. The count query for the ID page must accurately count matching `Customer`s.

## 12. Designing Tests to Catch N+1

### 12.1. Create Data with Multiple Parents

A test with only one `Customer` cannot clearly expose N+1. Create multiple parents with varying association counts, e.g., 10 or 20 `Customer`s, each with several `Order`s.

### 12.2. Flush and Clear Before Measuring

A test pattern:

```java
@DataJpaTest
class CustomerRepositoryNPlusOneTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void fetchPlanDoesNotIssueOneQueryPerCustomer() {
        // Create fixtures before the measurement section.
        for (int i = 0; i < 10; i++) {
            Customer customer = new Customer("Customer " + i);
            entityManager.persist(customer);

            // Even an empty lazy collection needs one SELECT after clear() to confirm it has no rows.
        }

        entityManager.flush();
        entityManager.clear();

        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();
        statistics.clear();

        List<Customer> customers =
            customerRepository.findNamedWithOrders();

        customers.forEach(c -> c.getOrders().size());

        long statements =
            statistics.getPrepareStatementCount();

        assertThat(statements).isLessThan(10);
    }
}
```

This is an illustrative test skeleton; constructors, active flags, mappings, and repository methods should match your real entities. In production-grade tests, set explicit fixtures and assert against the expected fetch plan (such as query content and exact count where applicable), rather than picking only a loose threshold.

`Statistics` is a shared counter in `SessionFactory`; avoid running query-count tests in parallel on the same context. If tests use caching, control cache state. Do not let fixture queries be counted in the measurement: reset statistics after persist/flush/clear.

### 12.3. Compare Across Multiple Dataset Sizes

Run the same use case with 1, 10, and 100 parents. If statement count grows linearly with parent count, N+1 is likely still present. If statement count stays nearly constant or grows according to expected batch counts, the fetch plan has likely improved.

Also verify:
- Returned `Customer` count is unchanged.
- Each `Customer` has the exact expected `Order` list.
- `Customer`s without `Order`s still appear if `LEFT JOIN` was intended.
- Page metadata and sorting are unchanged.
- No lazy queries fire during response serialization.
- Query count is not artificially low due to a warm cache.

## 13. Investigating N+1 in Real Environments

You can apply the following workflow:

1. **Pick a specific request:** identify the endpoint, inputs, entity count, and related data.
2. **Capture SQL:** enable controlled SQL logging or use a datasource proxy/APM.
3. **Group SQL by shape:** look for repeating SELECT statements with the same tables, predicates, and placeholder counts.
4. **Correlate bind values:** check which foreign key or ID changes across executions.
5. **Find the trigger:** inspect loops, mappers, lazy getters, serializers, and repository calls inside loops.
6. **Record a baseline:** note statement count, duration, row count, and connection wait time.
7. **Choose a fetch strategy:** join fetch, `EntityGraph`, projection, batch fetching, or separate queries.
8. **Re-measure under identical conditions:** keep fixtures and cache state the same.
9. **Verify correctness:** compare results, pagination, authorization, and related data.
10. **Monitor after deployment:** confirm query counts and latency on production-like data.

Do not fix N+1 merely by increasing the connection pool size. That may allow more queries to run concurrently, but total round-trips stay the same and may even overload the database.

## 14. Common Mistakes When Identifying N+1

| Misconception | Why It Is Wrong | Proper Check |
|---|---|---|
| Seeing multiple SELECTs means N+1 | They may be intentional independent queries | Look for 1 root query + repeated per-entity queries |
| Counting SQL only in the repository | Lazy loads can fire in mappers/serialization | Measure the entire use case/request |
| Looking only at SQL without bind values | You cannot tell which key each query loads | Check bind logs or parameterized SQL capture |
| Testing with only one parent | Cannot observe queries scaling with N | Seed multiple parents and compare 1/10/100 |
| Warm cache keeps query count low | Cache hides repeated loading | Control cache state and test cold cache |
| Using JOIN FETCH for every relationship | Can load too many rows or break pagination | Choose fetches per use case and measure row counts |
| Using global EAGER as a fix | Other endpoints may over-fetch data | Use per-use-case fetch plans |
| Assuming batch fetching eliminates N+1 | Multiple batch queries may still run | Count statements after enabling batching |
| Measuring time without counting queries | Varying cache/DB load creates noisy timings | Combine statement count, SQL shape, and latency |
| Fixing without checking responses | May drop data or alter semantics | Compare content and metadata before/after |

## 15. N+1 Identification and Resolution Checklist

- [ ] Selected an endpoint/use case and determined the root entity count.
- [ ] Captured SQL across the entire request, including mappers and serialization.
- [ ] Found an initial query fetching a list of root entities.
- [ ] Found repeated queries with the same SQL shape.
- [ ] Observed bind parameters changing by each entity's ID/foreign key.
- [ ] Verified secondary query count grows with parent count or accessed associations.
- [ ] Checked first-level and second-level cache behavior.
- [ ] Measured statement counts with Hibernate statistics or SQL capture.
- [ ] Identified the property/getter/repository call triggering the queries.
- [ ] Selected fetch join, `EntityGraph`, DTO, batch, or subselect based on the use case.
- [ ] Checked impact on pagination and joined row counts.
- [ ] Flushed/cleared fixtures and controlled cache state in tests.
- [ ] Compared query count, latency, and result contents before and after.
- [ ] Tested on a database and provider close to production.

## 16. Conclusion

Identifying N+1 requires combining two pieces of evidence: SQL statement counts growing with entity count and repeating SQL shapes with changing bind parameters. The typical pattern is one query loading N parent entities followed by N structurally identical queries loading associations for each entity. Monitor the entire request because queries can originate in service loops, DTO mappers, or JSON serialization.

SQL logs show query shape and ordering; bind logs show which IDs are loaded; Hibernate Statistics or datasource proxies help count statements. When measuring, control fixtures, transactions, persistence context, and caching to avoid false conclusions.

You can resolve N+1 with `JOIN FETCH`, `EntityGraph`, DTO projections, batch fetching, or subselect fetching. Choose according to data size and use-case needs, and take extra care when paginating collections. After applying a fix, re-run with the same data and compare statement counts, latency, row counts, and response payloads. The goal is to reduce round-trips while preserving data accuracy and API semantics.