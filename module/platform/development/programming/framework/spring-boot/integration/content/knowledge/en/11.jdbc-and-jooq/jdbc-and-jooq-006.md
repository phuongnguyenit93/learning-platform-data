# Integrating Spring Data JDBC and Boundaries with JPA

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects systems across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. A typical flow persists an order in PostgreSQL, emits an event via a transactional outbox, deduplicates broker redeliveries, and queries data to call downstream services. Choosing among **Spring Data JDBC**, **Spring Data JPA**, `JdbcTemplate`, or **jOOQ** shapes data boundaries, transactions, generated SQL, query optimization, and recoverability.

Spring Data JDBC provides **repositories and relational aggregate mapping**, yet **has no JPA persistence context**. It fits when you want explicit persistence boundaries, clear updates, and no reliance on lazy loading or dirty checking. Spring Data JPA adds JPA entity lifecycles, association mapping, persistence contexts, and deeper ORM capabilities. `JdbcTemplate`/`JdbcClient` give direct SQL control, while jOOQ excels at complex typed SQL queries.

This lesson belongs to the **JDBC and jOOQ** chapter and covers **Integrating Spring Data JDBC and Boundaries with JPA**. Its concepts tie directly into connection configuration, data contracts, transactions, error handling, idempotency, testing, and observability for Spring Boot integration flows.

After this lesson, you will be able to:

1. Distinguish JDBC drivers, `DataSource`, `JdbcTemplate`, `JdbcClient`, Spring Data JDBC repositories, JPA, and jOOQ.
2. Design **aggregate roots**, child entities, and references properly for Spring Data JDBC.
3. Use `@Table`, `@Id`, `@MappedCollection`, `@Version`, `CrudRepository`, and `save()`.
4. Explain why Spring Data JDBC has no JPA dirty checking, lazy loading, or managed entity graphs.
5. Decide when to use repositories vs. SQL projections, `JdbcClient`, or jOOQ.
6. Set local transaction boundaries properly, combining outboxes and idempotency for safe HTTP/broker delivery.
7. Test mappings, optimistic locking, rollbacks, and migrations using PostgreSQL Testcontainers.
8. Diagnose slow SQL, connection pool exhaustion, contention, and bugs caused by choosing the wrong abstraction.

> **Guiding principle:** Spring Data JDBC is *aggregate-oriented persistence*, not "minimalist JPA with fewer features." It adopts **a different persistence model**, so moving from JPA to JDBC involves far more than swapping dependencies.

## 1. Overview of SQL Layers in Spring Boot

~~~mermaid
flowchart TD
    S["OrderService / IntegrationFlow"] --> R["Spring Data JDBC Repository"]
    S --> J["JdbcTemplate / JdbcClient"]
    S --> Q["jOOQ DSLContext"]
    S --> P["Spring Data JPA Repository"]
    R --> M["Spring Data JDBC Relational Mapping"]
    J --> SQL["Explicit SQL"]
    Q --> SQL
    P --> E["JPA EntityManager / Hibernate"]
    M --> DS["DataSource / HikariCP"]
    SQL --> DS
    E --> DS
    DS --> DB["PostgreSQL / MySQL / SQL Server"]
~~~

| Component | Role | What It Does Not Provide Automatically |
| --- | --- | --- |
| JDBC driver | Speaks the SQL protocol with the database | Domain mapping and business transactions |
| `DataSource`/HikariCP | Provisions, manages, and reuses JDBC connections | Repository API |
| `JdbcTemplate` | Executes SQL, binds parameters, maps results | Aggregate lifecycle |
| `JdbcClient` | Fluent SQL API on Spring JDBC (Spring Framework 6.1+) | ORM or JPA persistence context |
| **Spring Data JDBC** | Persists relational aggregates via Spring Data repositories | JPA-style lazy associations or dirty checking |
| **jOOQ** | Typed SQL DSL, code generation, JOINs/CTEs/windows | JPA managed entities |
| **Spring Data JPA** | ORM entities/relationships, persistence context, dirty checking | Guaranteed minimal SQL or freedom from N+1 |

These layers can **coexist** on the same `DataSource`, provided they share the same transaction infrastructure and transaction manager to participate in one transaction. A manually created `DSLContext` outside Spring may open a separate connection and fail to roll back alongside a repository.

## 2. Designing Around Aggregate Roots

In Domain-Driven Design, an **aggregate** is a cluster of data that must stay consistent together; all changes go through the **aggregate root**. Example:

~~~mermaid
flowchart TD
    O["PurchaseOrder — aggregate root"]
    O --> L1["OrderLine SKU-A"]
    O --> L2["OrderLine SKU-B"]
    O -. "customerId reference" .-> C["Customer — independent aggregate"]
    O -. "shipmentId reference" .-> H["Shipment — independent aggregate"]
~~~

- `PurchaseOrder` is the root persisted by the repository.
- `OrderLine` is a child owned within the `PurchaseOrder` lifecycle.
- `Customer` and `Shipment` have independent lifecycles; `PurchaseOrder` holds only IDs or references.
- Invariants—such as positive quantities, no duplicate SKUs, or max line counts—are enforced in the domain or application service.
- Database constraints serve as the final guard against races or direct writes from other applications.

Spring Data JDBC deliberately centers on aggregate boundaries. If an object merely references another aggregate, do not map it as an object graph that cascades inserts/updates across everything.

### 2.1. JPA Thinks in Entity Graphs

In JPA/Hibernate, `OrderEntity` may hold `@OneToMany` lines and `@ManyToOne` customer, each with fetch and cascade rules. A persistence context tracks loaded entities and Hibernate dirty-checks fields.

Spring Data JDBC **does not** track objects in a persistence context and **does not lazy-load** associations on getter access. It loads and saves relationships strictly within the mapped aggregate boundary, avoiding unbounded ORM object graphs.

### 2.2. When Should a Child Become a Separate Aggregate?

Consider splitting when a child has its own identity, is referenced directly by other systems, has an independent lifecycle, faces high concurrent update contention, or makes loading/saving the root excessively heavy. For example, shipments or payments should rarely cascade blindly from an order when they have separate state machines and transactions.

## 3. Spring Boot Dependencies

Gradle Groovy DSL example with Spring Boot 3.x, Java 17+, and PostgreSQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    implementation 'org.flywaydb:flyway-core'
    // For Flyway releases that require a separate driver/dialect module:
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'

    // When serializing outbox JSON events with Jackson:
    implementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Let the Spring Boot BOM manage dependency versions. With Boot 4, newer Spring Data JDBC releases, or newer Flyway generations, starter/module/import names may differ; check against your exact project versions. Never add `spring-boot-starter-data-jpa` just to get Spring Data repositories.

### 3.1. Datasource and Pool Configuration

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/integration_db}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-jdbc
      maximum-pool-size: 12
      connection-timeout: 3000
      max-lifetime: 1800000

  flyway:
    enabled: true
~~~

Numeric Hikari timeouts like these are normally in **milliseconds**; verify against your property binder and driver version. `maximum-pool-size` applies **per instance/pod**: 8 replicas × 12 ≈ 96 connections, excluding other services. Never hardcode production passwords. PostgreSQL TLS and server hostname verification must be configured explicitly per JDBC driver and security policy.

### 3.2. Auto-Configuration Does Not Generate Your Entire Schema

With the right dependencies, Boot provisions the `DataSource`, JDBC mapping/repositories, transaction manager, and Flyway. Production schemas should be managed via migrations. Do not expect Spring Data JDBC to auto-create or sync tables like an ORM schema-generation tool.

## 4. SQL Schema for the `PurchaseOrder` Aggregate

PostgreSQL migration example:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    external_id VARCHAR(120) NOT NULL UNIQUE,
    customer_id VARCHAR(120) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE purchase_order_lines (
    order_id BIGINT NOT NULL
        REFERENCES purchase_orders(id) ON DELETE CASCADE,
    line_position INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_position)
);

CREATE INDEX idx_purchase_orders_customer
    ON purchase_orders(customer_id);
~~~

Assume the migration is stored in `db/migration/V1__create_orders.sql`. Per the scope of STEP 4, this lesson only provides the SQL snippet without creating extra migration files.

**Responsibility boundaries:**

- `purchase_orders.id` is the technical primary key.
- `external_id` is the business identity, constrained unique for idempotency.
- `version` enables optimistic locking.
- `purchase_order_lines.order_id` is the foreign key to the root.
- `line_position` stores collection order; **it is not a stable business `lineId`**.
- `CHECK (quantity > 0)` protects the invariant even against external SQL writers.

If each order line needs a stable identity across reorderings, add a business line ID/unique constraint or redesign the aggregate rather than relying indefinitely on list indexes.

## 5. Mapping Root and Child Entities in Spring Data JDBC

### 5.1. `PurchaseOrder` Aggregate Root

~~~java
// PurchaseOrder.java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Version Long version,
        @Column("external_id") String externalId,
        @Column("customer_id") String customerId,
        String status,
        @MappedCollection(
                idColumn = "order_id",
                keyColumn = "line_position")
        List<PurchaseOrderLine> lines) {

    public PurchaseOrder {
        lines = List.copyOf(lines);
    }

    public PurchaseOrder withStatus(String status) {
        return new PurchaseOrder(
                id, version, externalId, customerId,
                status, lines);
    }
}
~~~

`@Id` and `@Version` come from `org.springframework.data.annotation`, not `jakarta.persistence.Id`/`jakarta.persistence.Version`. `@Table` and `@MappedCollection` belong to Spring Data Relational.

Java records support immutable state; the compact constructor makes a defensive copy, requiring `lines` to be non-null and free of null elements. Validate inputs before constructing the aggregate.

### 5.2. Child Entity

~~~java
// PurchaseOrderLine.java
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order_lines")
public record PurchaseOrderLine(
        String sku,
        int quantity) {

    public PurchaseOrderLine {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be > 0");
        }
    }
}
~~~

`@MappedCollection(idColumn="order_id", keyColumn="line_position")` specifies the foreign key and list/map key column. With immutable root/child records, Spring Data JDBC requires constructor/value mapping compatible with your version. Always write integration tests for save, load, and update—especially when combining immutable aggregates with generated IDs.

### 5.3. Mapping Annotations Differ from JPA

| Spring Data JDBC | JPA |
| --- | --- |
| `org.springframework.data.relational.core.mapping.Table` | `jakarta.persistence.Table` |
| `org.springframework.data.annotation.Id` | `jakarta.persistence.Id` |
| `org.springframework.data.annotation.Version` | `jakarta.persistence.Version` |
| `@MappedCollection` | `@OneToMany`, `@ElementCollection` |
| Explicit aggregate persistence | `EntityManager` / persistence context |
| No JPA lazy loading | Supports `LAZY` per provider/mapping |

Never annotate a single Java class as both a JPA entity and a Spring Data JDBC aggregate without a compelling, thoroughly tested reason; their annotation and lifecycle models conflict.

## 6. `CrudRepository`: Saving and Querying the Root

~~~java
// PurchaseOrderRepository.java
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByExternalId(String externalId);

    boolean existsByExternalId(String externalId);
}
~~~

The repository is a Spring-managed proxy; it **is not a JDBC `Connection`**. `DataSource`/HikariCP supplies connections per operation as needed. Domain services normally inject singleton repositories.

### 6.1. Inserting an Aggregate

~~~java
import java.util.List;

PurchaseOrder draft = new PurchaseOrder(
        null,
        null,
        "EXT-2026-001",
        "CUST-10",
        "DRAFT",
        List.of(
                new PurchaseOrderLine("SKU-A", 2),
                new PurchaseOrderLine("SKU-B", 3)));

PurchaseOrder saved = repository.save(draft);

// Use saved.id(), saved.version().
// Do not assume an immutable draft is mutated in place.
~~~

With generated IDs, `save` returns **a new instance** populated with the ID and version rather than mutating the input object. Always use the returned instance when continuing work with an immutable aggregate.

### 6.2. Reading an Aggregate

~~~java
PurchaseOrder loaded =
        repository.findByExternalId("EXT-2026-001")
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Order not found"));
~~~

Spring Data JDBC loads the root along with mapped child collections. It has no JPA persistence context or Hibernate-style lazy loading; large child collections can trigger extra SQL queries. For endpoints needing only summaries, do not load a thousand-line aggregate when an SQL projection suffices.

### 6.3. Explicit Updates

~~~java
PurchaseOrder existing =
        repository.findByExternalId("EXT-2026-001")
                .orElseThrow();

PurchaseOrder confirmed =
        repository.save(existing.withStatus("CONFIRMED"));
~~~

**There is no dirty checking:** calling `existing.withStatus("CONFIRMED")` and returning from `@Transactional` **without `save`** causes Spring Data JDBC to issue no `UPDATE` at all.

### 6.4. New vs. Existing Detection on `save`

Spring Data JDBC decides whether an entity is new or existing using the ID, `@Version`, and hooks like `Persistable`. Null generated IDs and versions typically signify a new entity. If the application **assigns IDs itself**, verify new-state detection carefully—an entity with a pre-populated ID will not automatically execute an `INSERT` unless configured properly.

## 7. Save Semantics and the Cost of Updating Children

Spring Data JDBC persists the **full aggregate state** supplied. In many versions and configurations, saving an existing aggregate root **deletes and re-inserts dependent child rows**, even when only a root field changed. Exact SQL depends on version, mappings, and optimizations.

Implications:

- Orders with 2–20 lines are easy to manage.
- Aggregates with 50,000 lines can trigger massive `DELETE`/`INSERT` churn, locks, and transaction latency.
- Triggers, audit logs, and foreign keys referencing child rows may be affected.
- Never assume `save` updates only changed columns like JPA dirty checking.
- Inspect real generated SQL before modeling very large aggregates.

### 7.1. Adjust Aggregate Boundaries Instead of Enlarging the Pool

If child rows update independently, carry separate identities, or experience high write rates, split them into their own aggregate and reference them by ID. Increasing the Hikari pool will not fix an aggregate update issuing thousands of writes.

### 7.2. Root References Do Not Cascade

References to other aggregates like `Customer` or `Shipment` should be IDs. Spring Data JDBC provides `AggregateReference<T, ID>`:

~~~java
import org.springframework.data.jdbc.core.mapping.AggregateReference;

// Customer is an illustrative type in another bounded context.
AggregateReference<Customer, Long> customer =
        AggregateReference.to(123L);
~~~

This reference models identity only—it **never auto-queries/lazy-loads `Customer`** and never cascades saves. If the referenced entity lives in another microservice, a plain `String customerId` may be simpler.

## 8. Comparing Spring Data JDBC and JPA

| Topic | Spring Data JDBC | Spring Data JPA |
| --- | --- | --- |
| Model | Aggregate root and owned children | JPA entities / object graphs |
| Persistence context | None (no JPA context) | `EntityManager` tracks managed entities |
| Dirty checking | No; explicit `save` required | Yes, on managed entities |
| Lazy loading | No JPA-style lazy loading | Supports `LAZY` per association/provider |
| Relationships | `@MappedCollection`, IDs/references | `@OneToMany`, `@ManyToOne`, cascades |
| Repository | Spring Data `CrudRepository` | `JpaRepository` |
| Entity annotations | Spring Data Relational | Jakarta Persistence |
| ORM state management | No JPA flush/first-level cache | Flush, identity map, snapshots |
| Querying | Derived queries, SQL `@Query`, projections | JPQL, Criteria, native SQL, projections |
| Child persistence | Scoped to aggregate boundary | Governed by persistence context/cascade |
| Optimistic locking | Spring `@Version` | JPA `@Version` |
| Batch/complex SQL | Pairs with `JdbcTemplate`/jOOQ | Can supplement with native SQL/jOOQ |
| Complexity | Easy to reason about for moderate aggregates | More powerful, requires mastering fetch/flush/N+1 |

### 8.1. JPA Dirty Checking Example

~~~java
// JPA-only code, not Spring Data JDBC.
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class JpaOrderEntity {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    protected JpaOrderEntity() {
    }

    public void confirm() {
        this.status = "CONFIRMED";
    }
}
~~~

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void confirmJpa(Long id) {
    JpaOrderEntity entity =
            entityManager.find(JpaOrderEntity.class, id);

    entity.confirm();

    // Hibernate/JPA may flush when appropriate;
    // the managed entity is tracked in the persistence context.
}
~~~

This snippet assumes `entityManager` is properly injected. Flushing can occur before subsequent queries or at commit depending on flush mode, not exclusively on method return.

### 8.2. Spring Data JDBC Equivalent

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void confirmJdbc(Long id) {
    PurchaseOrder order =
            repository.findById(id).orElseThrow();

    repository.save(order.withStatus("CONFIRMED"));
}
~~~

With JDBC, `@Transactional` groups SQL operations into one local transaction—it **adds no Java object-tracking mechanism**.

### 8.3. Choosing Based on Use Case

Consider Spring Data JDBC when:

- Write models have clear aggregate boundaries.
- You want lean domain models with predictable SQL and lifecycles.
- You do not need lazy JPA entity graphs.
- Aggregates are moderate in size.
- Read models and reports are frequently written in custom SQL.
- Local transactions and outboxes drive external integration.

Consider JPA when:

- Complex entity graphs and associations are core to the domain.
- Persistence context, cascading, and dirty checking eliminate significant boilerplate.
- You need JPA capabilities like JPQL, Criteria, or entity graphs.
- The team understands and operates fetch plans, flush modes, N+1 prevention, and caching.

**Never pick JPA just because a schema has many tables**; complex reporting `JOIN`s often fit jOOQ better than an ORM graph.

## 9. Repository vs. `JdbcTemplate`/`JdbcClient`/jOOQ?

One application can combine:

- **Spring Data JDBC** to write root aggregates.
- **`JdbcClient` or `JdbcTemplate`** for lean read projections, batch updates, and direct SQL.
- **jOOQ** for typed SQL generation, CTEs, window functions, and vendor-specific features.
- **JPA** in a separate bounded context that genuinely needs ORM.

### 9.1. Read Projection with `JdbcClient`

Spring Framework 6.1+ provides `JdbcClient`:

~~~java
// OrderReadRepository.java
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadRepository {

    private final JdbcClient jdbcClient;

    public OrderReadRepository(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public List<OrderListItem> findRecent(int limit) {
        if (limit <= 0 || limit > 200) {
            throw new IllegalArgumentException(
                    "limit must be in 1..200");
        }

        return jdbcClient.sql(
                """
                SELECT id, external_id, status
                FROM purchase_orders
                ORDER BY id DESC
                LIMIT :limit
                """)
                .param("limit", limit)
                .query((rs, rowNum) ->
                        new OrderListItem(
                                rs.getLong("id"),
                                rs.getString("external_id"),
                                rs.getString("status")))
                .list();
    }

    public record OrderListItem(
            long id, String externalId, String status) {
    }
}
~~~

This fetches only 3 columns and **does not materialize any lines**. On Spring Framework earlier than 6.1, use `JdbcTemplate` or `NamedParameterJdbcTemplate`.

**SQL injection:** bind all values; never concatenate user inputs into SQL. Dynamic column names, `ORDER BY` fields, or table names must come strictly from an allowlist.

### 9.2. jOOQ with Generated SQL Types

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'
}
~~~

Snippet assuming the project has run **jOOQ code generation** from its schema:

~~~java
import java.util.List;
import org.jooq.DSLContext;

import static com.example.jooq.tables.PurchaseOrders.PURCHASE_ORDERS;

public List<String> findExternalIds(
        DSLContext dsl, String status, int limit) {

    return dsl.select(PURCHASE_ORDERS.EXTERNAL_ID)
            .from(PURCHASE_ORDERS)
            .where(PURCHASE_ORDERS.STATUS.eq(status))
            .orderBy(PURCHASE_ORDERS.ID.desc())
            .limit(limit)
            .fetch(PURCHASE_ORDERS.EXTERNAL_ID);
}
~~~

`com.example.jooq.tables.PurchaseOrders` **is not generated automatically by adding the starter**; you need a jOOQ codegen build task and a real schema. jOOQ excels at complex SQL, though it does not replace Spring Data JDBC's aggregate persistence.

### 9.3. Shared Transactions When Combining Tools

When a Spring Data JDBC repository, `JdbcTemplate`, and jOOQ `DSLContext` share **the same `DataSource` and compatible Spring transaction integration**, they can participate in one local JDBC transaction. Boot's jOOQ starter integrates transaction/connection providers when conditions align; if you manually instantiate a `DSLContext` on another connection, **never assume shared rollbacks**.

Verify by intentionally throwing an exception after both a repository save and a jOOQ update, asserting that **both roll back**.

## 10. `@Query` and `@Modifying`

Spring Data JDBC repositories allow explicit SQL when derived queries become awkward:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;

public interface OrderStatisticsRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("SELECT COUNT(*) FROM purchase_orders WHERE status = :status")
    long countByStatus(String status);
}
~~~

When custom queries return aggregates containing collections, check how materialization works; do not assume an arbitrary `JOIN` enables Spring Data JDBC to reconstruct every association automatically.

### 10.1. SQL Update with Optimistic Condition

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface OrderMaintenanceRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
            UPDATE purchase_orders
               SET status = 'ARCHIVED',
                   version = version + 1
             WHERE id = :id
               AND version = :version
            """)
    int archiveIfVersionMatches(
            @Param("id") Long id,
            @Param("version") Long version);
}
~~~

Check the affected row count: `1` means updated; `0` means not found or version conflict. Direct SQL can **bypass aggregate callbacks, repository version mechanics, and business invariants**; avoid using it casually for complex domain commands.

### 10.2. When to Use Direct SQL

Use it for read models, bulk updates, upserts, and operations where explicit SQL control is deliberate. Always:

- Verify transaction boundaries.
- Protect optimistic locking and unique keys where needed.
- Respect aggregate invariants.
- Write audit/outbox entries for relevant side effects.
- Validate SQL parameters and permissions.

## 11. `@Version` and Optimistic Locking

Two workers concurrently read order `version=3`:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant D as PostgreSQL
    A->>D: SELECT order version=3
    B->>D: SELECT order version=3
    A->>D: UPDATE id=? AND version=3
    D-->>A: Version updated to 4
    B->>D: UPDATE id=? AND version=3
    D-->>B: Conflict, zero matching rows
~~~

Spring Data JDBC `@Version` detects lost updates via optimistic locking when saving an existing aggregate. Depending on version, conflicts raise `OptimisticLockingFailureException` or a Spring data-access subtype.

### 11.1. Optimistic Locking Does Not Replace Unique Business Keys

Two concurrent requests can both observe `existsByExternalId("EXT-10") = false` and both attempt to insert. Only **`UNIQUE (external_id)`** in the database resolves insert races reliably. Map duplicate-key exceptions to idempotent responses or HTTP `409` per contract.

### 11.2. Handling Version Conflicts

1. Reload the latest aggregate.
2. Check whether the business command is still valid.
3. If the operation has already been applied, return an idempotent result.
4. Otherwise compute the new state from the fresh version.
5. Retry a bounded number of times if safe.
6. Never emit HTTP/broker side effects **on each retry attempt**.

Keeping external side effects inside the transaction means an optimistic conflict after a network call cannot roll back the remote side effect.

## 12. Database Transactions vs. HTTP/Broker Transactions

~~~mermaid
flowchart LR
    C["Confirm command"] --> T["Spring @Transactional"]
    T --> R["Spring Data JDBC repository"]
    T --> O["Outbox SQL insert"]
    R --> D["PostgreSQL"]
    O --> D
    D --> W["Outbox relay after COMMIT"]
    W --> K["Kafka / RabbitMQ"]
    W --> H["HTTP partner"]
~~~

`@Transactional` with a JDBC transaction manager is atomic only across managed database resources. Redis caches, HTTP requests, Kafka sends, and RabbitMQ publishes are not automatically enlisted in the same transaction.

### 12.1. Anti-Pattern: HTTP Inside an SQL Transaction

~~~java
@Transactional
public void confirmAndNotify(String externalId) {
    PurchaseOrder current = repository
            .findByExternalId(externalId)
            .orElseThrow();

    repository.save(current.withStatus("CONFIRMED"));

    erpRestClient.post()
            .uri("/v1/orders")
            .body(current)
            .retrieve()
            .toBodilessEntity();

    kafkaTemplate.send("orders.events", externalId, "CONFIRMED");
}
~~~

This snippet illustrates a design trap, assuming injected dependencies. The ERP might commit before SQL rolls back; async Kafka sends might finish after SQL commits or succeed before SQL rolls back; and JDBC connections sit idle during HTTP timeouts.

**Pool size does not solve distributed consistency.** Use a transactional outbox, saga/reconciliation, or deliberate distributed transaction tooling where supported.

### 12.2. Transactional Outbox Schema

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_outbox_due
ON integration_outbox(status, next_attempt_at, created_at);
~~~

Persist event intent in the same transaction as the aggregate update; a separate worker publishes after commit. `eventId` must remain stable across retries. Consumers need an inbox/unique constraint so they never apply business effects twice.

## 13. Application Service Persisting Aggregate and Outbox

Use `NamedParameterJdbcTemplate` because the outbox SQL is not root aggregate mapping:

~~~java
// OrderConfirmationService.java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationService {

    private final PurchaseOrderRepository orders;
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public OrderConfirmationService(
            PurchaseOrderRepository orders,
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper objectMapper) {
        this.orders = orders;
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public PurchaseOrder confirm(String externalId) {
        PurchaseOrder current = orders
                .findByExternalId(externalId)
                .orElseThrow();

        if ("CONFIRMED".equals(current.status())) {
            return current; // Idempotent command.
        }

        if (!"DRAFT".equals(current.status())) {
            throw new IllegalStateException(
                    "Status does not allow confirmation");
        }

        PurchaseOrder saved =
                orders.save(current.withStatus("CONFIRMED"));

        UUID eventId = UUID.randomUUID();
        String payload = toJson(new OrderConfirmedEvent(
                eventId.toString(),
                saved.externalId(),
                saved.version()));

        var params = new MapSqlParameterSource()
                .addValue("eventId", eventId)
                .addValue("aggregateId", saved.id())
                .addValue("payload", payload);

        jdbc.update(
                """
                INSERT INTO integration_outbox(
                    event_id, aggregate_type, aggregate_id,
                    event_type, payload, status)
                VALUES (:eventId, 'PurchaseOrder', :aggregateId,
                        'OrderConfirmed', CAST(:payload AS jsonb), 'PENDING')
                """,
                params);

        return saved;
    }

    private String toJson(OrderConfirmedEvent event) {
        try {
            return objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(
                    "Failed to serialize outbox event", e);
        }
    }

    public record OrderConfirmedEvent(
            String eventId, String externalId, Long version) {
    }
}
~~~

If the outbox `INSERT` fails, Spring rolls back the aggregate update as well (since the exception is runtime). `@Transactional` must be invoked via the Spring proxy—never self-invoked while expecting a transaction.

**Business idempotency:** If the order is already `CONFIRMED`, emit no new event. Under concurrent requests, `@Version` and database constraints must be tested to prevent duplicate commits. If commands carry their own IDs, add a `processed_commands` table with `UNIQUE (command_id)`.

**Outbox is at-least-once:** The broker may accept an event before the relay crashes prior to recording `BROKER_CONFIRMED`; on restart, the relay republishes. Consumers/partners must implement idempotency or reconciliation.

### 13.1. Never Hold an SQL Transaction During Network Calls

If an HTTP call times out after 15 seconds inside an SQL transaction, the JDBC connection and row locks remain held for 15 seconds. Under concurrency, the pool starves. Record event intent inside a short local transaction and perform network calls **after commit** with a dedicated retry budget.

### 13.2. Consumer Handoff

When a broker consumer persists an aggregate, ack/commit the offset only after the business transaction or durable handoff completes per contract. If the DB commits and the ack fails, the message redelivers; use an inbox or unique event ID to prevent double processing.

## 14. `JdbcAggregateTemplate` and Explicit Operations

Alongside `CrudRepository`, Spring Data JDBC offers `JdbcAggregateTemplate` for programmatic aggregate operations:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderWriter {

    private final JdbcAggregateTemplate aggregates;

    public PurchaseOrderWriter(JdbcAggregateTemplate aggregates) {
        this.aggregates = aggregates;
    }

    public PurchaseOrder insertNew(PurchaseOrder order) {
        return aggregates.insert(order);
    }
}
~~~

`insert` makes insertion intent explicit. Use the API matching your version and test with generated IDs. `JdbcAggregateTemplate` remains an aggregate persistence abstraction, **not a JPA `EntityManager`**.

### 14.1. When to Use Bulk SQL

A batch of 100,000 inventory counter updates rarely needs 100,000 materialized aggregate roots if it only updates counters conditionally. `JdbcTemplate.batchUpdate` or jOOQ bulk/upserts perform much better, provided you manually enforce:

- Unique constraints and idempotency.
- Business version checks.
- Transaction chunking and bounded memory.
- Audits/outbox entries where required.
- Respect for aggregate invariants.

## 15. Read Models, Pagination, and Streaming

An order-listing API typically needs only `id`, `externalId`, and `status`. Use SQL/jOOQ projections instead of loading every `PurchaseOrderLine`.

### 15.1. Keyset Pagination

~~~sql
SELECT id, external_id, status
FROM purchase_orders
WHERE id > ?
ORDER BY id
LIMIT ?;
~~~

Keyset pagination fits polling/reconciliation over large datasets with a stable cursor. Offset pagination skips or duplicates rows when data changes rapidly. Use bounded batch sizes and checkpoints to process millions of records.

### 15.2. JDBC Streams Hold Connections

A `ResultSet`/cursor ties up a JDBC connection and transaction. Returning a stream out of a method to an async executor after the transaction closes renders the cursor unusable. Materialize small chunks or keep the cursor lifecycle tightly scoped without holding pool connections too long.

### 15.3. Aggregate with SQL Instead of Entity Graphs

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM purchase_orders
WHERE status = 'CONFIRMED'
GROUP BY customer_id
ORDER BY order_count DESC;
~~~

This query belongs in `JdbcClient` or jOOQ. Never load entire aggregates just to run `stream().collect(groupingBy(...))` in Java.

## 16. JDBC Error Handling and Concurrency

| Situation | Typical Exception / Group | Response Strategy |
| --- | --- | --- |
| Duplicate business key | `DuplicateKeyException` | Return conflict or idempotent response |
| Version mismatch | `OptimisticLockingFailureException` | Reload, reconcile, or bounded retry |
| FK / CHECK / NOT NULL violation | `DataIntegrityViolationException` | Fix input, logic, or schema |
| Bad SQL syntax / migration mismatch | `BadSqlGrammarException` | Fix code/schema; do not retry |
| Connection unavailable | `CannotGetJdbcConnectionException` | Check DB, pool, and network |
| Deadlock / serialization failure | `TransientDataAccessException` subtype | Bounded transaction retry |
| Query timeout | Driver / Spring data-access exception | Distinguish query, network, and outcome |

Exact exception classes depend on driver, SQLState, Spring version, and exception translation. Never catch `DataAccessException` broadly and retry forever.

### 16.1. Three Complementary Safeguards

- `@Version`: guards against lost updates on an **existing root**.
- `UNIQUE (external_id)`: prevents duplicate identities during **concurrent inserts**.
- `@Transactional`: enforces atomicity across operations **within the same local DB transaction**.

They complement one another. Version columns do not replace unique keys, and transactions do not replace domain validation or roll back HTTP calls.

### 16.2. Retry Only When Safe

On optimistic conflicts, reload fresh state and re-evaluate the command. Never retry an entire service method that already issued external API side effects. When `COMMIT` outcomes are unknown, use business keys/idempotency and status lookups to verify state.

## 17. Testing with PostgreSQL Testcontainers

Domain unit tests do not verify schema mappings, generated IDs, child persistence, version SQL, or transaction rollbacks. Test against real PostgreSQL via Testcontainers.

### 17.1. Test Dependencies

~~~groovy
dependencies {
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

In Boot 4, test starters/packages may be reorganized; adjust to your project's version. `@ServiceConnection` is supported in modern Boot releases with Boot Testcontainers support.

### 17.2. `@DataJdbcTest` for Repositories

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void saveAndReloadLines() {
        PurchaseOrder draft = new PurchaseOrder(
                null, null, "TEST-ORDER-001", "CUST-1",
                "DRAFT",
                List.of(
                        new PurchaseOrderLine("SKU-A", 2),
                        new PurchaseOrderLine("SKU-B", 3)));

        PurchaseOrder saved = repository.save(draft);

        assertNotNull(saved.id());

        PurchaseOrder loaded =
                repository.findById(saved.id())
                        .orElseThrow();

        assertEquals("TEST-ORDER-001", loaded.externalId());
        assertEquals(2, loaded.lines().size());
    }
}
~~~

This test requires migrations to run in the test context under compatible Spring Boot and Testcontainers versions. H2 does not prove PostgreSQL `JSONB`, `ON CONFLICT`, locks, transaction isolation, or identity semantics.

### 17.3. Mandatory Test Cases

| Test | What to Assert |
| --- | --- |
| New aggregate insert | ID/version populated; root + children persisted |
| Reload aggregate | Accurate fields, list ordering, child count |
| Save updated root | Updated status and children remain intact |
| Invalid quantity | Rejected by domain validation / DB `CHECK` |
| Duplicate `externalId` | `UNIQUE` constraint blocks races |
| Two concurrent versions | Stale save rejected by optimistic locking |
| Outbox insert fails | Root update rolls back in the same transaction |
| jOOQ + repository transaction | Both SQL operations roll back together |
| Outbox relay crash after broker ack | Replay reuses old `eventId`; no lost intent |
| Kafka/Rabbit consumer replay | Inbox/dedup protects business side effects |
| Connection pool saturation | Timeouts and bounded concurrency behave predictably |
| Migration compatibility | Real schema matches mappings |

### 17.4. Testing Transaction Rollback

~~~text
Given PurchaseOrder DRAFT in PostgreSQL
When OrderConfirmationService.confirm()
And outbox INSERT fails
Then transaction rolls back
And Order status remains DRAFT
And no outbox row is committed
~~~

Test against a real database rather than mocking repositories. If the repository uses `DataSource` A and the outbox uses `DataSource` B, this test exposes partial commits and forces fixing transaction wiring.

### 17.5. Testing Optimistic Locking Properly

Two separate transactions/instances read `version = 3`; transaction A saves successfully; transaction B tries to save its `version = 3` copy and must be rejected. Never test concurrency by mutating a single shared Java object in memory.

## 18. Observing and Operating SQL in Integration Flows

| Metric / Trace | Layer | Meaning |
| --- | --- | --- |
| `hikaricp.connections.active` | Pool | Active connections in use |
| `hikaricp.connections.idle` | Pool | Idle connections available |
| `hikaricp.connections.pending` | Pool | Threads waiting for a connection |
| `hikaricp.connections.timeout` | Pool | Acquisition timeout count |
| SQL query/update duration | Database | Query, lock, and binding latency |
| Transaction duration/rollback | Spring / DB | Long-running or failing transactions |
| Duplicate/version conflicts | Application | Concurrent requests and replays |
| Outbox oldest pending age | Integration | Undelivered publish intents |
| Broker producer confirmed | Messaging | Broker accepted—not yet consumer-processed |
| Consumer inbox duplicates | Consumer | Event replays handled safely |
| End-to-end business lag | Application | From command receipt to downstream completion |

Exact SQL/transaction metric names depend on instrumentation, drivers, and Boot version. Actuator can expose Hikari metrics when configured, though do not assume custom SQL timers exist out of the box in every project.

### 18.1. Pool Starvation Pattern

~~~text
HTTP request A
  -> @Transactional BEGIN
  -> JDBC SELECT + UPDATE
  -> wait 15s for ERP HTTP
  -> COMMIT + return JDBC Connection

Requests B..N
  -> wait on Hikari pool
  -> connectionTimeout
~~~

The primary fix is **shortening transactions** and moving remote calls to outbox/sagas. Raising `maximum-pool-size` will not help when long-running transactions saturate an overloaded DB.

### 18.2. Secrets, PII, and Metric Cardinality

Never log full query bind values containing customer PII, DB passwords, access tokens, or raw event payloads. Keep metric tags bounded (`component=jdbc`, `operation=confirmOrder`, `outcome=optimistic_conflict`); never add `eventId`, `orderId`, or `customerId` as metric labels.

### 18.3. Health Does Not Equal Business Completion

`DataSource` health `UP` only proves the DB was reachable at probe time. It does not prove the outbox relay is publishing, consumers have no backlog, or the ERP processed requests. Monitor transaction/pool metrics **alongside** business lag, retries, and DLQs separately.

## 19. Common Anti-Patterns

| Anti-Pattern | Problem | Better Approach |
| --- | --- | --- |
| Treating Spring Data JDBC as JPA with different imports | Wrong mapping and lifecycle assumptions | Design aggregate-oriented models |
| Updating an immutable object without saving | No dirty checking exists | Call `repository.save(updated)` |
| Using JPA `@OneToMany` on JDBC children | Wrong annotation | Use `@MappedCollection` |
| Putting customer/order/payment graphs in one aggregate | Excessive SQL and broken consistency boundaries | Split aggregates and reference by ID |
| Using list index as a stable line ID | Reordering changes identity | Add a business `lineId` when needed |
| Loading all lines just for a summary page | Wastes SQL and memory | Use `JdbcClient`/jOOQ projections |
| Custom SQL updates forgetting version/outbox | Lost updates or missing events | Conditional updates + event contracts |
| `existsByExternalId` before insert without `UNIQUE` | Race condition | Enforce database unique constraints |
| Calling HTTP/Kafka inside an SQL transaction | Cannot roll back remote side effects | Use outboxes and reconciliation |
| Using jOOQ on another `DataSource` assuming shared transaction | Partial commits | Wire Spring transaction integration |
| Retrying every `DataAccessException` | Infinite loops on permanent errors | Classify errors and bound retries |
| Increasing pool size to fix slow queries/locks | Worsens contention | Tune indexes, SQL, and transactions |
| Using H2 to test PostgreSQL `JSONB`/locks | Divergent SQL semantics | Use PostgreSQL Testcontainers |
| Treating broker ack as consumer completion | Wrong messaging semantics | Track business completion metrics |

## 20. Production Checklist

- [ ] Chose Spring Data JDBC deliberately for an aggregate-oriented write model.
- [ ] Clearly distinguished `JdbcTemplate`/`JdbcClient`, Spring Data JDBC, JPA, and jOOQ.
- [ ] Defined clear aggregate root/child boundaries and invariants.
- [ ] Stored external aggregate references as IDs or `AggregateReference`.
- [ ] Used Spring Data JDBC mappings (`@Table`, `@Id`, `@Version`, `@MappedCollection`).
- [ ] Managed tables, FKs, `CHECK` constraints, and `UNIQUE` business IDs via migrations.
- [ ] Captured returned instances from `save` on immutable entities to obtain new IDs/versions.
- [ ] Tested insert, load, update, and delete on roots and child collections.
- [ ] Measured aggregate resave costs and avoided oversized aggregates.
- [ ] Protected concurrency with `@Version`, unique constraints, and application idempotency.
- [ ] Ensured direct SQL/jOOQ preserves audits, optimistic versions, and invariants.
- [ ] Used projections and pagination for list/reporting queries.
- [ ] Verified Spring Data JDBC, jOOQ, and `JdbcClient` share transactions where atomicity is required.
- [ ] Kept SQL transactions short; delegated HTTP/broker side effects to outboxes where appropriate.
- [ ] Assigned stable `eventId`s in outboxes and guarded consumers against replays.
- [ ] Classified retries by error type, never looping infinitely on non-transient SQL/auth errors.
- [ ] Verified mappings, migrations, locks, and rollbacks with PostgreSQL Testcontainers.
- [ ] Exposed metrics for pool active/idle/pending, SQL latency, conflicts, and business lag.
- [ ] Excluded sensitive SQL parameters, tokens, and PII from logs and metrics.
- [ ] Configured DB TLS, secret-managed credentials, least privilege, and connection budgets.

**Remember:** Spring Data JDBC uses Spring Data repositories to persist **relational aggregates**, without JPA's persistence context, lazy loading, or dirty checking. Calling `save()` is explicit, and oversized aggregates can generate heavy SQL when updating children. Spring Data JDBC pairs cleanly with `JdbcClient` or jOOQ for expressive SQL without turning your write model into an ORM graph. In Spring Boot Integration, correctness comes from **aggregate boundaries, database constraints, local transactions, outbox/inbox patterns, testing, and observability**—not merely from picking an SQL access library.

## References

- [Spring Data JDBC — Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): aggregate model, repositories, and mapping.
- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): immutable entities and constructors.
- [Spring Data JDBC — Entity Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): save/new-state detection and aggregate persistence.
- [Spring Data JDBC — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): `@Table`, `@Id`, `@MappedCollection`, references.
- [Spring Data JDBC — Transactions](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction behavior.
- [Spring Data JPA — Reference](https://docs.spring.io/spring-data/jpa/reference/): JPA repositories and ORM lifecycle.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate` and `JdbcClient`.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `PlatformTransactionManager`.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `DataSource`, pooling, JDBC, jOOQ, and JPA.
- [jOOQ — Manual](https://www.jooq.org/doc/latest/manual/): SQL DSL, code generation, transactions.
- [Flyway — Documentation](https://documentation.red-gate.com/fd): versioned schema migrations.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): integration tests against PostgreSQL.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): atomic business data + outbox.
