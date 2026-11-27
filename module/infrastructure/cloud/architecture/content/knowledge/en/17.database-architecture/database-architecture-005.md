# Replication, Read Replicas, and Read/Write Routing

As a cloud application grows its user base, its database must simultaneously serve two very different workload profiles: state-mutating transactions and read queries. If one database server handles everything, heavy reporting queries or read-intensive views can compete for CPU, RAM, I/O, and connections with critical transactions. **Database replication**, **read replicas**, and **read/write routing** are techniques for scaling serving capacity, improving availability, and distributing load appropriately.

Replication maintains copies of data across different nodes. Read replicas typically receive change streams from the writer node to serve read queries. Read/write routing decides which queries go to the primary, which can go to a replica, and when read-your-writes must be guaranteed. None of these techniques automatically provide strong consistency or safe failover. The architecture must account for replication modes, replication lag, consistency limits, write ordering, fencing, and recovery after node disconnects.

This lesson belongs to the **Database Architecture** chapter of the **Cloud Architecture** track. The focus is on trade-offs among performance, reliability, security, cost, and operability when deploying replicated databases in the cloud.

After this lesson, you can:

- Distinguish replication, backups, read replicas, standbys, and multi-primary setups.
- Explain synchronous, asynchronous, and semi-synchronous replication.
- Measure and handle replica lag, stale reads, and read-after-write consistency.
- Design read/write routing in the application, a proxy, or the database cluster.
- Choose which queries can route to replicas and which must read from the primary.
- Design failover, promotion, fencing, and split-brain prevention.
- Manage connections, transactions, session affinity, retries, and errors during node transitions.
- Evaluate topologies, RPO/RTO, costs, and recovery testability.

## 1. What Is Replication?

**Replication** is the process of maintaining one or more copies of data across separate database nodes. One node receives changes and propagates them to remaining nodes using mechanisms supported by the database engine.

In a common single-primary, multi-replica topology:

- **Primary/leader/writer:** accepts authorized writes and is typically the authoritative source for the latest data.
- **Replica/follower/reader:** receives changes from the primary and can serve read queries.
- **Replication channel:** ships logs or changes from writer to replicas.
- **Replication position/offset/LSN:** tracks the progress of changes sent, received, or applied.
- **Promotion:** elevates a replica to become the primary during a failover decision.
- **Failover:** shifts operations to another node when the primary fails or is no longer fit to serve.

Exact terminology varies by database. Engines may use WAL, binlogs, transaction logs, oplogs, or proprietary log formats. Understand the semantics of your chosen product rather than assuming all engines replicate identically.

### 1.1. Primary and Read Replica Diagram

~~~mermaid
flowchart TB
    APP["Application / API"] --> ROUTER["Read-write router"]
    ROUTER -->|Write| P[("Primary database")]
    ROUTER -->|Read| R1[("Read replica A")]
    ROUTER -->|Read| R2[("Read replica B")]
    P -->|Replication stream| R1
    P -->|Replication stream| R2
~~~

The primary handles writes; replicas receive changes and can process read queries. This diagram does not imply every write is immediately visible on replicas. The time between a commit on the primary and when a replica finishes applying it is a central part of the design.

## 2. How Is Replication Different from Backup?

Replication and backups both create extra copies of data, yet they serve different goals.

| Capability | Replication | Backup |
| --- | --- | --- |
| Primary goal | Scale read load, improve availability, or distribute data | Recover data after accidental deletion, corruption, or incidents |
| Freshness | Near real-time, subject to replication lag | Point-in-time of snapshots and archived logs |
| When primary fails | A replica may be promoted if eligible | Typically requires restoring snapshots and replaying logs |
| Accidental data deletion | Delete commands replicate to replicas | Can restore from a backup taken before the incident |
| Logical corruption | Can propagate to replicas | Clean backups prior to the bug are helpful |
| Interchangeability | Does not fully protect against all data-loss scenarios | Does not offload real-time read traffic |

If an operator accidentally runs a statement deleting an entire table, replication will replicate that operation to the replicas. Therefore, read replicas do not replace backups, point-in-time recovery, restore testing, or safeguards against destructive operations.

## 3. Primary, Read Replica, and Standby

These terms are sometimes used interchangeably, though their roles can differ:

- **Read replica:** a copy configured to accept read queries from applications.
- **Standby replica:** a copy dedicated primarily to failover or disaster recovery; it may not accept read traffic or may restrict queries.
- **Hot standby:** a node that has received and applied logs continuously so it can be activated rapidly per engine mechanics.
- **Warm/cold standby:** lower readiness levels requiring extra startup, restore, or log catch-up time.
- **Multi-primary/multi-writer:** multiple nodes accept writes, requiring more complex conflict resolution and consistency mechanisms.

A cloud service may offer read replicas and standby instances as separate options. Verify their roles, read connectivity, promotion behavior, deployment zones/regions, and committed RPO/RTO.

### 3.1. A Read Replica Is Not Automatically the Best Failover Node

A replica running heavy reporting queries may fall behind on lag or lack spare capacity. Promoting it to primary without verification can switch the system to a node missing recent commits or unable to sustain write load. Failover designs should designate and monitor explicit candidate replicas based on freshness, health, and capacity.

## 4. Synchronous and Asynchronous Replication

The critical difference lies in when the primary acknowledges a commit relative to when replicas receive and apply changes.

### 4.1. Asynchronous Replication

In asynchronous replication, the primary commits and returns success to the client without waiting for replicas to apply the change.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant P as Primary
    participant R as Replica
    A->>P: INSERT / UPDATE
    P->>P: Commit transaction
    P-->>A: Commit success
    P-->>R: Send log/change
    R->>R: Apply change
~~~

Advantages:

- Lower write latency because the primary does not wait on replicas.
- Replicas can sit farther away and tolerate higher network latency.
- The primary keeps accepting writes if a replica temporarily falls behind, within log/storage limits.
- Fits many read-heavy workloads where bounded stale reads are acceptable.

Trade-offs:

- A client can write successfully, then immediately read from a replica and miss its own write.
- If the primary fails before logs are shipped or applied, acknowledged transactions may be absent from the promoted replica.
- Replication lag can grow under heavy write bursts or under-provisioned replicas.

### 4.2. Synchronous Replication

In synchronous replication, the primary waits for confirmation from a replica or quorum per system semantics before acknowledging the commit to the client.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant P as Primary
    participant R as Replica
    A->>P: INSERT / UPDATE
    P->>P: Prepare/record transaction
    P-->>R: Send commit record
    R->>R: Persist required log
    R-->>P: Acknowledgement
    P-->>A: Commit success
~~~

The advantage is reduced risk of losing acknowledged transactions across the covered nodes/quorum. In return, write latency and availability depend on networking, replica placement, and the required acknowledgement count. If a required replica becomes unresponsive, writes may stall or halt depending on configuration.

### 4.3. Semi-Synchronous and Quorum Replication

Some engines support semi-synchronous mode: the primary waits for at least one replica to receive or persist a defined durability level, without waiting for every replica to finish applying the transaction. Distributed databases may use quorums for commits and leader election.

Never broadly assume that "semi-sync guarantees every replica already has the data." Read the exact specification on whether acknowledgements mean log received, flushed to disk, or applied. Those levels directly dictate RPO and read consistency.

### 4.4. Quick Comparison

| Criterion | Async | Sync | Semi-Sync / Quorum |
| --- | --- | --- | --- |
| Write latency | Typically lower | Can be higher | In between depending on topology |
| Network dependency on replicas | Lower at commit time | Higher | Per quorum/ack policy |
| Risk of losing committed writes on failover | Potentially higher | Lower within guaranteed scope | Depends on ack level and quorum |
| Read replica freshness | Can lag | Not necessarily applied immediately even when log-committed | Depends on apply progress |
| Availability on node/network failure | Primary can keep writing | Can block if mandatory acks are missing | Depends on achieving quorum |
| Use cases | Read scaling, latency-sensitive writes | High durability needs with suitable topology | Balancing durability and latency |

## 5. Understanding the Three Milestones: Send, Receive, and Apply

A replication pipeline has distinct stages of progress:

1. The primary generates a log record upon transaction commit.
2. The log is transmitted over the network.
3. The replica receives and persists the log to durable storage.
4. The replica replays/applies the log to update data pages or queryable state.

Engines may report separate metrics for each stage. If a replica has received the log without applying it yet, it may hold the data durably while queries still do not see the changes.

When assessing lag, distinguish:

- **Transport/send lag:** changes not yet sent or transmitted to the replica.
- **Receive/write lag:** replica has not yet received/flushed the logs.
- **Apply/replay lag:** logs received, but replay has not caught up.
- **Query visibility:** data is applied and visible to queries per engine isolation semantics.

Never treat a vaguely defined "replica lag" number as sole proof of durability or freshness.

## 6. Replica Lag and Stale Reads

**Replica lag** is the progress or time gap between data on the primary and on a replica. A lagging replica can return outdated state.

Example:

1. A customer creates a booking on the primary.
2. The primary commits and returns success.
3. The client loads the booking screen from a read replica.
4. The replica has not applied the new write yet.
5. The client sees "no booking found" even though the transaction succeeded.

This is a read-after-write failure when the application expects to immediately read newly written data.

### 6.1. Time Lag vs. Log Position Lag

Lag can be measured in estimated seconds or log position distance. The two are not strictly equivalent. During idle periods, byte/LSN distance may vary while apply time is short; during long-running transactions or lock contention, a small byte gap can still stall apply time.

Monitor all of:

- Latest commit timestamp on the primary.
- Replay/apply timestamp or log position on each replica.
- Bytes/transactions behind where exposed by the engine.
- Replication queue backlog.
- Replica query latency and health.
- Per-replica lag, not just cluster averages.

### 6.2. Why Does Lag Grow?

- Write rates exceed replica replay capacity.
- Replicas have less CPU, RAM, disk IOPS, or network bandwidth than the primary.
- Heavy reporting queries contend for CPU/I/O on the replica.
- Long-running transactions or DDL statements block apply.
- Cross-zone/cross-region networking degrades or drops.
- Replica maintenance, restarts, or post-outage catch-up backlogs.
- Replication slots/log retention hold excessive WAL/binlogs, creating storage pressure.

## 7. Read-After-Write Consistency

Read-after-write requires callers to see changes they just wrote. With async replicas, routing all reads to replicas can violate this guarantee.

### 7.1. Sticky Reads / Session Affinity

After a write, the application can temporarily route related reads for the same session to the primary. This is often called read-your-writes routing or primary stickiness.

You can attach context to requests:

~~~text
requestContext:
    principalId
    tenantId
    lastWriteDatabase = primary
    writeCommitToken = replication_position
~~~

The stickiness window should be long enough to protect user experience without staying sticky forever and pushing all traffic back to the primary. Clear the flag once a replica catches up or after a bounded TTL, per the consistency contract.

### 7.2. Wait Until Replica Catches Up

Some engines return a commit token/position and let applications wait for a replica to reach that position. Conceptual flow:

1. Write to primary and commit.
2. Capture the write position/token.
3. Select a replica and inspect its replay position.
4. If the replica has not reached the token, wait up to a short deadline.
5. If it still lags, fall back to the primary or return an appropriate status.

API names and semantics vary by database; never invent position comparisons without understanding how your engine defines them.

### 7.3. Primary Reads for Sensitive Operations

These queries usually require the latest data or authoritative source:

- Reading state immediately after creation/update.
- Checking balances or limits before executing a new transaction.
- Performing final inventory checks before confirming a reservation.
- Checking payment/refund status prior to triggering the next command.
- Checking permissions or account status for sensitive authorization decisions.
- Queries that must participate in a write transaction or hold locks.

Replicas can serve histories, lists, and reports with bounded stale tolerance where business rules allow.

## 8. Where Should Read/Write Routing Happen?

There are three primary placement options, which can also be combined.

### 8.1. Routing in the Application

The application maintains two explicit database connections/pools:

- Writer connection to the primary.
- Reader connection to one or more replicas.

The repository/data access layer decides which queries use writer vs. reader. The benefit is that application code understands use cases and consistency needs. The downside is implementing consistent routing, health detection, and failover handling across every service.

### 8.2. Database Proxy or Connection Router

A proxy sits between applications and the database cluster, routing connections by endpoint, session, or policy. Depending on the product, it may provide connection pooling, stable endpoints, health checks, and failover support.

The benefit is reducing duplicated routing code and centralizing governance. The trade-off is another component in the connection path requiring HA, capacity, monitoring, and careful handling of SQL/session state. A proxy cannot always infer which queries are safe for replicas.

### 8.3. Managed Database Role Endpoints

Many cloud services expose writer endpoints, reader endpoints, or cluster endpoints. Applications connect by role rather than individual nodes. This is convenient, yet you must verify:

- Does the reader endpoint load-balance connections or individual queries?
- Do active connections shift automatically during failover?
- Do DNS TTLs and connection pools cause clients to stick to old IPs/nodes?
- Does the reader endpoint exclude lagging or under-maintenance replicas?
- Is read-after-write/session affinity supported?

Never assume a reader endpoint automatically guarantees consistency or per-statement load balancing.

### 8.4. Comparison

| Routing Location | Pros | Trade-offs |
| --- | --- | --- |
| Application | Understands domain and per-query consistency | Logic spread across codebases; clients must stay consistent |
| Proxy/router | Centralized policies, pooling, and health routing | Extra network hop and HA dependency; SQL semantics can get complex |
| Managed reader/writer endpoints | Simplifies client configuration | Features and semantics depend on the provider |

## 9. Query Classification Rules

Avoid naive rules like "`SELECT` always goes to replicas, `INSERT`/`UPDATE` to primary." A `SELECT` may be the gating check of a financial transaction; a stored procedure may mutate data; a transaction may read-then-write and require a consistent snapshot.

| Operation Type | Recommended Target | Rationale |
| --- | --- | --- |
| `INSERT`/`UPDATE`/`DELETE` | Primary/writer | Authoritative write source |
| `SELECT` immediately following a write in the same request | Primary or confirmed caught-up replica | Preserves read-your-writes |
| Reading inventory before committing a hold | Primary or appropriate transaction coordinator | Avoids deciding on stale state |
| Aggregate dashboards with staleness tolerance | Read replica / projection | Offloads reads from writer |
| Transaction history tolerating a few seconds of lag | Replica under explicit contract | Read-heavy and staleness-tolerant |
| Queries inside a write transaction | Same transaction/primary | Preserves isolation and consistency |
| Heavy read-only analytics | Dedicated replica or warehouse | Prevents starving transactional load |
| Critical authorization checks | Authoritative source per consistency requirement | Replica lag can cause wrong access decisions |

A `SELECT` can acquire locks, use temporary tables, rely on session state, or invoke side-effecting stored procedures. Route based on semantics and workload, not SQL keywords alone.

## 10. Transactions and Connection Pooling

Read/write routing must preserve transaction integrity. Once a transaction begins on the primary, all queries in that transaction generally must remain on the same connection/node until commit or rollback.

Rules:

- Never route a mid-transaction `SELECT` off to a different replica.
- Never swap connections under an open transaction during proxy failover without handling transaction state.
- Separate writer and reader pools and cap total connections to database capacity.
- Clean up stale connections after failover; clients must reconnect per policy.
- Release connections promptly on request timeout or cancellation.
- Prevent oversized reader pools from exhausting total connections even when DB CPU looks low.

### 10.1. Read Transactions and Isolation

A transaction reading multiple tables may require a consistent point-in-time snapshot. Issuing sequential queries across different replicas or nodes can return results from inconsistent points in time.

To preserve consistency, run the transaction on a node supporting the required isolation level, or read from a snapshot/projection with explicit semantics. Never split a single logical transaction arbitrarily across multiple read replicas.

## 11. Offloading Reads: Replicas, Caches, or Read Models?

Read replicas are one way to scale reads at the database layer. Not every query belongs on a replica.

| Solution | Best Fit When | Trade-offs |
| --- | --- | --- |
| Read replica | Queries match source schema and tolerate bounded lag | Node cost, replication overhead, and lag |
| Cache | Repeated lookups with controllable freshness | Invalidation, cache stampedes, and isolation |
| CQRS / read projection | Query shape differs from write model; custom aggregates/indexes needed | Sync pipeline and eventual consistency |
| Data warehouse | Large analytics/reporting with heavy scans and aggregations | Unsuited for low-latency transactional reads |
| Vertical scaling | Moderate load needing a simple solution | Hardware ceilings and upgrade costs |
| Sharding / partitioning | Data or throughput exceeds a single node | Higher data distribution and query complexity |

A report scanning billions of rows does not necessarily belong on a production read replica; it can spike lag and saturate I/O. A warehouse or dedicated projection may fit much better.

## 12. Replication Topology: Single-Region or Multi-Region?

### 12.1. Same-Region Replicas

Replicas in the same region—potentially across availability zones—typically offer lower network latency and fit in-region read scaling/HA. Verify whether the service guarantees cross-zone replica placement and how promotion behaves.

### 12.2. Cross-Region Replicas

Replicas in another region support disaster recovery, local reads for distant users, or geographic compliance goals. Trade-offs include higher network latency, greater replication lag, data transfer fees, disconnect risks, and more complex promotion procedures.

### 12.3. Example Topology

~~~mermaid
flowchart TB
    subgraph R1["Region A - primary region"]
        APP["Application"] --> W[("Primary writer")]
        W --> RA1[("Reader AZ A")]
        W --> RA2[("Reader AZ B")]
    end
    W -->|Cross-region replication| RB[("DR replica - Region B")]
    DRAPP["DR application"] -. "Activate on failover" .-> RB
~~~

A cross-region replica can serve as a DR candidate. If applications read directly from a remote-region replica, assess lag and latency; if it exists strictly for recovery, you may keep regular read traffic disabled.

## 13. Read Scaling and Practical Limits

You can estimate read and write load to size replica counts, though adding replicas does not scale throughput linearly forever.

If each replica handles $Q$ queries/sec for a measured workload and you have $N$ relatively balanced replicas:

\[
Q_{\text{aggregate}} \approx N \times Q
\]

This is an ideal estimate. Real capacity is bounded by primary log shipping, networking, storage, connection routers, query skew, cache locality, and replication overhead. If queries have hotspots or one tenant dominates load, balancing connection counts does not balance CPU or I/O.

Benchmark using realistic query mixes, not a trivial single `SELECT`. Monitor p95/p99 latency, CPU, IOPS, buffer/cache hits, connection counts, replication lag, and cost.

### 13.1. Replicas Can Slow Down the Primary

Replication consumes resources to generate, transmit, and maintain log streams. Many replicas or cross-region replicas increase network, storage, and CPU load. Depending on the engine, lagging replicas or stalled replication slots force the primary to retain logs longer, increasing disk pressure.

## 14. Failover, Promotion, and Fencing

Failover shifts the writer role to another node when the primary can no longer continue. It is a stateful transition, not merely changing a hostname.

A typical failover sequence includes:

1. Detecting primary failure or isolation.
2. Verifying state and choosing a candidate replica.
3. Assessing replica freshness and potential transaction loss.
4. Preventing the old primary from accepting further writes.
5. Promoting the candidate via engine/control plane mechanisms.
6. Updating the writer endpoint/routing.
7. Dropping stale application connections and reconnecting.
8. Verifying consistency, read/write health, and the new replication topology.
9. Rebuilding or rejoining the old node as a new replica once safely synchronized.

### 14.1. Split Brain

**Split brain** happens when two nodes both believe they are primary and both accept writes. This leads to diverged data, conflicts, and loss of automatic mergeability.

**Fencing** is required to guarantee the old primary can no longer write before promoting the new writer. Depending on the system, fencing uses quorums/leases, control-plane revocation, network isolation, writer credential revocation, or fencing tokens. Simply updating DNS while the old primary still accepts writes is not safe fencing.

### 14.2. RPO and RTO

- **RPO (Recovery Point Objective):** maximum acceptable data loss measured in time/recovery point.
- **RTO (Recovery Time Objective):** target duration to restore service.

Async replication can have an RPO greater than zero if the primary dies before logs replicate; sync/quorum replication reduces RPO within guaranteed semantics while adding latency or quorum dependencies. RTO also includes failure detection, promotion, endpoint propagation, client reconnection, application verification, and resolving ambiguous in-flight transactions.

Never equate database promotion time alone with full application RTO.

## 15. In-Flight Transactions During Failover

If the primary drops between the application sending `COMMIT` and receiving a response, the client may not know whether the transaction committed. Blindly retrying the entire operation can create duplicate records or double charges.

Designs require:

- Idempotency keys for critical commands/transactions.
- Unique constraints or business keys to prevent duplicates.
- Error-classified, bounded retries.
- Reconciliation when transaction outcome is unknown.
- Explicit cleanup of invalid connections and clear rollback/reconnect handling.
- Never assuming an open transaction continues seamlessly onto the new primary.

A network error during commit does not guarantee the transaction rolled back. Applications should query state by business identifier or idempotency key before retrying side effects.

## 16. Read Routing Under High Replica Lag

Routers should not blindly round-robin across all replicas regardless of health and lag.

A sound policy includes:

- Connection and basic query health checks.
- Use-case-specific lag thresholds.
- Excluding replicas that are resyncing, in maintenance, or overloaded.
- Preferring same-region/same-zone replicas where possible.
- Falling back to the primary only when the primary has spare capacity and the query is permitted.
- Returning degraded/temporarily unavailable responses when consistency contracts cannot be met.
- Tracking the rate of reads routed to primary due to lag.

### 16.1. Avoiding Primary Overload During Fallback

If all replicas lag simultaneously and the router shifts every read to the primary, the writer can collapse right when it is already under replication stress. Cap fallback traffic, prioritize critical queries, rate-limit non-essential reads, and use load shedding or caching.

Avoid "try replica, wait for a long timeout, then retry primary" on every query; that pattern multiplies tail latency and total query load.

## 17. Security for Replication and Read Endpoints

Replicas hold the same data as the primary and must receive the same level of protection.

- Encrypt replication traffic and authenticate nodes with proper identities/certificates.
- Encrypt replica storage and snapshots per policy.
- Restrict network paths between primary, replicas, and applications.
- Ensure read-only accounts genuinely lack write/DDL or excess administrative privileges.
- Separate writer and reader credentials.
- Never allow end users direct database access just because a node is labeled a read replica.
- Enforce authorization/tenant filters at the application or data layer; read-only privileges do not equate to cross-tenant access.
- Audit promotion permissions, topology edits, replication config changes, and sensitive data queries.
- Apply identical retention/privacy policies to replica snapshots and backups.

If the primary enforces row-level security or restricted views, verify those same policies apply on replicas and across actual access paths. Never assume reading from a replica automatically preserves tenant isolation.

## 18. Managing Schema Changes and DDL

Schema migrations affect replication and concurrently running application versions.

A safe workflow typically uses expand–migrate–contract:

1. **Expand:** add new schema structures compatibly with existing code; avoid immediate renames or drops.
2. **Deploy application:** roll out code that reads/writes the compatible schema.
3. **Migrate/backfill:** update data in rate-limited batches to avoid inducing lag.
4. **Verify:** check both primary and replicas, query plans, and replication health.
5. **Contract:** drop old columns/schemas only once no consumers depend on them.

DDL replication semantics vary across engines. Some operations acquire long locks, spike replica apply lag, or must run out-of-band. Test on production-like engine versions and topologies.

## 19. Read Replicas and Reporting

Moving reports to replicas shields the primary from heavy scans, yet replicas share finite resources and can still overload.

Best practices:

- Isolate heavy reporting onto a dedicated replica or data warehouse.
- Enforce query timeouts and resource groups/workload management where supported.
- Avoid running massive full-table scans while replicas are catching up.
- Track lag correlated with report execution times.
- Define freshness expectations for dashboards and exports.
- Cap concurrency and export row limits.
- Never run writes or side-effecting stored procedures from read-only accounts.

For reports needing point-in-time consistency across multiple queries, use snapshots or a reporting projection rather than running long queries against a continuously updating replica.

## 20. Application Routing Example

A data access layer can classify queries by consistency requirement.

~~~java
enum ReadConsistency {
    STRONG,
    EVENTUAL
}

public final class DatabaseRouter {
    private final DataSource writer;
    private final DataSource reader;

    public DatabaseRouter(DataSource writer, DataSource reader) {
        this.writer = writer;
        this.reader = reader;
    }

    public Connection getConnection(ReadConsistency consistency)
            throws SQLException {
        return consistency == ReadConsistency.STRONG
                ? writer.getConnection()
                : reader.getConnection();
    }

    public Connection getWriteConnection() throws SQLException {
        return writer.getConnection();
    }
}
~~~

This is a conceptual sketch. Production routing must account for transaction context, session stickiness, failover, health/lag, and connection lifecycles. Do not force callers to choose `STRONG`/`EVENTUAL` ad hoc; repositories/APIs should codify policies per use case.

### 20.1. Repository Policy Example

~~~text
createBooking(command):
    write transaction on primary
    return bookingId and commit position

getBookingImmediately(bookingId):
    read primary
    or wait for a replica to reach commit position

listPastBookings(customerId):
    read eligible replica
    stale tolerance = product-defined

checkInventoryBeforeReservation(assetId):
    read authoritative state on primary
    then execute reservation transaction
~~~

The key point is that consistency requirements belong to the use case. Node selection should not be buried inside a router blind to domain semantics.

## 21. Testing Replication and Failover

Merely verifying connectivity to a replica is insufficient. Test data, lag, routing, and application behavior.

- **Replication correctness:** write data and confirm replicas receive/apply accurately in required order.
- **Lag tests:** increase write load, run heavy replica queries, and measure lag behavior.
- **Read-after-write tests:** write then read across every route to verify consistency semantics.
- **Failover tests:** perform controlled primary termination; measure detection, promotion, endpoint updates, and reconnection.
- **Split-brain tests:** verify the old primary is fenced before the new writer activates.
- **Unknown commit tests:** sever network between commit and response; verify idempotency and reconciliation.
- **Replica outage tests:** failing one replica stops the reader router from sending traffic to it.
- **Restore tests:** recover from backups independently of replication.
- **DDL/migration tests:** apply schema changes under load and measure locks and replication lag.
- **Security tests:** confirm reader accounts cannot write, and verify tenant isolation and promotion permissions.

### 21.1. Runbook Drills

Each scenario needs an owner, entry criteria, abort criteria, data-loss assessment steps, promotion commands, endpoint updates, post-failover validation, and old-node rejoin procedures. Rehearse in production-equivalent staging before applying to production.

## 22. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Treating read replicas as backups | Accidental deletes/corruption replicate to copies | Separate backups/PITR and restore drills |
| Routing every `SELECT` to replicas | Read-after-write bugs and stale business decisions | Classify queries by consistency requirement |
| Assuming async replication has zero lag | Broken UI or flawed business decisions | Measure lag and define stale tolerance |
| Selecting replicas by blind round-robin | Queries hit overloaded or lagging nodes | Health- and lag-aware routing with load metrics |
| Promoting a lagging replica | Loss of commits acknowledged on the old primary | Verify log position/RPO and enforce fencing |
| Changing DNS without fencing the old primary | Split brain with two writers | Enforce fencing/quorum and verify writer role |
| Falling back 100% of reads to primary | Writer collapses during replica issues | Cap fallback, prioritize, and shed load |
| Spanning transactions across multiple nodes | Broken isolation and inconsistent snapshots | Keep each transaction on one connection/node |
| Blindly retrying failed commits | Duplicate transactions or side effects | Idempotency keys and reconciliation |
| Adding replicas without measuring workload | Costs and log pressure rise without matching throughput | Benchmark query mixes and replication overhead |
| Running heavy analytics on production read replicas | Lag spikes, hurting readers and primary | Dedicated reporting replica or warehouse |
| Monitoring only cluster-average lag | One stalled replica/partition goes unnoticed | Monitor per-node lag and apply progress |
| Unthrottled DDL/backfills | Replicas lag behind and apps hit locks | Expand–migrate–contract, batching, and rate limits |
| Sharing writer/reader credentials | Read accounts can write or escalate privileges | Separate identities and apply least privilege |

## 23. Design and Implementation Process

1. **Measure current load:** read/write ratio, query mix, peak QPS, connections, CPU, IOPS, and p95/p99 latency.
2. **Define consistency requirements:** which flows need strong/read-your-writes consistency; acceptable staleness windows.
3. **Set RPO/RTO:** define acceptable data loss and service recovery windows.
4. **Choose replication mode:** async, sync, or semi-sync based on durability, latency, and topology.
5. **Select topology:** primary + readers, standby, cross-zone/cross-region, or multi-writer if truly required.
6. **Design routing:** application, proxy, or managed endpoints; define read/write policies.
7. **Define lag policies:** thresholds, fallbacks, query priorities, stale handling, and alerts.
8. **Design failover:** candidate selection, fencing, promotion, endpoint updates, and node rejoin.
9. **Isolate workloads:** dedicated replicas, caches, projections, or warehouses where needed.
10. **Enforce security:** encryption, separate credentials, network isolation, auditing, and tenant authorization.
11. **Test thoroughly:** lag, read-after-write, failover, unknown commits, backup restores, and DDL.
12. **Operate continuously:** capacity, log retention, connection pools, cost, and periodic drills.

## 24. Well-Architected Evaluation

| Perspective | Design Questions |
| --- | --- |
| **Reliability** | Does the replication mode match RPO? Are candidates caught up? Is failover fenced and rehearsed? Are independent backups restore-tested? |
| **Security** | Do replicas match primary data protections? Are reader/writer credentials split? Are networking, encryption, tenant isolation, and promotion audits clear? |
| **Performance Efficiency** | Is read load actually distributed? Do lag, p95/p99, connections, and I/O meet SLOs? Do reports disrupt replication? |
| **Cost Optimization** | Do replicas, cross-region transfers, log storage, proxies, and ops costs align with load and SLOs? |
| **Operational Excellence** | Are lag dashboards, alerts, routing policies, failover/rejoin runbooks, and transaction reconciliation in place? |

### Acceptance Checklist

- [ ] Primary, read replicas, and standbys have clear roles, regions/zones, and owners.
- [ ] Replication mode and acknowledgement semantics are understood and documented.
- [ ] RPO/RTO are tied to topology and verified.
- [ ] Replica lag is monitored per node with clear thresholds.
- [ ] Queries are classified by consistency rather than blindly routing all `SELECT`s to replicas.
- [ ] Read-after-write is protected via primary stickiness or position-waiting where required.
- [ ] Transactions remain bound to an appropriate single connection/node.
- [ ] Reader/writer connection pools and fallback paths are bounded.
- [ ] Failover covers candidate selection, fencing, promotion, reconnection, and rejoin.
- [ ] Unknown commits and retries use idempotency/reconciliation.
- [ ] Replicas are not treated as backups; PITR/backups have tested restores.
- [ ] Separate reader/writer credentials, encryption, networking, and tenant authorization are verified.
- [ ] Load tests cover realistic query mixes, lag, cross-region paths, and heavy reporting.
- [ ] Dashboards, alerts, and runbooks exist for lag, failover, storage, and connections.

## 25. Applied Exercise

An equipment-rental platform runs a primary database serving transactions. Peak traffic is 70% reads and 30% writes. The order-listing page tolerates up to 3 seconds of lag; however, immediately after a customer creates a booking, the confirmation screen must show the newly created order. End-of-day reporting runs heavy aggregate queries. The business requires a maximum RPO of 5 seconds for an in-region primary outage and a 2-minute RTO.

Design the following:

1. Should you add same-region read replicas? Do you need a cross-region replica/standby for DR?
2. Choose async, sync, or semi-sync on each replication link; explain the impact on latency and RPO.
3. Which queries route to replicas and which must read from the primary?
4. How do you protect read-after-write on the confirmation screen?
5. Design lag thresholds, fallbacks, and alerts when a replica exceeds 3 seconds.
6. Should heavy reports run on a dedicated replica or a warehouse, and what criteria decide?
7. Describe failover including fencing, promotion, DNS/endpoints, reconnection, and old-node rejoin.
8. If a client times out right at commit, how does the system prevent duplicate bookings?
9. How will you test to prove real-world RPO/RTO and consistency?

A well-grounded approach routes order listings to read replicas while lag stays under threshold, keeps post-booking confirmation reads on the primary or waits for the replica to reach the commit position, offloads heavy reporting to a warehouse or dedicated replica, and selects a DR topology matched to RPO/RTO. Prove RPO/RTO through live drills rather than relying solely on service configuration flags.

**Key takeaway:** Replication creates copies to support reads, availability, or recovery; read replicas help offload reads but typically incur replica lag; read/write routing must respect each use case's consistency needs. Safe failover also requires fencing, controlled promotion, handling ambiguous transactions, and independent backups. Strong design balances freshness, latency, durability, cost, and operability rather than merely adding more replicas.
