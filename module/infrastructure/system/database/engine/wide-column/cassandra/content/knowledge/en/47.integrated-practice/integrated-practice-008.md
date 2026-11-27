# Integrating Spring Data, Key Mapping, and Query Testing

## 1. Objectives and Practice Problem

This integrated practice uses **Apache Cassandra** as a distributed wide-column database, combined with **Spring Boot, Spring Data Cassandra, and Testcontainers**, to build, query, and test a complete Java feature. The core principle is: **design query-driven tables first, map partition keys and clustering keys accurately, and verify with integration tests against a real Cassandra instance**.

After completing this lab, you should be able to:

1. Given a concrete read requirement, choose suitable partition and clustering keys and explain why the query avoids a full-table scan.
2. Write CQL to create a keyspace, table, and queries matching the exact primary key; understand ordering and Cassandra constraints.
3. Map composite primary keys using `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@PrimaryKey`, and `@Table` in Spring Data Cassandra.
4. Build a repository with explicit CQL queries, call it from a Java service, and validate input preconditions.
5. Use Testcontainers to run integration tests verifying create/read/delete, clustering order, tenant isolation, and time-range boundaries.
6. Distinguish what a single-node test proves from distributed operational concerns such as replication, consistency levels, compaction, repair, and network failures.

**Scenario:** An order management application records order events—such as `CREATED`, `PAID`, and `SHIPPED`—so the order detail screen displays the **20 newest events**. Multiple tenants share the Cassandra cluster; every query must enforce tenant boundaries.

The two most important queries:

- **Q1:** "Given tenant T and order O, fetch the N newest events in descending chronological order."
- **Q2:** "Given tenant T and order O, fetch N events occurring from timestamp S onward."

There is no requirement to find all events with status `PAID` across all tenants. Such a query would require **a separate query-driven table** or a dedicated search/analytics engine.

### Mini Architecture for the Lab

~~~mermaid
flowchart LR
    Client["Client / API"] --> Service["EventTimelineService"]
    Service --> Repo["OrderEventRepository"]
    Repo --> Mapping["Spring Data Cassandra mapping"]
    Mapping --> DB[("Apache Cassandra")]
    Test["JUnit + Testcontainers"] --> Service
    Test --> Repo
    Test --> DB
~~~

Note: Spring Data Cassandra is a mapping/repository layer on top of **CQL and the Java Driver**; it does not alter partitioning rules or turn Cassandra into a relational database with arbitrary joins.

## 2. Deriving the Data Model from Queries

For Q1 and Q2, an event row's partition is identified by the **pair (tenant_id, order_id)**; rows within the same partition are sorted by `occurred_at` descending. Adding `event_id` to the clustering key disambiguates two events sharing the same timestamp.

| Component | Column | Meaning |
| --- | --- | --- |
| Partition key | `(tenant_id, order_id)` | Places all events for one order belonging to a specific tenant into the same logical partition |
| Clustering column 1 | `occurred_at DESC` | Supports reading the newest events and filtering by time threshold |
| Clustering column 2 | `event_id ASC` | Distinguishes simultaneous events, ensuring deterministic ordering within the same timestamp |
| Regular columns | `event_type`, `amount` | Display fields; cannot be used arbitrarily as efficient filter predicates |

Primary schema:

~~~sql
CREATE KEYSPACE IF NOT EXISTS workshop
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS workshop.events_by_order (
    tenant_id uuid,
    order_id uuid,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    amount decimal,
    PRIMARY KEY ((tenant_id, order_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

**Why are there two pairs of parentheses around the partition key?** In `PRIMARY KEY ((tenant_id, order_id), occurred_at, event_id)`, the **inner** parentheses denote a **two-column composite partition key**. The outer parentheses enclose the entire primary key. If you wrote `PRIMARY KEY (tenant_id, order_id, occurred_at, event_id)`, Cassandra would treat only `tenant_id` as the partition key and all remaining columns as clustering keys: a completely different design that easily produces oversized partitions per tenant.

Examples of valid queries:

~~~sql
-- Q1: Reads a single exact partition in the declared clustering order.
SELECT tenant_id, order_id, occurred_at, event_id, event_type, amount
FROM workshop.events_by_order
WHERE tenant_id = 00000000-0000-0000-0000-000000000001
  AND order_id = 00000000-0000-0000-0000-000000000002
LIMIT 20;

-- Q2: Full partition key followed by a range predicate on
-- the first clustering column.
SELECT *
FROM workshop.events_by_order
WHERE tenant_id = 00000000-0000-0000-0000-000000000001
  AND order_id = 00000000-0000-0000-0000-000000000002
  AND occurred_at >= '2026-11-01T00:00:00Z'
LIMIT 20;
~~~

These queries do not require `ALLOW FILTERING` because Cassandra can locate the partition directly and scan in clustering order. By contrast, `SELECT * FROM events_by_order WHERE event_type = 'PAID'` lacks a partition key and is not designed to run on this table.

**Important limitation:** keying partitions by order makes order-history reads fast, but a single order can accumulate too many events. If you must retain millions of events for the same order, consider **time bucketing** (e.g., `event_month` in the partition key), retention TTLs, and multi-bucket reading logic. Do not introduce time buckets into this lab prematurely when there is no need, as they complicate the read path.

## 3. Creating the Java Project and Running Local Cassandra

The example uses **Java 17, Spring Boot 3.3.4, Spring Data Cassandra managed by Spring Boot, Testcontainers 1.20.1, and Cassandra 4.1** as a consistent illustrative stack. When using different versions, verify compatibility across the Java Driver, Spring Data, Testcontainers, and corresponding property names. Your machine needs JDK 17+, Maven, and a running Docker Engine to execute integration tests.

Suggested project layout:

~~~text
cassandra-practice/
├── pom.xml
├── src/main/java/com/example/cassandraworkshop/
│   ├── CassandraPracticeApplication.java
│   ├── domain/OrderEventKey.java
│   ├── domain/OrderEvent.java
│   ├── repository/OrderEventRepository.java
│   └── service/EventTimelineService.java
├── src/main/resources/application.yml
├── src/test/java/com/example/cassandraworkshop/
│   └── OrderEventRepositoryIntegrationTest.java
└── src/test/resources/schema.cql
~~~

### 3.1. Maven Dependencies

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>cassandra-practice</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.4</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <testcontainers.version>1.20.1</testcontainers.version>
    </properties>

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
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${testcontainers.version}</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>cassandra</artifactId>
            <version>${testcontainers.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

The Spring Boot starter provides Spring Data Cassandra, the CQL driver, and auto-configuration. Do not add a JPA-style ORM library for Cassandra tables.

### 3.2. Setting Up a Single-Node Cluster to Run the App

Run from a terminal with Docker installed:

~~~bash
docker run --name cassandra-lab \
  -e CASSANDRA_DC=datacenter1 \
  -p 9042:9042 \
  -d cassandra:4.1

docker exec -it cassandra-lab cqlsh
~~~

Wait for Cassandra to accept connections before opening `cqlsh`; if connecting fails while the server is still starting up, re-run `docker exec` once the container is healthy. Paste the `CREATE KEYSPACE` and `CREATE TABLE` statements from section 2 into `cqlsh`.

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: cassandra-practice
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: workshop
    schema-action: NONE
~~~

`schema-action: NONE` expresses the intent to **manage schemas via CQL/migrations**, preventing the application from automatically creating or dropping tables on startup. The keyspace must already exist before connecting. For production environments, never keep `SimpleStrategy`/replication factor 1; configure `NetworkTopologyStrategy`, per-datacenter replication factors, and consistency levels according to requirements.

`CassandraPracticeApplication.java`:

~~~java
package com.example.cassandraworkshop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CassandraPracticeApplication {
    public static void main(String[] args) {
        SpringApplication.run(CassandraPracticeApplication.class, args);
    }
}
~~~

## 4. Mapping a Composite Primary Key in Spring Data Cassandra

This is the most critical part of the lab. The Java key class must mirror **both the column order and the role** of every column in CQL. You cannot replace the four-column key with a single `UUID id` and expect the repository to locate the right partition automatically.

`domain/OrderEventKey.java`:

~~~java
package com.example.cassandraworkshop.domain;

import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderEventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "order_id", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private UUID orderId;

    @PrimaryKeyColumn(
        name = "occurred_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID eventId;

    public OrderEventKey() {
    }

    public OrderEventKey(
            UUID tenantId, UUID orderId, Instant occurredAt, UUID eventId) {
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.occurredAt = occurredAt;
        this.eventId = eventId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID tenantId) { this.tenantId = tenantId; }

    public UUID getOrderId() { return orderId; }
    public void setOrderId(UUID orderId) { this.orderId = orderId; }

    public Instant getOccurredAt() { return occurredAt; }
    public void setOccurredAt(Instant occurredAt) { this.occurredAt = occurredAt; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID eventId) { this.eventId = eventId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderEventKey that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(orderId, that.orderId)
            && Objects.equals(occurredAt, that.occurredAt)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, orderId, occurredAt, eventId);
    }
}
~~~

Each annotation fulfills a specific role:

| Annotation / property | Effect | Common mistake |
| --- | --- | --- |
| `@PrimaryKeyClass` | Marks the class holding a composite key | Putting `@PrimaryKey` on a single `UUID` field inside the entity |
| `type = PARTITIONED` | Column belongs to the partition key | Marking `order_id` as `CLUSTERED` even though CQL defines a composite partition key |
| `type = CLUSTERED` | Column sorts rows within the partition | Swapping the clustering order of `occurred_at` and `event_id` |
| `ordinal` | Defines the column position in the key | Reordering ordinals so mapping diverges from CQL schema |
| `ordering` | Mirrors clustering sort direction | Leaving ascending in mapping when the table uses `DESC` |
| `equals/hashCode` | Stable Java key equality | Comparing only `orderId`, conflating tenants or events |

`domain/OrderEvent.java`:

~~~java
package com.example.cassandraworkshop.domain;

import java.math.BigDecimal;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_order")
public class OrderEvent {

    @PrimaryKey
    private OrderEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("amount")
    private BigDecimal amount;

    public OrderEvent() {
    }

    public OrderEvent(OrderEventKey key, String eventType, BigDecimal amount) {
        this.key = key;
        this.eventType = eventType;
        this.amount = amount;
    }

    public OrderEventKey getKey() { return key; }
    public void setKey(OrderEventKey key) { this.key = key; }

    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }
}
~~~

The `@PrimaryKey` value is the **entire `OrderEventKey`**. In Cassandra, an `INSERT` with **the same primary key** updates/upserts that same row; if two events sharing the same `occurredAt` must coexist, `eventId` must differ. Also, CQL `timestamp` has millisecond precision; avoid relying on the nanosecond portion of `Instant` for uniqueness.

The event timestamp must reflect domain `occurredAt`; never use `UUID.randomUUID()` as a substitute for chronological ordering. `eventId` acts as a tie-breaker providing deterministic ordering **when timestamps collide**, not real-time chronological ordering among same-timestamp events.

## 5. Repository: Writing Explicit CQL Queries

`repository/OrderEventRepository.java`:

~~~java
package com.example.cassandraworkshop.repository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.example.cassandraworkshop.domain.OrderEvent;
import com.example.cassandraworkshop.domain.OrderEventKey;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.stereotype.Repository;

@Repository
public interface OrderEventRepository
        extends CassandraRepository<OrderEvent, OrderEventKey> {

    @Query("SELECT * FROM events_by_order " +
           "WHERE tenant_id = ?0 AND order_id = ?1 LIMIT ?2")
    List<OrderEvent> findRecent(UUID tenantId, UUID orderId, int limit);

    @Query("SELECT * FROM events_by_order " +
           "WHERE tenant_id = ?0 AND order_id = ?1 " +
           "AND occurred_at >= ?2 LIMIT ?3")
    List<OrderEvent> findSince(
            UUID tenantId, UUID orderId, Instant since, int limit);
}
~~~

In `@Query`, `?0`, `?1`, `?2`, `?3` are **0-based positional bind parameters** managed by Spring Data, preventing string-concatenation CQL injection. Both Q1 and Q2 supply **both partition key components**. Rows are read in the schema's declared `CLUSTERING ORDER BY`; `LIMIT` bounds the number of rows returned from Cassandra.

For requirements spanning more than one partition, never assume repository methods can perform joins, cross-partition `GROUP BY`, or dynamic filtering like JPA. Create a new query-driven table or route data to a search/analytics system when requirements demand it.

### Service Layer

`service/EventTimelineService.java`:

~~~java
package com.example.cassandraworkshop.service;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import com.example.cassandraworkshop.domain.OrderEvent;
import com.example.cassandraworkshop.domain.OrderEventKey;
import com.example.cassandraworkshop.repository.OrderEventRepository;
import org.springframework.stereotype.Service;

@Service
public class EventTimelineService {
    private final OrderEventRepository repository;

    public EventTimelineService(OrderEventRepository repository) {
        this.repository = repository;
    }

    public OrderEvent record(
            UUID tenantId,
            UUID orderId,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            BigDecimal amount) {

        var key = new OrderEventKey(
            Objects.requireNonNull(tenantId),
            Objects.requireNonNull(orderId),
            Objects.requireNonNull(occurredAt),
            Objects.requireNonNull(eventId));

        if (eventType == null || eventType.isBlank()) {
            throw new IllegalArgumentException("eventType is required");
        }
        return repository.save(new OrderEvent(key, eventType, amount));
    }

    public List<OrderEvent> recent(UUID tenantId, UUID orderId, int limit) {
        if (tenantId == null || orderId == null) {
            throw new IllegalArgumentException("tenantId/orderId required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }
        return repository.findRecent(tenantId, orderId, limit);
    }

    public List<OrderEvent> since(
            UUID tenantId, UUID orderId, Instant since, int limit) {
        if (tenantId == null || orderId == null || since == null) {
            throw new IllegalArgumentException("key and since required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }
        return repository.findSince(tenantId, orderId, since, limit);
    }
}
~~~

Here the 100-record cap per read is an API policy of this example, not a hard Cassandra limit. A real application can use **driver paging state** or an appropriate `Slice` to iterate sequentially within a partition. Cassandra does not provide offset pagination like relational `OFFSET 1000`. Paging state is a continuation token that must be managed safely and bound to the corresponding query and parameters.

This service also does not yet handle **version contention**. If the domain requires preventing two writers from concurrently mutating a status, design conditional writes (LWT/CAS where appropriate) or application-level versioning. Having a unique composite key per event does not turn multi-partition Cassandra operations into ACID transactions.

## 6. Testcontainers: Testing Against Real Cassandra

Unit tests mocking the repository only verify Java method invocations; they **do not** prove key mappings are right, CQL is valid, or results follow clustering order. That is why this lab uses **integration tests** against a real Cassandra 4.1 container.

`src/test/resources/schema.cql` uses the same schema as the manual setup:

~~~sql
CREATE KEYSPACE IF NOT EXISTS workshop
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS workshop.events_by_order (
    tenant_id uuid,
    order_id uuid,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    amount decimal,
    PRIMARY KEY ((tenant_id, order_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Testcontainers starts an isolated Cassandra instance, executes `schema.cql`, and injects the **actual mapped host/port** into Spring Boot via `@DynamicPropertySource`. Each run is independent of the earlier `cassandra-lab` container's keyspace.

`src/test/java/com/example/cassandraworkshop/OrderEventRepositoryIntegrationTest.java`:

~~~java
package com.example.cassandraworkshop;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.example.cassandraworkshop.domain.OrderEvent;
import com.example.cassandraworkshop.domain.OrderEventKey;
import com.example.cassandraworkshop.repository.OrderEventRepository;
import com.example.cassandraworkshop.service.EventTimelineService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class OrderEventRepositoryIntegrationTest {

    @Container
    static final CassandraContainer<?> cassandra =
        new CassandraContainer<>(DockerImageName.parse("cassandra:4.1"))
            .withInitScript("schema.cql");

    @DynamicPropertySource
    static void cassandraProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cassandra.contact-points", cassandra::getHost);
        registry.add("spring.cassandra.port",
                     () -> cassandra.getMappedPort(9042));
        registry.add("spring.cassandra.local-datacenter",
                     () -> "datacenter1");
        registry.add("spring.cassandra.keyspace-name", () -> "workshop");
        registry.add("spring.cassandra.schema-action", () -> "NONE");
    }

    @Autowired
    private OrderEventRepository repository;

    @Autowired
    private EventTimelineService timeline;

    @Test
    void savesAndFindsByFullCompositeKey() {
        var key = new OrderEventKey(
            UUID.randomUUID(),
            UUID.randomUUID(),
            Instant.parse("2026-11-01T08:00:00Z"),
            UUID.randomUUID());

        repository.save(new OrderEvent(
            key, "CREATED", new BigDecimal("120.50")));

        OrderEvent actual = repository.findById(key).orElseThrow();
        assertThat(actual.getKey()).isEqualTo(key);
        assertThat(actual.getEventType()).isEqualTo("CREATED");
        assertThat(actual.getAmount()).isEqualByComparingTo("120.50");
    }

    @Test
    void returnsLatestEventsInClusteringOrderAndRespectsLimit() {
        UUID tenant = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        Instant base = Instant.parse("2026-11-01T09:00:00Z");

        timeline.record(tenant, order, base.minusSeconds(60),
                        UUID.randomUUID(), "CREATED", BigDecimal.TEN);
        timeline.record(tenant, order, base,
                        UUID.randomUUID(), "PAID", BigDecimal.TEN);
        timeline.record(tenant, order, base.plusSeconds(60),
                        UUID.randomUUID(), "SHIPPED", BigDecimal.TEN);

        List<OrderEvent> actual = timeline.recent(tenant, order, 2);
        assertThat(actual)
            .extracting(OrderEvent::getEventType)
            .containsExactly("SHIPPED", "PAID");
    }

    @Test
    void isolatesTenantsEvenWhenOrderIdMatches() {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-01T10:00:00Z");

        timeline.record(tenantA, order, at,
                        UUID.randomUUID(), "FROM_A", BigDecimal.ONE);
        timeline.record(tenantB, order, at,
                        UUID.randomUUID(), "FROM_B", BigDecimal.ONE);

        assertThat(timeline.recent(tenantA, order, 10))
            .extracting(OrderEvent::getEventType)
            .containsExactly("FROM_A");
        assertThat(timeline.recent(tenantB, order, 10))
            .extracting(OrderEvent::getEventType)
            .containsExactly("FROM_B");
    }

    @Test
    void filtersWithinPartitionByClusteringTime() {
        UUID tenant = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        Instant cutoff = Instant.parse("2026-11-01T10:00:00Z");

        timeline.record(tenant, order, cutoff.minusSeconds(1),
                        UUID.randomUUID(), "BEFORE", BigDecimal.ONE);
        timeline.record(tenant, order, cutoff,
                        UUID.randomUUID(), "AT_CUTOFF", BigDecimal.ONE);
        timeline.record(tenant, order, cutoff.plusSeconds(1),
                        UUID.randomUUID(), "AFTER", BigDecimal.ONE);

        assertThat(timeline.since(tenant, order, cutoff, 10))
            .extracting(OrderEvent::getEventType)
            .containsExactly("AFTER", "AT_CUTOFF");
    }

    @Test
    void deletingByFullKeyRemovesOnlyThatEvent() {
        UUID tenant = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-01T11:00:00Z");
        OrderEventKey key1 = new OrderEventKey(
            tenant, order, at, UUID.randomUUID());
        OrderEventKey key2 = new OrderEventKey(
            tenant, order, at, UUID.randomUUID());

        repository.save(new OrderEvent(key1, "ONE", BigDecimal.ONE));
        repository.save(new OrderEvent(key2, "TWO", BigDecimal.ONE));
        repository.deleteById(key1);

        assertThat(repository.findById(key1)).isEmpty();
        assertThat(repository.findById(key2)).isPresent();
    }
}
~~~

Run the tests from the Maven project root:

~~~bash
mvn test
~~~

In this project, the test class name ends with `Test`, so Maven Surefire discovers and runs it in the `test` phase. Testcontainers pulls/starts the image using Docker and initializes the keyspace/table before Spring connects. If Docker is unavailable, the tests cannot verify real Cassandra behavior; that is an environment issue to resolve, not a reason to replace integration tests with mocks.

### 6.1. What Each Test Verifies

| Test | What it confirms | Bugs it catches |
| --- | --- | --- |
| `savesAndFindsByFullCompositeKey` | All four key columns map and convert values accurately | Missing key fields, wrong column names, precision/type loss |
| `returnsLatestEventsInClusteringOrderAndRespectsLimit` | Q1 reads the right partition with DESC ordering and LIMIT | Wrong clustering direction, query not using key |
| `isolatesTenantsEvenWhenOrderIdMatches` | Tenant is part of the partition key | Querying by order ID alone causing cross-tenant data mixing |
| `filtersWithinPartitionByClusteringTime` | Q2 applies range filter on the clustering key | Filtering wrong column/order, returning events before cutoff |
| `deletingByFullKeyRemovesOnlyThatEvent` | DELETE targets one exact primary key | Accidentally deleting the whole partition or omitting a key component |

Because each test generates unique `tenantId/orderId` values, tests do not depend on execution order or full-table truncation. In a larger test suite, still manage container lifecycles, connections, and seed data consistently.

## 7. Manual Query Testing and Counterexamples

Once the table exists, try inserting sample rows via `cqlsh`:

~~~sql
INSERT INTO workshop.events_by_order (
    tenant_id, order_id, occurred_at, event_id, event_type, amount
) VALUES (
    00000000-0000-0000-0000-000000000001,
    00000000-0000-0000-0000-000000000002,
    '2026-11-01T09:00:00Z',
    00000000-0000-0000-0000-000000000011,
    'CREATED',
    120.50
);

INSERT INTO workshop.events_by_order (
    tenant_id, order_id, occurred_at, event_id, event_type, amount
) VALUES (
    00000000-0000-0000-0000-000000000001,
    00000000-0000-0000-0000-000000000002,
    '2026-11-01T09:05:00Z',
    00000000-0000-0000-0000-000000000012,
    'PAID',
    120.50
);

SELECT occurred_at, event_type
FROM workshop.events_by_order
WHERE tenant_id = 00000000-0000-0000-0000-000000000001
  AND order_id = 00000000-0000-0000-0000-000000000002
LIMIT 2;
~~~

Expected results in order:

~~~text
2026-11-01 09:05:00+0000 | PAID
2026-11-01 09:00:00+0000 | CREATED
~~~

Displayed timestamp formatting depends on `cqlsh` version/timezone settings; what to verify is **PAID sorted before CREATED**.

### Queries You Must Understand as Invalid for This Table

~~~sql
-- Missing part of the composite partition key: not served by this table.
SELECT * FROM workshop.events_by_order
WHERE tenant_id = 00000000-0000-0000-0000-000000000001;

-- No partition key, filtering by a regular column.
SELECT * FROM workshop.events_by_order
WHERE event_type = 'PAID';

-- Filtering directly on a clustering key without the partition key.
SELECT * FROM workshop.events_by_order
WHERE occurred_at >= '2026-11-01T00:00:00Z';
~~~

Cassandra rejects queries missing required key restrictions, or requires different filtering/indexing mechanisms depending on query type and version. **Do not add `ALLOW FILTERING` just to "make tests pass"**: succeeding on a handful of lab rows proves nothing about performance at hundreds of millions of rows across many partitions.

For a requirement like "find events by `customer_id` across a tenant," design an additional table `events_by_customer` with partition key `(tenant_id, customer_id)`, or stream events to a search/analytics store. When duplicating data across multiple tables, explicitly design the update pipeline, retries, idempotency, and divergence detection; two writes to two partitions do not automatically form an atomic distributed transaction.

## 8. Combining Consistency Levels, Replication, and the Java Driver

Spring Data Cassandra delegates statement execution to the Java Driver. Every request operates within Cassandra's distributed model; understanding replication and consistency matters even when the repository interface is only a few lines long.

### 8.1. Single-Node Lab vs. Multi-Replica Production

The lab keyspace uses `SimpleStrategy` with `replication_factor = 1` to run cleanly in one container. It **does not test** disconnected replicas or how quorum behaves inside a real datacenter.

For multi-node systems, an example datacenter-aware keyspace:

~~~sql
-- Illustrative example: run only when the real cluster has a DC named dc1.
CREATE KEYSPACE IF NOT EXISTS app_prod
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

With RF = 3 in a DC, `LOCAL_QUORUM` requires acknowledgments from a majority of replicas in that DC (2/3). Choosing a consistency level balances latency, availability, and consistency requirements; to reason about reading the latest written value, examine **both write and read consistency levels**, network conditions, and Cassandra's conflict-resolution semantics.

When an individual CQL statement needs an explicit consistency level, the Java Driver supports configuring it per statement. The illustrative snippet below sits in an infrastructure access layer using `CqlSession` directly:

~~~java
// Separate illustrative snippet, not part of the required lab files.
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare(
    "SELECT event_type FROM events_by_order " +
    "WHERE tenant_id = ? AND order_id = ? LIMIT ?");

BoundStatement bound = prepared.bind(tenantId, orderId, 20)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
session.execute(bound);
~~~

`session`, `tenantId`, and `orderId` in the snippet are variables initialized by the caller. To configure consistency on Spring Data repository operations, use the request/session configuration mechanism appropriate for your Spring Data and driver versions; never assume all repository calls automatically use `LOCAL_QUORUM`.

### 8.2. TTL, Tombstones, Compaction, and Repair

- **TTL:** if the application auto-expires history, writes can attach a TTL, but expired data produces tombstones that affect read latency and compaction. Do not use TTL when audit rules mandate permanent retention.
- **DELETE:** `repository.deleteById` emits a delete mutation; it does not mean bytes immediately vanish from all SSTables. Subsequent reads obey Cassandra's consistency and version-resolution rules.
- **Compaction:** merges SSTables and removes shadowed data/tombstones when safety conditions allow. Choose a compaction strategy suited to the data model and write lifecycle; never treat compaction as a repair mechanism for missing replicas.
- **Repair:** synchronizes divergence between replicas after outages or missed writes; maintain an operational repair schedule aligned with `gc_grace_seconds` and deletion policies to prevent deleted data from resurrecting after tombstones expire.
- **Partition size:** an `orderId` with unbounded history can grow into a large partition; monitor row counts, physical partition size, and tail latency, adjusting bucketing or TTLs as needed.

These are operational constraints requiring dedicated validation on a multi-replica cluster. **Never conclude a system is fault-tolerant just because five tests passed on a single-node container.**

## 9. Extending Tests for Real-World Environments

After the baseline lab, add these verification tests:

| Scenario | How to execute | What to observe |
| --- | --- | --- |
| Multiple events with identical timestamp | Insert two events with equal `occurredAt` but distinct `eventId` | No event lost; tie-breaking order follows `eventId ASC` |
| Same-key upsert | Write the same composite key again with a new `eventType` | Only one row exists for that key; verifies overwrite semantics |
| Bounded query | Write 200 events for one order, call service with limit 20 | Returns at most 20 without loading the whole partition into JVM |
| Invalid input | Call `recent(..., 0)`, `recent(..., 101)`, missing tenant | Service rejects before calling Cassandra |
| Schema drift | Rename a column in mapping or query | Integration test fails loudly, catching drift early |
| Disconnection / timeout | Interrupt network or stop a node in a suitable test environment | Timeouts, retries, error reporting, and client idempotency |
| RF = 3, single-replica failure | Spin up a 3-node cluster in one DC and test consistency levels | Quorum availability/latency under fault scenarios |
| Tombstones / repair | Test DELETE, TTL, replica outage, and controlled recovery/repair | No zombie data resurrection; lag, tombstone, and repair metrics behave as expected |

Never write tests that merely "assert the number of declared columns" as a substitute for behavioral verification. The most valuable tests target ways **the system can actually break**: misordered key columns, cross-tenant leakage, inverted clustering order, expensive scatter queries, or unsafe retries.

### End-to-End Business Flow Verification

Example operational sequence to verify:

1. Create order `O1` under `T1`, record `CREATED`.
2. Record `PAID` and `SHIPPED` for `T1/O1` with increasing timestamps.
3. Call `recent(T1, O1, 2)` → receives `SHIPPED`, `PAID`.
4. Record an event for `T2/O1` → `T1/O1` query remains unchanged.
5. Call `since(T1, O1, timeOfPaid, 10)` → receives `SHIPPED`, `PAID`, excluding `CREATED`.
6. Delete by the exact key of `PAID` → only that event is deleted; other events remain intact.

**Acceptance criteria:** results follow the exact partition and clustering keys, no `ALLOW FILTERING` is used, tenants stay isolated, integration tests pass against real Cassandra, and the schema is explicitly managed.

## 10. When Should the Design Change?

| New requirement | Design impact |
| --- | --- |
| List all orders for a customer | Requires a customer-keyed table or dedicated projection/search index |
| Filter all orders by `status` across tenants | Dedicated query-driven table or search engine; never scan `events_by_order` |
| Order history grows massive | Add time buckets/retention bounds, update queries, and test pagination |
| Monthly order analytics | Use a query-driven summary model or analytics store; raw event tables are poorly suited for ad-hoc aggregation |
| Write events and current state with strong guarantees | Explicitly design atomicity, sequence/versioning, and idempotency; evaluate partition-scoped batch/LWT limits |
| Multi-datacenter consistent reads | Define keyspace replication, local/remote DC routing, CL, retries, and recovery paths |

Changing a partition key alters **how data is distributed across the cluster** and usually cannot be done merely by editing a Java annotation. You must create a new table, backfill data, migrate write/read paths, verify, and decommission the old table.

## 11. Self-Assessment Checklist

- [ ] I can explain why `PRIMARY KEY ((tenant_id, order_id), occurred_at, event_id)` has a **two-column** partition key.
- [ ] I know why `ordinal = 0,1` map to partition columns and `ordinal = 2,3` map to clustering columns.
- [ ] I used `@PrimaryKeyClass` and `@PrimaryKey` properly, with `equals/hashCode` implemented on the Java key class.
- [ ] The repository executes queries specifying the full partition key, bound parameters, and `LIMIT`.
- [ ] Testcontainers executes the schema, Spring Boot connects, and create/read/sort/tenant/delete tests all pass.
- [ ] I did not use `ALLOW FILTERING` to compensate for an unaligned table design.
- [ ] I understand a single-node test does not prove fault tolerance under replica failures, and I understand the roles of consistency, repair, compaction, and TTL/tombstones.
- [ ] I can describe the schema/design changes required if customer-based queries or analytical reports are introduced.

**Core lesson:** With Spring Data Cassandra, repositories and annotations reduce boilerplate connection code, yet **the CQL partition key and clustering key still dictate whether queries execute efficiently**. Validate your design with integration tests on real Cassandra, then test distributed failure and operational behavior in an environment matching your production topology.
