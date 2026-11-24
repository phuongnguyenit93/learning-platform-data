# CassandraTemplate, Repositories, and Choosing the Right API

## 1. Context and objectives

In the **SPRING_BOOT_INTEGRATION** module, Apache Cassandra is a NoSQL storage option when a system must sustain high read/write throughput across multiple nodes and access data by relatively well-defined keys and query patterns. Spring Boot integrates with Cassandra via **Spring Data Cassandra**, offering high-level access APIs such as **CassandraTemplate** and **CassandraRepository**, alongside lower-level APIs like **CqlTemplate** and **CqlSession**.

This topic belongs to the **Other NoSQL Stores** chapter. It complements integration flows spanning HTTP clients, databases, caches, message brokers, and Spring Integration adapters. Choosing a Cassandra API requires considering connection configuration, data contracts, transactions/consistency, failures, deduplication, testing, and observability together. Picking the right Java API is only part of the picture: **your partition key design and query patterns determine whether Cassandra actually fits the domain**.

After this lesson, you will be able to:

1. Explain the roles of **CqlSession**, **CqlTemplate**, **CassandraTemplate**, **CassandraRepository**, and their reactive counterparts.
2. Configure Spring Boot to connect to Cassandra, map entities, and use repositories against a table with a clear partition key.
3. Switch to CassandraTemplate when needing `Query`/`Criteria`, write options, or finer control than standard CRUD.
4. Use CqlTemplate or the raw driver for specialized CQL, parameter-bound queries, and checking conditional write results.
5. Understand how consistency levels, TTL, LWT, pagination, timeouts, and retries affect integration correctness.
6. Test API selection and data models against real Cassandra in a test environment.

## 2. API layers and responsibilities

Spring Data Cassandra exposes two axes of choice: **abstraction level** and **execution model**.

| API | Abstraction level | Strengths | When it fits |
| --- | --- | --- | --- |
| **CassandraRepository<T, ID>** | Entity repository | Common CRUD, key lookups, derived query methods, concise service code | Stable aggregates with few complex queries |
| **CassandraTemplate / CassandraOperations** | Entity mapping + fine-grained control | `Query`/`Criteria`, select, insert, update, delete; per-query options | Repository lacks flexibility; custom read/write options needed |
| **CqlTemplate / CqlOperations** | CQL, callbacks, and `RowMapper` | Full CQL control, parameter binding; minimal entity-mapping overhead | Specialized CQL, counters, statements not ergonomic in entity APIs |
| **CqlSession** (Java driver) | Direct driver | `PreparedStatement`/`BoundStatement`, paging state, execution profiles, driver options | Driver-specific capabilities or custom query policies needed |
| **ReactiveCassandraRepository / ReactiveCassandraTemplate** | Reactive repository/template | `Mono`, `Flux`, composition, non-blocking I/O | Reactive systems handling many concurrent I/O requests |
| **ReactiveCqlTemplate** | Reactive CQL | Direct CQL returning `Mono`/`Flux` | Specialized CQL inside reactive pipelines |

Diagram:

~~~mermaid
flowchart TD
    A["Application service"] --> B{"Access need"}
    B -->|"Entity CRUD"| C["CassandraRepository"]
    B -->|"Entity + Query/Criteria"| D["CassandraTemplate"]
    B -->|"Custom CQL"| E["CqlTemplate"]
    B -->|"Driver-specific"| F["CqlSession"]
    C --> G["Spring Data mapping & error translation"]
    D --> G
    E --> H["CQL execution & error translation"]
    G --> I["Cassandra Java Driver"]
    H --> I
    F --> I
    I --> J["Cassandra cluster"]
~~~

**CassandraTemplate** implements **CassandraOperations**, and **ReactiveCassandraTemplate** implements **ReactiveCassandraOperations**. In business code, you can inject the `*Operations` interfaces to reduce coupling to concrete classes. Spring-managed templates are reusable across requests.

**Note:** repositories delegate to Spring Data templates and mapping underneath. “Repository vs. template” is a code-organization decision, not two different storage engines. Never switch APIs hoping to fix slow queries caused by a poorly chosen partition key.

## 3. Getting started with Spring Boot

### 3.1. Dependencies

With Maven and dependency versions managed by the Spring Boot parent/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle equivalent:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

If the entire application is reactive, consider **spring-boot-starter-data-cassandra-reactive** and its reactive APIs. Match dependencies to your Spring Boot generation and check the test/slice modules provided by that version. Avoid manually pinning an incompatible driver version when the starter already manages aligned dependencies.

### 3.2. Connection configuration

Example local configuration in **application.yml**:

~~~yaml
spring:
  cassandra:
    contact-points: localhost:9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
    request:
      timeout: 3s
      consistency: LOCAL_QUORUM
    schema-action: none
~~~

This configuration is illustrative—**not a universal default for every cluster**. Replace **datacenter1** with the exact datacenter name from your cluster, and select consistency based on replication factor, topology, and business requirements. If production requires authentication/TLS, configure credentials and SSL/SSL bundles accordingly; supply secrets via a secret manager or environment variables rather than committing passwords to source control.

Key distinctions:

- **spring.cassandra.contact-points** are initial discovery nodes for the cluster; the driver is not permanently restricted to them.
- **local-datacenter** governs routing policy; specifying the wrong value prevents the client from selecting eligible nodes.
- **keyspace-name** acts like a table namespace; the keyspace must exist before the application runs queries.
- **request.timeout** caps how long the driver waits for a single request, without guaranteeing the entire integration workflow finishes in 3 seconds.
- **schema-action: none** stops the application from altering schemas at startup; manage schemas through controlled migration/release workflows.

When auto-configuration conditions match, Spring Boot creates supporting beans such as **CqlSession**, **CqlTemplate**, **CassandraTemplate**, and repository infrastructure so services and repositories can inject them—normally without creating a new session per request. Auto-configuration rules vary across versions, custom beans, and classpaths: inspect the **Condition Evaluation Report** on bean errors instead of assuming every bean always exists.

## 4. Data modeling must start from queries

Cassandra does not work like a relational database. It organizes data around the **partition key** (which determines where rows live) and **clustering columns** (which sort rows inside each partition). Before writing a Repository, you must know which keys queries will filter by, how large each partition can grow, and what sort order is needed.

### 4.1. Simple example: inventory snapshot by SKU

Suppose an integration service maintains a **reference snapshot** of inventory supplied by an external system. Never use this snapshot for financial decisions or inventory deductions requiring strong transactions unless backed by a dedicated consistency architecture.

~~~sql
CREATE TABLE shop_integration.inventory_snapshot (
    sku text PRIMARY KEY,
    available_qty int,
    source_version bigint,
    updated_at timestamp
);
~~~

Here **sku** is the partition key. Queries like **WHERE sku = ?** are natural; however, “count all SKUs with `available_qty > 0`” is not a partition-key query. Serving that at high scale calls for a separate projection table, an appropriate index, or another search/analytics engine.

Java entity (imports abbreviated):

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("inventory_snapshot")
public class InventorySnapshot {
    @PrimaryKey("sku")
    private String sku;

    @Column("available_qty")
    private int availableQty;

    @Column("source_version")
    private long sourceVersion;

    @Column("updated_at")
    private Instant updatedAt;

    protected InventorySnapshot() {} // for mapping

    public InventorySnapshot(
            String sku, int availableQty, long sourceVersion, Instant updatedAt) {
        this.sku = sku;
        this.availableQty = availableQty;
        this.sourceVersion = sourceVersion;
        this.updatedAt = updatedAt;
    }

    public String getSku() { return sku; }
    public int getAvailableQty() { return availableQty; }
    public long getSourceVersion() { return sourceVersion; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

Spring Data uses mapping metadata from **@Table**, **@PrimaryKey**, **@Column**, and converters to map objects to Cassandra rows. Verify `timestamp`/`Instant` mapping with your driver and Java versions; this example has no auto-incrementing ID because Cassandra has no RDBMS-style sequences.

### 4.2. Composite key example: events by tenant and day

If the system needs to read “the 50 most recent events for tenant A on day D,” a more suitable table is:

~~~sql
CREATE TABLE shop_integration.events_by_tenant_day (
    tenant_id text,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

**(tenant_id, event_day)** is the composite partition key; **(occurred_at, event_id)** is the clustering key. Daily bucketing avoids packing all of a tenant's history into a single unbounded partition, though you must still estimate real partition sizes—very high-volume tenants may require hourly buckets or extra sharding.

Spring Data Cassandra maps composite keys using **@PrimaryKeyClass** and **@PrimaryKeyColumn**:

~~~java
@PrimaryKeyClass
public class TenantEventKey implements Serializable {
    @PrimaryKeyColumn(
            name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private String tenantId;

    @PrimaryKeyColumn(
            name = "event_day", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
            name = "occurred_at", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
            name = "event_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED)
    private UUID eventId;

    // Constructor, getters/setters, equals(), and hashCode()
    // must be implemented consistently with key identity.
}

@Table("events_by_tenant_day")
public class TenantEvent {
    @PrimaryKey
    private TenantEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    // Constructor and getters/setters compatible with the active converter.
}
~~~

Imports for **PrimaryKeyClass**, **PrimaryKeyColumn**, **PrimaryKeyType**, **Ordering**, **Serializable**, **LocalDate**, **Instant**, and **UUID** are omitted. This snippet outlines the mapping; production code must implement complete constructors/accessors and **equals/hashCode** on the key class. Every partition-selecting query must supply **all partition key components**. Range predicates on clustering columns must also obey CQL rules; you cannot filter arbitrary columns freely as in relational SQL.

## 5. When is a Repository the best choice?

For the SKU-keyed snapshot table, a Spring Data repository is clean and concise:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface InventorySnapshotRepository
        extends CassandraRepository<InventorySnapshot, String> {
    // Provides findById, save, deleteById, existsById, ...
}
~~~

Service:

~~~java
@Service
public class InventorySnapshotQueryService {
    private final InventorySnapshotRepository snapshots;

    public InventorySnapshotQueryService(
            InventorySnapshotRepository snapshots) {
        this.snapshots = snapshots;
    }

    public Optional<InventorySnapshot> findBySku(String sku) {
        return snapshots.findById(sku);
    }
}
~~~

**findById** is clear, targets the partition key, and needs no manual CQL. Repositories also support custom query methods via method-name derivation or **@Query** when supported by Cassandra.

Example query method on **events_by_tenant_day**:

~~~java
public interface TenantEventRepository
        extends CassandraRepository<TenantEvent, TenantEventKey> {

    @Query("""
        SELECT * FROM events_by_tenant_day
        WHERE tenant_id = ?0 AND event_day = ?1
        """)
    List<TenantEvent> findEventsForDay(
            String tenantId, LocalDate eventDay);
}
~~~

This query uses a valid **partition key**, yet can return thousands of rows for a busy day. Real systems must add limits, paging state, or clustering-key pagination. Repositories stay readable only when queries reflect actual CQL capabilities.

**Do not mistake `save()` for “insert only if absent.”** Keyed writes in Cassandra normally have **upsert** semantics; saving an existing key overwrites column values instead of throwing a duplicate-key error like an RDBMS insert. When you need “accept a request only once,” use conditional writes with **IF NOT EXISTS** and check whether it applied, accounting for LWT cost.

Repositories shine when domains are stable, operations are mostly keyed CRUD, and per-call statement tuning is unnecessary. If a service accumulates lots of conditional branching just to control consistency, TTLs, conditional writes, or custom mappings, move that logic to a custom repository using Template or CQL.

## 6. CassandraTemplate: entity operations with fine-grained control

**CassandraTemplate** fits applications that still want POJO mapping while needing more control than default CRUD methods. Its interface is **CassandraOperations**:

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

@Repository
public class SnapshotTemplateDao {
    private final CassandraOperations cassandra;

    public SnapshotTemplateDao(CassandraOperations cassandra) {
        this.cassandra = cassandra;
    }

    public Optional<InventorySnapshot> find(String sku) {
        InventorySnapshot value = cassandra.selectOne(
                query(where("sku").is(sku)),
                InventorySnapshot.class
        );
        return Optional.ofNullable(value);
    }

    public InventorySnapshot insertSnapshot(InventorySnapshot value) {
        return cassandra.insert(value);
    }
}
~~~

**query(where("sku").is(sku))** maps to a partition-key query. **selectOne** returns `null` when no record matches. **insert** writes the entity, yet does not automatically prevent overwrites—understand upsert semantics and specific options.

### 6.1. TTL and conditional writes

Sometimes a snapshot is only valid for a bounded window and duplicate keys should be rejected. Spring Data provides **InsertOptions**:

~~~java
public boolean insertIfAbsent(InventorySnapshot value) {
    InsertOptions options = InsertOptions.builder()
            .ttl(Duration.ofHours(6))
            .withIfNotExists()
            .build();

    WriteResult result = cassandra.insert(value, options);
    return result.wasApplied();
}
~~~

In this snippet:

- **ttl(6 hours)** writes the record with a TTL; data expires per Cassandra's TTL mechanics. When updating individual columns or clearing TTLs, check exact statement semantics.
- **withIfNotExists()** issues a conditional insert using a **lightweight transaction (LWT)**.
- **wasApplied()** tells whether the condition succeeded.

**Important:** LWT is costlier than normal writes and should not be enabled blindly for every snapshot. If the goal is preserving the newest **source_version**, **IF NOT EXISTS** alone cannot prevent an older event from overwriting an existing newer row, nor handle subsequent updates. Design version-conditional updates or dedicated ordering logic, and test under out-of-order request arrivals.

### 6.2. When more flexible queries are needed

The template supports **Query**, **Criteria**, update/delete operations, and per-statement options. However, **Query/Criteria does not turn Cassandra into SQL capable of filtering arbitrary attributes**. Querying non-key columns may require indexes or a redesigned table; slapping **ALLOW FILTERING** onto a query to bypass CQL errors can scan massive numbers of partitions, causing unstable latency and cluster overload.

If you need “all snapshots with `source_version` below X,” evaluate a query-specific projection table or a segmented background scan rather than adding non-key predicates directly to `Query`.

## 7. CqlTemplate and CqlSession: when direct CQL is required

**CqlTemplate** removes high-level object mapping so you write CQL directly and map rows manually. It manages statement execution, translates data-access exceptions, and handles parameter binding:

~~~java
@Repository
public class SnapshotCqlDao {
    private final CqlOperations cql;

    public SnapshotCqlDao(CqlOperations cql) {
        this.cql = cql;
    }

    public Optional<Integer> quantity(String sku) {
        List<Integer> quantities = cql.query(
                "SELECT available_qty FROM inventory_snapshot WHERE sku = ?",
                (row, rowNum) -> row.getInt("available_qty"),
                sku
        );
        return quantities.stream().findFirst();
    }

    public void upsertQuantity(String sku, int quantity) {
        cql.execute(
                "UPDATE inventory_snapshot SET available_qty = ? WHERE sku = ?",
                quantity, sku
        );
    }
}
~~~

Imports for **CqlOperations**, **List**, and **@Repository** are omitted. Returning a list from **query** handles missing rows cleanly; **queryForObject** throws **IncorrectResultSizeDataAccessException** if the row count is not exactly one. With parameterized statements, **CqlTemplate** uses prepared statements, safely binding values instead of concatenating user strings into CQL.

Use **CqlSession** directly only when you need explicit driver control: **PreparedStatement**, **BoundStatement**, **ConsistencyLevel**, paging state, execution profiles, specific query tracing, or full **ResultSet** metadata. Example conditional insert checking whether it applied:

~~~java
@Repository
public class ProcessedEventDao {
    private final CqlSession session;
    private final PreparedStatement markProcessed;

    public ProcessedEventDao(CqlSession session) {
        this.session = session;
        this.markProcessed = session.prepare("""
            INSERT INTO processed_event (consumer_name, event_id, processed_at)
            VALUES (?, ?, ?) IF NOT EXISTS
            """);
    }

    public boolean markFirstTime(
            String consumerName, UUID eventId, Instant processedAt) {
        BoundStatement statement = markProcessed.bind(
                consumerName, eventId, processedAt);
        ResultSet result = session.execute(statement);
        return result.wasApplied();
    }
}
~~~

This assumes the **processed_event** table exists with a primary key containing **consumer_name** and **event_id**, and the driver supports `Instant` mapping in your setup. The snippet focuses on API syntax; real applications create tables via migrations and pick partition keys that avoid cramming too many entries into one partition. The Spring-managed **CqlSession** is shared—never call **close()** on it after each request.

**Never treat `markFirstTime()` as proof that an external task finished.** If you mark an event before calling HTTP or publishing a message and the process crashes, the “already processed” marker persists even though the side effect never ran. Align status tracking, checkpoints, outboxes, or acknowledgments with the consistency boundaries of the entire workflow.

## 8. Choosing imperative vs. reactive

Cassandra supports synchronous, asynchronous, and reactive APIs. Do not judge solely by the word “Cassandra” in class names:

| Need | Common choice | Return type |
| --- | --- | --- |
| Spring MVC / synchronous service | `CassandraRepository` or `CassandraTemplate` | `Optional`, `List`, entity |
| Synchronous raw CQL | `CqlTemplate`, occasionally `CqlSession` | Scalar, `List`, `ResultSet` |
| WebFlux or reactive pipelines | `ReactiveCassandraRepository`/`ReactiveCassandraTemplate` | `Mono`, `Flux` |
| Custom CQL in reactive flows | `ReactiveCqlTemplate` | `Mono`, `Flux` |
| Need `CompletableFuture` | `AsyncCassandraTemplate` or driver async API | `CompletableFuture` |

Reactive repository example:

~~~java
public interface ReactiveInventorySnapshotRepository
        extends ReactiveCassandraRepository<InventorySnapshot, String> {
}

@Service
public class ReactiveInventoryLookup {
    private final ReactiveInventorySnapshotRepository snapshots;

    public ReactiveInventoryLookup(
            ReactiveInventorySnapshotRepository snapshots) {
        this.snapshots = snapshots;
    }

    public Mono<InventorySnapshot> find(String sku) {
        return snapshots.findById(sku);
    }
}
~~~

Reactive template example:

~~~java
@Repository
public class ReactiveSnapshotDao {
    private final ReactiveCassandraOperations cassandra;

    public ReactiveSnapshotDao(ReactiveCassandraOperations cassandra) {
        this.cassandra = cassandra;
    }

    public Mono<InventorySnapshot> find(String sku) {
        return cassandra.selectOneById(sku, InventorySnapshot.class);
    }
}
~~~

In reactive flows, **Mono.empty()** represents “not found.” Queries execute only when subscribed; **never call `block()`** on a WebFlux event-loop thread. Reactor's **timeout** bounds downstream waiting, yet client-side cancellation does not prove the server aborted an in-flight database write.

Spring Data Cassandra's reactive API builds on the Java driver's async capabilities; it is not JDBC or R2DBC, and CQL/consistency semantics remain Cassandra's. Never assume `Flux` lets you stream unbounded datasets without impacting memory or connections.

## 9. Scenario-based API selection guide

| Integration scenario | Initial choice | Rationale | What to verify |
| --- | --- | --- | --- |
| Read snapshot by SKU | `CassandraRepository` | Clear `findById`, minimal boilerplate | Partition key match, stale-read tolerance |
| Save entity with TTL and `IF NOT EXISTS` | `CassandraTemplate` | `InsertOptions`, `WriteResult` | LWT latency, `wasApplied`, TTL |
| Read events by tenant/day with paging | `CassandraTemplate` or custom repository | Bounded query, paging state | Avoid large partitions; sort by clustering key |
| Counters and specialized CQL | `CqlTemplate` | Control CQL syntax and binding | Counter semantics, safe retries |
| Driver execution profiles, tracing, detailed bound statements | `CqlSession` | Direct access to driver features | Consistency, timeouts, resource lifecycle |
| High-concurrency I/O in WebFlux | `ReactiveRepository`/`ReactiveTemplate` | Non-blocking I/O threads | Backpressure, timeouts, error handling |
| Multi-system reads/writes (DB + broker + HTTP) | Per-store API + orchestration | Manage consistency at application layer | Outbox, idempotency, compensation, observability |

**Rule of thumb:** start with a Repository when most operations are keyed CRUD; move conditional or option-heavy queries to Template; drop to `CqlTemplate`/`CqlSession` only when lower-level features are genuinely needed. Each step down grants control while adding maintenance responsibility for CQL, mapping, paging, and errors.

## 10. Consistency, LWT, and limited transaction guarantees

Relational systems rely on **@Transactional** to coordinate multiple tables and roll back automatically on error. Cassandra has different transaction, consistency, and isolation semantics; **never assume Spring Data Cassandra's `@Transactional` gives multi-row/multi-table ACID transactions like JDBC/JPA**.

Key concepts:

- **Consistency level** (`LOCAL_ONE`, `LOCAL_QUORUM`, etc.) dictates how many replicas must respond given your replication factor and per-operation setting. Reading the latest data is never guaranteed merely by picking Template vs. Repository.
- **LWT** with **IF NOT EXISTS** or **IF column = value** uses consensus for conditional writes; always inspect **wasApplied()** and weigh latency/throughput overhead.
- **CQL batches** are designed primarily to group related mutations; they are not a general bulk-write speed booster or an RDBMS-style multi-partition ACID transaction.
- **TTL** expires data automatically; watch tombstones, retention, TTL updates, and query impact.
- **Timestamps/LWW** and out-of-order updates can produce results differing from application processing order; build explicit version checks and late-event handling.

### Handling duplicate deliveries

A consumer receives **inventory.snapshot.changed** at least once. On duplicate delivery, calling `Repository.save()` twice yields the same state if values and timestamps match, yet **it does not ensure correctness** when events arrive out of order or external side effects are involved.

A pattern to consider:

~~~text
Broker delivers event (eventId, sku, version, quantity)
      |
      v
Check version / business state
      |
      v
Conditional snapshot write or idempotency marker
      |
      v
Execute/record remaining side effects
      |
      v
ACK broker only when processing policy permits
~~~

Decide explicitly when to record completion, when to ACK, and how to recover after crashes between steps. **An LWT on a marker does not bundle multiple Cassandra writes, HTTP calls, and message publishes into a distributed transaction.** Where strict cross-system atomicity is required, keep the source of truth in a transactional store and use Cassandra strictly as a projection.

## 11. Pagination, filtering, and query limits

A query like:

~~~sql
SELECT * FROM events_by_tenant_day
WHERE tenant_id = 't-01' AND event_day = '2026-11-21';
~~~

may be valid CQL and still return thousands of rows. Never expose a repository method returning an unbounded **List** directly inside an HTTP handler.

Cassandra supports **driver paging state**. Spring Data offers **Slice**, **CassandraScrollPosition**, and Query **pageRequest**/**pagingState** depending on version:

- **Slice** checks whether a next page exists without running an expensive total count across large datasets.
- Paging state is tied to the exact query and parameters. If exposed as an API cursor, bind it to tenant/query, protect the token, and limit its lifetime; never treat it like an arbitrary SQL offset.
- **Sorting** works only in orders supported by Cassandra—normally matching clustering columns inside the selected partition.
- Fetch size controls how many rows the driver pulls per network page; it does **not** cap the total rows your app reads overall.
- **ALLOW FILTERING** is not a performance shortcut; evaluate against data models and query plans.

For multi-day histories, a service can query sequential daily buckets under explicit limits. Bound how many buckets one request may scan; merging and sorting across multiple partitions belongs in the application layer or a dedicated projection table.

## 12. Timeouts, retries, errors, and observability

### 12.1. Common error classes

| Category | Situation | Designed response |
| --- | --- | --- |
| Connection or cluster discovery | Wrong contact point, wrong local DC, TLS/auth failure | Fix topology, credentials, driver config; never retry indefinitely |
| Timeout | Slow coordinator/replica, overload, network loss | Separate read vs. write timeouts; keep deadlines and unknown-outcome state |
| Unavailable | Insufficient replicas for consistency level | Bounded retry or degraded mode per business rules |
| Mapping error | Entity, column, or codec mismatches schema | Fix mapping/migration; never mask as “no data” |
| Invalid CQL | Missing partition key, missing index, reckless `ALLOW FILTERING` | Fix table model/query; never auto-retry |
| LWT not applied | Row already exists or write condition failed | Handle as business outcome, not transport failure |

Driver exceptions may be translated by Spring Data into **DataAccessException**, yet you should still log structured root causes. In particular, a write timeout never proves Cassandra rejected the mutation.

### 12.2. Bounded retries and idempotency

Message brokers can redeliver messages. Operations like **counter increments** must never be retried blindly: running twice increments twice. Standard updates also require checking timestamps, versions, and conditions to determine replay safety.

Principles:

1. Enforce a **workflow-level deadline** alongside driver timeouts; never stack retries past the budget.
2. Retry only transient faults proven safe per verified driver/application policies.
3. Apply bounded backoff with jitter at the orchestration layer; avoid uncoordinated multi-layer retries.
4. For conditional writes, inspect the applied flag to separate **unmet condition** from **I/O failure**.
5. For side effects outside Cassandra, use confirmation checks, idempotency keys, and crash recovery.

### 12.3. Metrics, logs, and tracing

Monitor:

- Latency p95/p99 by operation/table/driver node, timeouts, and request failures.
- Request counts, in-flight requests, throttling, pool/connection pressure, and queue depth from driver metrics.
- LWT applied vs. not-applied counts, version conflicts, and duplicate events per integration flow.
- Paged row/page counts, response sizes, multi-partition scan rates, and tombstone warnings.
- Trace/correlation IDs flowing from HTTP or broker into Cassandra queries and ACK/publish steps.

Never log credentials, tokens, full payloads, or bound sensitive values. Never put `sku`, `tenantId`, or `eventId` in high-cardinality metric labels. Enable query tracing or bind-value logging only under strict control in suitable environments.

## 13. Testing true Cassandra semantics

Unit tests can mock **CassandraOperations** or repositories to verify service branching. Mocks cannot prove query validity, consistency, LWT, or paging. Test those against **real Cassandra**, such as Testcontainers Cassandra with schemas created beforehand.

Tests to include:

| Scenario | Expected result |
| --- | --- |
| Boot context connects | `CqlSession`, template, and repository inject; keyspace/dialect match |
| `findById` for existing/missing SKU | Returns entity or `Optional.empty`; no cluster scan |
| Query by tenant + day | Reads only target partition; sorted by clustering key |
| `InsertOptions` `IF NOT EXISTS` twice | First call applied, second call not applied |
| Short TTL in test | Record expires per TTL, accounting for timing jitter |
| Schema column rename | Mapping or test fails loudly with clear error |
| Timeout / node disconnect | Timeout not treated as “not found”; retries stay within budget |
| Out-of-order events for same SKU | Snapshot does not regress to older version |
| Paginated API | Cursor matches query; no unintended drops/duplicates under updates |
| Crash between marker write and side effect | Recovery/reconciliation finishes or repairs state per design |

**@DataCassandraTest** is Spring Boot's test slice for Cassandra data components. Annotations and test starter dependencies can differ between Boot 3.x and 4.x; service classes outside the slice may require **@Import** or **@SpringBootTest**. Boot 4.x introduces a dedicated Cassandra test starter—check your exact dependencies. Tests still require a running cluster/keyspace/schema; the annotation alone does not launch a Cassandra cluster.

Example template-level business-outcome test (assuming schema and fixture setup):

~~~java
@DataCassandraTest
class CassandraSnapshotTest {

    @Autowired
    CassandraOperations cassandra;

    @Test
    void insertIfNotExistsDoesNotOverwriteExistingSku() {
        InventorySnapshot data = new InventorySnapshot(
                "SKU-01", 5, 1L, Instant.now());
        InsertOptions opts = InsertOptions.builder()
                .withIfNotExists()
                .build();

        assertTrue(cassandra.insert(data, opts).wasApplied());
        assertFalse(cassandra.insert(data, opts).wasApplied());
    }
}
~~~

Tests must clean data or isolate fixtures beforehand so **SKU-01** does not already exist. To verify network faults and concurrency, run integration tests against a properly configured container or cluster instead of merely mocking exceptions.

## 14. Common misconceptions

**“Repositories optimize every `findBy...` method automatically.”** Repositories generate queries from method names, yet queries must still respect Cassandra access rules. You cannot arbitrarily filter or sort non-key columns on large tables.

**“CassandraTemplate executes slow queries faster than Repository.”** Both use the same database driver and query engine; a query missing its partition key stays slow. Fix the data model and access pattern.

**“`save()` throws an error if the ID already exists.”** Most Cassandra writes have upsert semantics. Use **IF NOT EXISTS** or versioning workflows when duplicate writes must be rejected.

**“`@Transactional` in Cassandra behaves like multi-table JDBC transactions.”** Never assume that. Explicitly verify the atomicity and consistency Cassandra provides alongside external side-effect boundaries.

**“LWT can be enabled on every write with zero performance impact.”** LWT runs consensus rounds at noticeably higher cost; reserve it for conditional writes where business rules demand it.

**“Reactive `Flux` eliminates the need for pagination.”** Reactive adds composition and non-blocking I/O, not immunity from oversized partitions, memory exhaustion, network limits, or request deadlines.

**“A timeout means the operation definitely failed.”** The database may have persisted the mutation before the caller lost the response. Design retries and idempotency accordingly.

**“`ALLOW FILTERING` turns Cassandra into an analytics database.”** It can trigger full cluster scans. Redesign tables, pick appropriate indexes, or route ad-hoc analytics to a suitable engine.

## 15. Pre-deployment checklist

1. List real queries: keys, time ranges, ordering, and result limits.
2. Verify partition keys, clustering keys, projected partition sizes, and retention policies.
3. Choose **Repository** for keyed CRUD, **Template** for entities with custom options, and **CqlTemplate/CqlSession** for specialized CQL/driver features.
4. Align **imperative vs. reactive** APIs with your application's threading model; never block event loops.
5. Verify contact points, local DC, keyspace, TLS, consistency levels, and driver timeouts per environment.
6. Define **upsert, `IF NOT EXISTS`, TTL, version, and retry** semantics; separate duplicate events from ambiguous timeouts.
7. Cap page sizes, bucket counts, concurrency, and response sizes; never leave unbounded queries in HTTP handlers.
8. Test queries, LWT, paging, network faults, and out-of-order events against real Cassandra.
9. Track latency, retries, timeouts, throttling, conditional write outcomes, and tracing while protecting sensitive data.
10. Across HTTP/database/broker workflows, document ACK points, side effects, recovery states, and deduplication.

**Conclusion:** choosing between `CassandraRepository` and `CassandraTemplate` comes down to query control and desired abstraction level. Both rely on **access-pattern-driven data modeling**, clear consistency policies, and realistic testing. When raw CQL or driver features are needed, `CqlTemplate` and `CqlSession` provide the right lower-level layer; in reactive apps, stick to reactive variants instead of blocking event loops.

## References

- [Spring Boot — Working with NoSQL Technologies (Cassandra)](https://docs.spring.io/spring-boot/reference/data/nosql.html): starters, configuration, and auto-configured beans.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): Cassandra configuration keys, timeouts, consistency, and schema actions.
- [Spring Data Cassandra — Persisting Entities / CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `CassandraOperations`, `Query`/`Criteria`, and options.
- [Spring Data Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): parameter binding, CQL queries, and row mapping.
- [Spring Data Cassandra — Cassandra-specific Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): repositories, query derivation, consistency, and paging.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): primary keys, clustering columns, and mapping.
- [Spring Data Cassandra — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): reactive templates/repositories and execution model.
