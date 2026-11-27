# Evaluating Solutions by Correctness, SQL, Performance, and Maintainability

A Spring Data JPA solution cannot be evaluated solely by whether an endpoint returns the expected data in a simple test or how few lines of code a repository method takes. You must assess four dimensions together: **business correctness**, **actual SQL generated**, **performance under production-like load**, and **design maintainability**.

A good solution preserves invariants and transaction boundaries, queries the right data with a reasonable statement count and payload size, delivers measurable performance, and remains easy to read, test, and evolve as business rules grow. Optimizing one dimension at the expense of breaking the others is not an improvement.

## 1. The Four-Dimensional Evaluation Framework

| Dimension | Core Question | Required Evidence |
|---|---|---|
| Correctness | Do results and side effects satisfy business rules in all critical cases? | Unit tests, integration tests, transaction/concurrency tests, database state assertions |
| SQL | What SQL does the ORM actually emit, and are filters and joins right? | SQL logs, bind parameters, query plans, SQL counts, returned datasets |
| Performance | Do latency, CPU, memory, connections, and database load meet requirements? | Representative benchmarks, p95/p99 latency, throughput, query counts, execution plans |
| Maintainability | Can the code be understood, tested, extended, and changed safely? | Clear responsibility boundaries, query readability, readable tests, coupling assessment, decision docs |

Evaluate in this order:

1. Define business behaviors and invariants to protect.
2. Verify results and resulting database state are correct.
3. Inspect the SQL to understand what the ORM is doing.
4. Measure performance under representative data and load.
5. Compare complexity, risk, and maintenance cost across options.

Do not start by counting annotations or comparing lines of code. An option with less code may generate far more expensive SQL or hide hard-to-control behavior.

## 2. Evaluate Correctness Before Optimizing

### Translate Business Requirements into Verifiable Conditions

Before writing repository queries, write down:

- Valid and invalid inputs.
- Filtering and authorization rules.
- Related data that needs to be loaded.
- Allowed state transitions.
- Return payload, ordering, and pagination rules.
- Transaction boundaries and failure behavior.
- Behavior when multiple requests mutate the same data concurrently.

For example, an "order confirmation" requirement might specify:

- Only orders in `DRAFT` status can be confirmed.
- Order lines must have valid quantities.
- Order status and inventory deduction must remain consistent per the transaction design.
- Two concurrent confirmation requests must never trigger duplicate side effects.
- If a required step fails, data must roll back within the intended scope.

Without these conditions, even a fast query can produce corrupted data.

### Entity Lifecycle and Dirty Checking

For managed entities, field mutations are detected by JPA dirty checking on flush. Not every change requires calling `save()` again:

```java
@Transactional
public void renameUser(Long id, String newName) {
    User user = userRepository.findById(id)
        .orElseThrow(() -> new UserNotFoundException(id));

    user.changeDisplayName(newName);
    // Entity is managed; dirty checking tracks the change.
}
```

Correctness review checks:

- Is the entity truly managed inside the transaction?
- Is code accidentally mutating a detached entity?
- Is the caller using the instance returned from `merge()`/repository `save()`?
- Does any `flush`/`clear` alter managed state mid-flow?
- Do `cascade` and `orphanRemoval` match the relationship lifecycle?

Do not sprinkle `save()` after every setter as a mechanical habit. Still, for new or detached entities, understand how repository `save()` chooses between `persist()` and `merge()` via newness detection.

### Transaction Boundaries and Rollback

Solution evaluation must identify where transactions start, where they end, and which operations must be atomic.

```java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryService inventory;

    public OrderService(
            OrderRepository orders,
            InventoryService inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();
        inventory.reserve(order.getLines());
    }
}
```

This is an illustrative structure. If `InventoryService.reserve()` joins the transaction using default `REQUIRED` propagation, changes share the same physical transaction. If the inventory step fails and marks the transaction rollback-only, catching the exception and continuing will not allow that transaction to commit.

Tests should cover:

- Rollback when a mandatory step fails.
- Checked exceptions and rollback rules (`rollbackFor`, `noRollbackFor`).
- Propagation modes `REQUIRED` and `REQUIRES_NEW` where needed.
- Errors surfacing at flush or commit time.
- Side effects executing only after commit when required by business rules.

### Concurrency and Invariants

If concurrent requests update the same entity or dataset, the design must protect invariants:

- `@Version` and optimistic locking when write-time conflict detection is acceptable.
- `@Lock(PESSIMISTIC_WRITE)` when database row locks and serialized access are needed.
- Database unique/check constraints for expressible invariants.
- Transaction isolation matching the concurrency anomalies being prevented.

Never assess correctness solely through sequential tests. Concurrent scenarios require integration tests running multiple independent transactions/connections.

## 3. Read Actual SQL Instead of Guessing from Repository Methods

Spring Data JPA generates SQL via the JPA provider, mapping metadata, fetch strategies, and database dialect. The same repository method can emit different SQL when mappings or providers change.

### Enable SQL Logging During Investigation

With Hibernate, enable logging in development or test environments:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.springframework.transaction: TRACE
```

The bind parameter logger depends on the Hibernate version. Enable bind logging only in controlled environments, as parameter values can contain personal data, tokens, or sensitive fields.

When reading SQL, check:

- Number of `SELECT`/`INSERT`/`UPDATE`/`DELETE` statements.
- Whether selected columns are actually needed.
- Whether `WHERE` predicates are accurate and index-friendly.
- Whether `JOIN`s duplicate rows due to collection relationships.
- Whether repeated queries execute per entity.
- Whether unexpected bulk `UPDATE`/`DELETE` statements occur.
- Whether pagination executes a separate count query.
- Whether bind parameters and data types match expectations.

### N+1 Queries

Example fetching orders and accessing each order's customer:

```java
List<Order> orders = orderRepository.findAll();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

If `customer` is not loaded yet and the association is lazy, the provider may issue one query for orders plus one query per customer. With N orders, total queries scale with N.

You cannot diagnose N+1 solely from `FetchType.LAZY` annotations; inspect actual SQL and how the code accesses relationships.

Possible remedies include:

- DTO projections when only specific columns are needed.
- `JOIN FETCH` when loading associations in one query with suitable cardinality.
- `@EntityGraph` to declare fetch plans per use case.
- Provider batch fetching where appropriate.
- Splitting into a two-step query to prevent collection joins from multiplying rows.

Choose based on actual data and result shapes, not query count alone.

## 4. Comparing Fetch Join, EntityGraph, and DTO Projection

### Fetch Join

```java
@Query("""
    select o
      from Order o
      join fetch o.customer
     where o.status = :status
    """)
List<Order> findWithCustomerByStatus(
    @Param("status") OrderStatus status
);
```

Pros:

- Queries and loads required associations in one SQL statement.
- Eliminates N+1 for fetched associations.
- The query explicitly documents which associations the use case needs.

Risks:

- Collection joins multiply returned rows.
- Combining pagination with collection fetch joins can force in-memory pagination or trigger warnings/errors depending on configuration.
- Over-fetching associations inflates network transfer and memory usage.

### @EntityGraph

```java
@EntityGraph(attributePaths = {"customer"})
List<Order> findByStatus(OrderStatus status);
```

`EntityGraph` separates the fetch plan from JPQL, fitting when reusing a query method while tailoring which relationships load per use case. Final SQL remains provider-determined; inspect SQL to see whether the graph executes as a join or another strategy.

### DTO Projection

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    String customerName,
    BigDecimal total
) {}
```

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id, o.number, c.name, o.total
    )
      from Order o
      join o.customer c
     where o.status = :status
    """)
List<OrderSummary> findSummariesByStatus(
    @Param("status") OrderStatus status
);
```

DTO projections suit read-only endpoints that do not modify entities or invoke lifecycle behaviors. They slim down column selection and keep entity graphs out of the API layer.

| Criterion | Fetch Join | EntityGraph | DTO Projection |
|---|---|---|---|
| Goal | Load entity and associations | Declare fetch plan | Fetch only display data |
| Managed entity | Yes | Yes | No managed entity needed |
| Query flexibility | Explicit JPQL | Reuses existing query methods | Tailored query/projection |
| Risks | Row multiplication, collection pagination | Provider-dependent SQL | Projection changes when output structure changes |
| Best suited when | Entity and specific relationships are needed | Fetch plans vary by use case | Read models/APIs need only selected fields |

## 5. Correct and Efficient Pagination

A pagination design must ensure both page contents and total counts are accurate. Spring Data uses `Page<T>` when total counts are needed, which may run an extra count query. If total page counts are unneeded, `Slice<T>` avoids count overhead.

```java
PageRequest pageRequest = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
);

Page<Order> page = orderRepository.findByStatus(
    OrderStatus.PAID,
    pageRequest
);
```

Evaluation points:

- Sort order must be deterministic; add a unique tie-breaker column when rows can share sort values.
- Indexes should align with filter predicates and sort order.
- Count queries can be expensive with complex joins.
- Avoid direct collection fetch joins with large pagination unless you understand how the provider handles them.
- For large datasets and sequential traversal, consider keyset/scrolling over deep offsets.
- Test first page, last page, out-of-bounds pages, empty datasets, and concurrent mutations.

Example adding a tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

Stable sorting prevents records from shifting across pages when timestamps tie. It does not replace snapshot/isolation guarantees if rows change between page requests.

## 6. Inspecting Query Plans and Indexes

Short SQL does not equal fast SQL. The database might perform full table scans, in-memory sorts, or expensive joins.

Process:

1. Capture SQL and bind parameters from logs.
2. Run `EXPLAIN` or the database's query plan tool.
3. Inspect access paths: sequential/table scan, index scan, join strategy, sort nodes, and estimated rows.
4. Compare estimated rows with actual rows where supported.
5. Check whether indexes support predicates, join keys, and sort order.
6. Re-measure after modifying queries or indexes using representative data.

PostgreSQL example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

`EXPLAIN ANALYZE` executes the query for real. Use caution with write statements or heavy queries in production. Even `SELECT` statements consume resources and generate load. Check permissions and environment policies before running it.

Do not index a column blindly just because it appears in `WHERE`. Indexes add write overhead, storage cost, and maintenance burden. Choose indexes based on read/write workloads and real query plans.

## 7. Measuring Performance with Representative Data

A meaningful benchmark reflects:

- Entity counts and realistic data skew.
- Proportion of related records and collection cardinalities.
- Warm vs. cold cache ratios.
- Page sizes and offset depths.
- Request concurrency levels.
- Read/write traffic mix.
- Database engine, indexes, and connection pool matching production.

### Metrics to Track

| Metric | Meaning |
|---|---|
| p50/p95/p99 latency | Typical latency and tail latency |
| Throughput | Requests or transactions completed per second |
| SQL query count | SQL statements executed per use case |
| Rows examined/returned | Volume of data scanned vs. returned by the database |
| DB CPU and I/O | Database resource utilization |
| Connection pool active/wait | Pressure on the connection pool |
| Heap/GC | Cost of objects and entity graphs in the JVM |
| Lock wait/deadlocks | Data contention levels |

Never draw conclusions from a single run. Perform warm-ups, repeated iterations, realistic concurrency, and identical comparison baselines. Report p95/p99 rather than averages alone, since tail latency drives user experience.

### Hibernate Statistics

In test/benchmark environments, enable Hibernate statistics to observe entity loads, query executions, and cache hits:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Access `SessionFactory.getStatistics()` in tests or instrumentation tools. Statistics incur overhead and track scope per configuration; enable only where measuring, not globally in production without evaluating impact.

SQL logging also carries overhead and high log volume. For formal benchmarks, use metrics or datasource instrumentation to count queries without distorting timings.

## 8. Evaluating Batch Inserts and Updates

For large volumes, calling `save()` per entity can generate excessive round trips or bloat the persistence context. Hibernate JDBC batching and chunking can help.

Example Hibernate settings (verify compatibility with your version and ID generator):

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Checklist items:

- Does the provider actually batch statements?
- Does the ID generation strategy permit batching in the current configuration?
- Does the persistence context need periodic `flush()` and `clear()` to bound memory?
- Are transactions too large, holding locks too long, or costly to roll back?
- Does the batch size suit the driver and database?
- Does update ordering increase deadlock risk?

JPQL bulk updates/deletes differ from JDBC batching: bulk queries act directly on the database and bypass dirty checking and normal entity lifecycles. Clear or refresh the persistence context if managed entities may become stale.

## 9. Correctness of Mappings and Queries

Verify both mapping configuration and query semantics:

- Do `@ManyToOne`, `@OneToMany`, `@OneToOne`, and `@ManyToMany` reflect accurate cardinality?
- Are owning sides and `mappedBy` configured properly?
- Do `cascade` and `orphanRemoval` match business lifecycles?
- Do fetch types cause unexpected data loading?
- Are `equals()`/`hashCode()` safe across transient and generated-ID states?
- Are enum mappings stable in the database?
- Are nullability, unique constraints, and foreign keys enforced in the database?
- Do joins cause duplicate or dropped rows?
- Do sorting, paging, and count queries share consistent semantics?

In particular, never treat `CascadeType.ALL` or `FetchType.EAGER` as defaults for every association. They trigger unintended side effects and pull in broad graphs beyond what the use case needs.

## 10. Testing to Prove the Solution Works

### Unit Tests for Domain Logic

Use unit tests for pure Java rules: state transitions, totals, preconditions, and invariants. Skip loading a Spring context if the logic has no Spring/JPA dependencies.

### Repository Integration Tests

Use `@DataJpaTest` with an appropriate database to verify:

- JPQL/native queries execute accurately.
- Mappings and cascades behave as intended.
- Projections and pagination return accurate results.
- Unique and foreign key constraints are enforced.
- Flush/clear and dirty checking produce expected outcomes.

When testing commit-time failures, remember test transactions roll back by default. Use `flush()` to surface SQL errors immediately, or use non-transactional tests/`TestTransaction` to verify real commits.

### Service Integration Tests

Use a Spring context to verify:

- Transaction boundaries and rollbacks.
- Multiple repositories participating in a transaction.
- Exception translation.
- Transaction-phase event listeners.
- Retries and idempotency at the right boundaries.

### Concurrency Tests

Use multiple independent transactions and connections to verify:

- Optimistic locking.
- Pessimistic locking and timeouts.
- Deadlocks or lock ordering.
- Lost updates.
- Invariants under concurrent requests.

Concurrency tests need barriers/latches to enforce deterministic interleaving instead of relying on `Thread.sleep()` and hoping a race occurs.

## 11. Evaluating Maintainability

A solution can be fast yet painful to maintain. Look for these indicators:

### Clear Responsibility Boundaries

- Repositories handle data access.
- Services orchestrate use cases and transactions.
- Aggregates/entities enforce domain invariants.
- DTOs/projections serve read models or APIs.
- Mappers translate data at boundaries.

Avoid embedding complex business rules in query strings or controllers. At the same time, avoid excessive pass-through layers that add indirection without value.

### Readable and Testable Queries

Choose derived queries while method names stay clear. Choose JPQL or native SQL when queries are complex, require explicit join/aggregation control, or leverage database features. Name repository methods for business intent and write tests covering semantics.

A fast native query coupled tightly to a dialect increases database migration cost. Conversely, native SQL is justified when query plans or database features are critical. Document why it was chosen and test it on a production-like database.

### Explicit Fetch Plans per Use Case

Do not make every association `EAGER` to avoid lazy-loading exceptions. Define required data per use case via `EntityGraph`, fetch joins, or projections. Explicit fetch plans tell maintainers what data a query loads and reduce surprise N+1 regressions.

### Do Not Hide Costs Behind Abstractions

Generic repositories or base services can cut boilerplate, yet if they obscure queries, transactions, and lifecycles, the abstraction causes harm. Prefer straightforward code with clear names and verifying tests.

### Document Key Trade-Offs

For notable choices such as native queries, pessimistic locks, batch sizes, or outboxes, record briefly:

- The actual problem.
- The chosen approach.
- Alternatives considered.
- Measurements or evidence.
- Limitations and conditions for revisiting.

## 12. Example Evaluation of Two Approaches for an Order List Screen

Requirement: return the 20 most recent paid orders, including order number, creation time, customer name, and total amount.

### Option A: Load Entities and Access Associations

```java
List<Order> orders = orderRepository.findByStatus(
    OrderStatus.PAID
);

List<OrderSummary> result = orders.stream()
    .map(order -> new OrderSummary(
        order.getId(),
        order.getNumber(),
        order.getCustomer().getName(),
        order.getTotal()
    ))
    .toList();
```

Risks:

- Loading all matching orders scales memory and rows linearly with dataset size.
- Accessing `customer` can cause N+1 queries.
- Entity graphs may fetch fields/associations unused by this screen.
- Lacks pagination unless added.

### Option B: Paginated Projection

```java
public record OrderSummary(
    Long id,
    String number,
    String customerName,
    BigDecimal total
) {}
```

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id, o.number, c.name, o.total
    )
      from Order o
      join o.customer c
     where o.status = :status
    """)
Page<OrderSummary> findOrderSummaries(
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

Option B typically fits read-only lists better because it selects only needed columns and paginates. Still, verify:

- Does the SQL join properly and is the count query cost acceptable?
- Do indexes support filtering and sorting?
- Is sorting deterministic?
- Is the page size bounded appropriately?
- Do p95 latency and DB load actually improve?

If total counts are unnecessary, `Slice<OrderSummary>` or keyset pagination may fit the requirements. Do not conclude Option B is better merely because it uses a projection; measure on representative data and confirm semantics.

## 13. Solution Evaluation Scorecard

You can use the rubric below in reviews to ensure all four dimensions are checked. Scores are an internal discussion aid, not a replacement for technical evidence.

| Criterion | Suggested Weight | Score 1 | Score 3 | Score 5 |
|---|---:|---|---|---|
| Correctness | 35% | Violates invariants or lacks rollback/concurrency handling | Main flow correct, missing edge cases | Tests cover errors, boundaries, transactions, and required concurrency |
| SQL | 25% | Wrong SQL or severe N+1/table scans | Valid SQL with extra queries/columns | SQL inspected, query plan sound, accurate output |
| Performance | 25% | Unmeasured or fails requirements | Handles basic load, tail latency unclear | Representative benchmarks meet latency/throughput/resource goals |
| Maintainability | 15% | High coupling, hard to read and test | Acceptable structure | Clear responsibilities, readable queries/fetch plans, trade-offs documented |

Weighted score formula:

`Total Score = Σ (criterion score / 5 × weight)`

With the sample weights above, weights sum to 100%. Any severe correctness or security flaw must act as an independent blocker; never let a high performance score compensate for wrong data.

## 14. Pre-Acceptance Review Checklist

**Correctness**

- [ ] Outputs satisfy requirements and invariants.
- [ ] Transaction boundaries and rollbacks are verified.
- [ ] Relationships, cascades, orphan removal, and lifecycles are accurate.
- [ ] Pagination, sorting, nulls, and boundary inputs behave correctly.
- [ ] Concurrency/locking is tested where needed.

**SQL**

- [ ] Actual SQL and bind parameters have been inspected.
- [ ] No unintended N+1 queries exist.
- [ ] `WHERE`/`JOIN`/`ORDER BY` clauses are accurate.
- [ ] Projections/fetch plans select only needed data.
- [ ] Query plans and indexes have been evaluated.

**Performance**

- [ ] Benchmark data is representative.
- [ ] p95/p99 latency, throughput, and query counts are recorded.
- [ ] DB CPU/I/O, connection pool, and heap have been checked.
- [ ] Batch/page sizes are measured rather than guessed.
- [ ] No abnormal lock waits or deadlocks occur.

**Maintainability**

- [ ] Repositories, services, domain, and APIs have clear boundaries.
- [ ] Queries are readable and backed by tests.
- [ ] Native SQL, locks, and batching have explicit justifications.
- [ ] Trade-offs and constraints are documented.
- [ ] No unnecessary abstractions or annotations were added.

## Conclusion

Evaluating a Spring Data JPA solution starts with correctness, then verifies SQL, measures performance, and assesses maintainability. The SQL emitted by the ORM represents actual runtime behavior; annotations or repository method names alone never prove efficiency.

Accept a solution only when results and transactions are accurate, query plans are sound, performance meets targets on representative data, and code remains clear enough for the team to evolve. Whenever trade-offs exist, document the evidence and constraints instead of optimizing by intuition.