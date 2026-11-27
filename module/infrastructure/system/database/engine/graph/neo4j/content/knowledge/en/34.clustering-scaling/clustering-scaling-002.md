# Neo4j Cluster Architecture by Version and Edition

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **Neo4j Community**, **self-managed Neo4j Enterprise**, **Aura** tiers, and specialized scaling features by version/license.
- Explain the shift from **Core/Read Replica** in Neo4j 4.4 to **primary/secondary database allocations** in Neo4j 5.x and 2025–2026 releases.
- Describe **writer/leader**, Raft, **quorum**, synchronization across primaries, and asynchronous replication to secondaries.
- Choose topologies for **high availability**, read scaling, or multi-database distribution; understand why adding primaries **does not increase the number of writers for a single database**.
- Use `SHOW DATABASES`, `SHOW SERVERS`, and `CREATE/ALTER DATABASE ... TOPOLOGY` statements in an authorized Enterprise environment.
- Configure the Neo4j Java Driver with **READ/WRITE routing** and **bookmarks** when *read-your-writes* is required.
- Plan for single-member failure, quorum loss, rolling maintenance, backups, network partitions, monitoring, and resilience testing.
- Recognize **Infinigraph/property sharding** starting in Neo4j 2025.12 as a separate subscription-licensed capability, not to be confused with standard Enterprise clustering.

This lesson belongs to the **Clustering and Scaling** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Neo4j organizes connected data as a **property graph** (nodes, relationships, properties) and uses **Cypher** for relationship and path queries. When multiple Java Driver/Spring Data Neo4j applications access the graph concurrently, cluster architecture must guarantee **correct transactions, data durability, and read/write capacity** under load or when a server fails.

> **Scope:** This lesson uses concepts and syntax common to **Neo4j 5.x, 5.26 LTS, and 2025.x/2026.x releases**. Neo4j 4.4 has different architecture/configuration; Aura tiers restrict administrative privileges. **Do not run topology-changing commands or stop servers in production** without a change plan, backups, and a recovery plan. Consult official documentation for the **exact version and edition** deployed.

## 1. What Problems Does a Cluster Solve?

A single Neo4j server can serve both Cypher READ and WRITE queries. As a system grows, operations teams typically have three goals:

1. **High availability (HA):** if a machine or availability zone fails, the system can continue serving within its designed fault tolerance limits.
2. **Read scalability:** distribute `MATCH`/traversal/path queries across multiple database replicas to increase read throughput.
3. **Operational scalability:** add servers, distribute multiple databases, perform member-by-member maintenance/upgrades, and isolate workloads.

These goals are **not identical**:

| Goal | Common mechanism | Do not assume |
| --- | --- | --- |
| Tolerate one primary failure | **At least three primaries** for databases needing write HA | Two primaries suffice to tolerate one primary failure |
| Increase READ throughput | Add **secondaries** or use non-writer primaries to serve reads | Secondaries can accept WRITES |
| Reduce write latency | Optimize queries/indexes, transactions, and topology/geographic placement | Adding primaries always makes WRITES faster |
| Host multiple independent graphs | Multiple databases, allocator distributes replicas across servers | Automatic ACID transactions spanning across databases |
| Graph too large for one host | Scale up, split workloads, or conditional sharding mechanisms | Standard cluster replicas automatically partition one graph into shards |

**Core insight:** Standard clustering replicates the **full copy of a database** to allocated replicas. Adding replicas primarily adds **HA and read capacity**, rather than randomly splitting every relationship across servers.

## 2. Version, Edition, and Environment Matrix

Neo4j has evolved how clustering is organized over time. Consequently, a guide referencing “Core server” or `causal_clustering.*` settings may be outdated for newer systems.

| Version / product | Cluster concept | Support / limitations |
| --- | --- | --- |
| **Neo4j 4.4 Enterprise** | **Causal Cluster** with **Core servers** and **Read Replicas** | Legacy architecture; configuration files cannot be copied as-is to 5.x |
| **Neo4j 5.x Enterprise** | Redesigned cluster: **servers and databases decoupled**, each database has **primary/secondary allocations** | Supports per-database topology management and automated allocation |
| **Neo4j 5.26 LTS Enterprise** | 5.x architecture; a key LTS milestone in the upgrade path | Must follow specific upgrade/migration instructions |
| **Neo4j 2025.x/2026.x Enterprise** | Continues the **primary/secondary** model, with release-specific management and feature additions | Use exact version syntax/config; do not mix with 4.4 |
| **Neo4j Community** | Single-server database deployment, **no Enterprise clustering** | Enterprise clustering cannot be enabled via `neo4j.conf` alone |
| **AuraDB Business Critical / Virtual Dedicated Cloud** | Managed service with a **three-node cluster** per current service specifications | Provider manages many cluster and failover details |
| **Other AuraDB tiers** | May use a **single-node architecture** with infrastructure-level HA | Do not assume tenants can choose `TOPOLOGY 3 PRIMARIES` |
| **Infinigraph from 2025.12** | Dedicated distributed Neo4j **property sharding** capability | **Not included in standard Enterprise**; requires a separate subscription and is unavailable on Aura per current docs |

### Key Transition Milestones to Remember

- **Neo4j 4.4 → 5:** upgrade documentation explicitly maps **Core → primary database copy**, **Read Replica → secondary database copy**. This is not merely a rename; the 5.x cluster has its own allocator and organization, requiring redesign/reconfiguration rather than copying 4.4 settings verbatim.
- **Neo4j 5.23:** discovery service v1 was deprecated and v2 introduced; as of **2025.01**, v1 was removed. Older clusters must review discovery before upgrading.
- **From 2025.01:** the server moved to **Calendar Versioning (CalVer)** formatted as `YYYY.MM.PATCH`; do not infer compatibility solely from a `5.` prefix.
- **From 2025.12:** **Infinigraph property sharding** was introduced as a distinct capability from standard replication with separate licensing.

Sources: [Neo4j clustering introduction](https://neo4j.com/docs/operations-manual/current/clustering/introduction/), [Breaking changes 4.4 → 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/), [Versioning/upgrade guide](https://neo4j.com/docs/upgrade-migration-guide/current/), [Infinigraph overview](https://neo4j.com/docs/operations-manual/current/scalability/sharded-property-databases/overview/).

### 2.1. Checking the Running Version

In an environment with appropriate privileges:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Do not use the **Neo4j Browser version**, **Java Driver version**, or the presence of a procedure to infer the DBMS edition. On Aura, check the **service name and tier** in the management console; some DBMS commands may not be granted to tenant accounts.

## 3. 5.x/2025–2026 Architecture: Server Is Not Identical to Database Role

In modern Neo4j Enterprise clusters:

- **Server** is a Neo4j process on a physical machine, VM, or container.
- **Database** is an independently named collection of graphs and metadata; one cluster can serve multiple databases.
- **Allocation** is a replica copy of a database placed onto a server.
- **Primary**/**secondary** are **roles of a database replica**, not permanent labels for the entire server.
- **Writer/leader** is a primary elected to coordinate writes **for that database**.
- **Allocator** distributes database allocations onto servers satisfying constraints.

One server can hold a **primary of database A** and a **secondary of database B** if configuration allows. Two databases can elect **two different writers**.

~~~mermaid
flowchart TB
    APP["Java / Spring application"] --> R["Routing driver"]
    R --> DB1["Database orders<br/>independent quorum"]
    R --> DB2["Database network<br/>independent quorum"]
    subgraph S["Enterprise server pool"]
      A["Server A<br/>orders: primary/writer<br/>network: secondary"]
      B["Server B<br/>orders: primary/follower<br/>network: primary/writer"]
      C["Server C<br/>orders: primary/follower<br/>network: primary/follower"]
      D["Server D<br/>orders: secondary<br/>network: primary/follower"]
    end
    DB1 --> A
    DB1 --> B
    DB1 --> C
    DB1 --> D
    DB2 --> A
    DB2 --> B
    DB2 --> C
    DB2 --> D
~~~

The diagram illustrates that **roles can differ per database**; it is not a snapshot of a live cluster. Which allocation types a server may host also depends on `modeConstraint`, resources, permissions, and topology.

### 3.1. Distinguishing `modeConstraint` from Active Role

A server can be configured with a constraint:

| `modeConstraint` | Meaning |
| --- | --- |
| `PRIMARY` | Server is only eligible to host **primary** allocations |
| `SECONDARY` | Server is only eligible to host **secondary** allocations |
| `NONE` | Server may host **both primary and secondary**, at the allocator’s discretion |

`modeConstraint=PRIMARY` does not mean the server is currently the writer for every database. **Writer is a role elected within each database’s Raft group**. Nor does this constraint create extra replicas by itself; there must be enough eligible servers to satisfy the topology.

## 4. Primary, Leader, Raft, and Quorum

For a database with **three primaries**:

~~~mermaid
flowchart LR
    API["Write transaction"] --> L["Primary A<br/>Leader/Writer"]
    L -->|Raft / replication| B["Primary B<br/>Follower"]
    L -->|Raft / replication| C["Primary C<br/>Follower"]
    B -.->|ACK| L
    C -.->|ACK| L
    L -->|Commit after sufficient ACKs| API
    L -.->|Asynchronous log shipping| S["Secondary D<br/>Read-only"]
~~~

Conceptual steps:

1. The routing driver locates the **write route** for the target database.
2. The write transaction is coordinated by the current **writer/leader**.
3. The leader orders transactions consistently using Raft and replicates them to follower primaries.
4. A transaction is considered durably committed under cluster policy only when the required **quorum** acknowledgments are met.
5. Secondaries update via **asynchronous replication / transaction log shipping** to serve READs.

**There are not multiple simultaneous writers for the same standard database** simply because there are three primaries. The remaining primaries are members eligible for election when needed, while also serving reads.

### 4.1. Calculating Quorum

With `M` primaries participating in Raft, the simple majority acknowledgment count is:

\[
Q = \left\lfloor \frac{M}{2}\right\rfloor + 1
\]

The maximum number of primary failures tolerable while retaining **write quorum** (assuming remaining members and network operate normally) is:

\[
F = M - Q = \left\lfloor \frac{M-1}{2}\right\rfloor
\]

| Number of primaries | Write quorum | Max failures tolerated | Notes |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | Low write latency, no primary fault tolerance |
| 2 | 2 | 0 | Lose 1 → no quorum; does not solve write HA |
| 3 | 2 | 1 | Common HA choice |
| 4 | 3 | 1 | Cannot survive 2 failures; usually less beneficial than 3 or 5 |
| 5 | 3 | 2 | Tolerates 2 primary failures, higher write/resource cost |

Hence the standard rule to **tolerate F failures** is `M = 2F + 1`. Per current documentation, Neo4j allows up to 11 primary allocations for a standard database, though **increasing arbitrarily is not recommended**: more required acknowledgments and network effects can increase write latency.

### 4.2. Losing Quorum Does Not Mean Losing All Data

With three primaries, if two primaries become unreachable, the database loses the ability to **commit new WRITES**, yet a remaining member still holding a copy of the data may continue serving **some READS** depending on state, routing, and permissions. Do not conclude the entire graph was wiped just because writes fail.

Conversely, **still being readable** does not guarantee preserving every final write in all disasters. You still need backups and a failure-domain model: if every copy holding a committed transaction is destroyed, replication does not substitute for backups.

## 5. Secondaries: Scaling Reads, Not Participating in Write Quorum

A **secondary** is a database replica receiving transactions **asynchronously** from upstream, typically used to distribute read-only queries.

| Characteristic | Primary | Secondary |
| --- | --- | --- |
| Can become the database writer? | **Yes**, if elected leader | **No** |
| Participates in write quorum? | Yes, in multi-primary topologies | No |
| Serves read-only `MATCH`/traversals? | Yes | Yes |
| Receives changes from writer | Consensus replication across primaries | Asynchronous transaction log shipping |
| Can temporarily see stale data? | Depends on state/read path, though primaries use consensus for new commits | **Can lag** due to asynchronous replication |
| Impact of losing one replica? | May reduce write fault tolerance | Primarily reduces read throughput; does not alter primary quorum |

For example, a product recommendation application with heavy READ query volume might use **3 primaries + 2 secondaries**, sending many `MATCH`/path queries to secondaries while `MERGE`/`SET` transactions are coordinated through the database’s writer.

Do not view a secondary as an arbitrary shared HTTP cache. It is a **full graph replica** with real storage, CPU, RAM, page cache, connection, and operational costs. Adding secondaries pays off when the **read workload can genuinely be distributed** and the bottleneck is not elsewhere such as the API, network, or missing indexes.

### 5.1. Read Consistency

Because secondaries may receive logs with a delay, a read request right after a write risks **not seeing the new data** unless the application establishes causal ordering:

~~~text
T1: executeWrite() creates Order O-901 on writer
T2: commit succeeds
T3: READ request hits secondary that has not replayed the transaction yet
T4: secondary replays log, new Order appears
~~~

To ensure **read-your-writes** when needed, use the Neo4j Driver’s **bookmarks/causal consistency** (section 8). Never add `Thread.sleep(1000)` as a “consistency fix”; replication delay fluctuates with load and network glitches.

## 6. Choosing a Topology by Problem

| Topology of **one database** | Purpose | Write HA | Read scaling | Caveats |
| --- | --- | --- | --- | --- |
| **1 primary, 0 secondaries** | Lab, small workloads, simple low write latency | No | Limited | One host fails → service stops |
| **1 primary, N secondaries** | Analytics/read-heavy, accepting no write HA | No | Yes | Primary fails → reads may continue, writes stop |
| **3 primaries, 0 secondaries** | Write HA and moderate reads | Tolerates 1 primary failure | Reads from non-writer primaries | Raft sync, cost of 3 full copies |
| **3 primaries, N secondaries** | Write HA + heavy read scaling | Tolerates 1 primary failure | Yes, via secondaries | Must manage lag, cost, router |
| **5 primaries, N secondaries** | Requirement to tolerate 2 primary failures | Tolerates 2 primary failures | Yes | Higher sync, I/O, resource cost |

**Having 1 primary + multiple secondaries is not equivalent to write HA.** A secondary cannot be automatically promoted to become the new Raft writer to continue commits when the sole primary is lost. To write continuously across any single primary failure, choose **3 primaries** placed across appropriate independent failure domains.

### 6.1. Multi-Database Allocation

In a 6-server cluster, you might allocate:

- `orders_graph`: 3 primaries on A/B/C; 2 secondaries on D/E.
- `recommendation_graph`: 3 primaries on B/D/F; one secondary on A.
- `system`: topology managed by its own rules, unlike arbitrarily specifying primary count via `CREATE DATABASE`.

This is an example allocation; the **allocator** and server constraints determine actual placement. The aim is to avoid hotspots on a single host, protect HA, and place read workloads near application networks where appropriate.

**There are no atomic transactions across two databases** simply because they share a cluster. If business logic requires updating two graphs together, design explicit transaction boundaries and cross-system consistency workflows.

## 7. Managing Topology with Cypher

Commands in this section apply to **self-managed Neo4j Enterprise**, executed by an administrative account against the **`system` database**. Do not run them unapproved on production or Aura tenants where the service restricts them.

### 7.1. Viewing Servers and Database Allocations

~~~cypher
SHOW SERVERS;
~~~

~~~cypher
SHOW DATABASES
YIELD name, address, role, writer,
      requestedStatus, currentStatus, statusMessage
RETURN name, address, role, writer,
       requestedStatus, currentStatus, statusMessage
ORDER BY name, address;
~~~

In versions supporting these columns:

- `name`: allocated database.
- `address`: endpoint of the respective replica.
- `role`: `primary` or `secondary` for that allocation.
- `writer`: whether this primary replica is currently elected writer for the database.
- `requestedStatus` vs `currentStatus`: desired status versus actual status.
- `statusMessage`: diagnostic hint if allocation/recovery fails.

If a client does not see a column or procedure, verify **privileges and version**; do not immediately assume the cluster has no writer. A record with `writer=false` on a secondary is **normal**.

### 7.2. Creating a Database with a Specific Topology

~~~cypher
// RUN ONLY ON AN AUTHORIZED LAB CLUSTER.
// Requires at least 5 enabled eligible servers.
CREATE DATABASE graph_lab
TOPOLOGY 3 PRIMARIES 2 SECONDARIES;
~~~

Each allocation requires an eligible server according to `modeConstraint` and placement rules. With only three servers, the statement above can fail for lack of places to host all five replicas. Increasing topology does not create physical servers out of thin air.

If secondaries are not needed yet:

~~~cypher
CREATE DATABASE graph_lab
TOPOLOGY 3 PRIMARIES;
~~~

The two examples above are **alternatives**—do not run them sequentially on the same cluster if the database already exists.

### 7.3. Altering Topology and Re-Reading Status

~~~cypher
// Assumes graph_lab exists and the cluster has sufficient resources.
ALTER DATABASE graph_lab
SET TOPOLOGY 3 PRIMARIES 2 SECONDARIES;
~~~

Afterward, use `SHOW DATABASES` to verify the actual primary/secondary counts online. Topology change requests can take time while replicas are created/reallocated and data is seeded.

**Very important note:** Current Neo4j documentation does not allow **automatically shrinking from multiple primaries down to one primary** via `ALTER DATABASE ... SET TOPOLOGY 1 PRIMARY`. That process may require backup, drop/recreate, or seeding per official guidance; **never test this ad-hoc on real data**.

### 7.4. Adding a New Server

In a 5.x/2025–2026 cluster, a new server joining discovery **is not automatically used by the allocator to host databases right away**. It may enter in the **`Free`** state, requiring an administrator to run:

~~~cypher
// Placeholder: replace with the server ID obtained from SHOW SERVERS.
ENABLE SERVER 'server-id-from-show-servers';
~~~

For placement, you can specify `OPTIONS {modeConstraint: 'SECONDARY'}` in `ENABLE SERVER` syntax if supported by your version and goals. **Do not treat PRIMARY/SECONDARY on a server as a fixed Raft role**; it is an allocation constraint, not a leader assignment.

See [Managing databases in a cluster](https://neo4j.com/docs/operations-manual/current/clustering/databases/) and [Managing servers](https://neo4j.com/docs/operations-manual/current/clustering/servers/).

## 8. Java Driver: READ/WRITE Routing and Causal Consistency

Java applications should never hardcode the address of the “current leader” for WRITES: the leader **can change during elections or failovers**. Use **routing** schemes `neo4j://` or `neo4j+s://` against endpoints provided by the cluster.

| URI | Meaning | When to use |
| --- | --- | --- |
| `neo4j://host:7687` | Routing driver fetches routing table to select read/write routes | Self-managed cluster per network/TLS policy |
| `neo4j+s://host:7687` | Routing with TLS and trusted certificate verification | Production with proper CA/certificates |
| `neo4j+ssc://host:7687` | TLS routing accepting self-signed certificates per driver mode | Only when security policy permits; not a replacement for standard verification |
| `bolt://host:7687` | Direct connection to a single endpoint | Single-server environments or when direct connection is genuinely required |

When routing is used, **`executeRead`** creates a READ transaction, while **`executeWrite`** creates a WRITE transaction. The driver dispatches transactions to the appropriate server using the routing table and cluster state; applications cannot directly make a secondary writable.

### 8.1. Java Driver Example with Read-After-Write

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ClusterRoutingDemo {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        // Example URI: neo4j+s://cluster.example.com
        // Requires valid CA/certificate and an authorized account.
        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password));
             Session session = driver.session(
                SessionConfig.forDatabase("graph_lab"))) {

            // Run only on a lab database with appropriate constraints.
            session.executeWriteWithoutResult(tx ->
                    tx.run("""
                        MERGE (c:ClusterLabCustomer {
                          customerId: $id
                        })
                        SET c.displayName = $name
                        """, Map.of(
                                "id", "C-LAB-01",
                                "name", "Lan")).consume());

            String name = session.executeRead(tx ->
                    tx.run("""
                        MATCH (c:ClusterLabCustomer {
                          customerId: $id
                        })
                        RETURN c.displayName AS name
                        """, Map.of("id", "C-LAB-01"))
                      .single()
                      .get("name")
                      .asString());

            System.out.println(name);
        }
    }
}
~~~

Within **a single Session**, the Java Driver manages bookmarks so subsequent transactions observe prior changes with **causal consistency**. On a cluster, a READ may wait for the chosen member to catch up to the bookmark; this can raise latency or cause timeouts if replication lags.

**Scope limit:** If HTTP request A writes using Session A, and then request B opens Session B on another application instance, **they do not automatically share the same causal chain**. When read-after-write is required across Sessions or workflows, use **`BookmarkManager`**, pass bookmarks explicitly, or select an appropriate consistency strategy per driver/version. Independent reads or analytics reports may opt to tolerate secondary lag.

### 8.2. Retries and Transaction Callbacks

Managed transactions `executeRead` / `executeWrite` automatically retry **transient errors recognized by the driver**. When the cluster elects a new leader, a transaction may be retried, though **not every error is retried** nor guaranteed to recover before timeout.

Rules:

- Callbacks can re-run: use stable business IDs, constraints, and **idempotent** logic.
- Never call payment gateways, send emails, or publish to message brokers directly inside a retryable callback.
- Return a success response **only after `executeWrite` completes and commit is confirmed**.
- Track routing errors, transaction timeouts, retry rates, read/write latencies, and pool queues; do not hide incidents behind p50 averages.

With Spring Data Neo4j, repositories/`Neo4jClient` operate inside Spring’s transaction manager; configure connection/routing properly and avoid assuming two repositories targeting two databases share an ACID transaction.

Sources: [Java Driver transactions](https://neo4j.com/docs/java-manual/current/transactions/), [Coordinate parallel transactions with bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/).

## 9. Discovery Configuration and Cluster Networking

For Enterprise servers to locate one another, a consistent **cluster discovery** mechanism is required. Newer versions support environment-specific resolvers (endpoint list, DNS, Kubernetes, etc.). Do not copy Neo4j 4.4 `causal_clustering.*` settings into Neo4j 5/2025+.

Example of **a fragment** of `neo4j.conf` for modern Neo4j, with illustrative DNS names:

~~~properties
# Apply to each server with its own advertised address.
server.default_listen_address=0.0.0.0
server.default_advertised_address=neo4j-a.internal.example
dbms.cluster.discovery.resolver_type=LIST
dbms.cluster.endpoints=neo4j-a.internal.example:6000,neo4j-b.internal.example:6000,neo4j-c.internal.example:6000
server.cluster.system_database_mode=PRIMARY
~~~

**This is not a complete production-ready cluster config.** You also need edition/license, TLS, certificates, Bolt listen/advertised addresses, firewalls, volumes, failure domains, clock synchronization, filesystem permissions, CPU/RAM, and version-dependent intra-cluster ports.

Never set the same `server.default_advertised_address` across all three machines. DNS names must resolve **from other servers and required clients**; if an advertised Bolt route points to a private address unreachable by clients, the initial handshake may succeed while queries fail because the routing table contains unreachable endpoints.

### 9.1. Distinguishing Discovery from Data Traffic

| Connection group | Role | Protection |
| --- | --- | --- |
| Discovery/management | Enables servers to find each other and manage topology | Trusted cluster network only, appropriate ACLs/TLS |
| Intra-cluster replication / Raft | Synchronizes primaries and logs to secondaries | Stable network latency, encryption, never exposed to Internet |
| Bolt client | Java Driver, Spring Data Neo4j, queries | Routing URI, TLS, RBAC, connection pool |
| Backup/monitoring | Dedicated backups/metrics | Internal endpoints, separate accounts and retention |

With Docker/Kubernetes, do not assume container ports match endpoints usable by external clients. Account for host ports, Service/Ingress, DNS, NetworkPolicy, and advertised address configuration.

### 9.2. Specific Differences Between Discovery v1 and v2

According to migration documentation, **discovery v1 was deprecated in 5.23 and removed in 2025.01**. When operating an older 5.x cluster:

1. Check the exact version of every server.
2. Identify the active discovery implementation.
3. Plan migration to a mechanism supported by the target version.
4. Test cluster restart/rejoin, failover, and routing in staging.
5. Do not upgrade all binaries first and check v1 settings afterward.

Sources: [Neo4j 5 migration guidance](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/planning/), [Neo4j cluster deployment](https://neo4j.com/docs/operations-manual/current/clustering/setup/deploy/).

## 10. The `system` Database and Server Management vs. Business Databases

Neo4j uses the **`system` database** to store DBMS metadata such as databases, server allocations, users, and roles within supported product boundaries. When a cluster hosts multiple databases:

- Each **standard database** has its own primary/secondary topology and Raft group.
- The `system` database has its own placement/primary/secondary configuration; per modern docs, `server.cluster.system_database_mode` influences the `system` replica role on a server.
- Commands like `SHOW SERVERS`, `ENABLE SERVER`, `CREATE DATABASE`, or `ALTER DATABASE` require administrative context/privileges.
- Database allocations may require **reallocation** to rebalance after many topology changes, as adding a server does not automatically migrate all existing data.

### 10.1. Why Protect `system`?

Suppose a business graph has 3 healthy primaries, yet the cluster coordination metadata suffers a severe outage. Administrative/topology operations may be impacted even while portions of READ/WRITE on the business database continue running. Therefore monitor the **health of both `system` and each user database**, not just a single “cluster online” status.

Long-lived stable servers usually favor primary `system` allocations. Ephemeral analytics-only nodes may be suited to secondary `system` allocations depending on operational architecture. Consult official guidance when selecting topology; do not place `system` on a single server and claim administrative HA.

## 11. From HA Cluster to Performance Scaling: What Actually Increases?

### 11.1. READ Scale-Out

On large connected graphs, many `MATCH` queries can execute concurrently across secondaries. For example:

~~~cypher
MATCH (c:Customer {customerId: $id})
      -[:PLACED]->(o:Order)
RETURN o.orderId, o.status
ORDER BY o.orderId
LIMIT 20;
~~~

If the query has proper indexes/constraints, multiple secondaries help distribute **independent read requests**. However, a single query producing 10 million intermediate rows **is not automatically split into 10 pieces across 10 secondaries**; each query still executes on one replica unless an explicit distributed capability is designed.

### 11.2. WRITES Do Not Scale Linearly with Primary Count

A standard database has **one writer at a time**. Going from 3 to 5 primaries primarily increases fault tolerance, **not the number of writers**. Quorum and network replication may actually raise commit latency.

If WRITES are bottlenecked:

1. Inspect the Cypher plan and indexes/constraints on business keys.
2. Measure lock contention, transaction duration, batch size, CPU, disk, and transaction log I/O.
3. Use `UNWIND`/managed transactions for sensible batching without creating overly long transactions.
4. Separate read load competing for writer resources; consider secondaries to offload READs.
5. If genuinely independent write domains are required, consider **multiple databases/partitioning by business domain**, accepting that automatic cross-database ACID does not exist.

### 11.3. Graph Size Does Not Shrink per Replica

In a standard cluster, a **full replica** of the database requires corresponding storage. A 500 GB source graph does not become 100 GB per host when allocated across 5 replicas; each replica’s store data still approximates the full database, plus transaction logs, indexes, backups, and overhead.

To plan capacity:

- Disk sized for **store + logs + free space + growth + recovery headroom** on each host.
- RAM sized for **page cache + heap + native memory/OS** per each replica’s workload.
- Network throughput for **replication** and query results returned to clients.
- SLOs tracked by **p95/p99** and error rate, not merely total node/relationship count.

### 11.4. Analytics and GDS

Graph Data Science (GDS) jobs can consume significant RAM/CPU for in-memory graph projections. **Named GDS graphs in the in-memory catalog do not automatically become database replicas or replicate like standard store data**. Place analytics on appropriate servers or clusters, manage graph lifecycles, and prevent heavy jobs from spiking p99 on critical transactions.

## 12. Multi-Zone Architecture and Failure Domains

A **failure domain** is a group of components that can fail together: a host, rack, availability zone, data center, or region. Primaries might sit on separate hosts while sharing the same storage array or the same AZ; in that case, “3 primaries” does not prove zone fault tolerance.

### 12.1. Three Primaries Across Three Zones Pattern

~~~mermaid
flowchart LR
    AZ1["Zone A<br/>Primary 1"] <--> AZ2["Zone B<br/>Primary 2"]
    AZ2 <--> AZ3["Zone C<br/>Primary 3"]
    AZ1 <--> AZ3
    APP["Client routing"] --> AZ1
    APP --> AZ2
    APP --> AZ3
~~~

Under stable networking, losing one zone containing one primary leaves **two primaries = 2/3 quorum**. However:

- Inter-primary latency affects write commit latency because consensus messages are exchanged.
- If two zones fail or a network partition leaves the remaining group short of quorum, WRITES must stop to preserve safety.
- A lone zone holding one primary must never “force a writer” by bypassing consensus.
- Secondaries can be placed close to readers to reduce latency, but data on secondaries may lag.

### 12.2. When Should You Avoid Stretching Primaries Across Distant Regions?

Raft requires quorum acknowledgments before committing. Networks between distant regions have high RTT, increasing latency and sensitivity to partitions. If an application demands ultra-low write latency:

- Place quorum primaries in zones with suitable inter-zone latency per Neo4j guidance.
- Use secondaries or other data strategies to meet read locality.
- Establish separate SLOs and disaster recovery policies for full-region loss scenarios.
- Test leader election/failover, replication lag, and network partitions **in a controlled environment**.

No topology simultaneously guarantees minimal latency, resilience to every partition, zero downtime, and zero data loss across all disasters. Prioritize based on business requirements.

## 13. Infinigraph and Property Sharding Starting in Neo4j 2025.12

At this point, distinguish **two forms of “horizontal scaling”**:

| Mechanism | Nature | Conditions |
| --- | --- | --- |
| **Enterprise standard clustering** | Replicates an entire standard database across primaries/secondaries | Neo4j Enterprise, suitable topology and resources |
| **Infinigraph property sharding** | Separates **graph structure** and **property data** into specialized shards in a distributed graph architecture | Introduced in **2025.12**, requires a **separate Infinigraph subscription**, not included by default in Enterprise, and **unavailable on Aura** per current docs |

With Infinigraph property sharding:

- **Graph shard** stores **node/relationship structure**, preserving a logical graph view.
- **Property shards** store node/relationship properties across distributed members.
- Queries are processed as though operating against one logical graph, though property access, network, and placement costs must be measured separately.
- Do not describe this as “sharding arbitrary nodes and relationships by customerId” or assume all Cypher scales writes linearly.
- Features, procedure/security limits, Cypher version, and topology carry distinct constraints. Documentation requires **Cypher 25** for sharded property databases; many standard database utilities do not carry over identically.

**Pre-architecture check:** Does the actual project hold an Infinigraph subscription? Does the target version support the corresponding shard configuration? Is the deployment on Aura (which does not support this feature per current docs)? If the answers do not align, design around **standard clustering** rather than assuming automatic sharding.

Sources: [Scaling with Neo4j](https://neo4j.com/docs/operations-manual/current/scalability/scaling-with-neo4j/), [Infinigraph overview](https://neo4j.com/docs/operations-manual/current/scalability/sharded-property-databases/overview/), [Infinigraph requirements](https://neo4j.com/docs/operations-manual/current/scalability/sharded-property-databases/configuration/).

## 14. Aura: Managed Clusters Differ from Self-Managed

Neo4j Aura abstracts away many operational details. According to 2026 Neo4j service support documentation:

- **AuraDB Business Critical** and **AuraDB Virtual Dedicated Cloud** use a **three-node causal cluster** architecture for respective instances.
- Other tiers may rely on a **single-node architecture** with infrastructure-level HA; **do not infer** that tenants always control primary/secondary counts.
- The provider manages many aspects such as placement, upgrades, failover mechanics, and underlying infrastructure; tenants use tier APIs/dashboards for observability.

What the application remains responsible for:

1. Using the provided Aura URI with TLS/routing schemes as documented.
2. Configuring timeouts, retries, pools, and database names in the Java Driver/Spring Data Neo4j.
3. Setting SLIs for READ/WRITE latency, error rate, and transaction throughput.
4. Selecting capacity/availability tiers based on requirements, checking snapshots/backups, retention, and service limits.
5. Never treating `SHOW SERVERS`, `ENABLE SERVER`, or editing `neo4j.conf` as a universal runbook across all Aura tenants when the service API does not expose them.

**Distinction:** “A cloud service with HA” does not mean **tenants control Raft quorum** or can place primaries across arbitrary regions. Review the availability contract/SLA of the **specific tier**, rather than reading only self-managed Enterprise architecture.

See [Neo4j Aura Manual](https://neo4j.com/docs/aura/) and [Neo4j Support — Aura CPU usage & architecture](https://support.neo4j.com/s/article/1500013066801-Monitoring-a-Neo4j-AuraDB-Instance-CPU-usage).

## 15. Monitoring, Common Errors, and Runbooks

### 15.1. Multi-Layer Monitoring

| Layer | Metrics / checks | Rationale |
| --- | --- | --- |
| **Database** | `SHOW DATABASES`: status, role, writer, allocation address | Detect missing writer or offline databases |
| **Cluster/server** | `SHOW SERVERS`: enabled/free/cordoned, allocation eligibility | Detect servers not accepting allocations or skewed distribution |
| **Replication** | Secondary lag, transaction apply delay, routing failures | Assess READ freshness |
| **Consensus** | Writer election/quorum availability, primary communication errors | Explain WRITE unavailability |
| **Neo4j process** | CPU, heap, GC, page cache, disk, transaction log, I/O | Identify saturation |
| **Client** | READ/WRITE requests, retries, pool pending, Bolt TLS/handshake, p95/p99 | Reflect application experience |
| **Business** | Order commit success rate, accurate path queries | Never equate process health with business health |

### 15.2. Runbook A — Losing One Primary in a 3-Primary Topology

1. Identify **which database** lost an allocation, the server, and the failure domain.
2. Run `SHOW DATABASES` to inspect writer/role/status of remaining replicas; verify 2/3 quorum.
3. Re-measure synthetic WRITE and READ from the application; leader election may cause brief transient errors/latency.
4. Investigate network, disk, process/GC, and logs on the lost server; do not automatically deallocate the member before knowing the root cause.
5. Recover/rejoin or provision a replacement server per version guidance; confirm data synchronization.
6. Close the incident only after **additional fault tolerance has been restored**, not merely when WRITES resume.

### 15.3. Runbook B — Quorum Loss

- Symptoms: READs may still succeed from certain replicas while WRITE commits fail with no usable writer.
- Check how many primaries are online **and able to reach one another**; three “running” processes across three partitioned subnets do not necessarily form quorum.
- Inspect network partitions, internal TLS, cluster discovery, and configuration changes.
- Restore enough primaries in compatible states; never “force leader” by corrupting data or deleting cluster state.
- If the cluster must be rebuilt from backup, follow **Neo4j-supported recovery procedures** and evaluate actual RPO.

### 15.4. Runbook C — Secondary Read Lag

- Identify which operations require read-your-writes and which tolerate eventual reads.
- Inspect replication lag, network, disk I/O, and query load on the secondary.
- Verify bookmarks are passed properly across related Sessions.
- Avoid fixed sleeps; consider routing reads appropriately or waiting on bookmarks **with a timeout**.
- Alert on freshness according to business requirements rather than merely pinging port 7687.

### 15.5. Runbook D — Adding a Server Does Not Increase Throughput

1. Check whether the new server is **enabled**, its `modeConstraint`, and allocation eligibility.
2. Was the database topology updated to add a secondary, or is the server still empty?
3. Did the Driver receive the updated routing table and distribute READs to the secondary?
4. Do queries use indexes/constraints, or is the bottleneck at the writer/disk/locks?
5. Compare p95/p99, throughput, per-host CPU, and replication lag before and after.

**Adding infrastructure nodes does not automatically fix slow queries.** You must verify that workload is actually distributed and contention has genuinely dropped.

## 16. Backups, Rolling Maintenance, and Data Safety

### 16.1. Clustering Does Not Replace Backups

Synchronous replication will propagate **an accidental delete** to every primary; secondaries apply that change as well. Therefore:

- Use **online backups** when supported by your edition/version, or Aura-managed snapshots.
- Define RPO/RTO, retention, store copies outside the failure domain, and conduct periodic **restore drills**.
- Protect backups of **`system` database** metadata alongside user databases per policy.
- Verify backup/restore compatibility across Neo4j version upgrades.
- Reconcile data after restores, especially alongside PostgreSQL/Kafka/CDC or other systems.

### 16.2. Rolling Upgrades

With sufficient quorum and where documentation permits, members can be upgraded in stages:

1. Review **version compatibility** and upgrade instructions from the current version to the target version.
2. Back up and verify restore capability; confirm the cluster currently has healthy quorum.
3. Plan stopping/draining one member at a time per version procedure, ensuring too many primaries are never down concurrently.
4. Verify database allocations online, writer/routing, and replication lag before proceeding to the next member.
5. After each step, execute synthetic READ/WRITE probes and monitor p99/timeouts/driver retries.
6. Have a rollback plan using **supported restore/migration procedures**; never assume all downgrades are supported.

**Note on 4.4 → 5 migration:** This is a major clustering architecture change, not a simple rolling binary restart of the old cluster. Neo4j documentation recommends **provisioning a new 5.x cluster and migrating**; do not follow minor rolling-upgrade instructions as a substitute.

Sources: [Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/), [Cluster introduction](https://neo4j.com/docs/operations-manual/current/clustering/introduction/).

### 16.3. Inter-Member Security

- Permit cluster ports only between trusted servers; never expose discovery/Raft to the Internet.
- Use TLS/certificates and secret management according to version documentation.
- Protect `server.default_advertised_address` and DNS from misconfiguration into unreachable endpoints.
- Do not grant API accounts server/allocation admin privileges merely for health checks.
- Isolate backups, monitoring exporters, and logs containing topology metadata with appropriate read permissions.

## 17. Hands-On Topology Design and Testing

### 17.1. Context

An application manages a `Customer -[:PLACED]-> Order` network, using the Java Driver to write orders and Cypher to read purchasing behavior. The team plans to deploy 5 Neo4j Enterprise servers:

- Servers A/B/C placed across three availability zones.
- Servers D/E dedicated largely to READ/traversal capacity.
- Requirements: losing **one** primary must preserve WRITES; scale independent READ volume; read-your-writes must hold for the order creation flow.

### 17.2. Choosing the Topology

Proposal: **3 primaries + 2 secondaries** for database `graph_lab`, because three primaries retain quorum on a single-member failure while two secondaries distribute READs. Place **`system` primaries** and discovery properly across allocated servers, not just the business database.

On a **pre-built lab cluster with administrative privileges**, you can create the database:

~~~cypher
CREATE DATABASE graph_lab
TOPOLOGY 3 PRIMARIES 2 SECONDARIES;
~~~

Verify:

~~~cypher
SHOW DATABASES
YIELD name, address, role, writer, currentStatus
WHERE name = 'graph_lab'
RETURN name, address, role, writer, currentStatus
ORDER BY role, address;
~~~

Expect **three primary rows** and **two secondary rows** once the allocator finishes and all five allocations are online; among the three primaries, **one** is the writer under normal operation.

### 17.3. Testing Read/Write Queries Safely

Create the constraint on database `graph_lab`, not `system`:

~~~cypher
CREATE CONSTRAINT cluster_lab_customer_unique IF NOT EXISTS
FOR (c:ClusterLabCustomer)
REQUIRE c.customerId IS UNIQUE;
~~~

Run the Java Demo from section 8 with an authorized account. Once both WRITE and READ succeed within **a single Session**, record latency and verify read-your-writes. Then open two Sessions without sharing bookmarks to observe why causal dependencies must be managed across asynchronous replicas; do not force artificial lag just to “prove” an error.

### 17.4. Controlled Fault Injection

Only in a lab containing no business data:

1. Record the initial writer and status before testing.
2. Following the lab runbook, stop **one primary**; do not stop another member simultaneously.
3. Wait for election/routing stabilization per documentation; run a synthetic WRITE with a distinct ID and verify commit.
4. Execute READs from the routing client, observing transient errors and retries.
5. Restore the member, monitor rejoin and catch-up before continuing further tests.

**Never rehearse quorum loss by stopping two primaries in production.** In a lab, you can **discuss** the 2-of-3 primary failure scenario using the quorum table rather than inducing hazardous network partitions.

### 17.5. Comparing READ Scaling

Test a workload with many independent `MATCH` queries:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId, o.status
LIMIT 50;
~~~

Run at the same concurrency against two authorized configurations:

- **A:** 3 primaries, 0 secondaries.
- **B:** 3 primaries, 2 secondaries.

Measure **READ throughput, p50/p95/p99, per-server CPU, pool pending, secondary lag, and error rate**. Do not assume B is faster if the client uses `bolt://` pointing to one server, routing has not refreshed, or the query cannot distribute effectively. Test data and environment must represent production.

### 17.6. Self-Check Questions

**Question 1.** A cluster has 3 primaries and 2 primaries stop. Can new WRITES still commit?

**Answer:** No—quorum 2/3 is lost, so WRITES cannot continue committing under standard consensus. READs may still be possible on the remaining active replica depending on state.

**Question 2.** Does adding 3 secondaries give the system 3 writers?

**Answer:** No. Secondaries only serve asynchronous replication and READ queries; a standard database has one writer at a time.

**Question 3.** Can Server B as a whole be called a “secondary server”?

**Answer:** In Neo4j 5.x/2025+, primary/secondary roles belong to **database allocations**. A server can carry a `modeConstraint`, yet still hold different roles across different databases if permitted.

**Question 4.** Why might a `READ` on a secondary not see a just-committed transaction?

**Answer:** Secondaries receive transaction logs asynchronously. If a READ depends on a prior WRITE, use bookmarks/causal consistency or an appropriate read strategy.

**Question 5.** Can modern Neo4j Community form a cluster by copying `neo4j.conf` from Enterprise?

**Answer:** No. Clustering depends on edition/license, not just configuration.

**Question 6.** Does a 5-primary cluster definitely have double the write throughput of a 3-primary cluster?

**Answer:** No. A database still has a single writer; adding primaries primarily increases fault tolerance and can increase synchronization latency.

**Question 7.** Can Infinigraph property sharding be assumed as a default feature of Enterprise or Aura?

**Answer:** No. It was introduced in 2025.12, requires a separate subscription, and per current documentation is not available on Aura.

**Question 8.** Can clustering replace backups after an accidental data deletion?

**Answer:** No. Erroneous changes are replicated to all replicas; independent backups/snapshots and restore drills are required.

## 18. Misconceptions and Anti-Patterns

| Misconception | Correction |
| --- | --- |
| “Having 3 Neo4j servers means a 1-machine fault-tolerant cluster” | Must have **3 primary allocations of the HA database**, in proper failure domains with active cluster quorum |
| “Primary is a fixed server role” | Roles belong to **database copies**; servers also have `modeConstraint` |
| “Multiple primaries = multi-writer for the same database” | **One writer/leader** at a time per standard database |
| “Adding secondaries makes WRITE commits faster” | Secondaries mainly boost **READ capacity** and do not participate in quorum |
| “Force leader immediately when quorum is lost” | Risks breaking safety/consistency; follow official recovery runbooks |
| “Read-only replicas always see the newest data” | Asynchronous replication has lag; use bookmarks if read-your-writes is required |
| “Clustering automatically splits graph storage across servers” | Standard replicas hold full stores; property sharding is a separate mechanism |
| “Community supports clustering with enough RAM and config tweaks” | Enterprise clustering depends on edition |
| “4.4 configs run unchanged on 2025.x” | Architecture and discovery/settings have changed |
| “With a cluster, backups aren’t needed” | Backups remain essential to recover from human errors and disasters |
| “The Driver only needs one hardcoded `bolt://` leader” | The leader changes on failover; prefer routing URIs and proper bookmarks |
| “Aura rents VMs so users can manage `SHOW SERVERS`/topology” | Managed services impose administrative limits per tier |

## 19. Deployment and Operations Checklist

- [ ] Confirm **Neo4j version, edition/Aura tier, license**, and corresponding documentation.
- [ ] If upgrading from 4.4, review **4.4 → 5 migration**; never copy `causal_clustering.*` verbatim to newer releases.
- [ ] Define business requirements for **READ availability, WRITE availability, RPO, RTO, and latency SLOs**.
- [ ] Choose per-database topology by **quorum**: 3 primaries tolerate 1 failure; 5 primaries tolerate 2 failures.
- [ ] Use **secondaries** when read scale-out is genuinely needed; monitor lag and per-replica storage.
- [ ] Keep in mind **one writer per standard database**—do not assume more primaries equal parallel writes.
- [ ] Plan placement across failure domains instead of clustering primaries in one fault zone.
- [ ] Protect and configure the **`system` database**, cluster discovery, TLS, advertised addresses, and intra-cluster networking.
- [ ] Check server `enabled` status and allocation eligibility before altering topology.
- [ ] Use `SHOW SERVERS` and `SHOW DATABASES` to verify actual topology rather than guessing from container counts.
- [ ] Configure the Java Driver with READ/WRITE routing; use bookmarks when causal read-after-write is required.
- [ ] Never share one `Session` across threads; manage pools, timeouts, and retries against SLOs.
- [ ] Measure p95/p99, throughput, error rates, page cache, disk, GC, routing, and replication lag.
- [ ] Optimize indexes/Cypher/transactions before adding fleets of replicas.
- [ ] Plan rolling maintenance per version; avoid losing quorum from simultaneous maintenance.
- [ ] Maintain **online backups/snapshots** and rehearse restores; never treat replication as a backup.
- [ ] When using Infinigraph, confirm **subscription, version, Cypher 25, and constraints**; do not assume Aura availability.
- [ ] Maintain runbooks for primary loss, quorum loss, leader election, secondary lag, and routing failures.
- [ ] Test failover, data growth, high-degree nodes, and mixed WRITE/READ workloads.

## Official References

- [Neo4j Operations Manual — Introduction to clustering](https://neo4j.com/docs/operations-manual/current/clustering/introduction/)
- [Neo4j Operations Manual — Deploy a basic cluster](https://neo4j.com/docs/operations-manual/current/clustering/setup/deploy/)
- [Neo4j Operations Manual — Managing databases](https://neo4j.com/docs/operations-manual/current/clustering/databases/)
- [Neo4j Operations Manual — Managing servers](https://neo4j.com/docs/operations-manual/current/clustering/servers/)
- [Neo4j Operations Manual — Leadership, routing, load balancing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/)
- [Neo4j Operations Manual — Scaling with Neo4j](https://neo4j.com/docs/operations-manual/current/scalability/scaling-with-neo4j/)
- [Neo4j Operations Manual — Infinigraph property sharding](https://neo4j.com/docs/operations-manual/current/scalability/sharded-property-databases/overview/)
- [Neo4j Upgrade/Migration — Breaking changes from 4.4 to 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/)
- [Neo4j Upgrade/Migration — Versioning and upgrade paths](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Neo4j Java Driver — Routing, session and transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver — Bookmarks and causal consistency](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Aura Manual](https://neo4j.com/docs/aura/)

**Conclusion:** Neo4j cluster architecture must be selected according to **version, edition, service tier, and operational goals**. In Enterprise 5.x/2025–2026, each standard database has **primary/secondary allocations**, one **writer/leader**, Raft quorum for durable writes, and secondaries for read scaling. Three primaries tolerate one member failure; adding secondaries does not create additional writers. Combine failure-domain placement, Java Driver routing/bookmarks, quorum and replication lag monitoring, upgrade planning, and backup/restore. **Do not confuse cluster replication with sharding**, and only design for Infinigraph when your actual product and license support it.
