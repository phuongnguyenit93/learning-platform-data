# Detecting N+1 Queries and Query Count Regressions

N+1 is a performance issue that occurs when an application executes one query to fetch a list of root entities, and then runs one extra query per entity when accessing a lazy association. With N records, query counts can grow from 1 to 1 + N. The endpoint still returns correct data and may appear fast with a handful of records, yet degrades sharply as data grows.

Query count regression testing helps detect changes that unexpectedly increase SQL statement counts. To make tests meaningful, create representative datasets, measure queries over the exact business scope, eliminate cache and persistence context interference, and enforce query budgets aligned with the chosen fetch strategy.

## 1. What Is an N+1 Query?

Suppose an application has two entities: `Order` and `Customer`. Each order references a customer via a lazy association.

```java
@Entity
public class Order {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    // getters and other fields
}
```

The repository loads a list of orders:

```java
List<Order> orders = orderRepository.findByStatus("OPEN");
```

If a service or mapper then reads `order.getCustomer().getName()` one by one, Hibernate may have to load each order's customer separately:

```java
for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

For 5 orders with 5 distinct customers, the SQL flow can look like:

```sql
SELECT ... FROM orders WHERE status = 'OPEN';

SELECT ... FROM customer WHERE id = 101;
SELECT ... FROM customer WHERE id = 102;
SELECT ... FROM customer WHERE id = 103;
SELECT ... FROM customer WHERE id = 104;
SELECT ... FROM customer WHERE id = 105;
```

That totals 6 queries: one root query and five association-loading queries. With 100 orders across 100 distinct customers, the total can hit 101.

N+1 does not always equal strictly 1 + N. If multiple orders point to the same customer, the persistence context's first-level cache prevents Hibernate from reloading the same entity repeatedly. Batch fetching can also consolidate multiple loads into `IN` queries. Even so, SQL counts scaling with record count or small batches remain a warning sign worth investigating.

N+1 can occur with:

- Lazy `@ManyToOne` or `@OneToOne` associations.
- `@OneToMany` or `@ManyToMany` collections iterated individually.
- Mappers converting entities to DTOs.
- Jackson or JSON serializers when returning entities directly.
- Server-side templates accessing lazy properties.
- Business logic, logging, or `toString()` inadvertently reading associations.

Therefore, do not inspect repository queries alone. Inspect the entire path from entity loading through response construction.

## 2. Identifying N+1 From SQL and Runtime Metrics

### 2.1. Enabling SQL Logging During Development

With Spring Boot and Hibernate, enable SQL statement logging:

```properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
```

To inspect bind parameters in development, Hibernate 6 supports:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

SQL logs reveal the same query pattern repeating for many different IDs. Do not turn on bind parameter logging casually in production because values can contain personal data, sensitive details, or tokens.

Example N+1 signature in logs:

```text
select ... from orders where status=?
select ... from customer where id=?
select ... from customer where id=?
select ... from customer where id=?
select ... from customer where id=?
```

Repeated secondary queries sharing the same structure with differing parameters strongly indicate per-record association loading.

### 2.2. Using Hibernate Statistics

Hibernate provides `Statistics` to inspect prepared statement counts, entity/collection fetches, cache hits/misses, and more.

Enable statistics in configuration:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Read statistics in code:

```java
import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Component;

@Component
public class HibernateQueryMetrics {

    private final Statistics statistics;

    public HibernateQueryMetrics(EntityManagerFactory entityManagerFactory) {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public long preparedStatementCount() {
        return statistics.getPrepareStatementCount();
    }

    public long entityFetchCount() {
        return statistics.getEntityFetchCount();
    }

    public long collectionFetchCount() {
        return statistics.getCollectionFetchCount();
    }
}
```

The metrics mean different things:

- `getPrepareStatementCount()`: number of JDBC statements prepared by Hibernate within the stats window.
- `getEntityFetchCount()`: number of extra entity fetches beyond entities directly retrieved in primary queries.
- `getCollectionFetchCount()`: number of collection fetches.
- Cache hit/miss counts show whether data was served from cache or fetched additionally.

Statistics are `SessionFactory`-wide and can aggregate activity across concurrent requests and tests. When using them in tests, clear statistics right before the measured region, run tests sequentially or isolate the workload, and measure only the target window.

### 2.3. Using a Datasource Proxy or SQL Observation Tools

You can wrap the JDBC driver with a datasource proxy to count SQL statements, measure execution durations, and group queries per request. Libraries like `datasource-proxy` or `P6Spy` are useful for observing both Hibernate-generated SQL and direct JDBC calls.

Datasource-level instrumentation observes the actual SQL executed, including statements outside JPQL. Still, filter metrics per request/test and avoid logging sensitive parameter values. Under concurrent traffic, never treat global application SQL totals as the query count of a single endpoint.

## 3. Distinguishing N+1 From Intentional Multi-Query Designs

Not every multi-SQL flow is an N+1 problem. A use case may intentionally execute several queries, for instance:

- One query to fetch a page of IDs and one query to fetch detailed records.
- One query to fetch main entities and one query to fetch aggregate statistics.
- One query to load entities and one query to batch-load collections.
- Write statements or constraint checks inside a transaction.

Examine query structure and growth behavior rather than reacting to a single raw number.

| Symptom | Likely Cause |
|---|---|
| One root query, then the same SELECT repeating per ID | N+1 |
| Query count stays nearly constant as record count grows | Fetch plan is likely optimized |
| Association query executes per group of IDs in an `IN` clause | Batch fetching |
| Two clear queries: fetching a page of IDs then loading associations | Two-step paginated fetch |
| Single SQL query returns massive row counts from multiple collection joins | Potential row multiplication; low query count can still be slow |

N+1 is about round-trip multiplication and loading patterns. A single query can still be slow if joins explode row counts, read excessive columns, or use poor execution plans.

## 4. How to Eliminate N+1

Pick a solution based on the data the endpoint genuinely needs. No single fetch strategy fits every query.

### 4.1. Using JOIN FETCH for Needed Associations

For to-one associations required in the response, a JPQL fetch join is often the most direct fix:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select o
        from Order o
        join fetch o.customer
        where o.status = :status
        """)
    List<Order> findWithCustomerByStatus(
            @Param("status") String status
    );
}
```

The service maps to DTOs inside the transaction:

```java
public record OrderSummary(Long id, String customerName) {}

@Service
public class OrderQueryService {

    private final OrderRepository orderRepository;

    public OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> findOpenOrderSummaries() {
        return orderRepository.findWithCustomerByStatus("OPEN")
                .stream()
                .map(order -> new OrderSummary(
                        order.getId(),
                        order.getCustomer().getName()
                ))
                .toList();
    }
}
```

The main query already loaded the customer, so the mapper triggers no extra SELECT per order.

Use `left join fetch` when the association is optional and root entities must still be returned. Use `join fetch` when the association is required by the query contract.

### 4.2. Using @EntityGraph

`@EntityGraph` declares associations to load for a repository method:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {"customer"})
    List<Order> findByStatus(String status);
}
```

The service maps results to DTOs within the transaction as above. EntityGraphs keep fetch plans separate from lengthy JPQL, especially when the same entity has multiple read profiles.

You can specify multiple attributes or nested paths, e.g. `attributePaths = {"customer", "items.product"}`. Inspect the generated SQL and returned row counts; an EntityGraph is a fetch plan hint, not a guarantee of a single SQL query across all providers/scenarios.

### 4.3. Using DTO Projections When Only Specific Fields Are Needed

If the response only needs the order ID and customer name, query straight into a DTO instead of loading full entities:

```java
public record OrderSummary(Long id, String customerName) {}
```

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        c.name
    )
    from Order o
    join o.customer c
    where o.status = :status
    """)
List<OrderSummary> findSummariesByStatus(
        @Param("status") String status
);
```

Projections fit list endpoints, reports, and read-only views. They reduce columns/entities fetched and prevent serializers from accidentally triggering lazy loading.

The package name in the JPQL constructor expression must match the record's package. For interface projections, `SELECT` aliases must match the getters/properties expected by Spring Data projection.

### 4.4. Using Batch Fetching When Joining Everything Is Impractical

Batch fetching groups loading of multiple uninitialized proxies or collections into queries using an `IN` clause.

Configure a global default:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Or annotate specific entities/collections with Hibernate's annotation:

```java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 32)
public class Customer {
    // ...
}
```

On collections:

```java
@OneToMany(mappedBy = "order")
@BatchSize(size = 32)
private List<OrderItem> items = new ArrayList<>();
```

With 100 collections to load and a batch size of 32, collection queries drop from 100 to roughly 4. Exact counts depend on loaded collections, data distribution, dialect, and provider statement generation.

Batch fetching mitigates N+1 without forcing an entire endpoint into a single query. It helps when joining multiple collections causes row explosion or when lazy access patterns must be preserved.

### 4.5. Considering SUBSELECT for Collections

Hibernate supports `@Fetch(FetchMode.SUBSELECT)` on certain collection mappings. When a collection on parent entities is accessed, the provider can run one secondary query driven by the parent query rather than one SELECT per parent.

This is Hibernate-specific. It works well when parent groups are loaded together, yet can fetch more collections than needed if the persistence context holds many parents. Measure SQL and memory before adopting it.

## 5. N+1 Combined With Pagination

Fetch-joining to-one associations usually works fine with pagination. Fetch-joining collections requires care because one parent with multiple children multiplies SQL rows. Consequently, applying `LIMIT`/`OFFSET` directly on joined rows no longer paginates by parent count.

In Hibernate, combining collection fetch joins with pagination can emit warnings or force the provider to load large datasets and paginate in memory, depending on version and configuration. Do not ignore this warning in production.

A common alternative is two-step pagination:

1. Query a page of root entity IDs matching the filter and desired sort order.
2. Query the entities along with required associations using `where id in :ids`.
3. Reconstruct the original ID order from step 1, since `IN` does not guarantee result order.

Repository example:

```java
@Query("""
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findPageIds(
        @Param("status") String status,
        Pageable pageable
);

@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id in :ids
    """)
List<Order> findWithItemsByIdIn(@Param("ids") Collection<Long> ids);
```

The service fetches the page of IDs and then loads details. To restore ordering, map by ID or iterate the original ID list to assemble results in exact order. If the ID page is empty, return empty results without running the detail query.

Two-step fetching typically issues two main queries per page regardless of page size. This is an intentional fixed query count, not N+1. Handle rows deleted or modified between the two queries according to transaction isolation and business rules.

## 6. Designing Query Count Regression Tests

A strong query-count test catches when mapping, mapper, or serializer changes introduce extra SQL. Key rules:

- Seed multiple root records—at least several—with distinct associations so L1 caching does not mask N+1.
- Ensure test data actually populates the associations that will be accessed.
- Start counting only after seeding finishes.
- Measure within one specific request/service call rather than across whole-application activity.
- Use a fresh persistence context or invoke the service in its own transaction.
- Disable L2/query caches in N+1 tests, or evict caches before the measured window.
- Keep conditions identical when comparing baseline and changes.
- Set thresholds based on the intentional fetch plan rather than hardcoding one arbitrary number everywhere.

### 6.1. Using Hibernate Statistics in Integration Tests

The example below assumes:

- Hibernate is the JPA provider.
- Fixture data has been seeded and committed before measurement begins.
- `findOpenOrderSummaries()` uses a fetch join or EntityGraph to load customers.
- The service method runs in its own transaction and returns DTOs.
- The test does not run in parallel with other tests sharing the same `SessionFactory`.

Test configuration:

```properties
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.cache.use_second_level_cache=false
spring.jpa.properties.hibernate.cache.use_query_cache=false
```

Integration test:

```java
import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderQueryCountTest {

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Autowired
    private OrderQueryService orderQueryService;

    @Test
    void shouldLoadOpenOrderSummariesWithoutNPlusOne() {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        Statistics statistics = sessionFactory.getStatistics();

        // Fixture has been seeded and committed before this point.
        statistics.clear();

        orderQueryService.findOpenOrderSummaries();

        long statements = statistics.getPrepareStatementCount();

        // Fetch join/EntityGraph loads orders and customers in one SELECT.
        assertThat(statements).isEqualTo(1L);
    }
}
```

This example shows a service executing one SELECT with zero secondary queries. If a use case intentionally requires two queries, set the threshold accordingly. Do not blindly copy `1` into every test.

Do not wrap the test in `@Transactional` in a way that lets fixture setup, service call, and assertions share a single persistence context uncontrollably. If the test transaction keeps an L1 cache warm, lazy accesses may emit no SQL unlike real requests. Seed fixtures in a separate transaction, commit, and call the service via its proxy in its own transaction.

`Statistics` is global across the `SessionFactory`. If tests run in parallel, another test can increment counts between `clear()` and your assertion. Disable parallel execution for this test group or use request/test-scoped counters in a datasource proxy.

### 6.2. Verifying Query Counts Do Not Scale Linearly With N

A stronger regression check compares behavior at two data scales:

- With 5 orders, the service runs one query loading orders and customers.
- With 50 orders, the service still runs the same single query.
- If the query count jumps from 1 to 51, a lazy association is likely being loaded per order.

With batch fetching, query counts scale by batch count rather than staying strictly constant. For example, with batch size 32, 5 and 20 orders share one batch, while 50 orders require a second batch. In that case, assert expected batch scaling rather than demanding a single query.

Ensure test data contains enough distinct customers. If 50 orders all point to one customer, L1 caching needs just one customer query and fails to reproduce the worst case.

### 6.3. Testing Response Serialization Too

If an endpoint returns entities directly, extra queries can trigger only while Jackson serializes the response. Unit tests calling the service alone miss those queries.

For APIs, add integration tests with `MockMvc` or `WebTestClient`:

1. Create data with populated associations.
2. Call the real endpoint.
3. Let the framework finish building the HTTP response.
4. Measure SQL within the request scope and verify JSON output.
5. Run tests with `spring.jpa.open-in-view=false` when architecture requires services to finish all loading.

DTOs constructed inside the service make most transaction SQL explicit. Even so, measuring full requests catches queries triggered by other components.

## 7. Avoiding Misleading Query Count Tests

| Testing Pattern | Why It Misleads | How to Improve |
|---|---|---|
| Calling repository once with one entity | Too few rows to expose N+1 | Use multiple parents and distinct associations |
| Reading entities twice in the same `EntityManager` | Second read can come from L1 cache | Use a fresh persistence context |
| Leaving L2/query caches enabled | Cache hits hide repeated queries | Disable caches or evict before measuring |
| Counting SQL across the entire test suite | Includes setup, teardown, and other tests | Reset counter right before the measured operation |
| Counting a live app under traffic | Other requests pollute totals | Correlate per request or run isolated tests |
| Checking only elapsed runtime | Affected by hardware, caches, and system load | Combine query count, execution plan, and latency |
| Hardcoding query count without matching use case | Valid optimizations break tests | Document expected queries and rationale |
| Testing only the service when endpoints return entities | Misses queries triggered during serialization | Test the complete HTTP response |

Query count is an important metric, yet does not tell the whole performance story. One huge join query can run slower than two small queries. Always inspect row counts, network payload sizes, indexes, execution plans, and latency too.

## 8. Observability Tools in Production Environments

When investigating slow endpoints, combine multiple signals:

- **Hibernate SQL logs:** inspect query shapes and parameters in development.
- **Hibernate Statistics:** track entity fetches, collection fetches, prepared statements, and cache hits/misses.
- **Datasource proxy/P6Spy:** count and time SQL at the JDBC layer.
- **APM/tracing:** tie database spans to specific HTTP requests or background jobs.
- **Database slow query logs:** identify slow statements and execution plans.
- **Per-endpoint metrics:** monitor p50/p95/p99 latency, SQL-per-request, and timeout errors.

Do not keep verbose SQL logging enabled in production without data-protection policies and log volume caps. Prefer sampled traces and metrics, and mask bind parameter values.

When a regression occurs, compare both versions under matching data and workloads. Check changes across entity mappings, `fetch` types, EntityGraphs, mappers, serializers, repository queries, and cache configurations.

## 9. Common Optimization Mistakes

### 9.1. Switching Every Association to EAGER

Changing `LAZY` to `EAGER` may remove extra queries in one flow while loading unnecessary data across all other flows. Eager does not guarantee the provider emits a single JOIN; providers can still issue multiple SELECTs.

Choose fetch plans per use case via EntityGraphs, fetch joins, or projections.

### 9.2. Fetch-Joining Multiple Collections Simultaneously

Joining two large collections multiplies row counts by the Cartesian product of each collection's elements. For instance, one order with 10 items and 4 tags yields roughly 40 SQL rows for that single order before the provider deduplicates entities.

Prefer projections, batch fetching, or loading collections in separate queries. Do not trade N+1 for an uncontrolled giant query.

### 9.3. Using DISTINCT Without Measuring SQL

`DISTINCT` can deduplicate root entities in JPQL results, yet does not eliminate row multiplication inside the database SQL execution. Inspect the generated SQL and actual row counts returned by the database.

### 9.4. Overlooking Serializers and toString()

A getter invoked inside a JSON serializer, debugger, logger, or `toString()` can trigger lazy loading. Keep entity associations out of `toString()` and avoid serializing raw entity graphs indiscriminately.

### 9.5. Optimizing Query Count While Ignoring Payload Size

A fetch plan may minimize SQL statement count while dragging back thousands of unneeded columns or rows. Evaluate query count, row count, byte volume, memory, and latency together.

## 10. Checklist for Detecting and Preventing N+1 Regressions

- [ ] Identified endpoints/services and lazy associations prone to extra queries.
- [ ] Checked for SQL repeating per entity or collection.
- [ ] Fixtures contain multiple parents and distinct associations.
- [ ] Query counts are measured after seeding and scoped to the target request/service.
- [ ] A fresh persistence context is used for the measured window.
- [ ] L2/query caches are controlled so they do not mask queries.
- [ ] Fetch strategies match the data actually returned.
- [ ] Collection fetch joins and pagination are evaluated separately.
- [ ] Regression tests verify query counts at different data scales.
- [ ] API serialization is tested if responses touch lazy associations.
- [ ] Metrics/traces track SQL counts and latency post-deployment.
- [ ] Query counts are reviewed alongside row counts, execution plans, and transferred data.

Detecting N+1 requires inspecting both SQL structure and how statement counts scale as entity counts grow. Regression tests with sizable fixtures, fresh persistence contexts, and controlled caching catch issues reliably. When optimizing, pick fetch joins, EntityGraphs, projections, or batch fetching per use case and measure both query count and actual data volume.

## References

- [Hibernate ORM User Guide – Fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM – Statistics API](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/stat/Statistics.html)
- [Spring Data JPA – EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Boot – Data access and JPA configuration](https://docs.spring.io/spring-boot/reference/data/sql.html)