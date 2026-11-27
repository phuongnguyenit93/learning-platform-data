# Routing Keys and Token-Aware Routing Conditions in the Apache Cassandra Java Driver

## 1. Routing a Cassandra query: where does the problem lie?

In Apache Cassandra, **wide-column** data is distributed across nodes based on the **partition key**. When a Java application runs CQL, a **coordinator** node receives the request and interacts with the **replicas** holding the relevant partition. Replication factor, datacenter, rack, and consistency level govern which responses are needed for the request to succeed.

For a `SELECT` specifying the exact partition key, the Java Driver can use the **routing key** to compute the **token**, consult the cluster's **token map**, and **prefer a node holding the data as coordinator**. This is the foundation of *token-aware routing*.

Objectives of this lesson in the **Query Execution from Java** chapter, module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**:

1. Distinguish **partition key**, **routing key**, **token**, **replica**, and **coordinator**.
2. Understand the path from bound CQL values to routing key and token.
3. Identify the **conditions for Java Driver 4.x to perform token-aware routing automatically**.
4. Explain queries that **lack a single routing key**, such as multi-partition queries, token-range scans, or queries missing key components.
5. Use `PreparedStatement`, `BoundStatement`, and execution info to diagnose routing.
6. Understand the relationship between token-aware routing, **LOCAL_QUORUM**, multi-DC deployments, topology changes, and replica load.
7. Design tests, metrics, and workflows to investigate p99 spikes or hotspots without assuming every query automatically hits an optimal replica directly.

**Version note:** Java examples use **Apache Cassandra Java Driver 4.x** with the `com.datastax.oss.driver.api.*` packages. Driver 3.x uses different packages and load-balancing configuration; never apply legacy `TokenAwarePolicy` settings mechanically to 4.x.

## 2. Five concepts you must keep separate

| Concept | Meaning | Do not confuse with |
|---|---|---|
| **Partition key** | One or more CQL columns forming the partition component of the primary key | Clustering key or full primary key |
| **Routing key** | Encoded **byte sequence** representing the partition key values for a request | Table name, raw UUID string, or numeric token |
| **Token** | Value computed by the **partitioner** from the routing key to locate a position on the token ring | IP address or ID of a single replica |
| **Replica** | Node holding a copy of the partition per keyspace replication strategy and topology | Always being the coordinator for every query |
| **Coordinator** | Node receiving and coordinating a CQL request across required replicas | Necessarily owning that partition |

Logical flow diagram:

~~~mermaid
flowchart LR
    A["CQL: WHERE device_id = ? AND event_day = ?"] --> B["Java Driver: bind UUID + date"]
    B --> C["Routing key: binary partition-key components"]
    C --> D["Partitioner: token"]
    D --> E["Token map + RF + DC/rack"]
    E --> F["Partition replica set"]
    F --> G["Load balancing prefers suitable coordinator"]
    G --> H["Coordinator sends request to replicas per CL"]
~~~

This diagram shows the **client-side routing decision flow**; Cassandra servers still verify tokens, replica placement, and consistency requirements during execution. A client-side routing key is **a hint for coordinator selection**, not authority for the client to dictate where data lives.

### 2.1. Distinguishing primary key and partition key

Given a table with key:

~~~cql
PRIMARY KEY ((tenant_id, device_id, event_day), event_time)
~~~

then:

- Partition key: **`tenant_id`, `device_id`, `event_day`**.
- Clustering key: **`event_time`**.
- Full primary key: all four columns.
- Routing key: encodes the **three partition key values**, excluding `event_time`.
- Every row sharing `(tenant_id, device_id, event_day)` lives in the **same logical partition**, even across thousands of distinct `event_time` values.

Consequently, changing `event_time` in `WHERE` does not alter the token if all three partition key values stay the same. Conversely, changing `event_day` typically changes the routing key and token even when `device_id` is unchanged.

## 3. Practice dataset: telemetry table by tenant, device, and day

Assume lab datacenter `dc1` with enough nodes for RF=3:

~~~cql
-- Create only in an authorized lab environment.
CREATE KEYSPACE telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_lab.readings_by_tenant_device_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    PRIMARY KEY ((tenant_id, device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Sample writes:

~~~cql
INSERT INTO telemetry_lab.readings_by_tenant_device_day
(tenant_id, device_id, event_day, event_time, reading_value, status)
VALUES (
    22222222-2222-2222-2222-222222222222,
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6,
    'OK'
);

INSERT INTO telemetry_lab.readings_by_tenant_device_day
(tenant_id, device_id, event_day, event_time, reading_value, status)
VALUES (
    22222222-2222-2222-2222-222222222222,
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:29:00Z',
    24.1,
    'OK'
);
~~~

Both rows share the same partition key and go to the **same replica set**, since `event_time` is only a clustering key.

Matching query:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = 22222222-2222-2222-2222-222222222222
  AND device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

This query provides **all three partition key values** and targets one clear logical partition. It is the canonical case where the driver performs token-aware routing.

## 4. How is a routing key built?

### 4.1. Not concatenating three UUID/date strings

Partition key values are serialized by Cassandra according to **CQL types**. The Java Driver uses codecs to convert `UUID`, `LocalDate`, `String`, and other types into protocol-level byte representations.

For a **single-component** partition key like `device_id uuid`, the routing key corresponds to the encoded bytes of that UUID.

For a **composite** partition key like `(tenant_id, device_id, event_day)`, the routing key requires **composite encoding with per-component boundaries**, not raw concatenation of user-visible strings.

Conceptually:

~~~text
Partition values:
    tenant_id = UUID(...)
    device_id = UUID(...)
    event_day = LocalDate(...)

CQL codecs:
    tenant_id -> byte sequence A
    device_id -> byte sequence B
    event_day -> byte sequence C

Composite routing key:
    encoded component A + boundary metadata
    encoded component B + boundary metadata
    encoded component C + boundary metadata
~~~

The exact encoding follows Cassandra's composite partition key protocol rules. **Never write `tenant + ":" + device + ":" + day`** and hash it: that does not produce a valid Cassandra routing key.

### 4.2. Component order matters

`(tenant_id=A, device_id=B, event_day=C)` differs from `(tenant_id=A, device_id=C, event_day=B)`. Components must be encoded in the **exact partition key order defined in the schema**, not an arbitrary JSON or Map iteration order.

With prepared statements, the driver uses **statement and schema metadata** to know which bind marker maps to which partition key component. This is far safer and less error-prone than manually assembling routing keys from HTTP parameters.

### 4.3. A routing key is not tenant authorization

A valid routing key only indicates that the request can be routed to replicas holding that partition. It **does not prove the caller is authorized to read that partition**.

In multi-tenant applications, `tenant_id` must come from an **authenticated principal** or explicit authorization check; never accept an arbitrary `tenant_id` from a caller merely because Java bound it into a valid UUID.

## 5. How does a routing key become a token?

### 5.1. Role of the partitioner

The **partitioner** hashes routing key bytes into a **token**. Most modern Cassandra clusters use `Murmur3Partitioner`, producing signed 64-bit integer tokens. Other partitioners can exist depending on cluster version/configuration, so never hardcode a hash function or token range across environments.

Logical path:

~~~text
Serialized routing key (bytes)
       |
       v
Configured partitioner, e.g. Murmur3Partitioner
       |
       v
Token on the partition ring
       |
       v
Token ownership + replication strategy
       |
       v
Replica set for a specific keyspace
~~~

**A token is not a unique row key.** A token marks a position on the ring; different partition keys can hash to colliding tokens, and with vnodes a single node owns **multiple token ranges**.

### 5.2. A token is not a replica address

Illustrative example (not real tokens computed from the UUIDs above):

| Partition key | Hypothetical token | Consequence |
|---|---:|---|
| Tenant A / Device X / 21-11 | -7,100,000 | Maps to one region of the token ring |
| Tenant A / Device X / 22-11 | 4,300,000 | Can map to a different region/node |
| Tenant A / Device Y / 21-11 | 4,100,000 | May land near the previous row's token |

A token map **only identifies positions and nodes** when combined with a replication strategy and current topology. Never infer “positive tokens live on node B” or “smaller tokens mean older data”.

### 5.3. Local datacenter and replica placement

For a keyspace with `NetworkTopologyStrategy` and RF=3 in `dc1`, the token map combines with RF/topology to identify **three replicas** for that partition in `dc1`.

Querying the same token in a **keyspace with different replication settings** can yield a different replica set. Therefore routing decisions generally require all of:

- **Routing key or token**.
- **Routing keyspace**, to know which replication strategy/RF applies.
- **Token map, DC/rack, and node liveness** from metadata.
- The Java Driver's **load-balancing policy**.

**Never use a token while ignoring the keyspace.** A bare token alone cannot determine replica placement.

## 6. Token-aware routing in Java Driver 4.x

### 6.1. The coordinator selection problem

A query with a clear target partition sent to a **non-replica** coordinator still works:

~~~text
Java Client -> Coordinator N4 (does not hold partition)
                         |
                         +-> Replica N1
                         +-> Replica N2
                         +-> Replica N3
~~~

When the driver prefers a coordinator that is an eligible **replica**, extra inter-node forwarding hops can be avoided:

~~~text
Java Client -> Coordinator N2 (also a replica)
                         |
                         +-> Replica N1
                         +-> Replica N3
~~~

This is a **conditional benefit**, not a guarantee that all network hops disappear: consistency levels still require multiple replicas; speculative execution, replica health, DC routing, and other constraints still apply.

### 6.2. Java Driver 4.x builds token awareness into load balancing

In Java Driver 4.x, the default load-balancing policy combines **datacenter awareness** and **token awareness** using cluster metadata; applications do not need to copy Driver 3.x `TokenAwarePolicy` wrapping patterns.

When a valid routing key/token and routing keyspace are present, the policy can **prioritize matching replicas in the local datacenter** when building the query plan. If information is missing or metadata is not yet available, the driver falls back to another eligible node based on policy and connection state.

**Token awareness is a preference in coordinator selection, not a hard guarantee that every request always hits a replica.**

### 6.3. Contact points are not the target of every query

When building `CqlSession`, contact points are mainly used for **initial connection and cluster discovery**. Afterward, the driver opens connections to cluster nodes and uses the load-balancing query plan.

Configuring N1 as a contact point **does not mean every SELECT uses N1 as coordinator**.

~~~mermaid
flowchart TD
    A["Java CqlSession"] --> B["Contact points: cluster discovery"]
    B --> C["Metadata: token map, keyspace, nodes"]
    D["BoundStatement"] --> E{"Has routing key and keyspace?"}
    E -->|Yes| F["Prefer replicas by token and local DC"]
    E -->|No| G["Fallback query plan per policy"]
    C --> F
    C --> G
    F --> H["Selected coordinator"]
    G --> H
    H --> I["Replica read/write per CL"]
~~~

## 7. When does the driver automatically know the routing key?

The driver can best infer a routing key when a **prepared statement** supplies enough metadata to determine **a single partition key**.

### 7.1. Typical required conditions

1. The query is **prepared** against the cluster so metadata identifies partition key columns.
2. `WHERE` (or corresponding values in a mutation) specifies the **entire partition key**.
3. Every partition key component is a **concrete, validly bound value**, not an illegal `null`/unset.
4. The CQL query targets **one logical partition**, not arbitrary multiple partitions.
5. The driver knows the **routing keyspace** and token map to map the partition to replicas.
6. The active load-balancing policy **applies token-aware query planning** to that request.
7. Suitable nodes/replicas are available; otherwise the policy falls back.

These conditions form a **practical mental model**, not a promise that every CQL expression produces a routing key across every driver version. Complex expressions, named markers, batches, or uncommon syntax should be verified directly.

### 7.2. Canonical query: full partition key with markers

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT ?;
~~~

The first three markers belong to the partition key. The `LIMIT` marker **does not participate in the routing key**; changing `LIMIT` does not change the partition token.

### 7.3. You do not need to SELECT partition key columns for routing

This query still has the full partition key in `WHERE` even though its projection selects only two columns:

~~~cql
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

The driver derives the routing key from **bind markers and prepared metadata**; you do not need to add `tenant_id`, `device_id`, and `event_day` to the `SELECT` list just for routing.

### 7.4. Clustering ranges do not break single-partition routing

~~~cql
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT ?;
~~~

Because every partition key component uses equality and is bound, the query stays within **one partition**, even if the clustering range spans thousands of rows. `event_time` narrows the slice inside the partition without changing the routing token.

**Accurate routing does not mean a cheap query:** a wide partition, heavy tombstones, or overlapping SSTables still cause read amplification.

## 8. Java Driver 4.x: preparing, binding, and checking the routing key

### 8.1. Repository example with typed markers

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.nio.ByteBuffer;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

public final class RoutedReadingRepository {
    private final CqlSession session;
    private final PreparedStatement readQuery;

    public RoutedReadingRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.readQuery = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM telemetry_lab.readings_by_tenant_device_day " +
            "WHERE tenant_id = ? AND device_id = ? " +
            "AND event_day = ? LIMIT ?"
        );
    }

    public void read(UUID tenantId, UUID deviceId,
                     LocalDate day, int maxRows) {
        if (maxRows < 1 || maxRows > 100) {
            throw new IllegalArgumentException(
                "maxRows must be in [1, 100]");
        }

        BoundStatement statement = readQuery
            .bind(tenantId, deviceId, day, maxRows)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(Math.min(maxRows, 50));

        // Check PRESENCE only; never log raw bytes
        // because routing keys can expose partition IDs.
        ByteBuffer key = statement.getRoutingKey();
        if (key == null) {
            System.out.println(
                "No routing key inferred for this statement");
        } else {
            System.out.println(
                "Routing key available; bytes=" + key.remaining());
        }

        ResultSet rs = session.execute(statement);
        for (Row row : rs) {
            handle(row.getInstant("event_time"),
                   row.getDouble("reading_value"),
                   row.getString("status"));
        }
    }

    private void handle(java.time.Instant at,
                        double value, String status) {
        // Demo: bounded processing without accumulating every row.
    }
}
~~~

This snippet illustrates a synchronous request; in real services, create/close `CqlSession` with the service lifecycle, configure local DC/auth/TLS, and test against your actual driver version.

### 8.2. Key points explained

- The query template is `prepare`d **once** and reused.
- All three partition key values are bound with exact types `UUID`, `UUID`, and `LocalDate`.
- `maxRows` is bound yet **excluded from the routing key**.
- `getRoutingKey()` checks whether the statement has a usable routing key on the Java side.
- Returning `null` is a diagnostic signal, not necessarily proof that the query is invalid or rejected by servers.
- `LOCAL_QUORUM` governs replica response requirements, not “force the driver to always pick node X”.
- `setPageSize` sets the target per page, without replacing the total row cap of `LIMIT`.
- Code iterates `ResultSet` row by row rather than calling `all()` on large results.

### 8.3. Should you log routing keys or tokens?

**Never log raw routing key bytes** into production logs or metric labels: they can directly encode tenant IDs, UUIDs, or sensitive partition keys. Tokens can also reveal data distribution and inflate metric cardinality.

Instead, log **operation ID**, boolean `routing_key_present`, local DC, coordinator DC, and duration. When investigating a specific token, use restricted-access traces with strict retention and masking.

## 9. Observing the actual coordinator after execution

### 9.1. Reading ExecutionInfo

Java Driver 4.x exposes execution metadata on `ResultSet`. Example:

~~~java
import com.datastax.oss.driver.api.core.metadata.Node;
import com.datastax.oss.driver.api.core.cql.ResultSet;

ResultSet rs = session.execute(statement);
Node coordinator = rs.getExecutionInfo().getCoordinator();

if (coordinator != null) {
    System.out.println(
        "Coordinator DC=" + coordinator.getDatacenter() +
        ", rack=" + coordinator.getRack());
}
~~~

`Node` here is driver-side metadata. It tells you which coordinator handled the final response, **not** which replicas ACKed or every internal server network hop.

### 9.2. How to tell if the coordinator is a replica

Verify against:

1. The statement's **routing key/token**.
2. The **routing keyspace** and replication settings.
3. The current **token map** of the driver/cluster.
4. The replica set owning that token in that keyspace.
5. The coordinator recorded in `ExecutionInfo`.

This comparison is **point-in-time**, not static. Bootstrap, replace, decommission, RF changes, node outages, and topology shifts change replica sets and availability.

If a dashboard tracks a “token-aware hit” metric, **define the metric explicitly** and evaluate against live topology at execution time. Never assume Java Driver 4.x exports a built-in `token_aware_hit_rate` metric across every version.

### 9.3. Note on multiple attempts and speculative execution

A request may undergo retries or speculative execution depending on configuration. The final coordinator in `ExecutionInfo` does not necessarily reflect every attempt made.

For deeper diagnosis, use version-supported driver request tracking/instrumentation alongside retry and timeout metrics. **Never treat a single coordinator address as proof that every attempt went only to that node.**

## 10. Cases where the driver has no single routing key

### 10.1. Missing a partition key component

With PK `(tenant_id, device_id, event_day)`, the predicate below **does not specify a single partition**:

~~~cql
-- Illustrative WHERE INSUFFICIENT for the partition key;
-- on the example table, Cassandra can reject this query.
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?;
~~~

Without `event_day`, the driver cannot compute the partition's full routing key. Cassandra likewise rejects arbitrary SELECTs missing partition key components unless an appropriate access path exists.

**Never add `ALLOW FILTERING` just to “make the query run”** and expect single-partition token-aware routing. It triggers broad scans and heavy replica load.

### 10.2. Multi-partition queries with IN

Example on a table with a single-column partition key:

~~~cql
CREATE TABLE telemetry_lab.latest_by_device (
    device_id uuid PRIMARY KEY,
    last_seen timestamp
);
~~~

A multi-partition query:

~~~cql
SELECT device_id, last_seen
FROM telemetry_lab.latest_by_device
WHERE device_id IN (?, ?, ?);
~~~

Three `device_id` values can map to **three different tokens**, so no single routing key represents all three. Depending on version, Cassandra/the driver may optimize certain `IN` queries, yet **never assume the query is single-partition token-aware**.

When an application must read many devices, evaluate:

- Issuing prepared point reads per device with **bounded concurrency**.
- Designing a query strategy/data model tailored to the access pattern.
- Measuring coordinator/replica fan-out and network cost.
- Whether grouping data under a new partition key makes sense.

Never launch thousands of unbounded async futures just so each request gets its own routing key.

### 10.3. Lacking reliable prepared metadata

A `SimpleStatement` built by raw CQL string concatenation may lack enough metadata for the driver to infer a routing key. While some drivers/APIs accept manual routing hints, **do not rely on client parsers guessing arbitrary WHERE expressions**.

Prefer `PreparedStatement` and `BoundStatement` with typed markers. Calling **`prepare` on a string built with raw concatenated input** neither prevents injection nor guarantees accurate routing metadata.

### 10.4. Multi-partition, range-scan, or secondary-path queries

Queries that often lack a single routing key:

- **Token-range** scans.
- Queries without partition key restrictions.
- Queries over secondary indexes or search spanning multiple partitions.
- Multi-partition operations or multi-partition batches.
- Certain WHERE expressions/operations where prepared metadata cannot isolate a single PK.
- Schema/admin commands not tied to a regular logical partition.

Do not interpret `getRoutingKey() == null` as meaning all such queries are bugs. Some are valid for batch, analytics, or admin workflows, though their **cost and routing differ sharply from point reads**.

## 11. CQL `token()`: querying by ring position, not by time

### 11.1. What does `token(...)` represent?

CQL provides `token(...)` to inspect a partition key's token. For composite partition keys, pass **all partition key columns in exact schema order**:

~~~cql
-- Example reading the token of rows in a known partition.
SELECT tenant_id, device_id, event_day,
       token(tenant_id, device_id, event_day) AS partition_token,
       event_time
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = 22222222-2222-2222-2222-222222222222
  AND device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 5;
~~~

Every row with the same partition key shares the **exact same token**, regardless of differing clustering keys (`event_time`).

**A token is not a timestamp, row sequence, or business ordering key.** Never use tokens to fetch “the 20 latest events” or paginate chronologically.

### 11.2. Token-range scans

A token-range scan on a cluster using `Murmur3Partitioner`:

~~~cql
-- Illustrative only for RATE-LIMITED DATA EXPORT JOBS.
-- The two bounds below are sample integers in the signed 64-bit range.
SELECT tenant_id, device_id, event_day,
       event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE token(tenant_id, device_id, event_day) > -5000000000000000000
  AND token(tenant_id, device_id, event_day) <= 0;
~~~

This query can touch **many partitions across multiple nodes**. Its routing is not equivalent to a prepared SELECT with equality on the full partition key.

It is useful for **data exports, backfills, or token-range audits** when paired with capacity planning, bounded read concurrency, page sizes, checkpoints, and resource caps. Never use it as a default interactive API pattern.

### 11.3. Token boundaries must be managed carefully

When a job splits the ring into ranges:

- Pick a convention like **`(start, end]`** and apply it consistently.
- Avoid **gaps** between ranges or double-counting boundaries.
- Handle token ring **wrap-around** across min/max bounds.
- Match the cluster's actual partitioner instead of assuming Murmur3 everywhere.
- Watch for node/topology changes during multi-hour jobs.
- Never assume equal numeric token widths contain equal **bytes or partition counts**.
- Bound concurrent ranges against the **most heavily loaded node**, not just total workers.

### 11.4. Token-range scans vs keyset pagination

| Aspect | Token-range scan | Clustering-key keyset pagination |
|---|---|---|
| Splitting axis | Token/partition placement | Clustering order within a partition |
| Best use case | Export/backfill/parallel scan | UI “load more” by time/sort order |
| Spans multiple partitions? | Yes | Usually one partition or purpose-built set |
| Preserves business order? | No | Yes, when clustering schema supports it |
| Easy single-partition token awareness? | No | Yes, with full PK equality |
| Needs load limits? | Critically yes | Still yes, especially for wide partitions |

**Never use tokens as `OFFSET` or UI cursors.** Tokens solve data distribution, not chronological or business record ordering.

## 12. Manual routing tokens: benefits and risks

Some statement/driver APIs allow supplying an explicit **routing key or routing token hint** when the caller knows the exact target partition, such as in custom or query-builder statements.

This is an advanced technique; use it only when:

1. There is a concrete reason you cannot use a prepared statement with full PK.
2. Partition keys are encoded with **exact CQL types and component order**.
3. The **routing keyspace** is set accurately to match RF and replica placement.
4. The routing hint **matches the actual partition key in the statement**.
5. Lab tests verify coordinator selection and before/after latency.
6. A plan exists to remove hints if schema, partitioner, or routing logic changes.

**Never compute tokens using Java `hashCode()`, `UUID.hashCode()`, or ad-hoc MD5.** Cassandra tokens depend on the configured partitioner and CQL partition-key binary encoding.

### 12.1. A routing hint cannot fix a broken WHERE clause

Suppose a query has `WHERE device_id = A` while you attach a routing hint for partition B. The driver may pick a suboptimal coordinator; **the server still executes according to WHERE and cluster metadata**, rather than returning B's data for A.

A wrong hint typically **degrades performance**, adding extra hops and confusing diagnostics—it never fixes a missing partition key.

### 12.2. Never try to “pin all requests to one node”

Hardcoding a fixed routing key for all queries defeats token awareness, creates coordinator hotspots, and sends queries to nodes that do not hold the data.

If you truly need to **pin** an administrative operation to a specific node, that is separate from data routing keys. Never abuse token hints as a substitute for admin tooling or proper load balancing.

## 13. Token-aware routing, consistency level, and replica responses

### 13.1. Example with RF=3, LOCAL_QUORUM

Suppose partition P's token maps to replicas N1, N2, N3 in `dc1`.

~~~text
Java Driver picks coordinator N2 via token-aware routing
    |
    +-- N2 is a replica holding partition P
    +-- N2 communicates with N1 and N3
    +-- LOCAL_QUORUM requires responses matching
        the quorum for dc1's RF: 2/3
~~~

**Do not conclude only N2 receives mutations or only N2 serves reads.** The coordinator must still satisfy CL rules and Cassandra's read/write paths.

### 13.2. Token awareness does not alter CL

| Setting | What it governs | What it does NOT govern |
|---|---|---|
| Routing key/token | Identifies target partition to prefer replica coordinators | Does not increase/decrease RF |
| Token-aware load balancing | Prioritizes matching coordinators via replica metadata | Does not make data fresher |
| `LOCAL_ONE` | Response count required in local DC | Does not guarantee newest read in all cases |
| `LOCAL_QUORUM` | Quorum in local DC | Does not fix a missing routing key |
| `QUORUM` | Quorum across RF/request strategy | Does not pin a single “home node” |
| `EACH_QUORUM` (where supported) | Quorum in each DC | Does not make multi-partition scans cheap |

**Lowering CL to cut p99** weakens consistency guarantees; it is not “fixing token routing”. Keep those two decisions separate in Java service design.

### 13.3. Multi-DC

When a keyspace replicates across `dc1` and `dc2`, an app in `dc1` configures its **local datacenter** accordingly. The driver prefers local-DC replicas when routing metadata is valid.

If the local DC is misconfigured, connections and routing behave unexpectedly. Still, observing a coordinator in another DC **is not enough** to blame the routing key: check session config, load-balancing policy, node health, execution profiles, and failover rules.

## 14. Token awareness cannot cure hot partitions or skew

### 14.1. Hot partition scenario

Suppose 1 device generates **30% of total traffic** across a 100-device fleet. Without proper partition-key bucketing, most requests hit the exact same replica set.

Token-aware routing gets those requests **to those replicas faster**, yet it cannot split a hot partition across multiple tokens.

Design example:

~~~cql
-- Fixed partition per device can grow too wide over time.
PRIMARY KEY ((device_id), event_time)

-- Daily bucketing spreads load across multiple partitions/tokens.
PRIMARY KEY ((device_id, event_day), event_time)
~~~

Whether bucketing helps depends on **queries, write rates, and cross-day read needs**, not a blind rule. For ultra-high-write devices within a single day, smaller buckets or controlled sharding may be needed, trading off multi-partition fan-out on reads.

### 14.2. Balanced token distribution does not guarantee balanced load

Murmur3 hashes tokens fairly evenly, yet:

- Partitions vary in **byte size**.
- QPS across partitions can be **heavily skewed**.
- Nodes vary in hardware/IOPS or run compaction/repair at different times.
- Certain partitions are read at higher CLs or hold heavy tombstones/large collections.

Thus “even token ownership” does not mean CPU, disk, and latency stay even across nodes.

### 14.3. Routing cost also depends on row count and pagination

Two queries with the exact same routing key can impose vastly different load:

~~~cql
-- Same partition:
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT 20;

-- Same partition, but unbounded range can span many pages:
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?;
~~~

Identical routing keys do not imply identical resource cost. Check `LIMIT`, page size, SSTables scanned, tombstones, concurrency, and backpressure.

## 15. How do batches and multi-mutations handle routing keys?

### 15.1. Single-partition operations

A prepared `INSERT` or `UPDATE` with the full partition key carries its routing key.

~~~cql
INSERT INTO telemetry_lab.readings_by_tenant_device_day
(tenant_id, device_id, event_day, event_time, reading_value)
VALUES (?, ?, ?, ?, ?);
~~~

The routing key comes from the first three values; `event_time` is a clustering key and `reading_value` is payload.

### 15.2. Multi-partition batches

A CQL batch spanning multiple partitions **has no single routing key representing every statement**. Even though some drivers infer hints for tightly structured batches, never assume a multi-partition batch enjoys point-write token awareness.

Moreover, **multi-partition logged batches are not an ideal bulk loader**. They add batchlog overhead, large payloads, and wide replica fan-out.

For bulk imports or backfills, you usually need:

- Work split by partition or token range.
- Prepared point writes.
- Bounded concurrency, rate, and bytes/s.
- Checkpointing and controlled retries.
- Monitoring of compaction, commit logs, replica p99, and free disk space.

**Never cram multiple partitions into huge batches just for “fewer requests”.**

## 16. Java applications: async queries still need routing metadata

Java Driver 4.x supports `executeAsync`; running asynchronously does not strip a `BoundStatement`'s routing key when inference conditions hold.

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import java.util.concurrent.CompletionStage;

BoundStatement bound = prepared.bind(
        tenantId, deviceId, eventDay, 50)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(50);

CompletionStage<AsyncResultSet> stage =
    session.executeAsync(bound);
~~~

Here `prepared` is a prepared SELECT over all three partition key columns, and variables match `UUID`, `UUID`, `LocalDate`, and `int`.

**Notes:**

- Async routing still uses driver load balancing.
- Token awareness does not stop an app from launching **thousands of futures** at once.
- Bulk reads still require backpressure, in-flight limits, and deadlines.
- For multi-page results, `AsyncResultSet` provides `currentPage()`, `hasMorePages()`, and `fetchNextPage()`; fetch next pages at downstream processing pace.
- Never block driver callback threads with long I/O or `Thread.sleep`.

### 16.1. Routing keys + rate limits

An app can have perfect routing keys while blasting 10,000 requests/s at a single partition, saturating its replicas. **Token awareness chooses the path; it does not rate-limit.**

For hotspots, track **requests/s and bytes/s per query shape/partition group**, enforce quotas, and revisit the data model.

## 17. Changing metadata: bootstrap, replace, repair, and upgrades

### 17.1. The ring is not immutable

In Cassandra, operations such as:

- **Bootstrap** adding nodes.
- **Decommission/replace** changing membership/placement.
- **RF changes** and DC/rack topology adjustments.
- **Streaming, rebuild, and repair**.

can alter token range ownership or replica availability.

The Java Driver listens to cluster metadata to refresh routing state. Still, **driver metadata can lag briefly**, especially right after topology changes or network partitions.

### 17.2. Never cache replica mappings permanently in application code

Anti-pattern:

~~~text
Startup:
  token T -> node A
  cache this mapping in a static HashMap

Hours later:
  cluster bootstraps/replaces nodes
  still sends every token T query via stale mapping
~~~

Let the driver and load balancer manage metadata refreshes; if the app maintains any operational cache, pair it with proper invalidation/refresh.

### 17.3. Tracing and inspecting topology

Commands to verify cluster state:

~~~bash
# Node status, DC/rack, token ownership.
nodetool status

# Node info and running release.
nodetool info

# Streaming during bootstrap/rebuild/repair.
nodetool netstats

# Thread pools and dropped messages.
nodetool tpstats

# Compaction backlog and progress.
nodetool compactionstats
~~~

Never treat `nodetool status` from a single node as infallible cluster truth: gossip views can diverge briefly. Cross-check relevant nodes, metadata, and logs over a time window.

## 18. Observing token-aware routing: which metrics truly matter?

### 18.1. Java client layer

Track:

- Request QPS, p50/p95/p99, and timeouts/unavailable errors by **query ID**.
- Retries/speculative executions and final outcomes.
- In-flight requests, queue depth, and connection failures.
- `routing_key_present` per query template (boolean/counter, never raw keys).
- Coordinator DC/rack or node group (with bounded cardinality).
- Verification that queries carry full partition keys and valid keyspaces.

Never assume every driver version exposes a built-in “token-aware hit” metric; build custom instrumentation if required.

### 18.2. Server layer

Track:

- Coordinator and table/node read/write latencies.
- `nodetool tpstats`: Pending/Active/Dropped by stage.
- `nodetool tablehistograms` or SSTables-per-read stats per version.
- `nodetool compactionstats`: backlog and disk pressure.
- Disk IOPS/latency, network RTT/retransmits, CPU/GC.
- Node DOWN/UP events, streaming/repair, and RF/DC topology.

**Never average node p99s to estimate cluster p99.** Percentiles must aggregate full distributions/histograms properly and account for timeouts excluded from success-only histograms.

### 18.3. Diagnostic table

| Symptom | Hypothesis | Check |
|---|---|---|
| `getRoutingKey()==null` on point SELECT | Insufficient prepared metadata, query shape lacks PK, unbound marker | Full PK in WHERE, prepared metadata, keyspace |
| Coordinator often outside token's replicas | Load-balancing fallback, stale metadata, local DC, replica health | Query plan, token map, execution info, node status |
| Coordinator in remote DC | Wrong local DC/session policy, failover/routing rules | Driver config, contact points, DC/rack metadata |
| High p99 despite coordinator being a replica | Hot partition, tombstones, disk/GC/network, CL | Query profile, SSTables per read, metrics |
| p99 spikes after bootstrap | Token/replica placement shifted, streaming I/O contention | `netstats`, `compactionstats`, topology metadata |
| Timeouts during `IN` queries | Multi-partition/replica fan-out | Split into bounded point reads; review data model |
| Token-range CQL scan is very slow | Large ranges, skewed byte distribution, high concurrency | Token range sizes, disk/CPU, request rate |
| One node runs hot despite balanced token ownership | Hot keys or skewed QPS/row sizes | Partition workload, tracing, bytes/partition |
| Client retries surge | Slow nodes, timeouts, aggressive retry policy | Driver retry metrics, overload, backpressure |

**Never blame all latency on routing.** Token awareness can be working perfectly while a replica stalls on compaction, tombstones, repair, or infrastructure issues.

## 19. Runbook A: prepared point read has no routing key

**Scenario:** A repository queries by tenant, device, and day, yet `BoundStatement.getRoutingKey() == null` after binding.

**Step 1 — Confirm the actual query.** Record operation ID, normalized query template, keyspace/table, and driver version. Avoid logging sensitive tenant/device values.

**Step 2 — Verify full partition key.** Compare schema `PRIMARY KEY` against `WHERE`; does the query include `tenant_id`, `device_id`, and `event_day`? Are markers bound with matching types and order?

**Step 3 — Check prepared metadata.** Is code actually using `session.prepare` and `prepared.bind`, or did it fall back to `SimpleStatement`/string concatenation? Does the query use `IN`, expressions, or filters preventing single-partition inference?

**Step 4 — Check keyspace and schema.** Does the keyspace exist, is the routing keyspace resolved, and did schema metadata refresh after DDL/upgrades?

**Step 5 — Check runtime bindings.** Were illegal null/unset values bound, multiple values skipped, or custom codecs misconfigured? If queries reach replicas yet skip token-aware selection, inspect load-balancing fallback.

**Step 6 — Fix structure before forcing hints.** Prefer a prepared statement specifying the full PK. Consider manual routing hints only when you understand binary encoding/schema and have lab-tested it.

**Step 7 — Verify.** Confirm routing key presence, coordinator choice, p95/p99/timeouts, and correctness; never close the incident merely because `getRoutingKey() != null`.

## 20. Runbook B: p99 rises after a topology change

**Scenario:** After bootstrapping a new node, client p99 climbs and some coordinators lie outside the old replica set.

1. **Confirm change window:** which node is joining/replacing, and did tokens/RF change as planned?
2. **Compare new topology:** `nodetool status`, DC/rack, token ownership, gossip, and logs.
3. **Check client metadata:** has the driver discovered the new node/host IDs and matching local DC?
4. **Identify query shapes:** are requests single-partition token-aware point reads or token-range/`IN` scans without a single routing key?
5. **Check background load:** `netstats` streaming, `compactionstats` backlog, disk/network saturation?
6. **Inspect request attempts:** coordinators, retries/speculative execution, timeouts, and time to first page.
7. **Apply reversible mitigations:** throttle backfills or concurrency if overloaded, follow metadata/network runbooks; never spoof tokens or force fake routing.
8. **Verify SLOs:** compare before/after p50/p95/p99 and timeouts, and check replica health rather than just `UN` status.

**Important:** after a topology change, seeing a coordinator “outside the old replica set” can be **completely normal** because the replica set itself moved. Always compare against the **current token map**, not a pre-bootstrap hardcoded list.

## 21. Runbook C: token-range export overloads the cluster

**Scenario:** A Java export job scans token ranges with many workers. Disk latency spikes on several replicas, along with `ReadStage Pending` and timeouts.

**Step 1:** Pause worker scale-up and check production safety thresholds.

**Step 2:** Record active ranges, partitioner, boundary rules, bytes/s, rows/s, and in-flight requests.

**Step 3:** Confirm no range gaps or double-counting exist, including token-ring wrap-around.

**Step 4:** Measure range size skew in actual bytes rather than arithmetic token span.

**Step 5:** Throttle concurrency/rate against the **most overloaded node**; consider off-peak windows and checkpoint/resume support.

**Step 6:** Monitor `tpstats`, `compactionstats`, disk/GC, driver retries, and user-facing API p99.

**Step 7:** Once the cluster stabilizes, ramp rate gradually while keeping hard stops. Never raise or lower CL blindly to mask scan overload.

**Step 8:** After export completes, reconcile token coverage, logical row/partition IDs, checksums, and mutations that occurred mid-scan.

**Never assume a token-range scan yields a cluster-wide consistent snapshot.** Point-in-time exports require snapshots/backups or event logs/reconciliation.

## 22. Common misconceptions

| Claim | Assessment | Why |
|---|---|---|
| “The routing key is the partition key column name.” | **False** | It is the encoded bytes of the partition key **values** |
| “Routing key = token.” | **False** | The partitioner computes the token from the routing key |
| “Clustering keys are part of the routing key.” | **False** | Routing keys use partition key components only |
| “One token always maps to one node.” | **False** | Replica placement depends on keyspace RF and topology |
| “Contact points are always the coordinator.” | **False** | The driver uses metadata and load-balancing query plans |
| “Prepared statements are always token-aware.” | **False** | Requires valid PK/keyspace/metadata and single-partition queries |
| “SELECT without full PK knows the token if LIMIT is set.” | **False** | LIMIT does not identify a partition |
| “Multi-partition `IN` has a single routing key.” | **Cannot assume** | Multiple partitions can hash to different tokens |
| “A valid routing key means reading from just one replica.” | **False** | CL may require multiple replicas |
| “`LOCAL_QUORUM` only picks the coordinator.” | **False** | CL governs replica response requirements |
| “Larger token means newer event.” | **False** | Tokens are hash outputs, not timestamps |
| “`token()` range scans are cheap because they are token-aware.” | **False** | They can scan many partitions and replicas |
| “Token awareness eliminates hot partitions.” | **False** | A hot partition still concentrates on its replica set |
| “`getRoutingKey()!=null` guarantees the query is sound.” | **False** | Does not prove authz, CL, data model, or p99 |
| “A non-replica coordinator means the query is broken.” | **False** | Fallback/other coordinators can still execute properly |
| “Replica mappings never change after bootstrap.” | **False** | Topology and token maps evolve |
| “Use Java `hashCode` to compute tokens.” | **False** | Must match Cassandra binary encoding and partitioner |
| “Routing hints bypass authorization.” | **False** | Access control remains enforced by server/application |
| “Averaging node p99s gives cluster p99.” | **False** | Percentiles require proper distribution/histogram aggregation |

## 23. Exercises and answers

### Question 1 — Routing key components

A table has `PRIMARY KEY ((tenant_id, device_id, event_day), event_time)`. Which columns form the routing key?

**Answer:** `tenant_id`, `device_id`, and `event_day` in partition key order. `event_time` is a clustering key and is excluded from the routing key.

### Question 2 — Two rows differing in `event_time`

Two rows differ only in `event_time`. Do they share the same routing key and token?

**Answer:** Yes, if all partition key components match. They live in the same logical partition; clustering keys do not change the token.

### Question 3 — Limit and token

A query with full partition keys has `LIMIT ?`. Does changing limit from 20 to 100 change the routing key?

**Answer:** No. `LIMIT` is not part of the partition key; it only bounds returned rows.

### Question 4 — Partition key missing day

A query has `tenant_id = ? AND device_id = ?` without `event_day`. Can the Java Driver compute a single routing key for the example table?

**Answer:** No. The partition key is incomplete, and the query will likely be rejected under CQL restrictions on that table.

### Question 5 — RF=3 cluster

A token belongs to replicas N1/N2/N3. The client picks N2 as coordinator with CL=`LOCAL_QUORUM`. Is N2 responding alone enough?

**Answer:** No. `LOCAL_QUORUM` with RF=3 requires a quorum of two replicas in the local DC. Coordinator N2 may also be a replica, yet that does not reduce the required ACK count.

### Question 6 — Contact point

`CqlSession` uses contact point N1. Will every CQL request use N1 as coordinator?

**Answer:** No. Contact points serve initial discovery/connection; the driver selects coordinators using its load-balancing policy and metadata.

### Question 7 — IN

CQL `WHERE device_id IN (?, ?, ?)` on a table with `device_id` as a single partition key. Can you assume one token for the whole query?

**Answer:** No. Three devices can hash to three distinct tokens and replica sets.

### Question 8 — Routing bytes

A colleague concatenates `tenant + ":" + device + ":" + day` and calls `String.hashCode()` to build a token. Is this right?

**Answer:** No. Routing keys require typed/ordered CQL binary encoding, and tokens require Cassandra's partitioner. Java `hashCode` is not a Murmur3 token.

### Question 9 — Non-replica coordinator

The driver picks node N4 outside the replica set. Must the query always fail?

**Answer:** No. The coordinator forwards requests to the target replicas. However, it may add a network hop and latency; inspect liveness, DC, CL, and load balancing.

### Question 10 — Token range and time

To fetch the 20 latest events, should you `ORDER BY token(...) DESC` or take the highest tokens?

**Answer:** No. Tokens do not encode time. Use clustering `event_time DESC` within the target partition with `LIMIT 20`.

### Question 11 — Async

An app fires 20,000 concurrent `executeAsync` point reads, each with a valid routing key. Does that guarantee the cluster will not overload?

**Answer:** No. Token awareness does not replace backpressure, bounded in-flight limits, rate limiting, or per-replica capacity planning.

### Question 12 — Bootstrap

A new node joins the cluster and token owners/replica sets shift. Should the app keep a startup-cached `token -> node` map?

**Answer:** No. Rely on the driver's live metadata and load-balancing updates; manual caches go stale.

### Question 13 — Multi-DC

An app in `dc1` runs with `LOCAL_QUORUM`. Does that guarantee every replica in `dc2` ACKed before the request succeeded?

**Answer:** No. `LOCAL_QUORUM` requires quorum in the local DC; replication to remote DCs may still be in flight when the client receives ACK.

### Question 14 — Security

A request carries a valid `tenant_id` belonging to another tenant. Does valid binding and routing key calculation prove read authorization?

**Answer:** No. Enforce principal-based authentication and authorization; token routing locates data, it does not authorize access.

### Question 15 — Hotspot

One partition receives more queries than all others combined. Does enabling token-aware routing eliminate the hotspot?

**Answer:** No. It picks a better coordinator, yet that partition still lives on its fixed replica set. Consider bucketing/sharding, caching, rate limits, and query redesign.

### Question 16 — Finding the cause of slowness

`getRoutingKey()` is non-null and the coordinator is in the replica set, yet read p99 is 900 ms. What causes remain?

**Answer:** Wide/hot partitions, SSTable/tombstone read amplification, disk/GC, network, compaction/repair/streaming, CL, or large payloads. Good routing never guarantees fast reads.

## 24. Code review and operations checklist

### 24.1. Java application

~~~text
[ ] Using Java Driver 4.x APIs matching the exact version and local DC.
[ ] CqlSession is reused; never created per request.
[ ] CQL is prepared; bind markers use matching data types.
[ ] Queries specify full partition keys whenever point routing is intended.
[ ] Keyspace/schema names and routing metadata are verified.
[ ] Never concatenate partition key bytes manually or hash tokens with Java hashCode.
[ ] Never trust raw tenant_id from requests without authorization checks.
[ ] Never log raw routing key bytes in logs or metric labels.
[ ] LIMIT, page size, and max in-flight requests have sensible bounds.
[ ] Async paths enforce backpressure and deadlines without unbounded futures.
[ ] Tested in lab that requests hit expected coordinators/replicas.
[ ] Retries/speculative execution are observed and tuned to SLOs.
~~~

### 24.2. Cassandra cluster

~~~text
[ ] RF, NetworkTopologyStrategy, DC/rack, and snitch match design.
[ ] Driver sees current nodes, host IDs, and token map.
[ ] No unplanned topology changes or unresolved UJ/DN nodes.
[ ] Query workloads are measured per node/DC, not only cluster averages.
[ ] Token distribution is reviewed alongside bytes/QPS per partition.
[ ] tpstats/compactionstats/netstats and disk/GC/network remain healthy.
[ ] Read/write p95/p99 and timeouts stay within approved SLOs.
[ ] Token-range jobs define ranges, checkpoints, throttling, and stop conditions.
[ ] Replica health is verified after bootstrap, repair, or replacement.
~~~

## 25. Summary

For the Java Driver to route CQL effectively in Cassandra:

1. **Partition keys** define a logical partition; the **routing key** is the encoded byte sequence of those key values.
2. The **partitioner** maps the routing key to a token; **replication strategy + topology** map the token to a replica set.
3. **Token-aware load balancing** prefers a replica as coordinator to trim network hops, yet **never replaces CL correctness**.
4. **Prepared/bound statements with full partition keys** are the best way for the driver to infer routing keys automatically. Missing PK components, multi-partition `IN`, or token-range scans do not have a single routing key.
5. **Routing keys exclude clustering keys, LIMIT, and page size.** Changing those can alter query load, without changing the partition's token when the partition key stays constant.
6. **CQL `token(...)` is meant for token-range processing**, not chronological sorting or UI pagination.
7. **Contact points do not pin coordinators**, and a non-replica coordinator can still execute requests correctly.
8. **Token maps and replica placement change when topology changes.** Never cache `token -> node` permanently in application code.
9. **Good routing does not prevent hot partitions or read/write amplification.** Monitor nodes/replicas, p99, compaction, streaming, and rate limits.
10. **Security, consistency, and routing are three distinct layers:** proper binding does not grant permissions; routing hints do not fix WHERE clauses; CL governs replica response requirements.

The practical question when reviewing any Java–Cassandra query is: **“Does the statement identify a single partition, does the driver have the bytes and keyspace to compute the token, where do the current replicas live, and does the selected coordinator serve the workload well at the required consistency?”** Answering each step yields efficient token-aware routing while preserving data modeling, security, and cluster stability.
