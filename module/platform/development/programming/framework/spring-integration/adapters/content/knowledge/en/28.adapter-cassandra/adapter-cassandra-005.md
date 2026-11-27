# Partition keys in message flows with Apache Cassandra and Spring Integration

## 1. Problem: messages follow the flow yet Cassandra is still slow

An application receives `OrderPaid` events from HTTP or JMS, routes them through a Spring Integration `MessageChannel`, and stores them in Apache Cassandra. Initially everything runs smoothly with a few thousand events per day. When a large customer generates millions of events, some Cassandra nodes begin timing out, p99 latency spikes, and JMS backlogs start accumulating. Adding consumers or enlarging thread pools does not solve the issue—it may even overload the cluster faster.

The root cause can lie in the **partition key**: all events for that customer are written into a single oversized Cassandra partition, or the workload is unevenly distributed across token ranges/nodes.

In Cassandra, the **partition key determines how data is grouped into partitions and governs storage placement and request routing**. In Spring Integration, a **message key** may simply be a header used by a router/aggregator or by Kafka/JMS. The two concepts are related in design yet **do not map to each other automatically**. Without an explicit contract, messages travel cleanly through channels while Cassandra still writes to the wrong partition or breaks query correctness.

This lesson, **Partition keys in message flows**, part of the **Adapter Cassandra** chapter in the **SPRING_INTEGRATION_ADAPTERS** module, explains how to design keys for connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing message contracts, error handling, and connection lifecycles across JMS, Kafka, HTTP, and Cassandra.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish **Cassandra partition keys**, **clustering columns**, **full primary keys**, **Kafka partition keys**, **JMS message groups**, and Spring message headers.
2. Design Cassandra tables around **query patterns**, workload distribution, and bounded partition sizes.
3. Apply **composite partition keys** and **time bucketing/sharding** within read, write, and ordering constraints.
4. Map `@PrimaryKeyClass`, `@PrimaryKeyColumn`, and `PrimaryKeyType.PARTITIONED/CLUSTERED` in Spring Data Cassandra.
5. Build a Spring Integration flow from a validated message to a Cassandra outbound adapter or gateway.
6. Keep keys stable across retries/redeliveries, avoid misclassifying duplicates, and protect ordering/idempotency.
7. Measure hotspots, partition sizes, latency, and backlogs; write integration tests against real Cassandra.

## 2. Three kinds of keys often loosely called "partition key"

| Concept | Where does it live? | Primary purpose | Automatically synced with Cassandra? |
|---|---|---|---|
| **Cassandra partition key** | CQL schema, `PRIMARY KEY` | Selects partition, computes token, determines replica placement | It is the **storage target**, not populated from Spring headers automatically |
| **Kafka record key** | Kafka record metadata, often `KafkaHeaders.KEY` in Spring | Chooses Kafka partition via partitioner, aids per-partition ordering | **No**; requires an explicit transformer/mapper |
| **JMS `JMSXGroupID`** | JMS message property when broker supports message groups | Tags a message group to avoid concurrent processing of the same group | **No**; does not determine the Cassandra token |
| **Spring `correlationId`** | `MessageHeaders` | Correlates messages in an aggregator/request flow | **No**; may be a flow UUID rather than a business ID |
| **Business `eventId`** | Payload contract | Identifies an event across producer retries, broker redeliveries, and DLQ replays | Only when mapped to an appropriate PK/uniqueness mechanism |
| **Business `aggregateId/orderId`** | Payload contract | Groups events for the same order, protecting versions/ordering | Only when schema or routing explicitly uses it |

An application may choose the **same business key** as both the Kafka key and part of the Cassandra partition key to simplify ordering, yet **must never assume** the two systems share the same partition count, hash algorithm, nodes, or physical order.

### 2.1. Diagram from event to two forms of partitioning

~~~mermaid
flowchart LR
    A["OrderPaid event: tenantId, orderId, eventId, occurredAt"] --> B["Spring Integration validation/transform"]
    B --> C["MessageHeaders: routing/tracing/key hint"]
    C --> D["Kafka/JMS message metadata if present"]
    B --> E["Entity / BoundStatement with full CQL primary key fields"]
    E --> F["Cassandra partition key: tenantId + orderId + month"]
    F --> G["Murmur3 token / partitioner"]
    G --> H[("Replica nodes and partition data")]
    D -. "Does not auto-create CQL partition key" .-> E
~~~

**Key point:** Cassandra receives CQL writes carrying partition-key values via entities or statements. Broker headers may carry the same `tenantId`/`orderId`, but Cassandra **does not read JMS/Kafka headers** unless the flow explicitly maps them into CQL.

## 3. Structure of a CQL `PRIMARY KEY`

In Cassandra, the full primary key consists of the **partition key** and, optionally, **clustering columns**.

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.events_by_order_month (
    tenant_id text,
    order_id text,
    bucket_month text,
    occurred_at timestamp,
    event_id text,
    event_type text,
    payload_json text,
    PRIMARY KEY (
        (tenant_id, order_id, bucket_month),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Breakdown:

- `(tenant_id, order_id, bucket_month)` is the **composite partition key**. Together, all three values identify a single Cassandra partition.
- `occurred_at` and `event_id` are **clustering columns**. They sort rows **within the partition** and participate in row uniqueness.
- The full primary key is `(tenant_id, order_id, bucket_month, occurred_at, event_id)`, **not only** the three partition columns.
- `event_type` and `payload_json` are regular columns; they **do not determine** token/placement.

Example with three rows:

~~~text
partition = (tenant-42, ORD-9001, 2026-11)
    occurred_at=2026-11-23T03:02:00Z, event_id=evt-03
    occurred_at=2026-11-23T03:01:00Z, event_id=evt-02
    occurred_at=2026-11-23T03:00:00Z, event_id=evt-01

partition = (tenant-42, ORD-9001, 2026-12)
    occurred_at=2026-12-01T00:01:00Z, event_id=evt-04

partition = (tenant-42, ORD-9002, 2026-11)
    occurred_at=2026-11-23T03:03:00Z, event_id=evt-05
~~~

Within one partition, `occurred_at DESC` returns newest events first. **There is no global order across Cassandra partitions**, and clustering order **does not guarantee** business processing order when multiple consumers write concurrently.

### 3.1. Parentheses matter in PRIMARY KEY

Compare:

~~~sql
-- Only tenant_id is the partition key; order_id and event_id are clustering.
PRIMARY KEY (tenant_id, order_id, event_id)

-- tenant_id + order_id form the composite partition key; event_id is clustering.
PRIMARY KEY ((tenant_id, order_id), event_id)

-- All three columns form the composite partition key; no clustering.
PRIMARY KEY ((tenant_id, order_id, event_id))
~~~

These three declarations have vastly different **distribution and query** properties. Missing one pair of parentheses in a migration can force a large customer into a single giant partition.

### 3.2. Partition keys vs clustering keys in purpose

| Property | Partition key | Clustering column |
|---|---|---|
| Determines token/replicas | **Yes** | No |
| Groups rows in same partition | **Yes** | Sorts/uniquely identifies rows inside a partition |
| Efficient querying | Usually requires the full partition key | Supports range/order predicates per clustering rules |
| Causes a hot partition if poorly chosen | **Yes** | Cannot fix partition key skew |
| Number of unique keys grows | Increases number of partitions | Increases number of rows within the same partition |
| Changing after table creation | Requires migration strategy/new table | Also part of PK schema; cannot be arbitrarily `UPDATE`d |

**Correctness:** primary key columns cannot be modified like regular columns in an `UPDATE`. Moving an event from a wrong bucket to the right bucket typically requires **writing a row under the new key** and deleting/cleaning up the old row according to a plan; there is no `UPDATE bucket_month = ...` that mutates a primary key in place.

## 4. Token-aware routing and replica placement

With the standard **Murmur3Partitioner**, Cassandra computes a token from the bytes of the **entire partition key**. A composite key has schema-defined serialization and column ordering; it is not simple string concatenation with `-` followed by a text hash.

~~~mermaid
flowchart TD
    K["partition key tuple"] --> H["Partitioner: compute token"]
    H --> R["Token ranges in the ring"]
    R --> P["Replication strategy + topology"]
    P --> N1[("Replica node A")]
    P --> N2[("Replica node B")]
    P --> N3[("Replica node C")]
    D["Token-aware Java driver"] --> H
    D --> C["Select suitable coordinator"]
    C --> N1
~~~

The nodes in the diagram merely illustrate one replication topology. With RF=1 or multiple datacenters, replica counts and placement differ. One partition holds many rows yet is replicated across **one set of nodes** per strategy; it is not randomly split across all nodes simply because it has many clustering rows.

### 4.1. Token-aware routing depends on binding the full key

The driver can determine the routing key when:

1. The prepared statement includes metadata identifying partition-key columns.
2. The caller binds all partition values with matching types.
3. The driver uses a token-aware load-balancing policy and current cluster metadata.

Without sufficient metadata or bound key values, the driver can still send requests to a coordinator, but **optimal token-aware routing cannot be expected**.

### 4.2. Why is a Cassandra partition key different from a Kafka key?

Kafka's partitioner maps a record key to a **Kafka topic partition**, influenced by partition count, partitioner implementation, and version. Cassandra partitions data by **token range + replication strategy** and keyspace schema. The same string `orderId="ORD-9001"` creates no one-to-one mapping between Kafka partition 5 and Cassandra node A.

If a Kafka topic increases its partition count, record keys can remap under the new partitioner; if a Cassandra cluster adds/removes nodes or shifts token ranges, replica placement can change. Therefore **never derive Cassandra partitioning directly from a Kafka partition number** without an analyzed data contract.

## 5. Design keys by query first, not by field names

Cassandra uses **query-driven data modeling**: identify the questions you must answer, then pick partition and clustering keys. A single event may be stored in **multiple tables serving different query patterns**; denormalization is an intentional strategy, not a flaw.

### 5.1. Three distinct business queries

| Query | Candidate partition key | Clustering needed? | Risk |
|---|---|---|---|
| Find exact event by `eventId` | `(event_id)` | No | Needs a separate lookup table if the timeline table uses another key |
| Fetch latest events of an order within a month | `(tenant_id, order_id, bucket_month)` | `occurred_at DESC, event_id` | Multi-month queries must fan out across partitions |
| Fetch all tenant events in a day | `(tenant_id, bucket_day)` | `occurred_at` | Large tenants easily create wide/hot partitions |
| Track errors by status | Avoid low-cardinality status alone | Depends on goal | A single `status='ERROR'` partition can run too hot |

An ideal partition key **serves the exact query**, distributes well, and keeps partitions at manageable sizes. Picking a random UUID as the key distributes evenly yet **fails** orderId/time queries.

### 5.2. A pair of tables for one event source

~~~sql
-- Direct lookup of a single event.
CREATE TABLE IF NOT EXISTS shop_integration.event_by_id (
    event_id text PRIMARY KEY,
    tenant_id text,
    order_id text,
    occurred_at timestamp,
    payload_json text
);

-- Monthly per-order timeline (already declared in section 3).
-- shop_integration.events_by_order_month
~~~

Lookups by `eventId` hit `event_by_id`; timeline reads by order+month hit `events_by_order_month`. **Cassandra does not commit two tables atomically like a multi-table RDBMS ACID transaction by default.** Writing two tables from the same event requires a retry/idempotency strategy and handling partial failure when one write succeeds and the other fails.

## 6. Time bucketing: keeping partitions bounded

An order with few events can use `(tenant_id, order_id)` as its partition key and `occurred_at` for clustering. However, a huge "aggregate", IoT/log stream, or long-lived entity with millions of changes will grow the partition indefinitely over time. **Time bucketing** adds `bucket_month` or `bucket_day` to the partition key to bound data per partition.

~~~text
No bucket:
  (tenant-42, device-08) -> entire multi-year dataset

Monthly bucket:
  (tenant-42, device-08, 2026-09)
  (tenant-42, device-08, 2026-10)
  (tenant-42, device-08, 2026-11)

Daily bucket (high density):
  (tenant-42, device-08, 2026-11-21)
  (tenant-42, device-08, 2026-11-22)
  (tenant-42, device-08, 2026-11-23)
~~~

### 6.1. Computing buckets with a fixed timezone

When the source supplies `occurredAt` as an `Instant`, compute the bucket in **UTC** or the timezone specified by the contract:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class PartitionBuckets {
    private static final DateTimeFormatter MONTH =
            DateTimeFormatter.ofPattern("uuuu-MM");

    private PartitionBuckets() {}

    public static String utcMonth(Instant occurredAt) {
        if (occurredAt == null) {
            throw new IllegalArgumentException("occurredAt is required");
        }
        return MONTH.format(occurredAt.atOffset(ZoneOffset.UTC));
    }
}
~~~

For instance, `2026-11-30T23:59:59Z` belongs to `2026-11`, while `2026-12-01T00:00:00Z` belongs to `2026-12`. **Never use `LocalDate.now()` or the consumer host's default timezone** to compute buckets: when a message is replayed in a later month or processed on a node in another timezone, it lands in a different partition, breaking event identity.

### 6.2. Bucket size has no universal answer

Suppose a device emits 600 events/minute with an average payload of 1 KiB of JSON alone:

~~~text
600 events/min × 60 × 24 = 864,000 events/day.
JSON payload approx 843.75 MiB/day (864,000 KiB) before overhead/index/replication.
~~~

Even a **daily** bucket can be too wide/hot at that rate. Conversely, a device emitting one event/day with minute buckets creates excessive tiny partitions. Measure:

- Average and p99 rows/cells per partition.
- Actual size on disk (data + tombstones + overhead).
- Read/write throughput targeting a single partition key.
- TTL/retention, compaction, clustering scans, and repairs.
- How many partitions must be queried across a typical time range.

Apache Cassandra offers a **general guideline** to aim for partitions below roughly **100,000 values/cells and 100 MB**; this is **not a hard limit for every workload**. Appropriate sizing must be benchmarked against your cluster, schema, payload, and query plan.

## 7. Hot partitions and controlled sharding

Time bucketing bounds size over time yet **does not distribute writes within a single window**. If `tenant-42` writes 50,000 events/second into `(tenant-42, 2026-11-23)`, all writes for that day still hit **the same partition key**. Adding clustering column `event_id` distinguishes rows without **spreading load across multiple tokens**.

### 7.1. A design prone to hot partitions

~~~sql
CREATE TABLE shop_integration.events_by_tenant_day (
    tenant_id text,
    bucket_day date,
    occurred_at timestamp,
    event_id text,
    event_type text,
    PRIMARY KEY ((tenant_id, bucket_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Querying by tenant+day feels natural yet invites **skew**: small tenants have a few events/day while large tenants have millions. Never design schemas solely around average traffic.

### 7.2. Adding a shard to the composite partition key

~~~sql
CREATE TABLE shop_integration.events_by_tenant_day_shard (
    tenant_id text,
    bucket_day date,
    shard tinyint,
    occurred_at timestamp,
    event_id text,
    event_type text,
    PRIMARY KEY (
        (tenant_id, bucket_day, shard),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Assuming `shard` ranges from 0–15, one tenant/day has up to **16 partition keys** (not 16 Cassandra nodes). Those partition keys hash to tokens, giving writes a chance to distribute better. **There is no guarantee 16 shards land on 16 distinct nodes** or that throughput scales exactly 16x.

In return, reading **all events for a tenant on a given day** requires querying the relevant shards and merging/sorting results if a unified timeline is needed. Sharding trades **more complex reads** to solve write skew.

### 7.3. Choosing a shard with a stable algorithm

When deriving shard from `eventId`, use a hash function that is **deterministic across languages and replays**. Minimal example using SHA-256 and 16 shards:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class StableShards {
    private StableShards() {}

    public static int shard16(String eventId) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(eventId.getBytes(StandardCharsets.UTF_8));
            return (digest[0] & 0xff) % 16;
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

This algorithm is **not Cassandra's Murmur3 token**. It merely produces an evenly distributed shard field, after which Cassandra hashes the **entire composite partition key** via its partitioner. All producers, consumers, and backfill jobs must use **the exact same algorithm and shard count**.

**Important:** changing 16 to 32 shards after deployment without versioning/migrating existing data causes the same `eventId` to write into a different shard than before. When scaling, introduce `shard_scheme_version`, migrate/dual-read old and new schemas, or cut over to a new table cleanly.

### 7.4. Sharding by event can break per-order ordering

If `OrderCreated`, `OrderPaid`, and `OrderCancelled` for the same `orderId` have different `eventId` values, they can land in **three different Cassandra shards**. The timeline no longer lives in one partition. To keep all events for an order in one partition, include `orderId` and an appropriate bucket in the key, or shard **by `orderId`** (recognizing that one ultra-hot order can still bottleneck).

**No single partition key optimizes every read while evenly spreading every write:** balance queries, load, ordering, and table maintenance costs.

## 8. Message contracts must carry every partition key component

An input event serving as the data source:

~~~json
{
  "eventId": "evt-5001",
  "tenantId": "tenant-42",
  "orderId": "ORD-9001",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T03:00:00Z",
  "payload": {"amountMinor": 250000, "currency": "VND"}
}
~~~

In `events_by_order_month`, a complete key requires:

~~~text
tenant_id     <- tenantId
order_id      <- orderId
bucket_month  <- UTC month of occurredAt
occurred_at   <- occurredAt
event_id      <- eventId
~~~

**Never derive keys from ephemeral values** like the current JVM clock, broker delivery attempt count, or a random UUID generated per consumer attempt.

### 8.1. Distinguishing business keys from routing-only metadata

| Field | Contract | Used in Cassandra? | Purpose |
|---|---|---|---|
| `eventId` | Immutable across retries/replays | Clustering in timeline; partition key of lookup table | Business deduplication |
| `tenantId` | Verified from producer/context | Partition component | Tenant isolation and query scope |
| `orderId` | Immutable, belongs to tenant | Partition component | Per-order timeline |
| `occurredAt` | Event timestamp with timezone convention | Clustering + bucket source | Historical ordering and bucketing |
| `bucketMonth` | Computed or verified from `occurredAt` | Partition component | Bounds partitions by month |
| `schemaVersion` | Serializer contract | Regular column or header | Versioned deserialization |
| `JMSMessageID` | Provider-generated | Audit-only if stored | Never replaces `eventId` |
| `KafkaHeaders.RECEIVED_PARTITION` | Kafka consumer metadata | Not by default | Observing broker partition, not Cassandra partition |

### 8.2. Messages missing key fields must fail before Cassandra

Suppose `orderId` is blank or `occurredAt` fails to parse. Never dump all errors into a fallback `"unknown"` bucket: that creates a **hot partition**, leaks cross-tenant data, and corrupts queries.

Validate:

1. `eventId` is unique/stable and matches the specified format.
2. `tenantId` and `orderId` are non-blank, bounded in length, and authorized for the sender.
3. `occurredAt` has valid timezone/format and falls within acceptable bounds (with a policy for late events).
4. `bucketMonth` is **recomputed from the timestamp** or cross-checked against the producer's field.
5. `schemaVersion` is supported and payload size stays within byte limits.

An event violating the contract should go to **quarantine/error handling** by design, never written under an uncontrolled "fallback" partition key.

### 8.3. Keys should not hold secrets

Partition keys appear in CQL statements, logs, traces, monitoring, and operational tools. Never embed auth tokens, passwords, or unnecessary sensitive data in keys. `tenantId` must be verified via service identity/authorization; a self-asserted client header is never sufficient proof of access.

## 9. Spring Data Cassandra: mapping a composite partition key

Spring Data Cassandra provides **`@PrimaryKeyClass`** with `@PrimaryKeyColumn` to distinguish partition columns from clustering columns. For `events_by_order_month` from section 3, configure each field's `ordinal` and `type` explicitly.

### 9.1. Key class with complete equals/hashCode

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderTimelineKey implements Serializable {

    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private String tenantId;

    @PrimaryKeyColumn(name = "order_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private String orderId;

    @PrimaryKeyColumn(name = "bucket_month", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private String bucketMonth;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private String eventId;

    public OrderTimelineKey() {}

    public OrderTimelineKey(
            String tenantId, String orderId, String bucketMonth,
            Instant occurredAt, String eventId) {
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.bucketMonth = bucketMonth;
        this.occurredAt = occurredAt;
        this.eventId = eventId;
    }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getBucketMonth() { return bucketMonth; }
    public void setBucketMonth(String bucketMonth) { this.bucketMonth = bucketMonth; }

    public Instant getOccurredAt() { return occurredAt; }
    public void setOccurredAt(Instant occurredAt) { this.occurredAt = occurredAt; }

    public String getEventId() { return eventId; }
    public void setEventId(String eventId) { this.eventId = eventId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderTimelineKey key)) return false;
        return Objects.equals(tenantId, key.tenantId)
                && Objects.equals(orderId, key.orderId)
                && Objects.equals(bucketMonth, key.bucketMonth)
                && Objects.equals(occurredAt, key.occurredAt)
                && Objects.equals(eventId, key.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
                tenantId, orderId, bucketMonth, occurredAt, eventId);
    }
}
~~~

Per Spring Data Cassandra, **`@PrimaryKeyClass` requires `Serializable` and value equality semantics**. The `ordinal` values order the key columns to match CQL; set `PARTITIONED` on the first three columns and `CLUSTERED` on the last two.

**Do not equate Java's `equals/hashCode` with Cassandra's token hash:** Java equality governs entity identity and map/repository usage, whereas Cassandra tokens are computed by the partitioner over serialized partition keys. Having two different hash functions is normal.

### 9.2. Entity using @PrimaryKey

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_order_month")
public class OrderTimelineEvent {

    @PrimaryKey
    private OrderTimelineKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload_json")
    private String payloadJson;

    public OrderTimelineEvent() {}

    public OrderTimelineEvent(
            OrderTimelineKey key, String eventType, String payloadJson) {
        this.key = key;
        this.eventType = eventType;
        this.payloadJson = payloadJson;
    }

    public OrderTimelineKey getKey() { return key; }
    public void setKey(OrderTimelineKey key) { this.key = key; }

    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }

    public String getPayloadJson() { return payloadJson; }
    public void setPayloadJson(String payloadJson) {
        this.payloadJson = payloadJson;
    }
}
~~~

`@Table` specifies the target table, `@PrimaryKey` attaches the composite key class, and `@Column` maps regular fields. Spring Data maps partition and clustering fields from `OrderTimelineKey` to CQL columns.

### 9.3. Converter: from event to entity

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public record OrderEvent(
        String eventId,
        String tenantId,
        String orderId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String payloadJson) {}

public final class TimelineMapper {

    private TimelineMapper() {}

    public static OrderTimelineEvent toEntity(OrderEvent event) {
        if (event == null
                || event.eventId() == null || event.eventId().isBlank()
                || event.tenantId() == null || event.tenantId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || event.occurredAt() == null) {
            throw new IllegalArgumentException(
                    "OrderEvent is missing required key fields");
        }

        // Cassandra timestamp stores millisecond precision; normalize key before writing.
        Instant canonicalTime = event.occurredAt()
                .truncatedTo(ChronoUnit.MILLIS);
        String bucketMonth = PartitionBuckets.utcMonth(canonicalTime);

        OrderTimelineKey key = new OrderTimelineKey(
                event.tenantId(),
                event.orderId(),
                bucketMonth,
                canonicalTime,
                event.eventId());

        return new OrderTimelineEvent(
                key, event.eventType(), event.payloadJson());
    }
}
~~~

This example assumes `schemaVersion` was checked by a validator before conversion. Never drop `schemaVersion` from the application contract simply because the timeline table lacks a column for it; if schema tracking is needed, add the column/metadata deliberately per policy.

**Core rule:** derive keys **deterministically from the business event**. When the same event is redelivered, the transformer must emit the **exact same `tenantId`/`orderId`/`bucketMonth`/`occurredAt`/`eventId`**; changing `eventId` or bucketing by current time makes Cassandra treat it as **a different row**.

Here `occurred_at` uses CQL `timestamp` with millisecond precision, whereas Java `Instant` can contain nanoseconds. The mapper truncates via `truncatedTo(MILLIS)` so key comparisons across Java, Cassandra, and read-backs remain consistent. **Cross-language contracts must agree on timestamp precision**, not just timezone.

## 10. Java DSL: from MessageChannel to Cassandra outbound adapter

Spring Integration Cassandra (since 6.0) provides `Cassandra.outboundChannelAdapter(operations, Type.INSERT)`. The adapter wraps `CassandraMessageHandler` and Spring Data Cassandra's `ReactiveCassandraOperations`; it does **not** accept imperative `CqlTemplate` directly.

### 10.1. Minimum dependencies for the lab

~~~xml
<!-- Assumes Spring Boot BOM manages compatible versions. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
~~~

Example `application.yml` for a Cassandra test node:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

Addresses, datacenter, and keyspace must match the actual cluster. Keyspaces and test tables must be provisioned beforehand via migrations/test setup. Never use the lab's `SimpleStrategy/replication_factor=1` in multi-datacenter production.

### 10.2. Flow receiving OrderEvent and creating a Cassandra entity

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderTimelineIntegrationConfiguration {

    @Bean
    public IntegrationFlow orderEventsToCassandra(
            ReactiveCassandraOperations operations) {

        return IntegrationFlow.from("validatedOrderEvents")
                .transform(OrderEvent.class, TimelineMapper::toEntity)
                .handle(Cassandra.outboundChannelAdapter(
                                operations, CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Here `validatedOrderEvents` receives a Spring Message with an **`OrderEvent` payload**; the transformer builds the entity with its composite key; the adapter writes to Cassandra using Spring Data mapping. `endpoint.async(false)` makes the handler await completion synchronously, useful for labs and clear error observation. Per Spring Integration, **the handler defaults to `async=true`**; `async(false)` does not create a transaction between Cassandra and JMS/Kafka.

**The adapter is one-way:** it will not send CQL results back into the flow merely because the source Spring Message has a `replyChannel`. If you need SELECT/LWT results or write confirmation downstream, use the Cassandra **outbound gateway** with an explicit reply contract.

### 10.3. Creating and sending messages from a service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventFlowPublisher {

    private final MessageChannel validatedOrderEvents;

    public OrderEventFlowPublisher(
            @Qualifier("validatedOrderEvents")
            MessageChannel validatedOrderEvents) {
        this.validatedOrderEvents = validatedOrderEvents;
    }

    public void publish(OrderEvent event) {
        boolean accepted = validatedOrderEvents.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", event.eventId())
                        .setHeader("tenantId", event.tenantId())
                        .setHeader("orderId", event.orderId())
                        .build());
        if (!accepted) {
            throw new IllegalStateException("No subscriber accepted event");
        }
    }
}
~~~

The message headers above are **for Spring tracing/routing**, not the default source of Cassandra data. `TimelineMapper` reads the payload; even if a `tenantId` header is wrong, the key still comes from `OrderEvent.tenantId()`. Applications must ensure **headers and payloads do not conflict**, especially when headers originate from external gateways.

`send(true)` only indicates that delivery/configured handler invocation completed per channel semantics. With async channels or the default async Cassandra handler, callers **cannot infer Cassandra committed the write** from this boolean alone.

## 11. Querying by partition key and consequences of bucketing

### 11.1. Querying a single partition

~~~sql
SELECT event_id, event_type, occurred_at, payload_json
FROM shop_integration.events_by_order_month
WHERE tenant_id = 'tenant-42'
  AND order_id = 'ORD-9001'
  AND bucket_month = '2026-11'
LIMIT 50;
~~~

The query specifies **all three partition-key columns**. Because the table was defined with `CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)`, rows within the partition are stored/served in clustering order; the query caps results to the 50 latest events **inside that bucket**.

Results **do not automatically include events from October or December**. Callers needing a three-month timeline must determine which buckets to read and merge results carefully.

### 11.2. Querying a time range within one bucket

~~~sql
SELECT event_id, event_type, occurred_at
FROM shop_integration.events_by_order_month
WHERE tenant_id = ?
  AND order_id = ?
  AND bucket_month = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 100;
~~~

The `?` placeholders bind in exact order. The range predicate targets the **first clustering column**, `occurred_at`. A client building a multi-bucket timeline should **query each required bucket**, cap concurrency, page appropriately, and merge by an explicit sort key.

### 11.3. Cannot arbitrarily filter by part of a composite partition key

For a table with `PRIMARY KEY ((tenant_id, order_id, bucket_month), ...)`, the query:

~~~sql
-- Not a valid partition query; usually not supported efficiently.
SELECT * FROM events_by_order_month
WHERE tenant_id = 'tenant-42';
~~~

`tenant_id` is only **part** of the composite partition key—insufficient to compute a token and locate a partition. Cassandra may reject queries missing key components or require an expensive scan/filter. **Do not use `ALLOW FILTERING` as a default workaround**: design a dedicated table for tenant-level queries if that is a real use case.

### 11.4. Querying multiple buckets: bounded fan-out

~~~mermaid
flowchart LR
    Q["Lookup order ORD-9001 over 90 days"] --> B1["Bucket 2026-09"]
    Q --> B2["Bucket 2026-10"]
    Q --> B3["Bucket 2026-11"]
    B1 --> M["Merge by occurredAt DESC + eventId"]
    B2 --> M
    B3 --> M
    M --> R["Result page and safe cursor"]
~~~

When each bucket requires a CQL query, avoid firing hundreds of unbounded concurrent requests simply because the API permits it. Enforce a **maximum lookback window**, cap buckets per query, define cursor/continuation rules, and bound memory.

**Time bucketing complicates reads yet keeps partitions manageable.** It is an intentional trade-off, not a mistake to fix with a giant `IN` query.

### 11.5. Debugging tokens on Cassandra

On a test cluster containing data:

~~~sql
SELECT token(tenant_id, order_id, bucket_month)
FROM shop_integration.events_by_order_month
WHERE tenant_id = 'tenant-42'
  AND order_id = 'ORD-9001'
  AND bucket_month = '2026-11'
LIMIT 1;
~~~

`token(...)` reveals the token corresponding to the **composite partition key** under the active partitioner. Never manually hash `"tenant-42:ORD-9001:2026-11"` and claim it is the Cassandra token; Cassandra serializes key components per protocol, type, and schema.

If a partition is empty, querying the table returns **no rows**, which does not mean the token "mathematically doesn't exist". In a lab, insert a row before inspecting. Nodes/replicas are determined by token ranges and topology; there is no mandatory one-to-one mapping between "one token" and "one Kafka partition".

## 12. Java DSL for queries using the Cassandra outbound gateway

The Cassandra outbound **gateway** is the variant to use when the flow needs to return SELECT/statement results. It still uses `ReactiveCassandraOperations`, with replies enabled.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow orderTimelineQueryFlow(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("orderTimelineQueries")
            .handle(Cassandra.outboundGateway(operations)
                    .query("SELECT event_id, event_type, occurred_at "
                           + "FROM events_by_order_month "
                           + "WHERE tenant_id = :tenantId "
                           + "AND order_id = :orderId "
                           + "AND bucket_month = :bucketMonth LIMIT :maxRows")
                    .parameter("tenantId", message ->
                            ((TimelineQuery) message.getPayload()).tenantId())
                    .parameter("orderId", message ->
                            ((TimelineQuery) message.getPayload()).orderId())
                    .parameter("bucketMonth", message ->
                            ((TimelineQuery) message.getPayload()).bucketMonth())
                    .parameter("maxRows", message ->
                            ((TimelineQuery) message.getPayload()).maxRows()))
            .channel(c -> c.flux("orderTimelineResults"))
            .get();
}
~~~

Gateway input DTO:

~~~java
public record TimelineQuery(
        String tenantId,
        String orderId,
        String bucketMonth,
        int maxRows) {

    public TimelineQuery {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()
                || bucketMonth == null || !bucketMonth.matches("\\d{4}-\\d{2}")
                || maxRows < 1 || maxRows > 100) {
            throw new IllegalArgumentException("Invalid timeline query");
        }
    }
}
~~~

`.parameter(...)` accepts either a **SpEL String** or a **`Function<Message<?>, ?>`** to extract values from the message; the example uses Java functions for strongly typed access to the `TimelineQuery` record. `:tenantId`, `:orderId`, etc., in CQL are **named bind markers**, not Spring headers. The gateway never concatenates payloads directly into query syntax. Inputs must still pass **tenant/authorization checks**, because prepared parameters only bind values and do not enforce access control.

`FluxMessageChannel` in this example supports reactive flows; consumers of `orderTimelineResults` must handle the Publisher/Result payload type matching your Spring Integration version. If **imperative** request/reply behavior is required, `async(false)` can be configured while accounting for blocking and the reply contract.

**Do not use a one-way outbound adapter for SELECT expecting `replyChannel` to receive results automatically.** An adapter with `producesReply=false` does not emit replies like a gateway.

### 12.1. Parameters sourced from headers: use under strict control

Within a flow, `bucketMonth` may be placed in a Spring header after transformation:

~~~java
// Java DSL fragment, when headers have been validated/normalized.
.handle(Cassandra.outboundGateway(operations)
        .query("SELECT event_id FROM events_by_order_month "
               + "WHERE tenant_id = :tenantId "
               + "AND order_id = :orderId "
               + "AND bucket_month = :bucketMonth LIMIT 25")
        .parameter("tenantId", "headers['verifiedTenantId']")
        .parameter("orderId", message ->
                ((TimelineQuery) message.getPayload()).orderId())
        .parameter("bucketMonth", "headers['canonicalBucketMonth']"))
~~~

Naming it `verifiedTenantId` signals that this header was **produced after authentication/authorization**; never simply rename a client-supplied header and treat it as trusted.

### 12.2. Direct CQL statements

When custom CQL beyond Spring Data entity mapping is needed, the adapter also supports `STATEMENT` mode and `statementFunction(...)` taking a Spring Message and returning a driver `Statement<?>`:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow timelineBoundStatementFlow(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("timelineStatementWrites")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderTimelineEvent entity =
                                (OrderTimelineEvent) message.getPayload();
                        OrderTimelineKey k = entity.getKey();
                        return SimpleStatement.newInstance(
                                "INSERT INTO events_by_order_month "
                                + "(tenant_id, order_id, bucket_month, "
                                + "occurred_at, event_id, event_type, payload_json) "
                                + "VALUES (?, ?, ?, ?, ?, ?, ?)",
                                k.getTenantId(), k.getOrderId(), k.getBucketMonth(),
                                k.getOccurredAt(), k.getEventId(),
                                entity.getEventType(), entity.getPayloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`SimpleStatement.newInstance(query, args...)` separates CQL text from bound values. For systems explicitly using Java Driver `PreparedStatement`/`BoundStatement`, prepare the CQL once on `CqlSession` and call `prepared.bind(...)` per event inside `statementFunction`. Never concatenate keyspace names, table names, or event values from untrusted sources into CQL strings.

**Pick one consistent path:** entity `Type.INSERT` (section 10) or `STATEMENT` mode (section 12.2) per endpoint. Do not wire two adapters to the same input channel expecting each event to write only once.

## 13. Relation to Kafka partition keys and JMS message groups

Cassandra keys belong to the **data model**, whereas Kafka/JMS keys govern **broker ordering and routing**. They can share `orderId` at the business-contract level without automatically coupling to each other.

### 13.1. Kafka: sending a stable record key per order

~~~java
import org.springframework.kafka.core.KafkaTemplate;

public final class OrderKafkaPublisher {

    private final KafkaTemplate<String, String> kafka;

    public OrderKafkaPublisher(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    public void send(String tenantId, String orderId, String json) {
        String kafkaKey = tenantId + ":" + orderId;
        kafka.send("order-events", kafkaKey, json);
    }
}
~~~

With a key-based Kafka partitioner and a **stable topic partition count**, records sharing a key generally land in the same Kafka partition, enabling log-ordered consumption when consumer concurrency/offsets are configured accordingly. Still:

- Increasing topic partitions or changing partitioners can alter key→partition mapping.
- A consumer executing asynchronously can scramble side-effect order even when the log is ordered.
- Cassandra does not use the Kafka partition index as a token or partition key.
- A successful Kafka send does not confirm Cassandra has persisted anything.

When a Kafka inbound adapter populates `KafkaHeaders.KEY`/`RECEIVED_PARTITION` in Spring Message headers, **`CassandraMessageHandler` does not automatically extract those headers as keys**. A transformer must build `OrderTimelineKey` from the validated payload and context.

### 13.2. JMS: message groups have a different scope

If a JMS broker supports message grouping (e.g., certain ActiveMQ implementations), producers can set `JMSXGroupID` to a business group key:

~~~java
// Fragment using a configured JmsTemplate.
jmsTemplate.convertAndSend("orders.events.in", jsonBody, message -> {
    message.setStringProperty(
            "JMSXGroupID", tenantId + ":" + orderId);
    return message;
});
~~~

`JMSXGroupID` is a JMSX property used by some providers for **message groups**. Group-to-consumer assignment, failover, and ordering policies are **provider-specific** and must be tested on your actual broker. Never assume all JMS brokers share one policy or that Cassandra reads `JMSXGroupID` to pick partitions.

### 13.3. Choosing Kafka/JMS keys by aggregate vs by event?

| Message key | Advantage | Trade-off |
|---|---|---|
| `eventId` | Relatively even record distribution | Events for the same order can be processed concurrently out of business order |
| `orderId` (with tenant) | Events for the same aggregate stay in one broker partition/group | One ultra-hot order can cause skew |
| `tenantId` | Simple when tenants have balanced workloads | Large tenants create hot broker partitions/consumers |
| `tenantId + bucketDay` | Splits load by day | Breaks ordering continuity across day boundaries; large tenants can still be hot within a day |

**Broker partitioning and Cassandra partitioning must be analyzed separately:** Kafka typically optimizes consumption ordering and concurrency; Cassandra optimizes query performance, data placement, and partition size. When both are needed, share an event contract with dedicated mappers for each system.

## 14. Ordering: clustering order is not message processing order

Three distinct kinds of "order":

1. **Broker log/group ordering:** Kafka partitions or JMS message groups define delivery order per provider semantics.
2. **Processing order:** consumer threads, async channels, retries, and downstream callbacks can complete **out of receipt order**.
3. **Cassandra clustering order:** rows **already written** are sorted by clustering columns within a partition.

~~~mermaid
sequenceDiagram
    participant Broker as Kafka/JMS
    participant C1 as Consumer 1
    participant C2 as Consumer 2
    participant DB as Cassandra timeline
    Broker->>C1: event v1, occurredAt 03:00
    Broker->>C2: event v2, occurredAt 03:01
    C2->>DB: INSERT event v2
    DB-->>C2: Success
    C1->>DB: INSERT event v1 (late retry)
    DB-->>C1: Success
    Note over DB: Query can return v2 before v1 per clustering
    Note over DB: Yet state side effects in another handler may already be out of order
~~~

If the goal is purely **event history**, storing both v1 and v2 with clustering timestamps/versions may suffice. If the goal is **updating current order state**, enforce **`aggregateVersion`** or conditional writes; never rely on Cassandra `INSERT` arrival order.

### 14.1. Why is event ID a useful tie-breaker?

Two events can share the same `occurredAt` down to the millisecond—for example, due to timestamp rounding. If the full PK were only `((tenant_id, order_id, month), occurred_at)`, two events with the same timestamp would **collide on row key**. Adding `event_id` as the next clustering column separates them. Even then:

- Event ID must stay stable across retries.
- Timestamp must be the normalized event timestamp, never current time during consumer replay.
- When both timestamp and ID match yet payloads differ, that is a **conflicting duplicate** that must be detected.

### 14.2. Version guards on a state table

Example table for **current state**, distinct from the timeline table:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_current_state (
    tenant_id text,
    order_id text,
    version bigint,
    state text,
    last_event_id text,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

A conditional update:

~~~sql
UPDATE order_current_state
SET version = ?, state = ?, last_event_id = ?
WHERE tenant_id = ? AND order_id = ?
IF version = ?;
~~~

The application accepts event v3 only when stored version equals v2 per contract. For brand-new rows, use **conditional initialization `IF NOT EXISTS`** or an equivalent strategy. Inspect `[applied]` from the lightweight transaction (LWT) to distinguish stale versions. LWT incurs higher cost and does not atomically span a state table and a differently partitioned timeline table.

**Never rely purely on client `occurredAt` to settle every race**: producer clocks can skew. A monotonically increasing `aggregateVersion` managed by an authority usually suits business state better, paired with policies for duplicates and out-of-order events.

### 14.3. Broker grouping and Cassandra keys do not replace version checks

Even when Kafka puts all messages for an `orderId` into one partition, a consumer can still:

- Dispatch two asynchronous Cassandra writes concurrently.
- Retry a delayed event after a newer event already succeeded.
- Replay an older offset after a crash.
- Replay from a DLQ days later.

Thus, whenever business rules forbid state regression, **database/domain-layer protection** remains mandatory.

## 15. Retries, redeliveries, and stable keys

Cassandra and JMS/Kafka are separate resources. No Spring Integration annotation creates an atomic distributed transaction between broker acknowledgments and Cassandra writes.

### 15.1. Lifecycle of an event through failure

~~~mermaid
flowchart TD
    A["Broker deliver eventId=evt-5001"] --> B["Validate event contract"]
    B --> C["Compute bucketMonth from UTC occurredAt"]
    C --> D["Build deterministic OrderTimelineKey"]
    D --> E["Cassandra outbound handler"]
    E --> F{"Write completed?"}
    F -->|"Yes"| G["Commit/ack source per policy"]
    F -->|"Error or uncertain outcome"| H["Bounded retry/redelivery"]
    H --> B
    H --> I{"Permanent error or over threshold?"}
    I -->|"Yes"| J["DLQ/quarantine + investigate"]
~~~

In production, actual error/retry flow also depends on sync/async channels and acknowledgment modes. The diagram shows the **architectural target**, not an out-of-the-box default that automatically moves messages from Cassandra into a JMS DLQ.

### 15.2. Two unavoidable failure windows

| Window | What can happen | Protection |
|---|---|---|
| Cassandra write completes → JVM crashes before JMS commit/Kafka offset | Broker redelivers the same event | Deterministic key, idempotent write |
| Broker acks/commits before async Cassandra completion | Cassandra fails yet source won't automatically redeliver | Await completion before ack or use durable handoff/independent recovery |
| Cassandra times out after server wrote | Retry runs again even though row exists | Same key, read-back/conditional semantics |
| Event arrives months late | Bucket uses processing time if coded wrong | Derive bucket from the event's `occurredAt` |
| Backfill from archive generates new event IDs | Duplicate business event under a new key | Preserve original `eventId` or audited ID mapping |

### 15.3. `async(false)` exposes errors, not exactly-once

With a JMS message-driven inbound adapter using a transacted session, `DirectChannel`, and an `async(false)` Cassandra handler, certain synchronous Cassandra errors can propagate back to the listener for rollback. However, if Cassandra already wrote and the JMS commit fails, the event can still be redelivered.

When using `ExecutorChannel`, an in-memory `QueueChannel`, or the default async Cassandra handler, the JMS listener can finish before the Cassandra write actually completes. **An error occurring after source commit cannot roll back an already-committed JMS receipt.**

### 15.4. `errorChannel`, DLQ, and quarantine are distinct mechanisms

- **Spring `errorChannel`:** carries `ErrorMessage` inside Spring Integration, not a JMS DLQ.
- **JMS broker DLQ:** broker/provider moves undeliverable messages after its configured redelivery policy.
- **Kafka dead-letter topic:** application/handler or retry-topic infrastructure forwards records to another topic.
- **Application quarantine:** durable store for investigating data-contract violations or conflicting event IDs.

If an error handler catches an exception and returns normally, the inbound listener may commit per its config even though Cassandra never wrote. To trigger rollback/redelivery, the exception **must actually reach the acknowledgment boundary** rather than just being logged.

### 15.5. Two distinct kinds of idempotency

**Idempotent timeline INSERT:** identical full PK and identical values can be re-sent safely; Cassandra upserts normally without creating a second row. Yet if `occurredAt` or the bucket changes, the full PK changes and creates a duplicate record.

**Global deduplication by eventId:** an `event_by_id(event_id PRIMARY KEY, ...)` table helps look up or claim events. However, claiming via `IF NOT EXISTS` in table A followed by writing timeline in table B is **not an atomic cross-table transaction**. Crashing between claim and timeline write requires a **reconciler/replay** to backfill missing rows. Never build an unrecovered "idempotency gate" that blindly skips retries as if both writes always committed together.

### 15.6. When should LWT be used?

`IF NOT EXISTS` or `IF version = ...` fits when strict compare-and-set is needed within **Cassandra's supported scope**, such as guarding `order_current_state` by aggregate version. Still:

- LWT is slower and costlier than regular writes.
- It does not solve atomicity with JMS/Kafka sources.
- It does not update two differently partitioned tables in isolation like an SQL transaction.
- On response timeouts, uncertain states must be resolved by key/condition checks.

Do not enable LWT for every event simply to "be safe": define your business invariants and benchmark first.

## 16. Migration strategy when changing a partition key

A common mistake is discovering a hot partition, **changing a `@PrimaryKeyColumn` annotation or editing CQL DDL**, and expecting Cassandra to redistribute existing data automatically. A Cassandra table's primary key **cannot be transformed arbitrarily with `UPDATE`**. A safe strategy usually requires **a new table + backfill + controlled dual-read/dual-write**.

### 16.1. Example migrating from per-tenant/day to per-order/month

~~~text
Old schema:
  events_by_tenant_day
  partition key = (tenant_id, bucket_day)

New schema:
  events_by_order_month
  partition key = (tenant_id, order_id, bucket_month)
~~~

Runbook:

1. **Profile query workloads and partition metrics:** identify why the old schema runs hot and which queries change.
2. **Create the new table** with appropriate CQL schema, replication, and TTL without dropping the old table.
3. **Deploy the new transformer** computing deterministic keys from source records; version bucket conventions.
4. **Backfill in small batches** from old data/archive/source-of-truth; throttle concurrency and preserve business `eventId`/`occurredAt`.
5. **Dual-write or CDC/replay** from a reliable source; monitor partial failures where one write succeeds and the other fails.
6. **Shadow-read and reconcile** event counts, conflicts, key boundaries, query p95, and new partitions.
7. **Shift read traffic** gradually by tenant/percentage with a rollback plan.
8. **Stop old writes** once data is consistent and recovery is verified, then archive/drop per retention policy.

### 16.2. Never change hash/bucket schemes silently

Suppose an older producer computed buckets in `Asia/Ho_Chi_Minh` while a new consumer uses UTC. Events near day/month boundaries can shift partitions upon replay. Migrations must **document timezone/version rules**, test boundary timestamps, and dual-read old key schemes during transition if needed.

Likewise, changing shard counts from 16 to 32 alters `hash(eventId) % shards` for many events; version the scheme and plan backfills/read fallbacks. **The partition key is part of the durable data contract**, not merely a code optimization hint.

### 16.3. Avoid creating a hot migration job

Backfilling five years of events simultaneously at thousands of Cassandra writes/s into one hot partition can breach production SLAs. Shard backfill work across partition/key ranges, cap retries, halt if latency/error rates cross thresholds, and throttle during cluster compaction/repair.

## 17. Observability: spotting hot partitions instead of watching CPU alone

When throughput drops, do not simply add Spring Integration threads. Measure end-to-end from the message source to the Cassandra cluster.

| Metric/observation | Source | Signal to investigate |
|---|---|---|
| JMS queue depth / Kafka consumer lag | Broker | Backlog growing as Cassandra slows |
| Message ingress rate, handler success/error | Spring Integration | Messages arriving faster than writes complete |
| Cassandra write latency p50/p95/p99 | Driver/cluster | p99 spiking even while p50 looks normal |
| In-flight Cassandra requests | Driver | Too many pending requests; missing backpressure |
| Per-node request distribution | Driver/cluster | One or a few nodes carrying disproportionate load |
| Hot partitions / top partitions | Cassandra diagnostics | One partition key absorbing most reads/writes |
| Estimated/maximum partition sizes | Cassandra table stats | Wide partitions or skew |
| SSTables, compaction, tombstones | Cluster | TTL/deletes or repairs causing read pressure |
| Timeout/Unavailable/Overloaded | Driver exceptions | Cluster losing capacity to respond |
| Duplicate `eventId`, conflicting payloads | Business metrics | Redeliveries or contract errors |
| Buckets/shards per tenant, p99 rows/partition | Application analytics | Insufficient bucketing or skewed shard function |
| Backfill write rate and mismatch counts | Migration tool | Migration overloading cluster or missing data |

### 17.1. Diagnostic tools on real Cassandra

In test environments or under an approved runbook, use:

- `nodetool tablestats` to inspect table statistics, estimated partition sizes, and read/write metrics (exact fields vary by Cassandra version).
- Hot-partition/top-key tools or sampling/tracing supported by your Cassandra version; avoid running unbounded full-table scans in production.
- `TRACING ON` in `cqlsh` for test queries to observe coordinator/replica routing; tracing adds overhead, so never leave it enabled broadly.
- Driver metrics for request latency, in-flight requests, connection saturation, timeouts, and retries.
- Application logs recording `eventId`, **sanitized logical partition-key fields**, operation type, and exception class; avoid logging sensitive payloads.

Never run `SELECT COUNT(*) FROM huge_table` as a "quick partition count"; it triggers an expensive scan. When dataset size metrics are needed, rely on table stats or dedicated summary tables.

### 17.2. Measure shard distribution before deploying

Suppose you pick 16 shards by `eventId`. In a test environment:

1. Generate a set of event IDs matching production distribution.
2. Compute `StableShards.shard16(eventId)` and count events per shard.
3. Inspect min/max/p95 events/shard, not only the average.
4. Test a high-burst tenant alongside small tenants.
5. Measure latency and Cassandra coordinator load under real writes, not just offline hash distribution.

A hash function that looks balanced over 1 million random UUIDs **does not guarantee** balanced real traffic if event IDs follow structured prefixes or traffic concentrates on other keys.

### 17.3. Useful alerts

Alert on steadily rising source backlogs, Cassandra p99 write latency breaching SLAs, single-partition hotspots exceeding benchmark thresholds, timeout/error bursts, rising quarantine counts, and abnormal replay/duplicate rates. An alert watching only cluster-wide average Cassandra CPU can miss **a single hot partition or node**.

## 18. Common design mistakes

| Issue | Symptom | Cause | Fix |
|---|---|---|---|
| Using `tenantId` alone as partition key | Large tenants time out; huge partitions | High cardinality/skew | Add business discriminator and bucket/shard per query |
| Using random `eventId` as PK for all tables | Writes spread well, order history queries fail | Key doesn't match query | Add order/time-indexed table alongside event lookup |
| Making `orderId` clustering instead of partition component | One tenant's orders cram into one partition | Missing inner parens in CQL `PRIMARY KEY` | Use double parentheses for composite partition key |
| Adding clustering `occurredAt` to fix hot partition | Partition stays hot | Clustering does not alter token | Bucket/shard the partition key |
| Bucketing by consumer processing date | Replays on a new day create duplicate rows | Non-deterministic key | Bucket from event timestamp in UTC |
| Unversioned buckets | Old/new data land in different partitions | Granularity/timezone changed | Versioned migration + backfill |
| Hashing shard from `UUID.randomUUID()` at consumer | Same event hits different shards | Key changes across retries | Hash stable `eventId` |
| Changing 16 shards to 32 without migration | Reads miss old data | Modulo changes mapping | Version scheme, dual-read/backfill |
| Using Kafka partition index as Cassandra shard | Adding topic partitions shuffles data | Confusing two partitioners | Stable app-level shard function |
| Using unverified Spring `tenantId` header | Cross-tenant write or unauthorized read | Client-asserted header | Authorize + validate payload/context |
| Querying only `tenant_id` on composite PK | CQL fails or scans expensively | Missing partition columns | Dedicated table per query pattern |
| Querying full timeline from one bucket | Missing adjacent months | Time bucketing splits partitions | Bounded fan-out across buckets |
| Two events at same timestamp overwrite | Lost event with identical clustering key | Missing tie-breaker | Add `event_id` to clustering |
| Ordered Cassandra timeline yet corrupted state | Old event overwrites newer state | Clustering order ≠ processing order | Aggregate version/conditional state update |
| JMS source acks before Cassandra write | Lost redelivery on DB failure | Unclear async boundary | Sync completion or durable handoff |
| Redelivery generates new `eventId` | One event becomes two rows | Consumer mints new ID | Preserve original event ID |
| Cassandra LWT `false` treated as unconditional success | Conflicting payload silently ignored | Existing row not checked | Separate benign duplicate vs conflict |
| Writing two Cassandra tables treated as ACID | One table missing data after crash | No cross-partition SQL transaction | Repair/reconciliation/idempotent replay |
| Logging full partition keys/sensitive payloads | Sensitive data exposed in logs | Missing masking/ACLs | Minimal audit/tracing; keep logs safe |
| Raising consumer concurrency to cure DB hotspot | More timeouts and larger backlog | Node/partition already saturated | Fix data model and bound in-flight requests |

### 18.1. Partition-key design review checklist

1. **Query-first:** list every mandatory query with latency and result-size bounds.
2. **Partition identity:** write exact CQL `PRIMARY KEY` with inner parentheses and field order.
3. **Data distribution:** model top tenants/orders and average/p95/p99 partition sizes.
4. **Bounded partitions:** verify buckets/shards, TTL, and retention where needed.
5. **Deterministic keys:** do retries and backfills produce the exact same key?
6. **Ordering:** clustering for timelines vs version guards for current state?
7. **Security:** verified `tenantId`, no secrets in keys, no user input concatenated into table names.
8. **Mapping:** do `@PrimaryKeyClass`/`@PrimaryKeyColumn` match the CQL schema?
9. **Flow:** does the transformer run before the adapter, producing the right entity or `BoundStatement`?
10. **Ack/error:** when does the source commit, and how are DB timeouts recovered?
11. **Observability:** measure hot partitions, p99 latency, backlog, and duplicate/conflict counts.
12. **Migration:** if bucketing/sharding/PK changes, is there a backfill/dual-read/rollback plan?

## 19. Hands-on lab: from message flow to safe partition keys

**Environment:** Java 17+, compatible Spring Integration Cassandra 6+, Spring Data Cassandra reactive, a Cassandra test cluster or container, plus a test JMS/Kafka broker for advanced parts. Never run destructive or backfill load tests in production.

### Part A — Comparing three PRIMARY KEY definitions

1. Create three test tables with identical columns but different PK definitions:

~~~sql
CREATE TABLE shop_integration.lab_by_tenant (
    tenant_id text, order_id text, event_id text, payload text,
    PRIMARY KEY (tenant_id, order_id, event_id)
);

CREATE TABLE shop_integration.lab_by_tenant_order (
    tenant_id text, order_id text, event_id text, payload text,
    PRIMARY KEY ((tenant_id, order_id), event_id)
);

CREATE TABLE shop_integration.lab_by_event (
    event_id text PRIMARY KEY, tenant_id text, order_id text, payload text
);
~~~

2. Write 500 events across 5 tenants, with one tenant generating 80% of the workload.
3. Use `DESCRIBE TABLE` and CQL `token(...)` on the written rows to compare partition keys.
4. Query by tenant+order and by `eventId`. Identify which table serves each query directly and which needs a separate lookup.
5. Explain why **many clustering rows do not split a single partition across multiple tokens**.

**PASS:** Accurately identifies each table's partition key and its query/hotspot implications.

### Part B — Bucketing across UTC month boundaries

1. Call `PartitionBuckets.utcMonth(...)` with:

~~~text
2026-11-30T23:59:59Z -> 2026-11
2026-12-01T00:00:00Z -> 2026-12
2026-12-01T07:00:00+07:00 -> 2026-12 (same Instant 00:00Z)
~~~

2. Create one `OrderEvent` at the end of November and one at the start of December.
3. Run `TimelineMapper.toEntity(...)` and verify `bucketMonth`.
4. Simulate a replay in a later month while preserving the original `occurredAt`; the key must remain **unchanged**.
5. Intentionally bucket using `LocalDate.now()` in a negative test; demonstrate the duplicate risk.

**PASS:** The same event always produces the same UTC-based partition key.

### Part C — Mapping a composite key

1. Create `events_by_order_month` from section 3.
2. Define `OrderTimelineKey` with `@PrimaryKeyClass`, three `PARTITIONED` fields, and two `CLUSTERED` fields.
3. Use `OrderTimelineEvent` annotated with `@PrimaryKey` and `@Table`.
4. Send an entity through `ReactiveCassandraOperations` or the outbound adapter.
5. Query with **all three partition-key fields** and verify the row matches `event_id`.
6. Check `equals/hashCode` on two key objects with identical values; they must match under Java identity semantics.

**PASS:** Annotations match CQL positions, order, and types; Spring Data writes to the expected partition.

### Part D — Java DSL and JSON contract

1. Configure `orderEventsToCassandra` from section 10.
2. Transform `OrderPaid` JSON into `OrderEvent` with `Instant occurredAt`; validate the payload.
3. Send via `validatedOrderEvents` and query back from Cassandra.
4. Send JSON missing `orderId` and verify the message is rejected **before the CQL write**.
5. Send a `tenantId` header conflicting with the authenticated context in a test; the endpoint must raise an authorization/contract error instead of writing to another tenant.
6. Replace `async(false)` with the async default and measure when `send()` returns vs when Cassandra finishes writing.

**PASS:** No rows with blank/`unknown` keys, and the caller understands completion differences.

### Part E — Time bucketing and querying multiple buckets

1. Write events for one order spanning three consecutive months.
2. Query each `bucket_month` separately with `LIMIT` and appropriate paging.
3. Merge results ordered by `occurredAt DESC, eventId ASC`.
4. Confirm a single-month query does **not** return events from other months.
5. Intentionally query with `tenant_id` alone and record the error or scan cost; fix with a proper key/table query.

**PASS:** Multi-month timelines return complete rows without full-table scans.

### Part F — Sharding and hotspots

1. Run `StableShards.shard16` on 100,000 random event IDs and a production-like ID distribution.
2. Count events per shard and inspect skew.
3. Create `events_by_tenant_day_shard` with `shard` in the partition key.
4. Write high-volume traffic for one large tenant on the same day; compare p95 write latency and node distribution against unsharded `events_by_tenant_day`.
5. Query the full day across all 16 shards using **bounded fan-out**, merging by sort key.
6. Test switching the shard count to 32 in an experimental branch; confirm old data cannot be read accurately without a migration/compatibility layer.

**PASS:** Accurately explains write-distribution vs read fan-out trade-offs and hash stability.

### Part G — Kafka/JMS grouping and Cassandra keys

1. Have a Kafka producer send three events sharing a `tenantId + orderId` key; inspect the chosen broker partition.
2. Increase topic partitions **on the test broker** and observe how key mapping can shift per partitioner/version.
3. With a group-capable JMS broker, send events sharing `JMSXGroupID` and observe consumer assignment.
4. Route events from both sources through the transformer into `OrderTimelineKey`; verify the same business event generates the same Cassandra key regardless of broker metadata.
5. Enable async processing in the flow to see completion order diverge from delivery order.

**PASS:** Never confuses Kafka partitions/JMS groups with Cassandra tokens/partitions.

### Part H — Redelivery, version guards, and migration

1. Wire a transacted JMS listener → `DirectChannel` → sync Cassandra handler.
2. Let the Cassandra write succeed, simulate a crash before JMS commit, and redeliver the event.
3. Verify `eventId`/`occurredAt`/`bucketMonth` remain unchanged and no duplicate timeline row is created.
4. Send event v2 followed by v1; verify how timeline clustering differs from protecting current state.
5. Implement conditional update `IF version = ...` on `order_current_state` and distinguish `applied=true/false`.
6. Draft a migration plan from the old schema to the new schema covering backfill, dual-read, and load throttling.

**PASS:** Has an idempotent redelivery strategy, does not assume atomic Cassandra+JMS commits, and knows how to change a partition key without data loss.

### Final test matrix

| Case | Required outcome |
|---|---|
| Composite partition key | CQL and annotation mapping align |
| Clustering | Rows ordered within one partition; processing order not inferred |
| UTC bucket | Replaying the same event selects the exact original bucket |
| Shard function | Deterministic hash with a versioning strategy for changes |
| Query-first schema | Queries supply full partition columns |
| Kafka/JMS | Broker keys do not auto-populate Cassandra keys |
| Cassandra adapter | Entity transformed before writing |
| Cassandra gateway | Named parameters bind message fields to the right key |
| Duplicate event | Same full PK does not spawn a new row from current time |
| LWT | Condition checked; `applied=false` not confused with system error |
| Async boundary | Error/ack semantics properly observed |
| Backpressure | No unbounded fan-out/retries when cluster slows |
| Migration | Backfill/reconciliation and rollback plan ready |
| Security | Tenant key verified; untrusted client keys rejected |

**Partition placement, token-aware routing, hotspots, LWT, and timeouts must be tested against real Cassandra or test containers.** Mocking `ReactiveCassandraOperations` only confirms API calls; it cannot verify token distribution, replication, consistency, or partition placement after failover.

## 20. Self-assessment questions

1. How does a Cassandra partition key differ from the full primary key and clustering columns?
2. How does `PRIMARY KEY (tenant_id, order_id, event_id)` differ from `PRIMARY KEY ((tenant_id, order_id), event_id)`?
3. Why are two rows sharing a partition key normally stored by the same set of replicas?
4. Which part of the primary key does Cassandra's Murmur3 token hash?
5. Do a Kafka record key and a Cassandra partition key automatically target the same node/partition when both use `orderId`?
6. Does `JMSXGroupID` automatically become the Cassandra partition key?
7. Why is query-first modeling more critical in Cassandra than traditional RDBMS normalization?
8. When is `eventId` a suitable partition key, and when does it make order-based queries difficult?
9. Why can `tenantId` alone create a hot partition for large tenants?
10. Does adding clustering column `occurredAt` relieve a hot partition caused by a single tenant?
11. Why does time bucketing bound partition size without spreading writes within a single day?
12. How does UTC bucketing differ from bucketing with the JVM's default timezone?
13. Why must consumers never compute buckets with `LocalDate.now()` for replayed events?
14. If one partition contains 500,000 rows under a single partition key, is it automatically split across 500,000 tokens?
15. What are the benefits and trade-offs of adding `shard` to a composite partition key?
16. If the shard count changes from 16 to 32, how must historical data be handled?
17. When sharding by `eventId`, are events for the same order still guaranteed to live in one Cassandra partition?
18. What are `@PrimaryKeyClass` and `@PrimaryKeyColumn(type=PARTITIONED/CLUSTERED)` used for?
19. Why must `equals/hashCode` on a composite key class be complete and consistent?
20. Why normalize `Instant` to millisecond precision when the CQL column is `timestamp`?
21. With the Cassandra outbound adapter, do Spring message headers automatically map to partition keys?
22. Why should the payload for `Type.INSERT` be a `@Table` entity instead of a raw JSON `String`?
23. When should you choose the Cassandra outbound gateway over the outbound channel adapter?
24. Which two mechanisms transfer data in `.query(...).parameter("tenantId","payload.tenantId")`?
25. Why isn't `WHERE tenant_id = ?` equivalent to querying a three-column composite partition key?
26. When reading a three-month timeline, why use bounded fan-out and merging?
27. Does clustering order guarantee business state updates occur in event order?
28. How do `aggregateVersion` and conditional Cassandra updates protect current state?
29. Why must redelivering the same event produce the **exact same full PK**, not just the same `tenantId`?
30. Why doesn't an idempotency claim in table A followed by a write to table B form a cross-table ACID transaction?
31. What happens if a JMS source commits before an async Cassandra write fails?
32. Does `errorChannel` automatically trigger Cassandra retries or a JMS DLQ?
33. Why can't you simply edit `@PrimaryKeyColumn` to re-partition already persisted data?
34. Which metrics detect a hot partition even when cluster-wide average CPU looks modest?
35. What minimum steps belong in a partition-key migration plan?

## 21. Official references

- [Apache Cassandra — Data Modeling Introduction](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): query-first modeling, partition size, redundancy, and trade-offs.
- [Apache Cassandra — Logical Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/data-modeling_logical.html): designing tables from queries and choosing partition/clustering keys.
- [Apache Cassandra — Evaluating and Refining Data Models](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/data-modeling_refining.html): bucketing, evaluating partition size, and refining schemas.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html): `PRIMARY KEY`, composite partition keys, clustering order, and token/placement semantics.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `PrimaryKeyType.PARTITIONED`, `CLUSTERED`, and entity identity.
- [Spring Data Cassandra — PrimaryKeyColumn Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/mapping/PrimaryKeyColumn.html): `ordinal`, `type`, and `ordering`.
- [Spring Data Cassandra — Reactive Cassandra](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCassandraOperations`, reactive execution, and error handling.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, outbound channel adapter/gateway, `query`, `parameter`, and `statementFunction`.
- [Spring Integration — Cassandra DSL Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/Cassandra.html): `outboundChannelAdapter(...)` and `outboundGateway(...)` factories.
- [Apache Cassandra Java Driver — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): bind values, routing metadata, preparation/repreparation.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): Kafka record keys/partitions/consumer semantics compared with Cassandra keys.
- [ActiveMQ Classic — Message Groups](https://activemq.apache.org/components/classic/documentation/message-groups): `JMSXGroupID` and broker-specific message grouping.

**Key takeaway:** Cassandra's **partition key** governs **partitions, tokens, and replica placement**, while **clustering keys** sort rows within a partition. In Spring Integration, message headers, Kafka keys, and JMS groups **do not automatically become Cassandra partition keys**: transformers must build entities/statements holding every CQL schema field. Good design starts from **query patterns**, bounds **skew, partition size, and buckets/shards**, generates **deterministic keys across retries/replays**, and separates **clustering order from business processing order**. Changing a partition key requires real migration/backfill and testing—never merely editing an annotation.





