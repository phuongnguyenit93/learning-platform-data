# High Availability Goals and Single-Server Scaling Limits

## 1. The Problem: Is One Powerful Neo4j Server Enough for Every Goal?

A customer management application might use Neo4j to store `(:Customer)-[:PLACED]->(:Order)`, look up connected relationships, detect transaction patterns, and write orders via the Java Driver/Spring Data Neo4j. When initially deployed, a single Neo4j server with appropriate CPU, RAM, SSD, and page cache can meet all requirements. However, as traffic grows or continuous availability is required, two distinct questions arise:

1. **High availability (HA):** Can the system still answer queries or accept writes when a server, disk, network link, or deployment zone fails?
2. **Scaling:** As data volume, client count, or read/write load increases, how far can capacity grow by upgrading a single machine; when must work be distributed?

A machine equipped with NVMe and abundant RAM **does not automatically become HA**: the process, operating system, host, power supply, or deployment zone remain single points of failure. Conversely, a multi-server cluster **does not automatically make every Cypher write statement faster**. For a standard Neo4j database, primaries coordinate to provide fault tolerance, while secondaries primarily increase read capacity.

In the **Clustering and Scaling** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson explains **high availability goals and single-server scaling limits**, framed in the context of property graphs, Cypher, indexes/constraints, data ingestion, the Java Driver, and Spring Data Neo4j.

**Learning outcomes:**

- Distinguish availability, durability, consistency, RPO, RTO, and SLI/SLO metrics.
- Identify CPU, RAM/page cache, I/O, transaction log, lock, and network bottlenecks on a single server.
- Understand the **primary, secondary, writer, and quorum** model per Neo4j database.
- Explain why **3 primaries tolerate 1 primary failure for writes**, whereas **1 primary + multiple secondaries** does not provide equivalent write fault tolerance.
- Choose scale-up, read scale-out, workload/database splitting, or an appropriate data partitioning solution based on measurements.
- Design load tests and failover tests on an **isolated environment**, without disrupting production.

> **Versions and editions:** Cluster content references Neo4j Enterprise and the Operations Manual of current versions at the time of writing. Self-managed clustering, quorum, and specific administrative commands **do not apply as-is to Community Edition or all Neo4j Aura tiers**. Each release may change terminology, topology limits, scaling options, or interfaces. When deploying, consult the documentation for the exact version/edition.

## 2. High Availability Is Not Just a Single “Uptime” Number

For a database, a system may be **readable but not writable**, or writable with latency that causes the application to time out. Therefore, before choosing a cluster, you must clearly define “available” in business terms.

| Concept | Question to answer | Example |
|---|---|---|
| **Read availability** | Do graph read APIs still succeed within the latency limit? | Find recent orders within 300 ms |
| **Write availability** | Can APIs that create/update nodes and relationships commit? | Create an `Order` and link it to a `Customer` |
| **Durability** | Is committed data preserved across failures within the promised scope? | No loss of acknowledged transactions |
| **Consistency** | Will subsequent reads see previously written transactions or might they encounter stale data? | Read an order immediately after creating it |
| **RPO** | Up to what point in time can data loss be tolerated in a disaster? | Target RPO of 5 minutes |
| **RTO** | What is the target duration to restore the service to a servable state? | Target RTO of 15 minutes |

**Do not conflate these concepts:**

- Adding a read replica can improve **read** capability when the writer fails, but **does not guarantee writes** if the database has only one primary.
- Replication provides certain fault tolerance, but **does not replace backups**, because an accidental committed delete can be replicated.
- A system that automatically switches writers after failover still incurs a **brief interruption**, timeouts, or retries; HA does not mean 100% uptime.
- RPO/RTO belong to disaster recovery planning; an availability SLO measures service experience over a time window.

### 2.1. Writing SLIs Based on User Behavior

A **Service Level Indicator (SLI)** can be defined as:

\[
\text{Write availability SLI} =
\frac{\text{number of valid write requests that succeed on time}}
{\text{number of measured valid write requests}}
\]

When measuring, you must clearly specify the denominator: whether requests blocked by the network before reaching the database are counted, whether timeouts count as errors, whether responses after retries count as successes, and whether invalid requests are excluded.

A similar SLI can be created for reads with the condition `latency <= threshold`. Measuring a `RETURN 1` statement is not representative of APIs that traverse paths across a graph or transactions that create multiple relationships.

## 3. Calculating the Error Budget from an Availability Target

Suppose the SLO window is **30 days**:

\[
T = 30\times24\times60 = 43{,}200\text{ minutes}
\]

\[
\text{Downtime budget} = T \times (1 - \text{SLO})
\]

| Hypothetical availability SLO | Maximum outage duration over 30 days |
|---|---:|
| 99% | 432 minutes = 7 hours 12 minutes |
| 99.9% | 43.2 minutes = 43 minutes 12 seconds |
| 99.95% | 21.6 minutes = 21 minutes 36 seconds |
| 99.99% | 4.32 minutes = 4 minutes 19.2 seconds |

This is a **theoretical conversion** when using a time-based SLO; for an SLO calculated by the ratio of successful requests, it does not automatically convert accurately into minutes if traffic varies by hour of day.

For example, an ordering application sets a **write availability of 99.95%** over 30 days. A 3-minute failover event consumes part of the 21.6-minute budget. If maintenance, network errors, application timeouts, and failovers combined exceed the budget, the target is missed even if every server was “up at some point.”

**Practical point:** set separate **read SLO** and **write SLO** targets if their serviceability differs. `SHOW SERVERS` reporting that a server is reachable does not prove that business queries are meeting their SLO.

## 4. What Single Points of Failure Does One Server Have?

~~~mermaid
flowchart TB
    U["Java / Spring Data Neo4j application"] --> N["Single Neo4j server"]
    N --> P["Neo4j process + JVM"]
    N --> C["CPU, heap, page cache, and native memory"]
    N --> S["Volume: store, indexes, transaction log"]
    N --> W["NIC, DNS, TLS, and network connectivity"]
    N --> O["OS / VM / container / physical host"]
    O --> Z["Power supply, AZ / data center, operations"]
~~~

A single server can stop responding because:

- Process crash, upgrade requiring restart, JVM OOM, GC pauses, or thread starvation.
- CPU throttled by container/VM quotas, poor Cypher workloads, or queries generating excessive numbers of paths.
- Insufficient RAM for heap, native memory, page cache, and the operating system.
- Volume full, filesystem error, slow transaction log flush, or total loss of the storage device.
- NIC, DNS, TLS, firewall, or routing prevents clients from connecting.
- Physical host replacement, power outage, or failure of an entire deployment zone.
- Operational mistakes: dropping a database, altering user/role permissions, changing configuration, or deploying a faulty plugin.

**Scale-up only addresses certain capacity limits**, not single points of failure. A machine with 128 CPUs and 1 TiB RAM can still go down if the host loses power. Having backups helps recover after an incident, but does not keep requests succeeding continuously during recovery.

## 5. Single-Server Scaling Limits: Contending Resources

| Resource | Workload causing pressure | Typical symptoms | Verification approach |
|---|---|---|---|
| **CPU** | Deep traversals, filtering/aggregation, Cypher parsing, response serialization | CPU near ceiling, p95 rises as requests increase | Query plan, CPU per core, sampling/profiling |
| **Heap / GC** | Large `collect`, result processing, transaction state | GC pauses, heap pressure, OOM | Heap/GC, transaction memory, batch size |
| **Neo4j page cache** | Random lookups, traversing many graph/index pages | Cache misses increase, “cold” reads slow down | Page cache hit/miss and working set |
| **Disk / IOPS** | Random reads, index updates, checkpoints | I/O latency and queue depth rise | OS/cloud volume metrics and `PROFILE` |
| **Transaction log** | Many write transactions, continuous small commits | Commit p95/p99 rises; pressure on log volume | Write latency, log activity, batching |
| **Locks** | Multiple writers updating the same ID/supernode | Lock waits, retries/deadlocks, flat throughput | Transaction wait/lock diagnostics |
| **Network** | Returning very large graphs, many small round trips | High RTT/bytes/s, timeouts | Client tracing, NIC metrics, payload |
| **Connection pool** | Unclosed sessions/results, too many clients | Acquire timeouts even when server is not saturated | Pool metrics, Session hold duration |

There is no single “maximum number of nodes on one server” figure applicable to all graphs. Practical capacity depends on property sizes, relationship density, node degree distribution, number of indexes, workload, RAM, storage latency, cache, and SLO requirements.

### 5.1. Supernodes

Suppose a node `(:Topic {name:'popular'})` has millions of relationships. The query:

~~~cypher
MATCH (t:Topic {name:$name})-[:MENTIONED_BY]->(p:Post)
RETURN p
~~~

can produce an oversized result set, incurring high expansion, result serialization, and network costs. Adding RAM or multiple secondaries **does not automatically fix** a request whose algorithm/query must process millions of relationships.

Mitigation approaches include: clarifying the business objective, filtering early, indexing the starting point, limiting results, separating analytical queries from OLTP, or remodeling when genuinely necessary.

### 5.2. The Bottleneck Is Not Necessarily RAM

A 99.8% page cache hit ratio can still coincide with slow transaction commits due to high `fsync` latency on the log volume. Conversely, a query with high `DB Hits` and CPU-heavy traversal can be slow even when data pages are already in RAM. **Measure before adding memory.**

## 6. Saturation Law: Adding Concurrency Does Not Always Increase Throughput

In a data ingestion pipeline or a query-heavy API:

- Let `λ` denote the arrival rate of requests per second.
- Let `μ` denote the sustainable successful processing capacity per second under measured conditions.

If `λ > μ` over a sustained period, backlogs/queues grow. When pushing more clients, the system may spend more time waiting on locks, pools, or I/O instead of processing faster.

**Hypothetical example, not a Neo4j benchmark:**

| Concurrent workers | Successful write throughput | Batch latency p95 | Retry rate |
|---:|---:|---:|---:|
| 1 | 1,100 rows/s | 35 ms | 0% |
| 2 | 2,000 rows/s | 47 ms | 0.1% |
| 4 | 2,300 rows/s | 105 ms | 0.7% |
| 8 | 2,250 rows/s | 240 ms | 4% |

In the example, increasing workers from 4 to 8 **does not increase throughput**, while p95 and retries worsen. That indicates approaching a bottleneck; you must measure CPU, lock waits, and storage to identify the cause rather than concluding “CPU is weak” from the table alone.

### 6.1. Amdahl’s Law: Limits of Parallelization

When a portion of work cannot be parallelized, speedup is bounded by:

\[
S(N)=\frac{1}{s+\frac{1-s}{N}}
\]

where `s` is the serial fraction and `N` is the ideal number of workers. If `s=0.3` and `N=4`, `S(4)≈2.11` rather than 4. This is a conceptual performance model, **not a formula for predicting how many Neo4j primaries accelerate writes**. For a database cluster, the write leader and quorum also introduce their own replication overhead.

## 7. Optimizing a Single Server Before Deciding to Scale Out

When SLOs are still met and downtime risk is acceptable, **scale-up** can be simpler and more cost-effective operationally than deploying a cluster.

A prioritized workflow:

1. **Confirm the business issue:** throughput, p95/p99, timeout rate, successful request count, recovery time.
2. **Inspect Cypher with `EXPLAIN`/`PROFILE`:** index seek/scan, `Rows`, `DB Hits`, aggregations, Cartesian products, path expansions.
3. **Ensure proper schema:** unique constraints for business IDs, indexes matching predicates/queries, without adding excessive useless indexes that slow writes.
4. **Reduce over-fetching:** return only needed columns, paginate root nodes before loading relationships, avoid N+1 from Java services/SDN repositories.
5. **Reduce client overhead:** use a long-lived Driver, short-lived Sessions, `executeRead`/`executeWrite`, and `UNWIND` batching instead of one round trip per node.
6. **Measure memory:** balance heap, page cache, native memory, and OS RAM; avoid blindly inflating caches.
7. **Measure storage:** IOPS, random read latency, durable write latency, cloud quotas, checkpoints, log volume.
8. **Test upgrading CPU/RAM/SSD one variable at a time**, keeping workload and data equivalent.

Scale-up has stopping points: cost/CPU, max RAM, single cloud instance ceilings, storage throughput, single-transaction speed, and the serial nature of writes. More importantly, scale-up **does not solve host fault tolerance**. If HA is mandatory, do not delay multi-replica design merely by continuing to upgrade a single server.

## 8. Enterprise Clustering: Server Does Not Equal Database Role

Under current Neo4j architecture, a **cluster** is a set of servers that can host multiple databases. **Each database has its own topology** with replicas (*allocations*) operating in modes:

- **Primary:** participates in the fault-tolerant write mechanism; one primary can be elected as the **writer/leader** for that database.
- **Secondary:** a replica that receives updates asynchronously, primarily serving **reads** and scaling read capacity.

A single server can host a primary of database A and a secondary of database B depending on constraints/topology. You should not say “this server is the primary for the entire cluster” when describing a specific database.

~~~mermaid
flowchart TB
    J["Java Driver neo4j:// + routing"] --> R["Per-database routing table"]
    R --> P1["Server 1: primary DB sales (writer)"]
    R --> P2["Server 2: primary DB sales (follower)"]
    R --> P3["Server 3: primary DB sales (follower)"]
    R --> S1["Server 4: secondary DB sales"]
    P1 <-->|"Raft / quorum replication"| P2
    P1 <-->|"Raft / quorum replication"| P3
    P1 -. "Asynchronous transaction pull" .-> S1
    P2 -. "Can provide update source" .-> S1
~~~

The diagram depicts **a single database `sales`**; in a multi-database cluster, the leader of each database may reside on a different server. The arrows do not replace detailed protocol specifications; the key takeaway is that primaries coordinate for durable writes, while secondaries catch up asynchronously.

**Note:** Clustering is a feature of supported editions/deployments; spinning up three Neo4j Community containers behind a load balancer does not give you a quorum/HA database.

## 9. Quorum: How Is Write Fault Tolerance Calculated?

For a group of primaries using a *majority* to commit writes, a typical configuration requires:

\[
Q(M)=\left\lfloor \frac{M}{2}\right\rfloor + 1
\]

where `M` is the number of primary allocations designed for a database, and `Q` is the number of primaries needed to achieve a majority.

| Number of primaries | Majority needed for writes | Primary failures tolerated while keeping majority | Interpretation |
|---:|---:|---:|---|
| 1 | 1 | 0 | Losing the primary loses write capability |
| 2 | 2 | 0 | Losing one primary leaves insufficient write quorum |
| 3 | 2 | 1 | Common HA configuration, tolerates one primary failure |
| 5 | 3 | 2 | Tolerates two primary failures, higher cost/latency |

To tolerate any `F` primary failures, the minimal model typically chooses:

\[
M = 2F + 1
\]

**Example:** `F=1` requires **3 primaries** distributed across at least three suitable servers/failure domains; `F=2` requires **5 primaries**. These formulas are topology/quorum conditions, **not absolute SLO guarantees**: network partitions, DNS/TLS, overloaded resources, failover time, or application bugs can still cause requests to fail.

### 9.1. Example Member-Loss Scenarios

- **Three primaries:** lose one server, two remaining primaries can maintain quorum and elect a new writer if needed. Write service may experience a brief interruption during failover and client retries.
- **Two primaries:** lose one, one remaining does not form a majority; do not claim write HA with only two replicas.
- **One primary + two secondaries:** there are multiple data replicas for reads, but only one primary has writer authority. If the primary fails, **there is no primary quorum to take over** under the same topology.

The purpose of quorum is to prevent two sides of a network partition from concurrently accepting conflicting write sequences. Losing quorum can leave a database read-only or unwritable; **never “fix” this by forcing both sides to write simultaneously**.

## 10. Secondaries Scale Reads, Not Turn One Database Into Multiple Writers

Secondaries receive transactions from primaries **asynchronously**, so they can lag behind the writer for a period of time. Adding secondaries allows distributing many read queries, such as:

- Dashboards and broad read reports.
- Lookup APIs with very high read request volume.
- Offloading analytical traffic from primaries serving transactional workloads.

However, adding secondaries also carries costs:

- Additional disk and RAM to hold a copy of the database/indexes.
- Additional network traffic to ship transactions and manage state.
- Need to monitor **replication lag**, catch-up, and consistency when reading recently written data.
- A single read query can still be slow if Cypher/indexes are unsuitable.
- Secondaries do not automatically create **multiple independent writers** for **the same database**.

A **3 primaries + 2 secondaries** configuration typically serves two different goals: primaries protect write capability when a member fails, while secondaries increase read capacity. Do not treat it as “5 writers for the same database.”

### 10.1. Does Adding Primaries Multiply Write Throughput?

**Not by default.** For a standard database, **only one primary is the writer** at a time. Transactions must be replicated/acknowledged by quorum; adding primaries can increase durability/fault tolerance, but also increases coordination, network traffic, and latency. If the workload is **write-heavy**, you must optimize transactions, indexes, contention, and writer sizing; to scale write throughput across data regions, evaluate supported **database splitting/sharding** solutions rather than merely adding primaries.

## 11. Comparing Scale-Up, Read Scale-Out, and Data Partitioning

| Option | What increases? | Solves write HA? | Limitations / trade-offs |
|---|---|---|---|
| **Scale-up single server** | CPU, RAM, page cache, SSD/IOPS | **Does not** remove single-machine SPOF | Hardware ceiling, maintenance downtime, hardware cost |
| **3+ primaries for database** | Fault tolerance and continued writes while quorum holds | **Yes** within designed failure scope | Network/quorum, cluster operations, failover/retries |
| **Add secondaries** | Read concurrency, offload reads from primaries | **Does not create additional writers** | Replication lag, per-replica resource cost |
| **Split multiple databases by domain/tenant** | Resource isolation and leader distribution across databases | Depends on per-database topology | Cross-database queries, schema/transaction management, operations |
| **Composite database / federation or supported sharding** | Can distribute data and some read/write workloads | Depends on specific architecture | Partition key design, cross-shard joins/traversals, consistency |
| **Managed Neo4j Aura or specialized scaling offerings** | Depends on tier and provided features | Depends on SLA and service policy | Tier limits, shared responsibility model, cost |

Recent Neo4j documentation covers **composite database/sharding** options and scaling offerings for cases where data exceeds a single server’s limits. Features, Aura availability, transaction types, and deployment capabilities vary by version. This is a **separate architectural problem**—do not assume a primaries/secondaries cluster automatically shards a graph.

A graph with frequent traversals **across domains/shards** may incur higher network and result-merging overhead than keeping the data on a single machine. Partitioning decisions must be grounded in actual access patterns, not node count alone.

## 12. Java Driver: Configuring Routing Properly to Leverage the Cluster

For the Neo4j Java Driver, URIs:

- `neo4j://` or `neo4j+s://` allows the Driver to use topology-aware routing mechanisms.
- `bolt://` or `bolt+s://` connects to a specific endpoint and **does not automatically perform cluster routing like `neo4j://`**.

Applications should create a **shared Driver**, explicitly select the database, and create short-lived Sessions:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class ClusterClientExample {
    static void run(String uri, String user, String password,
                    String database) {
        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase(database))) {
                session.executeWrite(tx -> {
                    tx.run("""
                        MATCH (o:QA001Order {orderId:$id})
                        SET o.status = 'CONFIRMED'
                        """, Values.parameters("id", "O42"))
                      .consume();
                    return null;
                });

                String status = session.executeRead(tx ->
                    tx.run("""
                        MATCH (o:QA001Order {orderId:$id})
                        RETURN o.status AS status
                        """, Values.parameters("id", "O42"))
                      .single().get("status").asString()
                );

                System.out.println(status);
            }
        }
    }
}
~~~

With the fixture in section 16, the expected value when running successfully on a test database is `CONFIRMED`. Within the same Session, the Driver manages the bookmarks needed to execute causally ordered transactions.

**Production checklist:**

1. The URI uses appropriate TLS/certificates and the endpoint has working routing.
2. `SessionConfig.forDatabase(...)` selects the right database rather than accidentally relying on the user’s home database.
3. `executeRead`/`executeWrite` express the right intent and are permitted to retry appropriate transient errors.
4. Transaction functions **must not contain non-idempotent HTTP/email side effects**, because the Driver may re-invoke the function during failover.
5. Connection pool and timeouts match writer election duration, RTT, and real p95; never let clients instantiate a new Driver per request.

This code snippet does not create a cluster itself; it only illustrates how an application accesses a database on a cluster **that is already deployed and operated properly**.

## 13. Bookmarks and Consistency During Failover or Secondary Reads

Suppose request A creates an `Order`, and immediately afterward request B from another Java instance reads the order list. If request B is routed to a secondary that is lagging behind in transactions, the result might not yet contain the newly committed order unless an appropriate causal chaining mechanism is used.

~~~mermaid
sequenceDiagram
    participant W as Write API
    participant P as Primary writer
    participant S as Secondary
    participant R as Read API
    W->>P: Create Order in transaction
    P-->>W: Commit succeeded + bookmark
    P-->>S: Replicate transaction asynchronously
    R->>S: Read without dependent bookmark
    Note over R,S: May not see the new Order yet
    R->>S: Read with appropriate bookmark
    Note over S: Wait until committed mark is reached before returning
~~~

**Bookmarks** allow a client to specify the transaction mark that subsequent queries must observe. The Java Driver manages bookmarks within a single Session; across multiple Sessions or multiple instances, the application must pass bookmarks or use a `BookmarkManager` with the proper scope.

Java Driver 5.x example using a shared bookmark manager for **one workflow**:

~~~java
import org.neo4j.driver.BookmarkManager;
import org.neo4j.driver.BookmarkManagers;
import org.neo4j.driver.SessionConfig;

BookmarkManager manager = BookmarkManagers.defaultBookmarkManager();

SessionConfig workflowConfig = SessionConfig.builder()
    .withDatabase("neo4j")
    .withBookmarkManager(manager)
    .build();

// Sessions belonging to the same workflow can use workflowConfig.
~~~

**Do not** blindly share one bookmark manager across all tenants, all users, and all jobs if they have no data dependencies with one another. Bookmarks help guarantee read-your-writes when passed accurately, but can increase latency due to waiting for a secondary to catch up. They **do not replace** access control, transactions, backups, or business consistency policies.

## 14. Failure Scenarios: What Can the System Still Serve?

| Scenario | Single server | 3 primaries | 3 primaries + secondaries |
|---|---|---|---|
| One Neo4j process/database copy fails | Loses reads and writes for that database | Can continue reads/writes if quorum remains and clients route properly | Can continue reads/writes; read capacity drops depending on which member failed |
| Writer/leader stops | No other writer | Remaining primaries can elect a new writer | Same; secondaries are not elected writer |
| One secondary stops | Not applicable | Not applicable | Does not affect write quorum; reduces read capacity |
| One primary lost, two primaries healthy | Not applicable | Maintains 2/3 quorum | Maintains 2/3 quorum |
| Two primaries lost in a 3-primary setup | Not applicable | Loses write quorum | Secondaries do not restore write quorum |
| Entire zone hosting all primaries fails | Service outage | Loses quorum / service | Loses write quorum even if secondaries in another zone can still serve reads |
| Valid delete caused by human error | Data deleted | Delete can replicate | Delete can replicate |

All descriptions above assume remaining members are **healthy**, the network supports quorum, sufficient resources exist, topology configuration is accurate, and clients can route. In practice, timeouts/retries or brief pauses can still occur during failure detection and writer election.

### 14.1. Correlated Failures Matter More Than Container Count

Three primaries placed on **one physical host** still share power, RAM, storage, and networking; a single host failure can take down all three. To tolerate zone failures, primaries must be distributed across failure domains (host/rack/AZ/data center) aligned with your fault assumptions and network capabilities.

However, spreading across distant regions increases **quorum replication** RTT, which can raise write latency. You must balance **fault domain isolation** with **stable network latency**. Do not take a “3 AZ” diagram as proof that every transaction will have the same latency as a single host.

## 15. Metrics to Observe When Evaluating HA and Scaling

| Layer | SLI/metric | What to infer? |
|---|---|---|
| **Application** | Read/write success rate, p50/p95/p99, timeouts, retries | Are users actually completing business operations on time? |
| **Driver/pool** | Connection acquisition latency, routing errors, transaction retries | Are cluster routing and connection lifecycle resilient? |
| **Cluster** | Writer/leader per database, quorum, unavailable members, election frequency | Are write leadership and fault tolerance maintained? |
| **Replication** | Last committed/applied tx ID, lag, catch-up time | Are replicas/secondaries keeping up? |
| **Database** | Active/blocked transactions, lock waits, query execution time | Is workload experiencing locking or contention? |
| **CPU/RAM** | CPU per core, heap/GC, page cache hit/miss, native memory | Is there a single-machine resource bottleneck? |
| **Storage** | IOPS, MiB/s, durable write p99, queue depth, free disk | Are disk/log/checkpoints slowing commits? |
| **Operations** | Failover detection time, time to healthy route, restore duration | Do actual RTO and failure recovery meet targets? |

Cluster metrics are **per-database** information—do not merely ask “does the cluster have a leader?”. In a multi-database system, `sales` could lack quorum while `analytics` remains normal.

### 15.1. Read-Only Observation Queries

With appropriate privileges:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

On an Enterprise cluster, an administrative account can inspect servers:

~~~cypher
SHOW SERVERS YIELD *;
~~~

`SHOW SERVERS` helps observe health/state/constraints, but does not replace measuring business SLIs or verifying replicated data. Never run administrative `DROP/DEALLOCATE/STOP` commands in production as an “HA test command.”

To inspect a specific query’s performance:

~~~cypher
EXPLAIN
MATCH (o:QA001Order {orderId:'O42'})
      -[:QA001_BELONGS_TO]->(a:QA001Account)
RETURN o.orderId AS orderId, a.accountId AS accountId;
~~~

`EXPLAIN` only generates the planned execution without running the query; `PROFILE` actually runs it and incurs overhead. `DB Hits` reflects logical query work, not disk read count or proof that a cluster node is ready.

## 16. Fixture with Verified Answers for Load Testing and Read-After-Write

This section uses a **dedicated practice database**, on a standalone instance or an already-deployed staging cluster. You do not need to build a cluster to run the fixture. Fixing the dataset helps verify correctness before benchmarking.

### 16.1. Reset Only the Lesson’s Labels

Only on a test database that does not share these labels:

~~~cypher
DROP CONSTRAINT qa001_account_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa001_order_id IF EXISTS;
~~~

~~~cypher
MATCH (n)
WHERE n:QA001Account OR n:QA001Order
DETACH DELETE n;
~~~

### 16.2. Create Constraints and 10 Accounts

~~~cypher
CREATE CONSTRAINT qa001_account_id IF NOT EXISTS
FOR (a:QA001Account)
REQUIRE a.accountId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa001_order_id IF NOT EXISTS
FOR (o:QA001Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
UNWIND range(1,10) AS i
MERGE (a:QA001Account {accountId:'A' + toString(i)})
SET a.segment =
  CASE WHEN i <= 5 THEN 'GOLD' ELSE 'SILVER' END;
~~~

### 16.3. Create 100 Orders and 100 Relationships

~~~cypher
UNWIND range(1,100) AS i
MATCH (a:QA001Account {
  accountId:'A' + toString(((i - 1) % 10) + 1)
})
MERGE (o:QA001Order {orderId:'O' + toString(i)})
SET o.amount = i,
    o.status = 'NEW'
MERGE (o)-[:QA001_BELONGS_TO]->(a);
~~~

All IDs are generated deterministically. Each account has exactly **10 orders**. `A1` has O1, O11, ..., O91; `A10` has O10, O20, ..., O100.

### 16.4. Verification Results

~~~cypher
MATCH (o:QA001Order)
RETURN count(o) AS orders,
       sum(o.amount) AS amountTotal;
~~~

| orders | amountTotal |
|---:|---:|
| **100** | **5050** |

Explanation: the sum `1 + 2 + ... + 100 = 100 × 101 / 2 = 5050`.

~~~cypher
MATCH (a:QA001Account)
RETURN count(a) AS accounts,
       count(CASE WHEN a.segment='GOLD' THEN 1 END) AS gold,
       count(CASE WHEN a.segment='SILVER' THEN 1 END) AS silver;
~~~

| accounts | gold | silver |
|---:|---:|---:|
| **10** | **5** | **5** |

~~~cypher
MATCH ()-[r:QA001_BELONGS_TO]->()
RETURN count(r) AS relationships;
~~~

**Answer:** `relationships = 100`.

~~~cypher
MATCH (a:QA001Account)
OPTIONAL MATCH (o:QA001Order)-[:QA001_BELONGS_TO]->(a)
RETURN a.accountId AS accountId, count(o) AS orderCount
ORDER BY accountId;
~~~

**Answer:** **10 records**, and every record has `orderCount = 10`. Lexicographical sorting by `ORDER BY accountId` may produce A1, A10, A2, ..., which **does not change** the order count; do not use that lexicographical order to infer numeric IDs.

**Post-write check:** run the code from section 12 to change O42 to `CONFIRMED`, then read through a session with an appropriate bookmark. Expect one record for O42 with the new status; the counts of orders, accounts, and relationships remain 100/10/100 respectively.

## 17. Measuring Single-Server Limits: Do Not Look at Throughput Alone

Before upgrading hardware or adding a cluster, run load tests on a **sufficiently large, realistic dataset**. The 100-order fixture only validates Cypher queries and tooling—it **does not** represent production performance.

### 17.1. Define Four Workloads

1. **Point lookup:** find a `QA001Order` by ID and read its properties.
2. **Traversal:** from an account to many orders, with filtering/sorting/limit.
3. **Write transaction:** create/update an order and relationship by business key.
4. **Mixed workload:** for example, hypothetically 80% reads, 20% writes, with production-like concurrency.

Measure each workload independently first, then measure the mixed workload. Ensure read requests return the **right data**, write transactions **commit**, and results are not contaminated by old fixtures.

### 17.2. Controlled Test Design

- Fix the Neo4j/Driver versions, graph size, schema/indexes/constraints, storage type, and client count.
- Place the load generator **outside the Neo4j machine** so server CPU/memory numbers are not skewed by the load-generation tool.
- Warm up the pool/JIT/page cache before steady-state measurement runs; record cold-ish results separately.
- Step concurrency upward: 1 → 2 → 4 → 8 → 16, keeping duration/target request rate consistent.
- Record **committed transactions/s** throughput, p50/p95/p99, timeouts, retries, and graph correctness.
- Simultaneously track CPU, memory, page cache, GC, IOPS, durable write latency, lock contention, and network.
- Stop increasing load once latency SLO or error budget is violated; do not maximize throughput by ignoring errors.
- Repeat runs to avoid drawing conclusions from a single run or differing cache states.

### 17.3. Distinguishing Query Improvements from Topology Improvements

Compare:

| Test | Held constant | Changed single factor |
|---|---|---|
| Before/after creating proper index | Query, data, server | Index |
| Before/after increasing page cache | Query, graph, workload | Memory allocation |
| Stronger single server | Query, graph, workload | CPU/RAM/SSD |
| 3 primaries | Query, logical data, load source | Topology/fault tolerance; replication cost |
| 3 primaries + secondaries | Query, data, writer primaries | Number of replicas able to serve read queries |

Do not interpret “3 primaries + 2 secondaries achieved higher read queries/s” as “every write transaction is faster.” Separate **write throughput**, **read throughput**, **latency**, and **tolerance of failures**.

## 18. Testing HA and Failover in Staging

A system advertised as HA must undergo **controlled drills**, not just rely on a three-server diagram.

### 18.1. Before the Drill

1. Identify the staging database/cluster, actual topology, failure domains, and approvers.
2. Verify that backups can be restored, baseline data is accurate, and an abort plan exists.
3. Enable client metrics (availability/latency/retries) and cluster metrics (writer/quorum/lag).
4. Generate a simulated read/write request stream **with unique IDs and verifiable answers**.
5. Record the initial writer, count of healthy primaries, and state of secondaries.

### 18.2. Single-Primary Loss Scenario

In an environment **authorized for fault injection**:

- Stop exactly **one server/primary** using the staging orchestration tool; never use production, and never take down an entire real AZ.
- Record failure detection time, writer change if any, window of timed-out requests, and retry count.
- Verify the **remaining two primaries** maintain quorum for the database under a 3-primary topology.
- Verify transactions reported as committed still exist and retries did not create duplicate orders.
- Bring the server back to operational status per runbook, measure catch-up duration, and confirm return to normal fault tolerance.

**Do not** arbitrarily stop a second primary in a three-primary cluster unless the test includes a plan to observe quorum loss and roll back safely. That “the application cannot write” after quorum loss is the expected consistency protection behavior, not automatically an implementation bug.

### 18.3. Secondary Loss Scenario

- Stop one secondary in staging.
- Verify the write SLI is not materially affected solely by losing one secondary, while read capacity may decrease.
- Observe routing, replica catch-up, and latency when the secondary returns.
- Test read-after-write with bookmarks in a real workflow, avoiding conclusions drawn from stale reads lacking causal context.

### 18.4. PASS Criteria

Saying “the cluster elected a leader automatically” is not enough. You must prove:

- Read/write request success rates meet defined targets.
- Outage/recovery duration is smaller than the error budget and test RTO.
- No committed data loss within the tested commitment scope.
- Retries produce no external side effects or duplicate records.
- Quorum and healthy replica count are restored; do not remain for hours at zero-fault-tolerance state.
- Backup/restore still works and alerts reach the on-call engineer.

## 19. An Illustrative Design Option and Trade-Offs

A **hypothetical** graph service has these requirements:

- 4,000 read requests/s at peak.
- 350 write transactions/s, needing responses within a few hundred milliseconds.
- Write availability SLO of 99.95% over 30 days.
- Tolerates losing **one server** without manual intervention to restore the writer.
- Requires read-after-write for the order creation flow.

A design path could be:

1. Optimize Cypher, schema, and Driver first; measure true single-server capability.
2. Because surviving one primary failure is mandatory, choose a **three-primary topology** across independent failure domains, with enough CPU/RAM/disk for the remaining two members to handle the load when one fails.
3. Measure read throughput on the primaries; if read capacity saturates, **add secondaries** based on measurements rather than over-provisioning many upfront.
4. Use `neo4j+s://`, `executeRead/executeWrite`, explicit database names, and bookmarks for workflows requiring causal consistency.
5. Establish independent backups, alerts on replication lag/quorum, failover drills, and error budget tracking.
6. If writer CPU/locks/IOPS hit the ceiling even after tuning, evaluate partitioning data domains/workloads; **do not** expect adding primaries to give a single database multiple writers.

**This is a design example, not a guaranteed sizing.** A three-primary cluster can still be under-provisioned when one member fails; you must **measure degraded-mode capacity**, not only when all three are healthy.

## 20. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “One server with a very fast SSD is HA.” | SSD addresses latency/capacity, not process/host/AZ failures. |
| “Two primaries suffice to tolerate one failure and keep writing.” | Majority of 2 requires 2; losing one loses write quorum. |
| “Adding a secondary adds a writer.” | Secondaries primarily serve reads and replicate asynchronously; they do not join write quorum. |
| “Three primaries triple write speed.” | Each standard database has one writer, while replication/quorum adds overhead. |
| “The entire cluster has a single leader.” | Leader/writer is **per database**, so multiple databases can have different leaders. |
| “A read replica always sees the latest data.” | Secondaries can lag; use bookmarks when causal ordering is needed. |
| “Active quorum means zero downtime.” | Leader election, routing, and timeouts/retries can still create brief interruptions. |
| “More clients always means faster.” | Under saturation, p95/p99, queues, and retries typically rise while throughput stalls. |
| “Replication replaces backups.” | Accidental deletes and logic bugs replicate too; independent backup/restore is required. |
| “Healthy `SHOW SERVERS` means SLO is met.” | SLO must be measured by business workload outcomes/latency. |
| “Neo4j on 3 Community containers forms an HA cluster.” | Clustering/quorum is a supported edition/deployment feature, not container count. |
| “When the dataset grows too large, adding primaries automatically shards the graph.” | Primaries are replicas of one database; partitioning/sharding is a different architecture. |

## 21. Exercises with Answers

### Exercise 1 — Quorum

A database has three primaries. If one primary fails while the other two primaries remain healthy and reachable, can the database maintain write quorum?

**Answer:** Yes. Quorum is `floor(3/2)+1=2`; the two remaining primaries form a majority. A brief interruption may occur during writer election/re-routing.

### Exercise 2 — Two Primaries

A database has two primaries on two separate machines. If one machine is lost, can it still commit writes under quorum?

**Answer:** No. Quorum for two primaries is 2; the single remaining replica does not form a majority.

### Exercise 3 — Secondaries

A database has one primary and three secondaries. When the primary fails, do the three secondaries automatically guarantee write HA?

**Answer:** No. Read availability may persist depending on data/network state, but secondaries do not participate in the primary group to elect a writer. Surviving a write primary failure requires a proper multi-primary topology.

### Exercise 4 — 99.9% SLO

If a time-based availability target is 99.9% over 30 days, how many minutes is the equivalent error budget?

**Answer:** `43,200 × (1-0.999) = 43.2 minutes`, i.e., 43 minutes 12 seconds.

### Exercise 5 — Server Limits

In a hypothetical benchmark, raising workers from 4 to 8 did not increase throughput, p95 rose from 105 to 240 ms, and retries climbed. Should you keep adding workers?

**Answer:** Not by default. Inspect CPU, lock contention, I/O, queue depth, and pool metrics; prioritize resolving the bottleneck and bounding concurrency.

### Exercise 6 — Bookmark

Request A writes an order successfully, and request B immediately afterward reads from another secondary and does not see the order. How can this be explained and fixed?

**Answer:** The secondary may not have received the transaction yet. Pass a bookmark or use a BookmarkManager within the workflow requiring read-after-write to guarantee causal consistency, while measuring the wait cost.

### Exercise 7 — Fixture Answers

The fixture creates 10 accounts, 100 orders with `amount=1..100`, and 100 relationships. What is the total amount? How many orders does each account have?

**Answer:** `sum(amount)=5050`, and each account has **10 orders**. A1 has O1/O11/.../O91, A10 has O10/O20/.../O100.

### Exercise 8 — Scale-Up or Cluster?

A single-machine system still has spare CPU/RAM, but has a requirement: “survive the loss of one host and keep writing.” Should you simply upgrade to a stronger machine?

**Answer:** No. This requirement is fault tolerance, not lack of capacity. You need a multi-primary model across independent failure domains with routing and failover testing; you must still size for degraded mode.

### Exercise 9 — Writer Bottleneck

A clustered database has three primaries, and the writer suffers lock contention on a continuously updated node. Will adding two more primaries definitely increase write throughput?

**Answer:** No. A single writer handles writes for the database; adding primaries can increase replication/quorum overhead. You must examine access/locking patterns, batching, indexing, and workload partitioning options.

### Exercise 10 — Backup and HA

An accidental Cypher operation deletes thousands of relationships and is committed/replicated across the entire cluster. Will the cluster automatically restore the graph to its state before the deletion?

**Answer:** No. Replication propagates valid changes even if they are business mistakes. You need backups/restore, an edition-appropriate point-in-time strategy, and approval/auditing processes.

## 22. Architecture Decision Checklist

Before deciding between a single server or a cluster, the engineering team should align on:

- [ ] Separately defined read/write availability SLIs, latency thresholds, SLOs, and error budgets.
- [ ] Defined RPO/RTO and required failure modes to survive (process, host, AZ, data center).
- [ ] Known actual edition/version and supported topology/managed service options.
- [ ] Single-machine benchmark measuring CPU, RAM, I/O, locks, network, and p95/p99 on realistic workloads.
- [ ] Data on read/write ratio and concurrency, not relying solely on total node count.
- [ ] Verified queries/indexes/batching before blaming hardware for every slowdown.
- [ ] If write HA is needed, quorum primaries designed across independent failure domains.
- [ ] If read scaling is needed, secondaries added based on data with replication lag metrics.
- [ ] Driver configured with routing URI, read/write transaction methods, and explicit database name.
- [ ] Bookmark policy in place for workflows requiring causal consistency.
- [ ] Capacity plan for when **one primary is lost**, not just healthy-state capacity.
- [ ] Rehearsed backup/restore and staging failover tests.
- [ ] Alerts for quorum, writer/election, transaction lag, disk pressure, and client error budget.
- [ ] Rollback plan when changing topology/upgrading/scaling without resorting to ad-hoc destructive commands.

## 23. Cleaning Up the Fixture on the Practice Database

Run only on the **test database** used, after completing verification and tests. Do not run if the labels `QA001Account` or `QA001Order` belong to production data.

~~~cypher
MATCH (n)
WHERE n:QA001Account OR n:QA001Order
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa001_account_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa001_order_id IF EXISTS;
~~~

Verify:

~~~cypher
MATCH (n)
WHERE n:QA001Account OR n:QA001Order
RETURN count(n) AS remaining;
~~~

**Answer:** `remaining = 0`. Do not use this cleanup to simulate cluster failover or backup; it only removes test data.

## 24. Official References

- [Neo4j Operations Manual — Introduction to clustering](https://neo4j.com/docs/operations-manual/current/clustering/introduction/): server/database topology, primaries, secondaries, quorum, and fault tolerance.
- [Neo4j Operations Manual — Leadership, routing and load balancing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/): Raft leader, client/server routing, and per-database roles.
- [Neo4j Operations Manual — Deploy a basic cluster](https://neo4j.com/docs/operations-manual/current/clustering/setup/deploy/): topology requirements and example configuration.
- [Neo4j Operations Manual — Managing servers](https://neo4j.com/docs/operations-manual/current/clustering/servers/): health, enable/cordon/deallocate, and server metadata.
- [Neo4j Operations Manual — Scaling with Neo4j](https://neo4j.com/docs/operations-manual/current/scalability/scaling-with-neo4j/): scale-up, read scaling, federation/sharding, and limits of each option.
- [Neo4j Operations Manual — Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/): writer/leader, last committed transaction, and cluster metrics.
- [Neo4j Operations Manual — Cluster monitoring endpoints](https://neo4j.com/docs/operations-manual/current/clustering/monitoring/endpoints/): checking quorum, Raft lag, and member status.
- [Neo4j Java Driver Manual — Coordinate parallel transactions](https://neo4j.com/docs/java-manual/current/bookmarks/): bookmarks and causal consistency across sessions.
- [Neo4j Java Driver Manual — Connect](https://neo4j.com/docs/java-manual/current/connect/): routing URIs, authentication, and Driver lifecycle.
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/): recovery options independent of HA replication.

**Remember:** A single server can be **performance-tuned** via CPU/RAM/page cache/SSD and good Cypher, but cannot eliminate single points of failure. To achieve **write HA** for a Neo4j Enterprise database, understand **writer, primaries, and quorum**; to **scale reads**, use secondaries and monitor synchronization lag. **Adding machines does not automatically give one transaction or one database multiple writers.** Proper design must start from read/write SLOs, resource limits, and real failover tests, then verify with measurements rather than assumptions.
