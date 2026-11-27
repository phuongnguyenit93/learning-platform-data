# Load Balancing, Token-Aware Routing, and Locality

> **Chapter:** Java Driver Basics  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, distributed wide-column model, partition-key and query-driven table design, read/write consistency levels, CQL, replication, compaction, repair, troubleshooting, and Java application connectivity.

A Java application issuing `SELECT ... WHERE tenant_id = ?` to Cassandra does not necessarily hit the node storing that partition directly. **The Java Driver selects a coordinator**, and the coordinator forwards requests to **replicas** based on partition key, replication strategy, and consistency level (CL). If the driver picks a non-replica coordinator, the request incurs an extra internode hop. If it picks a coordinator in a remote datacenter (DC), the request also suffers WAN latency and misrouted region risks.

**Load balancing**, **token-aware routing**, and **datacenter locality** work together to solve this, yet they are not synonymous:

- **Load balancing:** selects which node acts as coordinator, priority ordering, and fallbacks in a *query plan*.
- **Token-aware routing:** given a known partition key and replica placement, promotes **matching replicas** to the front of the query plan to avoid extra hops.
- **Locality:** restricts/prefers nodes in the DC closest to the application, preventing unnecessary cross-region CQL traffic.

This lesson uses **Apache Cassandra Java Driver 4.x**, specifically behaviors documented in Driver **4.19**. Driver 3.x uses different configuration wrappers (such as `TokenAwarePolicy` around `DCAwareRoundRobinPolicy`); **never copy Driver 3.x code into Driver 4.x**. Examples assume a lab cluster matching the described topology; no fabricated benchmark numbers are presented as measured results.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **partition owner/replica**, **coordinator**, **contact point**, **local DC**, and **driver query plan**.
2. Explain node selection with and without a routing key, and predict the cost when the coordinator is not a replica.
3. Configure `DefaultLoadBalancingPolicy` and `local-datacenter`, understanding `LOCAL`, `REMOTE`, and `IGNORED` distances.
4. Use `PreparedStatement`/`BoundStatement` so the driver derives the routing key from **all partition key components**.
5. Explain why `SimpleStatement` normally **does not auto-derive** routing metadata, and how to inspect/set routing info.
6. Observe the actual coordinator via `ExecutionInfo` and expected replicas via `TokenMap` in Java Driver 4.x.
7. Analyze interactions among locality, CLs such as `LOCAL_QUORUM`, cross-DC failover, retries, and speculative execution.
8. Build labs and metric tables to spot wrong local DC, missing token metadata, hot partitions, and skewed load distribution.

## 2. Request Flow from Java to Replicas

### 2.1. Separating Coordinator from Replica

Given table:

~~~sql
CREATE TABLE route_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

The **partition key** is the pair `(tenant_id, event_day)`. Cassandra hashes the partition key's bytes into a **token**. From the token, keyspace replication strategy, and topology (DC/rack), metadata identifies **which nodes act as replicas** for that partition. `event_time` and `event_id` are clustering columns affecting row order inside the partition **without changing the token** while `tenant_id` and `event_day` stay constant.

~~~mermaid
flowchart TD
    A["Java: SELECT by tenant_id + event_day"] --> B["Does driver have routing key?"]
    B -->|Yes| C["TokenMap finds replicas by keyspace, token, RF, DC"]
    B -->|No| D["Prefer local nodes per query plan"]
    C --> E["Prefer replicas in local DC"]
    D --> F["Local coordinator, may not be a replica"]
    E --> G["Selected coordinator"]
    F --> G
    G --> H["Cassandra reads required replicas per CL"]
    H --> I["Merge results/tombstones and return to Java"]
~~~

A **coordinator** may be a replica or a node not storing the partition. Any eligible Cassandra node can coordinate CQL requests; replicas are the nodes assigned to hold data per token/RF. The driver selects the **coordinator**, not "which replicas ACK to satisfy CL"—that is handled by the coordinator and Cassandra's consistency protocol.

### 2.2. Two Paths for the Same Partition

Suppose the local DC has four nodes A, B, C, D; keyspace RF=3; and partition K's token is replicated on A, B, C.

**Optimal path:** The driver knows K and places A/B/C at the head of the query plan; the request hits A, so A acts as coordinator, can read its local copy, and contacts B/C as needed.

**Indirect path:** Without a routing key, the driver picks D; D acts as coordinator, contacts A/B/C, and returns data to the client. Consistency remains valid, yet extra internode hops and coordinator CPU are spent.

~~~text
Local DC: A, B, C, D     RF=3     replicas(K) = {A, B, C}

Token-aware:
  Java ---> A [coordinator + replica] ---> B/C per CL

Without routing metadata:
  Java ---> D [non-replica coordinator] ---> A/B/C

Picking A does not mean the request touches only A.
Satisfying LOCAL_QUORUM at RF=3 still follows Cassandra's CL rules.
~~~

Token-aware routing **does not alter consistency level**, add replicas, or cure hot partitions. It optimizes coordinator selection. When RF equals the local node count—e.g., 3 nodes with RF=3—**every local node is a replica**; such a lab cannot visibly contrast token-aware routing against round-robin.

## 3. Load Balancing Policy in Java Driver 4.x

### 3.1. A Query Plan Is a Priority List, Not One Fixed Node

`LoadBalancingPolicy` builds a **query plan** per request execution: an ordered list of nodes the driver tries in sequence. It governs:

1. Which nodes maintain open connections.
2. Which node is tried first as coordinator for a statement.
3. On errors, retries, or speculative executions, which node is tried next per policy.

| Concept | Role | Common Misconception |
|---|---|---|
| **Contact points** | Bootstrap addresses for initial connection and topology/schema metadata | "The driver only sends CQL to contact points" — false once discovery finishes |
| **Node distance** | Connection-management classification: `LOCAL` / `REMOTE` / `IGNORED` | Not physical geographic distance in kilometers |
| **Query plan** | Ordered candidate coordinators for **a single query** | Not a list of replicas guaranteed to return data |
| **Token-aware** | Prioritizes replicas for known keyspace + partition key | Not client-side sharding |
| **Slow replica avoidance** | Avoids sluggish replicas in the default policy | Does not replace monitoring or fixing degraded nodes |
| **Retry policy** | Decides whether to retry/continue on specific errors | Does not permit retrying arbitrary writes by default |
| **Speculative execution** | May dispatch backup executions per config for eligible requests | Does not create extra replicas or fix wrong CL |

In Java Driver 4.x, `DefaultLoadBalancingPolicy` is the **default and usually best kept**. It includes token awareness and slow-replica avoidance depending on version behavior. You do not wrap `TokenAwarePolicy` around `DCAwareRoundRobinPolicy` as in Driver 3.x examples.

### 3.2. Distances: LOCAL, REMOTE, IGNORED

- **`LOCAL`:** the driver maintains connections and can prioritize these nodes in query plans. Under the default policy with local DC configured, these are eligible nodes in that DC.
- **`IGNORED`:** the driver does not actively connect to the node for policy requests; remote DCs are ignored by default.
- **`REMOTE`:** appears only when policy or failover configuration permits using nodes outside the local DC, potentially with different pool sizes/costs.

By default, Java Driver 4.x's built-in policy keeps traffic within **one local DC**. Even when two DCs hold full RF, the driver never picks remote replicas just because they store the partition. This intentionally avoids WAN traffic. Behavior detail across 4.x: driver-level cross-DC failover was reintroduced in **Driver 4.10**, **disabled by default**.

### 3.3. Behavior With and Without Routing Metadata

Per Java Driver 4.19 documentation:

| Statement Information | Default Query Plan |
|---|---|
| Missing keyspace or routing key | Cycles/shuffles connected nodes in the local DC; coordinator is not guaranteed to be a replica |
| Routing keyspace + routing key present and `TokenMap` available | Places **local replicas of the partition** first (permuted for load spread), followed by local non-replicas |
| One local replica down/slow | Other replicas/local nodes follow in the query plan via retries and slow avoidance |
| All local nodes unavailable, failover disabled | Driver does not automatically fail over to another DC |
| Cross-DC failover enabled | Selected remote nodes appear **after local nodes** subject to config and CL constraints |

Never expect every request for a partition to hit the **exact same replica**. The driver shuffles replicas to balance coordinator load; errors, latency, stale metadata, speculative execution, and retries also affect which node ultimately replies.

## 4. Datacenter Locality: Which Region Should the App Connect To?

### 4.1. `local-datacenter` Is a Deployment Decision

If a Java app is deployed in **Region 1** while Cassandra has `dc1` in Region 1 and `dc2` in Region 2, set the session's local DC to `dc1`. Another Java instance in Region 2 should use `dc2`, provided the keyspace has sufficient RF and data there.

~~~mermaid
flowchart LR
    subgraph R1["Region 1"]
      A1["Java app: local-dc = dc1"] --> D1["Cassandra dc1"]
    end
    subgraph R2["Region 2"]
      A2["Java app: local-dc = dc2"] --> D2["Cassandra dc2"]
    end
    D1 -. "Replication / internode WAN" .- D2
~~~

**The driver's local DC governs coordinator routing**, whereas keyspace RF determines which DCs actually hold replicas. You could set `local-datacenter = dc2` on a keyspace whose RF exists only in `dc1`—picking a coordinator in `dc2` **will not make data local**. Always verify schema replication alongside topology.

### 4.2. Basic HOCON Configuration

Sample `application.conf` for Java Driver 4.x:

~~~hocon
datastax-java-driver {
  basic.contact-points = [
    "db1.dc1.internal.example:9042",
    "db2.dc1.internal.example:9042"
  ]

  basic.load-balancing-policy {
    class = DefaultLoadBalancingPolicy
    local-datacenter = dc1
  }

  advanced.metadata {
    schema.enabled = true
    token-map.enabled = true
  }
}
~~~

Hostnames are illustrative; use real reachable cluster DNS/IP endpoints. Add TLS truststores, credentials, and secret injection **outside this snippet** if the cluster requires them. Never put plaintext usernames, passwords, tokens, or private keys in source files.

Field breakdown:

- `basic.contact-points` specifies initial endpoints; they **do not** pin requests to those two nodes.
- `basic.load-balancing-policy.class` selects the policy; can be omitted when keeping the default.
- `local-datacenter` chooses the logical DC from node metadata; **must match the cluster-reported DC name exactly** (e.g., `dc1` vs. `DC1`).
- `advanced.metadata.schema.enabled` and `token-map.enabled` enable metadata needed to resolve per-keyspace replicas; usually enabled by default, shown explicitly here to highlight the dependency.

In production apps with explicit contact points, always **declare local DC explicitly**. `DcInferringLoadBalancingPolicy` can infer DC from contact points and is mainly intended for ETL tools. Never omit local DC trying to "spread load evenly across two regions": that increases WAN traffic and latency.

### 4.3. Creating the Session in Java

Without HOCON, configure programmatically:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("db1.dc1.internal.example", 9042))
        .addContactPoint(new InetSocketAddress("db2.dc1.internal.example", 9042))
        .withLocalDatacenter("dc1")
        // Supply auth/TLS from your deployment's secure configuration.
        .build()) {

    session.execute("SELECT release_version FROM system.local");
}
~~~

**One long-lived session per application** is far better than creating a session per request: the driver manages pools, metadata, prepared statement caches, heartbeats, and topology per session. `try-with-resources` here only demonstrates lifecycle in a standalone CLI; in web services, initialize at startup and close at shutdown.

If local DC is set in both Java code and HOCON, the **programmatic value takes precedence** in Driver 4.x. When a deployment still routes to another region, inspect **both config sources**, not just HOCON files.

## 5. What Data Does Token-Aware Routing Require?

### 5.1. Simultaneous Prerequisites

The driver can resolve matching replicas only when all four hold:

1. **Keyspace** of the statement, to fetch replication strategy/RF. The same token can map to different replicas across keyspaces.
2. **Routing key** — byte representation of the **entire partition key** per CQL types/codecs in exact component order.
3. **Up-to-date token map and schema metadata** carrying the partitioner, token ring, and keyspace replica mapping.
4. **Load balancing policy** supporting token awareness with eligible/connected local replicas.

~~~text
partition key: (tenant_id UUID, event_day DATE)
      |
      v  CQL type encoding + composite key encoding
routing key (byte buffer)
      |
      v  partitioner, e.g., Murmur3Partitioner
token (numeric)
      |
      v  token map + replication strategy + DC/rack
replicas for keyspace route_lab
      |
      v  filter local/eligible + query-plan policy
preferred candidate coordinator
~~~

**Never hash UUIDs into tokens manually using custom app code.** Composite partition keys follow specific byte-encoding rules. Always **let prepared statements and the driver handle it**. The token map reflects metadata learned by the driver; right after RF changes, bootstraps, decommissions, or schema edits, metadata refreshes after a brief lag.

### 5.2. BoundStatement: The Easiest Way to Get a Routing Key

Assume the table has:

~~~sql
PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
~~~

A prepared query:

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM route_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? LIMIT ?");

BoundStatement bound = prepared.bind(
    tenantId, eventDay, from, until, 50);
~~~

The driver learns from `PREPARED` metadata that `tenant_id` and `event_day` are **partition key variables**. Once both are bound with valid values, the driver computes `routing keyspace` and `routing key` automatically. Clustering parameters `from`/`until` do **not** participate in token calculation.

**Subtle detail in Driver docs:** even a query specifying the entire partition key as:

~~~java
PreparedStatement onlySomeBound = session.prepare(
    "SELECT * FROM route_lab.events_by_tenant_day " +
    "WHERE tenant_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = ?");
~~~

may **fail** to auto-compute the routing key because `tenant_id` is hardcoded as a literal instead of bound. In Driver 4.x, the routing key is auto-derived only when **every partition key component is bound as a variable**. Hardcoding literals in SQL skips full prepared routing metadata.

### 5.3. SimpleStatement: Does Not Auto-Derive Keys from CQL Strings

When calling:

~~~java
SimpleStatement simple = SimpleStatement.newInstance(
    "SELECT * FROM route_lab.events_by_tenant_day " +
    "WHERE tenant_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = '2026-11-21'");
~~~

The driver **does not parse arbitrary simple CQL strings to compute a routing key**. Even when the text contains both partition key components, `simple.getRoutingKey()` defaults to `null`. The query plan then round-robins across local nodes without token-aware preference.

You can supply properly encoded `routing keyspace` and `routing key` (or routing token) manually, though encoding composite keys **must use Driver APIs/codecs**—never concatenate UUID + date strings and hash manually. In most applications, **`PreparedStatement` with all partition components bound** is cleaner, prevents CQL injection, and saves server parsing.

### 5.4. Cases Where Routing Key Is Missing or Unusable

| Pattern | Auto Routing Key? | Reason |
|---|---|---|
| `SELECT ... WHERE tenant_id = ? AND event_day = ?` in prepared query | Usually **yes** | Both partition key components are bound variables |
| Prepared query binds `event_day` while `tenant_id` is a literal | Usually **no** | Missing variable metadata for one partition key component |
| `SimpleStatement.newInstance("SELECT ...")` with literal keys | **Not auto-derived** | Driver does not parse simple query text for keys |
| Prepared query filtering on secondary **index** without partition key | Usually no single partition | Query may span multiple token ranges |
| Query with `IN` across multiple partition keys | No single default routing key | One request targets multiple partitions; design specifically |
| Multi-partition `BatchStatement` | Cannot treat batch as simple single-partition routing | Driver may take routing metadata from a child; **does not** optimize cross-partition batches |
| Schema/token map disabled | No data to compute replicas | Policy falls back without ownership info |

**Warning:** Having a valid routing key never makes a bad query cheap. Huge partitions, heavy tombstones, or `ALLOW FILTERING` still cause high p99 even when hitting a local replica.

## 6. How Do CQL Partition Key, RF, and Locality Relate?

### 6.1. Partition Key Determines Data Locality

In `NetworkTopologyStrategy`, RF is configured **per DC**:

~~~sql
CREATE KEYSPACE route_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

This schema only **actually achieves the target RF** when each DC has enough nodes/racks per topology. Putting RF=3 on a two-node DC does not conjure a third node. When evaluating routing, verify:

- Which nodes are **actually** present and `Up/Normal`.
- The replica list for partition K in the **specific keyspace**.
- RF in the application's DC and secondary DCs.
- Query CL (`LOCAL_ONE`, `LOCAL_QUORUM`, `EACH_QUORUM`, etc.) and its exact semantics.

**Client locality** does not mean one local replica satisfies every request. With `LOCAL_QUORUM` and RF=3 in the local DC, the coordinator still waits for local quorum confirmations. Picking a local replica as coordinator saves a hop—it **does not change CL requirements**.

### 6.2. Three Topologies Running the Same Query

| Topology | Routing Priority | Key Consideration |
|---|---|---|
| `dc1` 4 nodes/RF=3, app in `dc1` | 3 local replicas of partition | Saves a hop compared to the 4th non-replica local node |
| `dc1` 3 nodes/RF=3, app in `dc1` | All 3 nodes are replicas | Tests won't easily show token-awareness difference |
| App in `dc2`, keyspace RF only in `dc1` | Local policy picks `dc2` coordinator, but data lives in `dc1` | A "local coordinator" **does not** make data local; fix replication/placement |

Building a low-WAN multi-region system requires aligning **app placement**, **driver `local-datacenter`**, and **keyspace RF**. Fixing one without checking the other two fails to guarantee locality.

### 6.3. Contact Points Are Not the Replica List

A service may bootstrap via node A and, after loading metadata, open connections to other local nodes per policy. If A later goes down, existing connections keep serving via B/C/D. You do not need to list **every node** as a contact point; supply a few stable contact points in the target DC to improve startup resilience.

**Never hide multiple nodes behind a generic TCP load balancer** without checking address discovery/NAT models: the Cassandra Driver normally expects to reach each node's **advertised** address after bootstrap. In Kubernetes, cloud VPCs, or NAT setups, configure an appropriate address translator/transport. This is a common infrastructure issue often misdiagnosed as "token-aware routing is broken".

## 7. Java Driver: Inspecting Routing Key, Replicas, and Coordinator

### 7.1. Java Driver 4.x Example with Full Metadata

This snippet assumes:

- An active `CqlSession session` connected to the lab cluster with the right local DC.
- Keyspace `route_lab` and table `events_by_tenant_day` exist.
- Token map and schema metadata are enabled.
- Sample data uses partition key `(tenant_id, event_day)`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.metadata.Node;
import com.datastax.oss.driver.api.core.metadata.TokenMap;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Set;
import java.util.UUID;

void inspectRouting(CqlSession session,
                    UUID tenantId, LocalDate day,
                    Instant from, Instant until) {
    PreparedStatement prepared = session.prepare(
        "SELECT event_time, event_id, payload " +
        "FROM route_lab.events_by_tenant_day " +
        "WHERE tenant_id = ? AND event_day = ? " +
        "AND event_time >= ? AND event_time < ? LIMIT ?");

    BoundStatement request = prepared.bind(
            tenantId, day, from, until, 100)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(50);

    System.out.println("Routing keyspace = " + request.getRoutingKeyspace());
    System.out.println("Routing key available = " +
        (request.getRoutingKey() != null));

    if (request.getRoutingKey() != null) {
        session.getMetadata().getTokenMap().ifPresent(tokenMap -> {
            Set<Node> expectedReplicas = tokenMap.getReplicas(
                "route_lab", request.getRoutingKey());
            for (Node replica : expectedReplicas) {
                System.out.println("Replica: " + replica.getEndPoint()
                    + ", DC=" + replica.getDatacenter());
            }
        });
    }

    ResultSet rows = session.execute(request);
    ExecutionInfo info = rows.getExecutionInfo();
    Node coordinator = info.getCoordinator();
    System.out.println("Coordinator: " +
        (coordinator == null ? "(unknown)" : coordinator.getEndPoint()));
    System.out.println("Speculative executions started: " +
        info.getSpeculativeExecutionCount());

    rows.forEach(row -> row.getUuid("event_id"));
}
~~~

**What this code proves and does not prove:**

1. `getRoutingKey() != null` confirms the driver computed **routing bytes** for the statement; it does not prove a replica was chosen. Inspect the coordinator and query plan/metadata.
2. `TokenMap.getReplicas("route_lab", routingKey)` returns **expected replicas from driver metadata**, potentially spanning multiple DCs regardless of connection state. It **does not** prove every node's data is in sync or that a given node served this request.
3. `ExecutionInfo.getCoordinator()` reports the coordinator for the **successful execution**; it does not list all replicas involved in satisfying CL. `ResultSet.getExecutionInfo()` reflects current execution info when called; with paging, subsequent pages have their own execution info.
4. If output always prints one node, do not jump to blaming the policy: other replicas may be down/slow/ignored, sample size too small, the cluster may have only one eligible node, or every test query hit the same partition with low variance.

Never call `setRoutingKey(...)` manually on a properly bound prepared query. Passing mis-encoded composite keys skews routing or misleads replica checks. Leave query plans and retries to built-in policies unless you have a thoroughly tested requirement.

### 7.2. Why Not Cache One Metadata Snapshot Forever?

Driver metadata updates on cluster bootstrap/decommission, node Up/Down, RF/schema edits, and topology changes; `session.getMetadata()` returns an immutable snapshot at call time. **Never cache a metadata snapshot indefinitely** to inspect replicas while the cluster evolves. Call `getMetadata()` fresh when verifying and listen to node events/schema agreement.

During topology transitions, `TokenMap` can temporarily **lag** behind a node that has not updated yet. Measure routing across multiple intervals after schema/token metadata stabilizes rather than sampling once mid-bootstrap.

### 7.3. Observing Another Query Type: SimpleStatement

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement statement = SimpleStatement.newInstance(
    "SELECT event_time, event_id FROM route_lab.events_by_tenant_day " +
    "WHERE tenant_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = '2026-11-21'");

System.out.println("Routing keyspace: " + statement.getRoutingKeyspace());
System.out.println("Routing key: " + statement.getRoutingKey());

// You can set keyspace alone:
statement = statement.setRoutingKeyspace("route_lab");
// Setting keyspace alone is NOT enough for token-aware replica selection without a routing key.
~~~

Remember Driver 4.x statements are **immutable**: `setRoutingKeyspace` returns a new instance; forgetting to reassign leaves the old statement unchanged. Do not treat this snippet as production guidance: it is a **metadata inspection example**, whereas production code should use prepared queries for automatic routing.

## 8. Cross-Datacenter Failover and Consistency

### 8.1. No Automatic Cross-DC Failover by Default

Per Java Driver 4.19 documentation, `DefaultLoadBalancingPolicy` connects only to the **local DC** and marks remote nodes `IGNORED`. If the entire local DC fails, the driver **does not automatically** switch to another DC.

This fits multi-region architectures: apps normally sit alongside Cassandra in each region; if an entire region fails, **infrastructure-level app/load-balancer failover** shifts traffic to the healthy region where both app instances and Cassandra replicas live. Enabling driver-level failover must be intentional because it introduces WAN traffic/latency and alters CL semantics.

### 8.2. Driver 4.10+ Failover Options

**Illustrative only for labs understanding topology and CL**—never enable blindly in production:

~~~hocon
datastax-java-driver {
  basic.load-balancing-policy.local-datacenter = dc1

  advanced.load-balancing-policy.dc-failover {
    max-nodes-per-remote-dc = 2
    # By default, DO NOT fail over LOCAL_ONE/LOCAL_QUORUM/LOCAL_SERIAL.
    allow-for-local-consistency-levels = false
  }
}
~~~

With `max-nodes-per-remote-dc = 0` (default), remote failover is off. Setting a positive value opens pools to that many remote nodes per DC and appends them **after local nodes** in query plans when policy permits. This **does not** change keyspace replication automatically and **does not** guarantee queries succeed if RF/CL mismatches.

### 8.3. Why Not Enable Failover for `LOCAL_QUORUM` Mechanically?

Suppose a keyspace has:

~~~sql
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 1
}
~~~

For `LOCAL_QUORUM`, the required replica count depends on the **coordinator's DC** and that DC's RF. If the coordinator fails over from `dc1` (RF=3) to `dc2` (RF=1), each DC's local quorum **differs**. Therefore, Driver 4.x **disables remote failover by default** for local consistency levels.

`allow-for-local-consistency-levels = true` exists for experts accepting the semantic trade-offs, yet **never use it as a quick fix for a failing DC**. First establish a DR plan, per-DC RF, stale-read policies, data reconciliation, failure testing, and backup-region capacity.

### 8.4. Failover Does Not Guarantee Latest Data

Even when a remote coordinator accepts a query, Cassandra still enforces CL/RF, timestamp conflict resolution, and replication state. If the remote DC lacks full replicas or lagged during an outage, routing cleanly over TLS does not guarantee business freshness. Product designs must explicitly define **RPO, RTO, read/write consistency, and acceptable staleness**.

## 9. Retries, Speculative Execution, Idempotence, and Locality

### 9.1. A Query Plan Is Not an Execution History

When a statement's preferred replicas are [A, B, C] followed by local non-replica D:

- Normal requests succeed at A; B/C/D receive no direct driver request.
- If A is unavailable, the retry policy may permit trying the next node in the query plan.
- If speculative execution is enabled and the query is eligible, the driver may launch a backup execution to another coordinator before the first completes.
- Cassandra coordinators still contact replicas per CL; **driver executions** do not equal **replica messages**.

**Never mark every request `idempotent=true` just to enable retries/speculation.** LWTs, counter increments, or non-idempotent writes can execute twice unintentionally. Only set it when statement semantics are genuinely safe and retry/speculation policies are reviewed.

### 9.2. Hot Partitions: Token Awareness Concentrates Load

Suppose 80% of traffic hits partition K with RF=3 on A/B/C. Token awareness routes directly to those three replicas. That fulfills hop reduction, yet loads A/B/C far more than D since D does not own K. That is not a "broken load balancer".

| Approach | Effect | Limitation |
|---|---|---|
| Keep token-aware, fix partition key/bucketing | Spreads data and traffic across more tokens/ranges | Requires schema/query redesign; may increase fan-out |
| Cache hot reads appropriately | Cuts replica read pressure for certain patterns | Does not fix hot writes or insufficient RF |
| Throttle client concurrency | Protects p99/timeouts under peak spikes | Does not raise sustained cluster throughput |
| Add nodes + rebalance tokens | Increases overall cluster capacity | Partition K still resides on only RF replicas |
| Route via non-replica coordinator to "share load" | Shifts some coordinator CPU to node D | Adds network hops and still hits replicas A/B/C; not a root fix |

Separate **coordinator load balancing** from **data load balancing**. Data distributes by partition key and RF; the driver never moves a partition onto an idle node per query.

## 10. CQL + Java Lab: Measure Real Routing Instead of Guessing

### 10.1. Set Up a Topology Separating Replicas from Non-Replicas

The ideal lab has **at least four nodes in `dc1` with RF=3**; then each partition has three local replicas and at least one non-replica node. You can add `dc2` to explore locality. On smaller clusters, the lab still runs, though replica vs. non-replica coordinator differences become harder to observe.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

**Caution:** DC names in examples must match real metadata; hostnames are placeholders. Never create an RF=3 keyspace on a single-node cluster expecting `CL=LOCAL_QUORUM` to work. Use isolated labs—never run failover experiments in production.

### 10.2. Create Table and Sample Data

In `cqlsh` on a **lab cluster** where `dc1` actually has four nodes:

~~~sql
CREATE KEYSPACE IF NOT EXISTS route_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS route_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO route_lab.events_by_tenant_day
    (tenant_id, event_day, event_time, event_id, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:15:00Z',
    22222222-2222-4222-8222-222222222222,
    'temperature=21'
);

SELECT event_time, event_id, payload
FROM route_lab.events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21';
~~~

`IF NOT EXISTS` **will not alter** an existing keyspace/table with different RF/schema. When reusing a lab, run `DESCRIBE KEYSPACE route_lab` and `DESCRIBE TABLE route_lab.events_by_tenant_day`. A single row tests statement syntax; real load measurements need many partition keys and iterations.

### 10.3. Verifying Replicas from Node Metadata

For **composite partition keys**, `nodetool getendpoints` requires version-specific key serialization syntax; never manually concatenate UUID and date strings assuming that computes the token. To identify a sample key's replicas, prefer:

1. `TokenMap.getReplicas(keyspace, BoundStatement.getRoutingKey())` in Java.
2. Topology metadata and `nodetool status` on nodes.
3. Use `nodetool getendpoints` only after confirming your release's exact composite-key formatting rules.

When cross-checking DC/rack across nodes, watch node state, token ring, and RF after bootstrap/repair. **Metadata replica placement** does not prove 100% value synchronization across replicas.

### 10.4. Run Three Conditional Variants

| Variant | Input/Statement | Pre-Test Prediction |
|---|---|---|
| **A — prepared/bound** | Binds both `tenant_id` and `event_day` | `getRoutingKey()!=null`; local replicas prioritized |
| **B — simple literal** | Text embeds the same two partition keys without routing key | No auto routing key; coordinator may be a non-replica |
| **C — bound with token-map disabled** | Keeps prepared query, disables token map on a **separate lab session** | Statement still has routing key, yet policy lacks `TokenMap` to find replicas |

HOCON example for **Variant C** (never use in production when token awareness is needed):

~~~hocon
datastax-java-driver {
  basic.load-balancing-policy.local-datacenter = dc1
  advanced.metadata.schema.enabled = true
  advanced.metadata.token-map.enabled = false
}
~~~

**Key point:** Variant C does not mean the driver "got the partition key wrong"; it isolates `TokenMap`'s role. Disabling schema metadata also strips `TokenMap`'s replication strategy lookup. Never judge policy quality from a single query's latency.

### 10.5. Run Across Many Partitions and Record Coordinators

To compute the rate of local-replica coordinators, per **request**:

~~~text
known = bound.getRoutingKey() != null && tokenMap is present
expected_replicas = tokenMap.getReplicas("route_lab", bound.getRoutingKey())
coordinator = resultSet.getExecutionInfo().getCoordinator()

if known && coordinator != null:
    coordinator_is_replica = expected_replicas.contains(coordinator)
    coordinator_dc = coordinator.getDatacenter()
    local_replica = coordinator_is_replica && coordinator_dc == "dc1"
~~~

Aggregate across **many distinct `tenant_id` values and iterations**, e.g., 1,000 partitions × 10 requests if your lab cluster has capacity. Never log sensitive raw tenant identifiers; group by hashes or anonymized labels.

Measure simultaneously:

- Percentage of **coordinators that are local replicas** for requests with a routing key.
- Coordinator distribution by node and by DC.
- End-to-end p50/p95/p99 and local read latency.
- Internode network bytes/packets, coordinator CPU, and replica CPU.
- Retry counts, speculative execution counts, timeouts, and reconnects.
- Up/Down node counts, metadata freshness, and SSTables/tombstones/hot partitions.

**Why multiple nodes are required:** if RF=3 and the local DC has only 3 nodes, "coordinator is replica" hits 100% **even for Variant B**, proving nothing about token awareness.

### 10.6. Results Table — Fill Only with Measured Cluster Numbers

| Variant | % with Routing Key | % Coordinator Is Local Replica | Coordinator Entropy/Distribution | Read p99 (ms) | Internode Bytes/Request | Errors/Retries |
|---|---|---|---|---|---|---|
| A: prepared + TokenMap | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |
| B: simple literal | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |
| C: prepared, TokenMap off | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |

Repeat trials multiple times, alternating A/B/C order while keeping partitions, CL, payloads, query count, warm-up, page size, and concurrency constant. No **hypothetical** numbers are pre-filled so examples are never mistaken for measured evidence.

## 11. Observing and Troubleshooting Routing Issues

### 11.1. Diagnostic Checklist When p99 Rises or Traffic Hits the Wrong DC

1. **Read effective driver config:** version, `local-datacenter`, policy, custom profiles, contact points, and address resolution.
2. **Cross-check topology:** `nodetool status`, actual DC/rack, and keyspace RF; never trust a sample config file's DC name.
3. **Check routing metadata:** `SimpleStatement` vs. `BoundStatement`? Are all partition key components bound? Is `getRoutingKey()` null?
4. **Check `TokenMap`:** are schema/token-map enabled, is the keyspace in metadata, and did recent topology changes refresh?
5. **Inspect actual coordinators:** `ExecutionInfo.getCoordinator()` by node/DC; are retries, speculative executions, or slow-node exclusions firing?
6. **Compare CL and replicas:** does local DC RF satisfy `LOCAL_QUORUM`? Are replicas down, bootstrapping, or out of sync?
7. **Check hot keys and query model:** partition key skew, large partitions, tombstones, compaction/repair backlogs.
8. **Check network/JVM:** DNS, TLS/SANs, firewalls, native ports, GC, pool saturation, event-loop backlogs, and remote RTT.

### 11.2. Common Symptoms and Causes

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `BoundStatement` still not token-aware | Not all partition components bound; routing key null | Print `getRoutingKeyspace()/getRoutingKey()` and prepared CQL |
| Routing key present yet coordinator is not a replica | `TokenMap` disabled/stale, replicas down/slow, failover, or retries | Compare `getReplicas`, coordinator, and topology |
| App in `dc1` queries via `dc2` | Wrong local DC, another profile, remote failover on, app moved | Inspect runtime config and coordinator DC |
| High WAN query latency | App not co-located with DC; keyspace RF only in remote DC | Check local DC, replication, and packet latency |
| Contact points healthy yet app misses other nodes | Advertised addresses unreachable; firewall/TLS/DNS | Inspect driver discovery logs and native connections |
| Uneven load across nodes | Hot partitions, specific key replicas, slow avoidance, or down nodes | Token/key histograms, coordinator/replica load |
| Disabling `TokenMap` leaves p99 unchanged | Hot cache, RF=all, light load, or underpowered test | Use a 4-node RF3 lab, test many keys and internode bytes |
| `LOCAL_QUORUM` throws `Unavailable` with 1 node Up | RF=3 requires 2 responding local replicas | Check CL, local RF, and replica states |
| DC failover behaves unexpectedly | Local CL failover off by default or remote RF differs | Inspect DC failover options, consistency, and DR plan |
| Newly added node causes odd query plans | Metadata/schema agreement still transitioning | Wait for topology stability; refresh and inspect token map |

Never abuse `Request.setNode()` to force all queries onto one host. That API **bypasses the load balancing policy** for the statement and is meant only for node-local queries like `system.local` or special admin tasks. Pinning nodes on business workloads breaks load distribution/token locality and fails when that node goes down.

## 12. Scenario Exercises

### Exercise 1 — Distinguishing Coordinator and Replica

A DC has A/B/C/D with RF=3. Partition K lives on A/B/C. Java sends a query to D and reads cleanly. Is D a replica of K? Why did the request still succeed?

**Hint:** D is a **non-replica coordinator**; it contacts A/B/C to read per CL. Request success does not prove optimal routing.

### Exercise 2 — Why Did a Prepared Query Lose Its Routing Key?

A table has `PRIMARY KEY ((tenant_id, event_day), event_time)`. A developer prepares a query with `tenant_id` hardcoded as a literal and binds only `event_day`. The driver returns `getRoutingKey() == null`. Is this a bug?

**Hint:** Per Driver 4.x behavior, routing keys are auto-derived only when **every partition key component is bound as a variable**. Prepare `tenant_id = ? AND event_day = ?` and bind both.

### Exercise 3 — Wrong Local DC

A service runs near `dc2`, yet driver config specifies `local-datacenter = dc1`. RF is equal in both DCs. What happens?

**Hint:** Coordinators are preferred in `dc1`, adding WAN RTT to requests; configure the DC closest to the app and verify certs, addresses, replicas, and CL. Never swap only contact points while forgetting `local-datacenter`.

### Exercise 4 — RF Equal to Node Count

A lab has three nodes with RF=3. Both `SimpleStatement` and `BoundStatement` show 100% of coordinators are replicas. Does that prove token-aware routing is useless?

**Hint:** No. Every local node is a replica, so the test lacks non-replicas to compare against. Add a fourth lab node with RF=3 or test a topology containing non-replica nodes.

### Exercise 5 — Enabling Cross-DC Failover

A cluster has `dc1` RF=3 and `dc2` RF=1. Services use `LOCAL_QUORUM`. Ops wants to enable `allow-for-local-consistency-levels=true` for quick failover. What is the risk?

**Hint:** Local quorum depends on RF in the coordinator's DC: `dc1` requires 2, `dc2` only 1. That silently alters consistency semantics and can spike WAN traffic/staleness. Establish DR design, failure testing, and approvals first.

### Exercise 6 — Hot Partition Still Overloaded

Token-aware prepared statements work properly, yet A/B/C run hot while D sits idle. Should you force the coordinator to D?

**Hint:** Not a root fix. Replicas for the hot partition remain A/B/C; routing via D adds an extra hop. Redesign keys/buckets, caching, or concurrency limits per access pattern.

### Exercise 7 — Keyspace and Routing Token

For the same partition token, keyspace X has RF=2 and keyspace Y has RF=3. The driver knows the token without a routing keyspace. Can it reliably pick the right replica set?

**Hint:** No. Determining replicas requires **keyspace replication metadata**; a routing token alone cannot resolve replica placement without the keyspace.

### Exercise 8 — Contact Point: Seed or Coordinator Pin?

The driver boots via `db1`, and subsequent requests execute on `db2` and `db3`. Is this abnormal?

**Hint:** Normal. Contact points bootstrap discovery; the driver learns other nodes and the policy selects coordinators per query.

### Lesson Completion Checklist

- [ ] Can distinguish coordinator, replica, contact point, and query plan.
- [ ] Understand that the partition key (all components) determines the token; clustering columns do not.
- [ ] Know that Driver 4.x's `DefaultLoadBalancingPolicy` is token-aware by default.
- [ ] Configure `local-datacenter` matching application placement and Cassandra topology.
- [ ] Provide `routing keyspace + routing key + token map` to prioritize local replicas.
- [ ] Use prepared/bound statements binding all partition components instead of expecting `SimpleStatement` to parse keys.
- [ ] Can inspect `getRoutingKey()`, `TokenMap.getReplicas()`, and `ExecutionInfo.getCoordinator()`.
- [ ] Know query plans include fallbacks/retries and coordinators do not alter CL ACK rules.
- [ ] Understand cross-DC failover is **off by default**, with strict constraints on local CL failover.
- [ ] Set up a lab with enough nodes to compare token-aware vs. round-robin without `RF=all` masking results.
- [ ] Can investigate hot partitions, topology, token metadata, WAN traffic, and p99 using measurements.

## 13. References

1. Apache Java Driver 4.19 — [Load Balancing](https://apache.github.io/cassandra-java-driver/4.19.0/core/load_balancing/): default policy, local DC, node distances, token-aware query plans, and cross-DC failover.
2. Apache Java Driver 4.19 — [Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): partition key metadata, bind variables, and automatic routing keys.
3. Apache Java Driver 4.19 — [Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): routing keyspace/key/token, statement immutability, and CL.
4. Apache Java Driver 4.19 — [TokenMap API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/metadata/TokenMap.html): looking up replica sets by keyspace and partition key bytes/tokens.
5. Apache Java Driver 4.19 — [Performance](https://apache.github.io/cassandra-java-driver/4.19.0/core/performance/): prepared queries, schema/token map metadata, and CPU/memory trade-offs.
6. Apache Java Driver 4.19 — [Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): HOCON, execution profiles, policies, and driver options.
7. Apache Java Driver 4.19 — [ExecutionInfo API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html): coordinator and execution metadata.
8. Apache Cassandra Documentation — [Dynamo Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): partitioning, token ring, replication, and consistency.
9. Apache Cassandra Documentation — [CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): partition/clustering keys and `NetworkTopologyStrategy`.
