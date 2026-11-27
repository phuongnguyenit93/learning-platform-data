# Prepared Statements, Parameter Binding, and Token-Aware Routing

> **Chapter:** Query Tuning  
> **Scope:** Apache Cassandra — a distributed wide-column database, query-driven table design, partition keys, replication, read/write consistency levels, and Java access.

## 1. Why Do These Three Concepts Go Together?

In Cassandra, a query can be sent to any eligible node acting as **coordinator**. The coordinator locates the replicas holding the data and orchestrates reads or writes at the requested consistency level. When the application knows the target partition upfront, the driver can select a better coordinator and eliminate extra inter-node hops.

These three concepts serve distinct yet complementary roles:

| Concept | Role | What it does NOT automatically guarantee |
|---|---|---|
| **Prepared statement** | Prepares a stable CQL template, reusing metadata and a statement ID | Does not turn a multi-partition scan into a fast query |
| **Parameter binding** | Populates typed values into statement placeholders | Does not replace proper partition key design |
| **Token-aware routing** | Uses the bound partition key to compute the token, preferring a matching replica as coordinator | Does not change replication factor or consistency level |

The tuning flow is: **query-driven table design → constrain the full partition key → use prepared statements and binding → let the driver apply token-aware routing**. For queries spanning many partitions, syntax tweaks or prepared statements cannot eliminate the inherent distributed cost.

After this lesson, you will be able to:

- Recognize when the driver knows the exact partition of a query.
- Use prepared statements and strongly typed binding in Java.
- Distinguish coordinator, replica, partition key, routing key, and token.
- Explain why token-aware routing does not imply stronger consistency.
- Inspect and troubleshoot prepared caches, metadata, missing-key queries, and oversized partitions.

## 2. Starting from a Query-Driven Table

Suppose an application frequently asks: "Fetch up to 20 newest events for a customer on a given day." A matching Cassandra table is:

~~~sql
-- Example assumes a datacenter named dc1 with at least 3 suitable nodes.
CREATE KEYSPACE IF NOT EXISTS app
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS app.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    created_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), created_at, event_id)
) WITH CLUSTERING ORDER BY (created_at DESC, event_id ASC);
~~~

In this schema:

- **Partition key** is the pair **(tenant_id, event_day)**. All events for the same customer on the same day reside in one logical partition.
- **Clustering columns** are **created_at, event_id**. Rows within a partition are sorted by descending timestamp, then by event ID to disambiguate same-timestamp rows.
- **Replicas** are nodes storing copies of the partition per the replication strategy; e.g., RF = 3 in **dc1** means three logical copies within that datacenter when topology permits.
- **Token** is the output of the partitioner hash function applied to the serialized partition key. The token maps the partition onto the token ring and its replica set.

Target query:

~~~sql
SELECT created_at, event_id, event_type, payload
FROM app.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT ?;
~~~

Equality conditions on **every component of the partition key** let Cassandra pinpoint one partition. The statement needs no **ALLOW FILTERING**. **`LIMIT`** caps the number of rows returned in the read; it does not cap the physical size accumulated in the partition.

> **Design rule:** If a customer can generate excessive events in a single day, revisit bucket granularity (e.g., hourly) or table modeling. Prepared statements cannot fix an oversized partition. The rule deriving **event_day** from timestamp and business timezone must match between writes and reads.

## 3. What Does a Prepared Statement Actually Prepare?

A prepared statement is a **CQL template with bind markers**, normally denoted by question marks. The application prepares this template once per query shape and reuses it across the session's lifetime.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant A as Java Application
    participant D as Cassandra driver
    participant N as Cassandra Node
    A->>D: prepare(CQL with ? placeholders)
    D->>N: PREPARE CQL template
    N-->>D: Statement ID and bind metadata
    D-->>A: PreparedStatement
    A->>D: bind(values)
    D->>D: Encode values, compute routing key/token if sufficient
    D->>N: EXECUTE ID + values + request options
    N-->>A: Results via driver
~~~

Key distinctions:

1. **Preparing differs from executing.** Calling `prepare` neither reads nor writes query data; each `execute` runs the query with the bound values.
2. **A prepared statement is not a stored procedure.** It stores no business logic and does not make Cassandra auto-create indexes.
3. **Bind metadata matters.** The driver learns marker positions and types; for eligible statements, it identifies which markers belong to the partition key.
4. **Prepared caches are node-scoped.** Cassandra nodes maintain their own prepared caches. When a node restarts, evicts cache entries, or schema changes, re-preparation may occur; modern Java drivers handle **UNPREPARED** server responses automatically. Monitor abnormal prepare/reprepare rates rather than assuming caches live forever.
5. **Reuse stable templates.** Re-preparing on every request or generating thousands of distinct CQL strings (e.g., concatenating literals into the statement) adds network round-trips, CPU overhead, and cache churn.

For instance, three reads for different customers should share **one** prepared statement and vary only the bound **tenant_id**, **event_day**, and **LIMIT** values. Never construct a new CQL string per customer.

## 4. Binding: Values, Types, and Limits

Given the template:

~~~sql
SELECT created_at, event_id, event_type, payload
FROM app.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT ?;
~~~

Bind positions map as:

| Position | CQL type | Common Java driver 4.x type | Meaning |
|---|---|---|---|
| 0 | uuid | java.util.UUID | tenant_id |
| 1 | date | java.time.LocalDate | event_day |
| 2 | int | int / Integer | Maximum rows |

Binding operates at the **value** level with strict typing. It mitigates CQL injection from user input and eliminates manual string escaping. However:

- Placeholders cannot substitute **table names, column names, CQL keywords, or query structure**. For instance, **SELECT * FROM ?** is invalid; dynamic object names must come from an explicit allowlist and separate validation.
- For **partition keys**, required components must carry valid non-null values. Never bind **null** or leave primary key columns unset.
- In writes/updates, binding **null** to a non-key column can emit a tombstone, whereas **unset** (where supported by protocol/API) leaves the column untouched. Distinguish both to avoid unintended tombstone overhead.
- Never mismatch types—such as passing a date string instead of **LocalDate** for a **date** column, or using **UUID.randomUUID()** for a **timeuuid** column. Here the schema uses **uuid**, so standard UUIDs apply.
- Create a fresh **BoundStatement** per request from the shared **PreparedStatement**. Avoid sharing mutable statement builders across threads.

## 5. Why Binding the Full Partition Key Enables Driver Routing

The routing key is the binary encoding of the **entire partition key** per Cassandra's serialization rules. When a statement is prepared and all partition-key bind markers are populated, the driver constructs the routing key, hashes its token, and consults cluster topology/token-map metadata to pick a favorable coordinator.

~~~mermaid
flowchart TD
    A["Prepared CQL + tenant_id + event_day"] --> B["Bind all partition key components"]
    B --> C["Driver encodes routing key"]
    C --> D["Compute token and inspect token map"]
    D --> E["Prefer replica coordinator in local DC"]
    E --> F["Coordinator contacts replicas"]
    F --> G["Return result per consistency level"]
~~~

In multi-datacenter deployments, the load-balancing policy also weighs **local datacenter**, node health, available replicas, and request policies. **Token-aware** is a preference when selecting a coordinator, not a guarantee that every execution hits the exact same node. Retries, speculative execution, topology shifts, or stale metadata can route to another coordinator.

Cassandra allows any **non-replica node** to act as coordinator too. That node forwards requests to the owning replicas, incurring an extra network hop. Token-aware routing increases the odds that the coordinator already holds a copy of the target partition.

### When Routing Info Is Sufficient vs. Insufficient

| Query shape | Can a single token be determined? | Consequence |
|---|---|---|
| **WHERE tenant_id = ? AND event_day = ?** | Usually yes, when both values are bound and driver has metadata | Eligible for token-aware routing |
| **INSERT** with all partition key columns bound | Usually yes | Eligible for token-aware write routing |
| **WHERE tenant_id = ?** missing **event_day** | No; on this table Cassandra usually rejects due to incomplete key | Must redesign query or table |
| **IN** on partition key spanning multiple partitions | No single token covers all partitions | Cannot be routed as a single-partition request |
| Conditions using **token(...)** or expressions preventing key extraction | Possibly no | Falls back to load-balancing coordinator policy |
| Filtering on regular columns with no partition key restriction | No | Risks invalid query rejection, wide scans, or schema redesign |

**Note:** Exact routing-key extraction depends on driver version, schema metadata, and CQL structure. A query accepted by the server does not guarantee the driver can extract a single token.

## 6. Complete Java Example with Driver 4.x

This example demonstrates **prepare once**, bind typed parameters, insert an event, and read from the exact partition at **LOCAL_QUORUM**. Java driver 4.x uses packages under **com.datastax.oss.driver.api**. Include a compatible **java-driver-core** dependency and point to a running Cassandra cluster.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class CassandraPreparedRoutingDemo {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
        LocalDate eventDay = LocalDate.of(2026, 11, 21);
        Instant now = Instant.now();
        UUID eventId = UUID.randomUUID();

        // Replace dc1 and contact point with your real cluster configuration.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO app.events_by_tenant_day " +
                "(tenant_id, event_day, created_at, event_id, " +
                " event_type, payload) VALUES (?, ?, ?, ?, ?, ?)");

            BoundStatement write = insert.bind(
                    tenantId, eventDay, now, eventId,
                    "login", "{\"success\":true}")
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);

            PreparedStatement select = session.prepare(
                "SELECT created_at, event_id, event_type, payload " +
                "FROM app.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement read = select.bind(tenantId, eventDay, 20)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(20);

            ResultSet result = session.execute(read);
            System.out.println(
                "Coordinator: " + result.getExecutionInfo().getCoordinator());

            for (Row row : result) {
                Instant createdAt = row.getInstant("created_at");
                UUID id = row.getUuid("event_id");
                String type = row.getString("event_type");
                String payload = row.getString("payload");
                System.out.printf("%s | %s | %s | %s%n",
                        createdAt, id, type, payload);
            }
        }
    }
}
~~~

Prerequisites to run this example:

- Keyspace and table from Section 2 exist; the cluster datacenter is genuinely named **dc1** or adjusted accordingly.
- With replication factor **3** and **LOCAL_QUORUM**, enough replicas must exist in the local datacenter to satisfy quorum. A single-node cluster cannot normally satisfy RF = 3 with `LOCAL_QUORUM`.
- When partitioning by business date, derive **eventDay** from **now** using the agreed timezone; a fixed date is used here to highlight binding.
- Production applications should store **PreparedStatement** instances in a singleton initialized once alongside a long-lived **CqlSession**, rather than preparing inside each API call. Opening the session inside **main** is solely for standalone execution.

Once prepared, subsequent reads simply bind new parameters:

~~~java
BoundStatement anotherRead = select.bind(otherTenantId, otherDay, 20)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
ResultSet otherResult = session.execute(anotherRead);
~~~

This snippet assumes **select**, **session**, **otherTenantId**, and **otherDay** are already in scope; it illustrates template reuse rather than a standalone Java program.

### Time-Range Queries Within the Same Partition

To filter further within a day:

~~~sql
SELECT created_at, event_id, event_type
FROM app.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT ?;
~~~

Both partition key columns remain equality-bound; the range filter applies to clustering column **created_at**. This stays a **single-partition** query and retains token-aware routing benefits. Clustering predicates must follow primary key column ordering rules.

## 7. Routing and Consistency Level Are Independent Decisions

**Routing** answers: "Which coordinator does the client initially send the request to?"  
**Consistency level** answers: "How many replicas must the coordinator hear from before acknowledging the result?"

Example with RF = 3 in the local datacenter:

| Consistency level | Simple meaning | Does token-aware routing change this requirement? |
|---|---|---|
| **ONE** | Typically requires one replica acknowledgment | No |
| **LOCAL_QUORUM** | Requires majority of replicas in local DC; **2** when RF = 3 | No |
| **ALL** | Requires all replicas per operation semantics | No |

With RF = 3, reading and writing at **LOCAL_QUORUM** in the same datacenter ensures read and write replica sets overlap (2 + 2 > 3), increasing the likelihood of reading acknowledged writes under normal conditions. Actual freshness still depends on concurrent mutations, failures, timeouts, and Cassandra internals. Routing to a local replica **never** silently upgrades **ONE** to **QUORUM**.

Depending on the workload, different consistency levels trade off latency, availability, and replica participation. **Lightweight transactions** with **IF** conditions also involve separate serial consistency—never conflate them with binding or token-aware routing.

## 8. Common Performance and Operational Pitfalls

| Symptom | Common cause | Remedy |
|---|---|---|
| Calling `prepare` on every request | Extra round-trips, repeated parsing, cache churn | Prepare once at startup; reuse shared statements |
| Concatenating literals directly into CQL | Floods query strings, breaks caching, CQL injection risk | Use bind markers for values |
| Bound parameters yet very slow reads | Query misses partition bounds or partition is oversized | Check primary key, bucketing, and partition sizes |
| Driver cannot determine routing key | Missing key part, complex expression, missing metadata | Use equality on full partition key; verify driver metadata |
| Coordinator changes across runs | Load balancing, retries, node health, or topology shifts | Inspect coordinator in execution info and driver config |
| **UNPREPARED** errors after restart/schema change | Node-side prepared cache cleared | Rely on driver re-preparation; investigate if persistent |
| Timeouts despite token-aware routing | Slow replica, insufficient quorum, hotspot, or network saturation | Measure per-node latency; check replication/CL and partition load |
| Heavy writes to one hot partition key | Owning partition and replicas overloaded | Add finer buckets; distribute keys by workload |
| Using **LIMIT** to bound partition size | `LIMIT` caps output rows only | Cap partition size in the data model |
| Wrapping unrelated queries in a giant `BATCH` | `BATCH` does not accelerate multi-partition operations | Use `BATCH` only for intended atomic/logged semantics; measure cost |

### Prepared Statements Do Not Replace Distributed Data Hygiene

- **Replication:** ensure replication strategy and RF match actual topology.
- **Compaction:** monitor SSTables and read/write overhead; slow reads may stem from many SSTables, tombstones, or compaction backlogs.
- **Repair:** reconcile replica divergence on schedule; prepared statements do not keep replicas consistent.
- **Error handling:** distinguish connection/coordinator errors, ambiguous write timeouts, CQL syntax/invalid errors, and schema mismatches. Retry only idempotent operations; never raise retries blindly.
- **Observability:** track latency, timeouts, prepare/reprepare counts, node load, tombstones, partition sizes, and selected coordinators.

## 9. How to Verify in a Lab Environment

1. **Inspect the schema.** Confirm the primary key truly is **((tenant_id, event_day), created_at, event_id)**. If the application needs another access pattern (e.g., querying by **event_type** across days), design a matching query table instead of forcing wide filtering here.
2. **Run the Java demo.** Observe the **Coordinator** printed from **result.getExecutionInfo()**. Repeat with different partition keys to see the chosen coordinator vary by token, topology, and load-balancing policy.
3. **Keep the statement fixed, vary bindings.** Query the same template for different customers/days and verify returned rows match only the requested partition.
4. **Test a missing-key query.** In a test environment, run a condition with only **tenant_id = ?**. Observe the CQL error or restriction and explain why a single partition cannot be resolved.
5. **Compare single-partition vs. multi-partition queries.** Measure p50/p95 latency, request counts, payload sizes, and replica load on a sufficiently large, controlled dataset rather than a single run.
6. **Monitor the system.** When needed, use controlled query tracing alongside driver/cluster metrics to inspect coordinators, contacted replicas, and slow phases. Tracing adds overhead; never enable it wholesale across production traffic.

**Self-Check Questions**

1. A table has composite partition key **(tenant_id, event_day)**. If you bind only **tenant_id**, can the driver compute the exact token? Why?
2. Does **LOCAL_QUORUM** guarantee the driver routes the request directly to a local replica? What role does the load-balancing policy play?
3. If every request uses a prepared statement yet still scans hundreds of partitions, which layer must be fixed first?
4. Why should you avoid generating a new CQL string by concatenating a different **UUID** on every call?
5. When a coordinator node restarts and loses its prepared cache, what must happen for subsequent `execute` calls to keep working?

**Answer Hints:** (1) No, because a partition key component is missing; (2) no—consistency and coordinator routing are separate mechanisms; (3) table design and query patterns; (4) breaks template reuse, adds prepare overhead, and risks string concatenation bugs; (5) re-prepare on the target node and re-execute, normally handled automatically by the driver.

## 10. Summary

To query Cassandra efficiently, start from the **access pattern** and **partition key**, then use **prepared statements** to reuse CQL templates and typed **parameter binding** per execution. When the driver can resolve the full partition key, it leverages **token-aware routing** to choose an optimal coordinator. Coordinator selection optimizes only the request's network path; correctness, consistency guarantees, and read/write costs still depend on replication, consistency levels, partition sizes, compaction, repair, and cluster health.
