# Migrating from JdbcTemplate to Repositories Use Case by Use Case

In **Spring Data Relational JDBC**, an application can migrate individual use cases from `JdbcTemplate` to repositories without rewriting the entire data access layer. Repositories are well suited for reading and saving aggregates with clear boundaries; `JdbcTemplate` remains useful for reporting, bulk updates, aggregate queries, stored procedures, or specialized SQL.

Both data access approaches can coexist within a single application. When sharing the same `DataSource` and transaction manager, Spring Data JDBC repository operations and `JdbcTemplate` calls can participate in the same transaction. This provides the foundation for migrating one use case at a time in a controlled manner.

The goal of the migration is to preserve business contracts, match the mapping to the existing schema, keep transactions consistent, and have tests proving before-and-after behavior. You should not refactor a DAO class merely to swap out the SQL-calling API; first determine which use cases genuinely benefit from an aggregate repository.

## 1. Understanding Both Data Access Approaches

### 1.1. JdbcTemplate

`JdbcTemplate` is a lower-level abstraction than a JDBC repository. The application still controls the SQL, parameter binding, `RowMapper`, batching, and many query details.

Example existing DAO:

~~~java
@Repository
public class JdbcPurchaseOrderDao {

    private final JdbcTemplate jdbcTemplate;

    public JdbcPurchaseOrderDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<PurchaseOrderRow> findByOrderNumber(
            String orderNumber) {

        List<PurchaseOrderRow> rows = jdbcTemplate.query(
                """
                SELECT id, order_number, customer_id, status, created_at
                FROM purchase_order
                WHERE order_number = ?
                """,
                (rs, rowNum) -> new PurchaseOrderRow(
                        rs.getLong("id"),
                        rs.getString("order_number"),
                        rs.getLong("customer_id"),
                        rs.getString("status"),
                        rs.getTimestamp("created_at").toInstant()
                ),
                orderNumber
        );

        if (rows.isEmpty()) {
            return Optional.empty();
        }
        if (rows.size() > 1) {
            throw new IllegalStateException(
                    "Order number is not unique: " + orderNumber);
        }
        return Optional.of(rows.get(0));
    }
}
~~~

The DAO has full control over SQL and mapping. That is flexible, but when many use cases repeat how they find, insert, update, and map the same aggregate, the JDBC code can become verbose and scattered.

### 1.2. Spring Data JDBC Repository

A repository expresses saving and finding aggregates through an interface:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

Spring Data JDBC generates implementations for standard repository operations and derived queries. Mapping metadata is declared on the aggregate/entity, while the application focuses business behavior in services and the domain model.

A repository is a good fit when:

- The data can be modeled as an aggregate root with clear boundaries.
- Use cases typically load and save the aggregate by ID or a business attribute.
- Insert, update, and delete operations follow the aggregate lifecycle.
- You want to reduce repetitive CRUD SQL and mapping code.
- You need optimistic locking, auditing, or a suitable repository abstraction.

`JdbcTemplate` remains a good fit when:

- Reporting queries return complex projections or aggregated data.
- Bulk updates or deletes affect many rows.
- Stored procedures, CTEs, or specialized SQL are hard to express with a repository.
- You need precise control over SQL, locks, or database-specific hints.
- Large datasets are read via streaming or batching with a dedicated contract.
- An operation is just a small SQL statement that does not need to load and save an aggregate.

There is no requirement to pick only one approach for the entire application. Choose the abstraction on a per-use-case basis.

## 2. Inventory Use Cases Before Modifying Code

Before migrating, build an inventory from the services, controllers, and jobs calling the DAO. For each use case, record:

| Information | Questions to Answer |
| --- | --- |
| Business purpose | What action is the user or system performing? |
| Read/write path | Which queries run and which tables change? |
| Cardinality | Does it return 0, 1, or many rows? |
| Aggregate boundary | Which rows belong to the same aggregate root? |
| Specialized SQL | Are there joins, CTEs, window functions, bulk updates, or stored procedures? |
| Transaction | Which steps must commit or roll back together? |
| Load | Frequency, row counts, latency, and concurrency level? |
| Contract | What does the service return, and how are errors and nulls handled? |

Then group them:

| Use Case Group | Migration Direction |
| --- | --- |
| Find a single aggregate by ID or unique key | Repository finder |
| Create/update a single aggregate | Repository `save` inside a service transaction |
| Delete an aggregate by version/ID | Repository delete matching the contract |
| Simple list filtering | Derived query or `@Query` |
| Multi-table join or grouped/aggregated reports | May keep `JdbcTemplate` |
| Multi-row bulk updates | Usually keep `JdbcTemplate` or specialized SQL |
| Import/export and batch jobs | Evaluate separately based on size and resource lifetime |
| Stored procedures or database-specific SQL | Keep an appropriate SQL abstraction |

A single use case can use both: a repository saves the primary aggregate while `JdbcTemplate` reads a secondary projection or updates a technical table in the same transaction.

## 3. Migrate by Use Case, Not Mechanically Table by Table

Spring Data JDBC repository boundaries center around the **aggregate root**, not just a single table. An aggregate root manages its owned entities and value objects and serves as the entry point for saving changes to the aggregate.

Example order model:

~~~text
PurchaseOrder (aggregate root)
  ├── id
  ├── orderNumber
  ├── customerId
  ├── status
  └── lines
        ├── OrderLine
        └── OrderLine
~~~

If `OrderLine` only exists within the lifecycle of an order, the application typically saves and modifies it through `PurchaseOrderRepository`. If an object has an independent lifecycle and is referenced and modified separately, it may be a separate aggregate root.

Do not create a repository for every table just because the legacy DAO layer had one class per table. Doing so can break aggregate boundaries and allow the application to manipulate child entities independently outside the root's invariants.

### 3.1. Do Not Bring the JPA Mental Model into Spring Data JDBC

Spring Data JDBC is not JPA:

- There is no JPA-style persistence context or identity map.
- There is no automatic dirty checking when modifying a loaded object without calling `save`.
- There are no JPA-style lazy-loading proxies for relationships.
- Aggregates are saved according to Spring Data JDBC's lifecycle and mapping.
- Relationships are loaded according to mapping and aggregate design, rather than an arbitrary object graph.

Therefore, when migrating from `JdbcTemplate`, design aggregates in the way Spring Data JDBC manages them; do not create large entity graphs just to mimic an ORM.

## 4. Example Existing Schema and Spring Data JDBC Model

Suppose the legacy system has the following schema:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    sku VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_order(id)
);
~~~

Model:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        @Column("order_number") String orderNumber,
        @Column("customer_id") Long customerId,
        String status,
        @Column("created_at") Instant createdAt,
        @MappedCollection(idColumn = "purchase_order_id")
        List<OrderLine> lines
) {
    public PurchaseOrder confirm() {
        if (!"PENDING".equals(status)) {
            throw new IllegalStateException(
                    "Only pending orders can be confirmed");
        }
        return new PurchaseOrder(
                id, orderNumber, customerId, "CONFIRMED",
                createdAt, lines);
    }
}

public record OrderLine(
        @Id Long id,
        String sku,
        Integer quantity
) {}
~~~

Table and column names are declared explicitly so the mapping matches the existing schema. When the schema uses a different naming convention, use `@Table`, `@Column`, `@MappedCollection`, or the corresponding mapping metadata instead of altering the database just to match default names.

This example uses records to represent immutable data. For mutable entities, constructors, getters/setters, and access strategies must follow Spring Data JDBC's mapping conventions. Use data types and annotations supported by your running Spring Data version.

### 4.1. Mapping Child Collections

`@MappedCollection(idColumn = "purchase_order_id")` tells Spring Data JDBC which column in the child table references the aggregate root. The column name must match the current schema.

If child order must be preserved, consider declaring a key column via `keyColumn` and matching schema support. Do not assume row ordering in the database is guaranteed if the query has no `ORDER BY` or the mapping does not store element positions.

### 4.2. Database-Generated Primary Keys

When IDs are generated by the database, `@Id` on a compatible type lets Spring Data JDBC receive the ID created upon insert. Use the instance returned from `save` to obtain the ID:

~~~java
PurchaseOrder saved = repository.save(newOrder);
Long generatedId = saved.id();
~~~

Do not assume an immutable input object will be mutated in place. If the legacy application uses sequences, application-generated UUIDs, or composite keys, establish the ID strategy before migrating.

## 5. Migrating Finders from RowMapper to Repository Methods

### 5.1. Legacy Code

A legacy DAO often writes the query manually:

~~~java
public Optional<PurchaseOrderRow> findByOrderNumber(String number) {
    List<PurchaseOrderRow> rows = jdbcTemplate.query(
            """
            SELECT id, order_number, customer_id, status, created_at
            FROM purchase_order
            WHERE order_number = ?
            """,
            purchaseOrderRowMapper,
            number
    );
    return rows.stream().findFirst();
}
~~~

Something to check in the legacy code: `findFirst()` silently discards a second row if duplicate data exists. If `order_number` is supposed to be unique, this behavior hides corrupt data.

### 5.2. New Repository

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

The repository finder expresses the contract "zero or at most one order". If multiple rows exist, Spring Data throws `IncorrectResultSizeDataAccessException` instead of picking one arbitrarily.

To enforce the contract, the database needs a unique constraint:

~~~sql
ALTER TABLE purchase_order
ADD CONSTRAINT uk_purchase_order_number UNIQUE (order_number);
~~~

Before adding the constraint, inspect and resolve duplicate data with a planned migration. Do not delete duplicate rows automatically before establishing the business rule.

### 5.3. Use Collections for Multi-Result Queries

If multiple orders are a valid result:

~~~java
List<PurchaseOrder> findByCustomerId(Long customerId);
~~~

Do not turn a multi-result query into `Optional<T>` just to save lines of code. The return type should reflect business cardinality.

## 6. Migrating Create/Update from Manual SQL to save

### 6.1. Legacy Code

A DAO might insert the root and then retrieve the generated key to insert children:

~~~java
public long insertOrder(CreateOrderCommand command) {
    KeyHolder keyHolder = new GeneratedKeyHolder();

    jdbcTemplate.update(connection -> {
        PreparedStatement ps = connection.prepareStatement(
                """
                INSERT INTO purchase_order
                    (order_number, customer_id, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                Statement.RETURN_GENERATED_KEYS
        );
        ps.setString(1, command.orderNumber());
        ps.setLong(2, command.customerId());
        ps.setString(3, "PENDING");
        ps.setTimestamp(4, Timestamp.from(command.createdAt()));
        return ps;
    }, keyHolder);

    long orderId = keyHolder.getKey().longValue();
    // Insert order_line rows with orderId.
    return orderId;
}
~~~

This code requires a transaction so that inserting the root and children succeed or roll back together. If the DAO manages multiple connections manually or lacks a transaction boundary, it can produce a partially persisted aggregate.

### 6.2. New Repository

~~~java
@Service
public class PlaceOrderService {

    private final PurchaseOrderRepository repository;

    public PlaceOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder place(CreateOrderCommand command) {
        PurchaseOrder order = new PurchaseOrder(
                null,
                command.orderNumber(),
                command.customerId(),
                "PENDING",
                command.createdAt(),
                command.lines().stream()
                        .map(line -> new OrderLine(
                                null, line.sku(), line.quantity()))
                        .toList()
        );

        return repository.save(order);
    }
}
~~~

Spring Data JDBC persists the aggregate root and its child collection according to the mapping. The service remains responsible for creating valid domain state and defining the transaction boundary.

Do not assume every child schema is immediately compatible with collection mapping. Check foreign keys, ID generation, child ordering, nullability, default values, and existing triggers. If a legacy schema is complex or children are managed independently, you can keep part of the operations in `JdbcTemplate` during the transition phase.

### 6.3. Updating an Aggregate

Repository `save` is used for both inserts and updates based on the entity state determined by Spring Data JDBC. When updating, load the aggregate, invoke a domain method, and save the new aggregate:

~~~java
@Transactional
public PurchaseOrder confirm(Long id) {
    PurchaseOrder current = repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    return repository.save(current.confirm());
}
~~~

Do not simply modify the object and forget to call `save`. Spring Data JDBC does not use JPA-style dirty checking to automatically persist changes when the transaction ends.

## 7. Keeping JdbcTemplate in the Same Service Transaction

A use-case-by-use-case migration often includes a phase where a service uses both a repository and `JdbcTemplate`.

For example, the repository saves the order aggregate while `JdbcTemplate` updates a technical projection table:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    public OrderApplicationService(
            PurchaseOrderRepository orderRepository,
            JdbcTemplate jdbcTemplate) {
        this.orderRepository = orderRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public PurchaseOrder confirm(Long id) {
        PurchaseOrder order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        PurchaseOrder confirmed = order.confirm();
        PurchaseOrder saved = orderRepository.save(confirmed);

        jdbcTemplate.update(
                """
                UPDATE order_search_projection
                SET status = ?
                WHERE order_id = ?
                """,
                saved.status(),
                saved.id()
        );

        return saved;
    }
}
~~~

If `JdbcTemplate` and the repository use the same `DataSource` and the same transaction manager, the JDBC operation can participate in the active transaction. If the projection update fails and the exception crosses the transaction boundary, the repository changes also roll back.

This condition must be verified in configuration. If there are multiple `DataSource`s, multiple transaction managers, or manual connection acquisition via `DataSource.getConnection()`, do not assume they participate in the same transaction. For direct JDBC inside a Spring transaction, use `JdbcTemplate`, `DataSourceUtils`, or an appropriate transaction-aware mechanism.

## 8. Migrating Custom Queries with @Query

Not every query needs to be rewritten as a derived method. Spring Data JDBC supports `@Query` to declare explicit SQL for a repository method:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number, customer_id, status, created_at
        FROM purchase_order
        WHERE customer_id = :customerId
          AND status = :status
        ORDER BY created_at DESC, id DESC
        """)
    List<PurchaseOrder> findRecentByCustomerAndStatus(
            @Param("customerId") Long customerId,
            @Param("status") String status
    );
}
~~~

`@Query` retains SQL control while bringing the query into the repository contract. This is useful when the query is a stable part of aggregate operations.

Notes:

- Column names must match the schema and mapping.
- The result set must include all columns needed for the return type.
- Use bound parameters instead of concatenating input into SQL.
- `ORDER BY` must be deterministic if callers depend on order.
- A query returning an aggregate root does not automatically turn a one-to-many join into a complete object graph.
- SQL inside `@Query` remains tied to the database dialect; it is not automatically portable across all databases.

If a query returns a complex DTO or report projection, `JdbcTemplate` with a `RowMapper` may be clearer and more appropriate.

## 9. Custom Repository Fragments When Combining Abstractions

Some use cases need a repository contract with a custom SQL implementation. You can use a repository fragment:

~~~java
public interface PurchaseOrderSearch {
    List<OrderSummary> search(OrderSearchCriteria criteria);
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long>,
                PurchaseOrderSearch {
}
~~~

The fragment implementation can use `JdbcTemplate`:

~~~java
public class PurchaseOrderSearchImpl implements PurchaseOrderSearch {

    private final JdbcTemplate jdbcTemplate;

    public PurchaseOrderSearchImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public List<OrderSummary> search(OrderSearchCriteria criteria) {
        return jdbcTemplate.query(
                """
                SELECT id, order_number, status, created_at
                FROM purchase_order
                WHERE customer_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_number"),
                        rs.getString("status"),
                        rs.getTimestamp("created_at").toInstant()
                ),
                criteria.customerId()
        );
    }
}
~~~

The implementation class name must follow the Spring Data repository fragment discovery convention for your project version. Repository fragments are useful when you want the search API on the repository while needing custom SQL. Do not convert every legacy DAO into a fragment just to rename classes.

## 10. Keeping Reporting Queries and Bulk Operations in JdbcTemplate

### 10.1. Reporting/Aggregates

For example, a dashboard needs grouping and counts:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM purchase_order
WHERE created_at >= ?
GROUP BY status
ORDER BY order_count DESC;
~~~

This is a reporting projection, not an aggregate root. `JdbcTemplate` with a DTO/RowMapper is usually the natural choice:

~~~java
public record OrderCountByStatus(String status, long count) {}

public List<OrderCountByStatus> countByStatus(Instant from) {
    return jdbcTemplate.query(
            """
            SELECT status, COUNT(*) AS order_count
            FROM purchase_order
            WHERE created_at >= ?
            GROUP BY status
            ORDER BY order_count DESC
            """,
            (rs, rowNum) -> new OrderCountByStatus(
                    rs.getString("status"),
                    rs.getLong("order_count")
            ),
            Timestamp.from(from)
    );
}
~~~

There is no need to construct a `PurchaseOrder` for each report row.

### 10.2. Bulk Updates

For example, closing thousands of expired orders:

~~~sql
UPDATE purchase_order
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND expires_at < ?;
~~~

This is a bulk operation across many rows. Using `JdbcTemplate.update` can be more efficient and clearer than loading each aggregate and calling `save` in a loop:

~~~java
int expirePendingOrders(Instant cutoff) {
    return jdbcTemplate.update(
            """
            UPDATE purchase_order
            SET status = 'EXPIRED'
            WHERE status = 'PENDING'
              AND expires_at < ?
            """,
            Timestamp.from(cutoff)
    );
}
~~~

However, bulk SQL bypasses lifecycle callbacks and per-aggregate domain logic. If `@Version`, auditing, or business invariants exist, you must update the relevant columns and account for optimistic locking impacts. Do not use bulk updates to bypass domain rules.

## 11. Transaction Boundaries During Migration

Place transactions at the service/use case level so that multiple data operations succeed or fail together:

~~~java
@Transactional
public void completeOrder(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow();

    orderRepository.save(order.complete());
    jdbcTemplate.update(
            "UPDATE customer_stats SET completed_orders = completed_orders + 1 " +
            "WHERE customer_id = ?",
            order.customerId()
    );
}
~~~

If both use the same local transaction manager and `DataSource`, the statements can commit or roll back together.

Things to verify:

- Whether the repository and `JdbcTemplate` are injected with the same `DataSource` configuration.
- Whether `PlatformTransactionManager` manages that exact `DataSource`.
- Whether the service is invoked through a Spring proxy rather than self-invocation.
- Whether exceptions cross the transaction boundary.
- Whether checked exceptions require `rollbackFor`.
- Whether `REQUIRES_NEW` or async tasks start separate transactions.

Do not assume a single `@Transactional` can roll back two independent database resources. If two DAOs use different DataSources or transaction managers, an appropriate distributed architecture or eventual consistency is required.

## 12. Preserving Service Contracts When Replacing Implementations

Controllers and consumers should depend on application services/use cases, not directly on `JdbcTemplate` or specific repositories.

Example contract:

~~~java
public interface OrderQueries {
    Optional<OrderDetails> findDetails(String orderNumber);
}

public interface OrderCommands {
    PurchaseOrder confirm(Long id);
}
~~~

During migration, the service can call the legacy DAO. Once the new repository is ready, swap the implementation inside the service without changing the external API:

~~~text
Controller / Message Handler
            │
            ▼
       Application Service
            │
       ┌────┴─────┐
       ▼          ▼
   Old DAO    New Repository
 JdbcTemplate  Spring Data JDBC
~~~

This reduces the blast radius of changes: callers still invoke the same use case while only the persistence adapter changes. Do not let controllers call a repository in some endpoints and a DAO directly in others.

## 13. Step-by-Step Migration Strategy

A safe sequence:

### Step 1: Pick a Small Use Case

Choose a read/write path with clear scope, minimal side effects, and independent testability—for example, finding an order by order number or updating order status.

Avoid starting with complex use cases involving multiple databases, large batches, triggers, and external side effects.

### Step 2: Document Current Behavior

Capture current SQL and bound parameters, return types and behavior for missing/multiple rows, null handling and exception mapping, transaction boundaries, generated keys/default values/triggers, result ordering if callers depend on it, and query latency and frequency.

Write characterization tests to lock down the current contract before making changes.

### Step 3: Define Aggregates and Mapping

Identify the root, child entities, IDs, columns, and relationships. Declare Spring Data JDBC mappings matching the existing schema. Do not change the schema at the same time unless necessary.

### Step 4: Create the New Repository

Start with simple finders and CRUD. Use `Optional` for 0/1 results, collections for multi-row results, and unique constraints for uniqueness invariants.

### Step 5: Migrate One Service Method

Replace the DAO call with a repository call inside the application service. Keep the method signature and transaction semantics unchanged if that is the desired contract.

### Step 6: Reconcile Results

Run tests against the same data, comparing return values, rows read/written, null/time/enum/numeric mappings, generated IDs, side effects, transaction rollbacks, and query count/latency when relevant.

### Step 7: Shift Traffic

Once tests are stable, route the use case through the new repository. For systems needing gradual rollout, use a feature flag at the application service layer to select the adapter. Do not dual-write to both implementations without explicit idempotency and reconciliation mechanisms.

### Step 8: Observe Production

Monitor mapping errors, duplicate results, transaction rollbacks, query latency, connection pool usage, and database load. Compare against the recorded baseline.

### Step 9: Remove Legacy Code After Verification

Only delete old DAOs and `RowMapper`s once no callers remain and an appropriate verification period has passed. Keep queries that still have a clear reason to use `JdbcTemplate`.

## 14. Do Not Dual-Write Arbitrarily

During a migration, teams are sometimes tempted to write through both the legacy DAO and the new repository to compare them. This can cause duplicate inserts or duplicate side effects, double version increments, triggers firing twice, duplicated audit events, race conditions, or divergent state if one write path fails mid-flight.

For read paths, you can run shadow reads in a controlled environment: one implementation returns results to the caller while the other reads purely for comparison. Account for database load and verify the secondary query has no side effects.

For write paths, prefer a single authoritative write path. To verify parity, use fixtures/tests or replay against a test database. Only dual-write when you have an explicit design for idempotency, reconciliation, and failure handling.

## 15. Mapping Differences to Watch Out For

When replacing a `RowMapper` with Spring Data JDBC mapping, check these data types:

| Legacy Data | What to Verify on Migration |
| --- | --- |
| Timestamp/Date | Time zone, precision, `Instant`/`LocalDateTime`, and JDBC driver |
| Enum | String or ordinal mapping; what the current schema stores |
| Boolean | Column type and database-specific conversion |
| Decimal | Precision/scale and `BigDecimal` |
| JSON/JSONB | JDBC type, converter, and driver-specific value |
| UUID | Driver/database representation and conversion |
| Null | Nullable columns, constructor parameters, and wrapper types |
| Generated ID | Identity/sequence/UUID and value returned from `save` |
| Naming | Existing table/column names and naming strategy |
| Child collection | Foreign key, key/order column, and aggregate ownership |

If a data type needs custom conversion, Spring Data JDBC supports custom conversions. Register converters according to the mapping configuration for your version and write round-trip tests from domain value to JDBC value and back.

Do not change how enums, timestamps, or JSON are stored simply because a default mapping is more convenient. Existing data must continue to read correctly.

## 16. Generated Columns, Defaults, and Triggers

Legacy DAOs may omit certain columns because the database assigns defaults or triggers populate values. When moving to a repository, inspect how Spring Data JDBC generates INSERTs and how the database returns generated values.

For example:

~~~sql
created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
~~~

If an entity passes `createdAt = null`, a database default is only applied when the INSERT statement omits the column or uses the DEFAULT keyword with appropriate syntax; if Spring Data sends the column with a NULL value, the default may not trigger. Inspect the actual SQL and mapping.

Similarly, a trigger may update `updated_at`, but the object returned from `save` will not necessarily reflect trigger changes automatically if the database/driver does not return them. If the caller needs post-trigger values, design an appropriate reload or generated-value mechanism.

## 17. Paging, Streaming, and Large Datasets

Not every repository collection is suitable for millions of rows. Before migrating a large query from `JdbcTemplate`, determine the maximum result size, whether all data is needed in memory, whether sorting/paging is required, whether cursors/streams and long-running transactions are needed, and whether keyset/batch processing can be used.

If the use case is a large export, `JdbcTemplate` with `RowCallbackHandler`, `ResultSetExtractor`, or streaming may be a better fit. If migrating to a repository, choose return types and transaction/resource lifecycles according to your Spring Data JDBC version's contract.

For pagination, inspect the count query, query counts, and sorting. For deep offsets, consider keyset pagination if the API allows it.

## 18. Testing the Migration

Multiple test layers should be in place:

| Test | What It Verifies |
| --- | --- |
| Mapping/repository test | Entities read/write cleanly against the schema |
| Query test | Finders return the expected 0/1/many results and ordering |
| Service test | Use cases preserve business contracts |
| Transaction integration test | Repository and `JdbcTemplate` commit/roll back together |
| Database integration test | Dialect, driver, generated keys, constraints, and type mappings are accurate |
| Performance comparison | Latency, query count, and resource usage do not regress unexpectedly |

Example repository test:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void findsOrderByUniqueOrderNumber() {
        PurchaseOrder saved = repository.save(
                new PurchaseOrder(
                        null, "PO-100", 42L, "PENDING",
                        Instant.parse("2026-01-01T10:00:00Z"),
                        List.of()
                )
        );

        Optional<PurchaseOrder> found =
                repository.findByOrderNumber("PO-100");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().id()).isEqualTo(saved.id());
    }
}
~~~

Example integration test verifying that the repository and `JdbcTemplate` share the same transaction:

~~~java
@SpringBootTest
class MixedPersistenceRollbackTest {

    @Autowired
    OrderApplicationService service;

    @Autowired
    PurchaseOrderRepository repository;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackRepositoryAndJdbcTemplateWritesTogether() {
        assertThatThrownBy(() -> service.createAndFail())
                .isInstanceOf(IllegalStateException.class);

        assertThat(repository.count()).isZero();

        Integer projectionCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM order_search_projection",
                Integer.class
        );
        assertThat(projectionCount).isZero();
    }
}
~~~

Transaction integration tests should invoke the service through a Spring bean/proxy. If the test method itself is annotated with `@Transactional`, the test transaction can mask whether the service actually has its own transaction boundary. Use a production-like database engine when relying on dialect, constraints, or driver behavior.

## 19. Measuring Performance Before and After

The repository abstraction does not automatically make queries faster. Generated SQL may differ from the legacy DAO in column count, query count, or aggregate loading behavior.

Compare before and after:

- Number of SQL statements per use case.
- Query latency p50/p95/p99.
- Rows read and rows returned.
- Unintended N+1 or repeated queries.
- Connection acquisition and usage time.
- Database CPU, I/O, and lock wait.
- Write operation throughput.
- Size of data/aggregates loaded into memory.

A simple finder may migrate cleanly, but if a repository loads an entire aggregate with many children where the legacy DAO only selected a small projection, performance can degrade. In such cases, keep the projection query in `JdbcTemplate` or design a dedicated query.

Do not benchmark with tiny datasets if production has millions of rows. Test data should reflect realistic distribution and cardinality.

## 20. Common Migration Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Repository cannot find table/column | Default mapping does not match legacy schema | Declare `@Table`, `@Column`, `@MappedCollection` |
| Root inserts but children are not saved | Wrong aggregate mapping/foreign key or child outside root | Check aggregate boundary and `idColumn` |
| Database default value becomes NULL | INSERT sends NULL instead of omitting column/default | Check SQL and generated/default column mapping |
| Returned ID differs from legacy DAO | Different generated key/sequence strategy | Verify ID strategy and use the instance returned from `save` |
| Query returns duplicate results | Single return type but data/query matches multiple rows | Add unique constraint, fix predicate, or return collection |
| Repository and `JdbcTemplate` do not roll back together | Different `DataSource`/transaction manager or transaction boundary | Share the same transaction resource and add integration tests |
| Update does not persist object changes | Forgot to call `save` or incorrect entity state | Load aggregate, call domain method, then save |
| Update rewrites more children than expected | Aggregate collection mapping differs from legacy DAO | Review ownership and aggregate save semantics |
| New query is slower | Loading large aggregates or different SQL | Measure query plan, projections, and SQL count |
| Batch operations are slow | Replaced bulk SQL with a loop saving individual aggregates | Keep bulk path in `JdbcTemplate` when appropriate |
| Triggers/auditing produce different values | Lifecycle callbacks and triggers both write the field | Define one clear contract and test final values |
| Tests pass but production fails | Tested only on embedded DB or test-managed transactions | Run integration tests against target database |

## 21. Per-Use-Case Checklist

Before migrating a use case, verify:

1. Are the use case and current contract documented and tested?
2. Does the query return 0/1/many rows and does the new return type express that accurately?
3. Does the data belong to a well-defined aggregate root?
4. Does the mapping match table/column names, IDs, nullability, defaults, and child keys?
5. Can custom SQL use a derived query/`@Query` or should it stay in `JdbcTemplate`?
6. Does the transaction boundary encompass the entire business operation?
7. Do the repository and `JdbcTemplate` share the same `DataSource`/transaction manager when needed?
8. Have rollback, generated IDs, triggers, and audit metadata been verified?
9. Do tests run against the target database and driver?
10. Have query count, latency, and write overhead been compared?
11. Is there a clear way to shift traffic or roll back the implementation?
12. Is the legacy DAO removed only after no callers remain and new behavior is confirmed?

## 22. Practice Exercises

**Exercise 1 — Use Case Inventory.** Pick three methods in an existing `JdbcTemplate` DAO. Document the SQL, tables, cardinality, transactions, and business purpose of each. Classify which should migrate to a repository and which should stay in SQL.

**Exercise 2 — Migrate a Finder.** Convert a `RowMapper` lookup by business key into a repository method returning `Optional<T>`. Add the corresponding unique constraint and test the not-found case.

**Exercise 3 — Migrate an Aggregate Write.** Convert a root/child insert operation into a Spring Data JDBC aggregate. Verify generated IDs and child foreign keys match the legacy schema.

**Exercise 4 — Keep `JdbcTemplate` in Transaction.** Write a `@Transactional` service calling repository `save` and `JdbcTemplate.update`. Intentionally fail the final step and verify both writes roll back.

**Exercise 5 — Custom Query.** Migrate a simple query to `@Query`. Compare the SQL, bound parameters, and result mapping against the legacy DAO.

**Exercise 6 — Reporting.** Keep a `GROUP BY` query in `JdbcTemplate` mapped to a DTO. Explain why reporting data should not become an aggregate root.

**Exercise 7 — Bulk Update.** Keep a bulk update in `JdbcTemplate`. Identify which version/audit columns must be updated and test the impact on repository optimistic locking if applicable.

**Exercise 8 — Custom Repository Fragment.** Create a repository fragment with a `JdbcTemplate` implementation for a complex search query. Check the naming/discovery convention for your Spring Data version.

**Exercise 9 — Legacy Mapping.** Migrate a timestamp, enum, or JSON column from `RowMapper` to Spring Data JDBC mapping. Write a round-trip test against the target database.

**Exercise 10 — Before/After Measurement.** Measure query count and latency for a use case before and after migration. Explain changes caused by aggregate loading, projections, indexes, or transactions.

**Exercise 11 — Feature Flag.** Keep both adapters behind the same service contract and toggle a read use case using a feature flag in staging. Compare results without dual-writing.

**Exercise 12 — Migration Rollback.** Pick a migrated use case, simulate a production error, and switch traffic back to the legacy implementation. Document the requirements for a safe rollback when the schema is unchanged.

### References

- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repositories, mapping, aggregate persistence, and queries in Spring Data JDBC.
- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): entity, table/column, and collection mapping.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): derived queries and query annotations.
- [Spring Framework — JdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): SQL execution, `RowMapper`, and JDBC abstractions.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries and rollback rules.
- [Spring Framework — JDBC Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource` connection management and transaction integration.
