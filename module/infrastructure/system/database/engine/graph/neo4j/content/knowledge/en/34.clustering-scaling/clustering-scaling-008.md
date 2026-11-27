# Network Latency, Network Partitions, and Impact on Serviceability in a Neo4j Cluster

## 1. From a Real Incident to Availability Questions

A B2B platform manages a supply graph with `Company`, `Product`, `Customer`, and `Order` nodes connected by `SUPPLIES` and `PLACED` relationships. Neo4j runs as a cluster so the Java Driver and Spring Data Neo4j can keep reading and writing when a server fails.

One day, the order-creation API begins timing out. Two of the three Neo4j machines are still up, the product-lookup dashboard works intermittently, yet some users receive stale results. Any of these may have occurred:

- A **network partition** split the primaries into two groups unable to reach each other.
- The cluster still holds **write quorum**, yet the Java service cannot connect to the majority side.
- Primaries hold quorum, but latency between machines required to confirm commits is too high.
- A secondary near users continues serving reads while lagging behind new transactions due to asynchronous replication.
- The Driver holds a stale routing table or an unreachable bootstrap address.
- Neo4j committed the transaction, yet the response packet was lost, leaving the client unsure whether the write succeeded.

This lesson in the **Clustering and Scaling** chapter explains the mechanics, monitoring signals, architectural trade-offs, and controlled drills. The goal is not merely “how many servers are in the cluster,” but **which queries are served, how fresh the data is, and how much latency users experience**.

> Scope: Neo4j Enterprise cluster with **primary/secondary** replicas and Java Driver 6.x. Neo4j Community/standalone lacks Enterprise cluster Raft/quorum capabilities. On AuraDB, cluster structure and administrative controls are managed by the service per tier.

## 2. Distinguishing Read Availability, Write Availability, Freshness, and Durability

| Concept | Question | Conditions to analyze |
| --- | --- | --- |
| **Write availability** | Can `CREATE`, `MERGE`, `SET`, `DELETE` commit? | Writer and **primary majority** in that database’s group are operational, plus network/routing path to writer |
| **Read availability** | Can a replica serve `MATCH` queries? | Primary/secondary replica is reachable with sufficient read privileges |
| **Freshness** | Does a read observe newly committed writes? | Replication lag, bookmarks, consistency level required by the use case |
| **Durability** | After commit, will machine failures lose the transaction? | Commit/quorum guarantees, disk health, and backups |
| **Application availability** | Do Java/Spring endpoints still meet SLOs? | Client networking, routing, pool, auth, queries, failover, and external dependencies |

A database can **lose write capability while remaining readable** from healthy replicas, though reads may be stale. Conversely, the database may be healthy while the Java service cannot reach it due to DNS, firewall, or TLS errors.

**Serviceability is not merely an open TCP port.** A health check returning HTTP 200 does not prove a write transaction will be accepted by a majority, nor that every replica has applied the latest logs.

## 3. Cluster Architecture: Primary, Secondary, Writer, and Raft

### 3.1. Primary/Secondary Are Per-Database Roles

Neo4j Enterprise can host multiple databases in one cluster. Each database has its own topology; Server A can be a primary for `orders` and a secondary for `catalog`.

```text
                    Neo4j Enterprise cluster
                   Server A  Server B  Server C
database orders     Primary   Primary   Primary
                    Writer    Follower  Follower

database catalog    Secondary Primary   Primary
                       -      Writer    Follower
```

**Leader/writer belongs to each database’s Raft group**, not as a permanent label for an entire server. The writer role can shift after an election or topology change.

### 3.2. Primaries Confirm Writes via Quorum

In a database with three primaries:

```text
 Java Driver --WRITE--> P1 (writer)
                            | \
                      Raft  |  \ Raft
                            v   v
                           P2   P3
                          (ack) (slow)
                            |
                  P1 + P2 = quorum
                            |
                     valid commit
```

Conceptual flow:

1. Client sends the transaction to the database’s writer primary.
2. Writer orders changes into the Raft log.
3. Writer ships logs to follower primaries.
4. The transaction requires acknowledgment from a **primary majority** to be recognized as committed.
5. After commit, the client receives confirmation if the client network path remains healthy.

In a three-primary group, quorum is **two**. The writer does not wait for all followers; if the nearest follower is unavailable, the writer may need an ACK from a more distant follower, raising write latency.

### 3.3. Secondaries Replicate Asynchronously for Read Scaling

Secondaries pull transaction logs from upstream via catch-up:

- Can serve **read-only** queries.
- Do not vote in Raft and never become writer simply by being added to the cluster.
- Can **lag** behind primaries.
- Help distribute read workloads and scale read throughput when resources permit.
- Do not replace a lost primary when computing write quorum.

This explains why “adding five secondaries” will not resolve a loss of primary majority.

## 4. Quorum and Fault-Tolerance Limits

For `N` primary replicas of **one database**:

```text
quorum = floor(N / 2) + 1

Primaries that can be lost while preserving writes
  = N - quorum
```

| Primaries | Quorum | Primaries that can be lost | Meaning |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | Minimal, no primary fault tolerance |
| 2 | 2 | 0 | Losing one primary loses write availability |
| 3 | 2 | 1 | Common HA pattern |
| 5 | 3 | 2 | Survives two primary failures if remaining members stay connected |

The formula `N = 2F + 1` is commonly used to size primaries to tolerate `F` failures. However, **tolerating F primary failures does not automatically mean surviving F datacenter losses**: that depends on how replicas are distributed across zones.

This quorum is **per database**. The `system` database has its own topology; if `orders` retains quorum while `system` loses it, administrative metadata operations may fail differently from regular data queries.

## 5. Along Which Paths Does Network Latency Affect Queries and Commits?

| Path | Description | Impact |
| --- | --- | --- |
| Client ↔ Bolt | Java Driver sends Cypher, receives records, opens connections | Adds directly to read/write request time |
| Writer ↔ primary followers | Raft replication, heartbeats, and ACKs | Affects **commit latency** and elections |
| Primary/upstream ↔ secondary | Transaction log shipping | Affects **read freshness** and catch-up time |
| Driver ↔ routing endpoint | Routing tables, DNS, bootstrap | Affects failover/routing refresh |
| Server ↔ disk/CPU/GC | Not network, yet slows Raft processing | Easily misdiagnosed as a network error |

### 5.1. Write Timing Model

A reasoning model, **not a precise Neo4j measurement formula**:

```text
T_write_end_to_end
 ≈ T_client_to_writer
 + T_execute_and_validate
 + T_replicate_to_majority
 + T_commit_and_response
 + T_queueing
```

`T_replicate_to_majority` depends on receiving ACKs from **enough followers to reach quorum**, not simply the sum of RTTs to all primaries.

The numbers below are **hypothetical**, not benchmarks:

| Network path | Example RTT |
| --- | ---: |
| API ↔ primary in same zone | 2 ms |
| Primary ↔ primary in same datacenter | 1 ms |
| Primary ↔ primary across regions | 80 ms |
| API ↔ local secondary | 2 ms |

When a local follower disconnects and ACKs must come from a distant region, write p95 can climb noticeably even with unchanged CPU and Cypher. Yet **you cannot conclude “adding 80 ms RTT slows every write by exactly 80 ms”**: disk handling, batching, leader location, queueing, and jitter all interact.

### 5.2. Read Latency and Locality

A query traversing many relationships can return thousands of records. If the app sits in region A while the read endpoint sits in region B, response transfer time becomes significant. A secondary near the app shortens the path, yet if data lags:

- Queries without bookmarks may observe stale snapshots.
- Queries with bookmarks may **wait for catch-up**, eroding the latency advantage.
- Fast local stale reads may be the wrong choice for a post-payment API requiring fresh state.

**Always distinguish RTT, query p95/p99, and replication lag**; they are not the same metric.

## 6. Network Partitions: Servers Alive Yet Unreachable

A **network partition** occurs when server groups remain running yet cannot reliably exchange traffic. Causes include firewalls/security groups, switches/routers, WAN cuts, packet loss, routing issues, or blocked cluster ports.

```text
Initially:                   During partition:
 P1 ----- P2                   P1 ----- P2
  \       /                     (2 machines)
   \     /                           |
      P3                         X   X
                                     P3
                                  (1 machine)
```

Raft protects commit history: **only a quorum-holding group can acknowledge new writes**. The minority side cannot declare itself an independent writable cluster.

That **does not guarantee every client stays served**:

- Clients that can reach only the minority side will error even while the majority side is healthy.
- Time is needed for elections, routing refreshes, and retries.
- A secondary isolated from upstream may continue returning stale data if reachable.
- Once networking heals, lagging members must **catch up** on logs.

### Three Different Connectivity Losses

| Lost link | Primary consequence |
| --- | --- |
| Java service ↔ Bolt members | App appears unavailable even though internal cluster holds quorum |
| Primary ↔ primary Raft | Quorum loss / leader election / no commits on minority side |
| Secondary ↔ upstream | Read scaling/freshness degrades; primary quorum may stay fine |

Never rely solely on IP `ping` to conclude client and cluster protocols/ports are healthy.

## 7. Three-Primary Scenario, 2–1 Partition

Suppose `orders` has P1, P2, P3, with P1 initially acting as writer.

### 7.1. P3 Is Isolated

```text
          P1 writer ------ P2 follower
                \          /
                     2/3 quorum

             X-----------X
                     P3
                   isolated
```

Expected outcome:

- P1+P2 form quorum and **can continue committing** if the rest of the system is healthy.
- P3 cannot commit new writes independently.
- Data on P3 will miss transactions committed after the partition began.
- Clients trapped on P3’s side unable to reach P1/P2 lose write capability and encounter routing errors.
- Once connectivity returns, P3 catches up on missed changes.

### 7.2. P1 (Old Writer) Is Isolated

```text
           P1 (old writer)
                  X
            -------------
              P2 ---- P3
                quorum=2
```

P2/P3 hold a majority to elect a new writer. During election, applications may encounter **`TransientException`, timeouts, or retries**. P1 cannot commit new writes once it loses quorum, even if a Java client still holds an open TCP connection to P1.

Note: a single member reporting itself as leader at one instant does not prove the writer is stable. Compare status across multiple primaries alongside actual commit success.

### 7.3. Three Primaries Split 1–1–1

No group has **2 votes**. Primaries may still hold copies for limited reads, yet **no group can commit new write transactions** for that database until quorum is restored or a supported disaster recovery procedure is executed.

### 7.4. Client-Side View

| Symptom | Likely meaning | Action |
| --- | --- | --- |
| Write timeouts during election | Leader/routing still stabilizing | Bounded retries and idempotency |
| `MATCH` on secondary still works | Potentially stale data | Verify freshness requirements |
| App only knows P3’s address | Bootstrap/routing lost path to majority | Fix discovery/advertised addresses |
| Write committed yet app errored | Server ACK lost in transit | Reconcile status via business key |
| Read-after-write misses node | Replica lag / missing bookmark | Use bookmarks or causal session reads |

## 8. Five-Primary 3–2 Partition and Multi-Region Effects

With `N=5`, quorum is `3`:

```text
             Partition A                  Partition B
          P1 --- P2 --- P3                 P4 --- P5
               3/5                          2/5

           Can WRITE                    Cannot WRITE
```

The three-primary group can elect a writer and commit; the two-primary group cannot commit. Still, application availability depends on whether clients can reach the majority partition.

### 8.1. 2+2+1 Distribution Across Three Datacenters

Neo4j documentation recommends considering **5 primaries distributed 2P+2P+1P** across three datacenters when you must survive losing **any single** datacenter:

- Lose a datacenter with 2 primaries: 3 remain, keeping quorum.
- Lose the datacenter with 1 primary: 4 remain, keeping quorum.
- More WAN links carry Raft traffic, raising latency and cost compared to one datacenter.

Conversely, three primaries placed **2P+1P** across two datacenters cannot survive losing the two-primary zone. Five primaries placed **3P+1P+1P** across three datacenters also cannot survive losing the three-primary zone.

### 8.2. Do Not Optimize Primary Count on a Single Metric

Choose topology based on:

- Actual write latency p95/p99 and throughput.
- Resilience to primary/datacenter loss.
- RTT/jitter/packet loss among primaries.
- RPO, RTO, and post-failover catch-up speed.
- Bandwidth, WAN costs, and security requirements.
- Local-read strategy near users.

More primaries **does not make individual Cypher queries faster**. Under heavy write loads, larger primary counts increase replication and operational overhead.

## 9. Read-After-Write: Secondaries Can Lag, Bookmarks Can Wait

Suppose the Java service creates an order:

```cypher
MERGE (o:NetDemoOrder {orderId: 'o501'})
SET o.status = 'NEW';
```

Right after the write commits on quorum, a secondary may not have applied the update yet, so an independent `MATCH (o:NetDemoOrder {orderId:'o501'})` read misses the node.

A **bookmark** marks a database state watermark. When a read request carries the bookmark of a committed transaction, Neo4j runs the read only on a replica that has reached at least that state, or waits until it does.

```text
Write session --commit--> bookmark B
                            |
Read request + B -----------+
                            |
            Has replica applied B?
              /          \
           Yes            No
            |              |
          Read        Wait for catch-up
                           |
                     Read / timeout
```

Trade-offs:

- Guarantees read-your-writes when successful.
- Increases latency when replicas lag.
- During prolonged partitions, bookmark-bound operations may time out rather than return stale data.

| Use case | Required freshness | Recommended approach |
| --- | --- | --- |
| Viewing an order just placed | Read-your-writes | Same session or cross-session bookmarks |
| Periodically refreshed KPI dashboard | Lag acceptable | Secondaries with data timestamp displayed |
| Payment / duplicate-order prevention | Cannot miscount | Unique constraints + write transactions; never rely on negative replica reads |
| Historical reporting | Clear point-in-time mark | Read model/secondaries displaying as-of time |
| Authorization checks | Stale permissions must not leak data | Appropriate strong consistency and fail-closed checks |

**Bookmarks do not accelerate replication**; they only coordinate operations that require causal ordering.

## 10. Java Driver: Routing URIs vs. Direct URIs

For the Java Driver:

- `neo4j://` and `neo4j+s://`: Driver uses **routing**, fetching role-based endpoint tables and refreshing as needed.
- `bolt://` and `bolt+s://`: **Direct** connection to one specific member without automatic writer/reader topology routing.
- Security scheme must match deployment TLS and certificates.

If application code hardcodes `bolt://primary1:7687`, `primary1` dying breaks the application even though `primary2`/`primary3` still hold quorum. Production cluster apps should therefore use the routing URI provided by operators.

### 10.1. Bootstrap/Discovery Matters as Much as Quorum

The Driver fetches its routing table from an entrypoint, yet:

- If a single entrypoint is partitioned, the Driver may fail to refresh its table.
- Multi-record DNS (A/AAAA) or a **custom address resolver** improves bootstrap resilience.
- **Advertised** addresses returned by servers must be reachable from all authorized clients.
- Firewalls, security groups, TLS hostnames, and Bolt ports must permit access to every routed endpoint.
- A misconfigured TCP load balancer/proxy can accidentally turn the whole cluster into a client-side **single point of failure**.

Good routing cannot fix quorum loss; healthy quorum without client reachability still fails users.

## 11. Java Driver 6.x: Idempotent Writes and Consistent Session Reads

Assuming database `supply`, schema, and credentials exist; example using a constrained business key:

```cypher
CREATE CONSTRAINT net_demo_order_id IF NOT EXISTS
FOR (o:NetDemoOrder) REQUIRE o.orderId IS UNIQUE;
```

Java Driver example using a routing URI:

```java
import java.time.Duration;
import java.util.Map;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String uri = System.getenv("NEO4J_URI");  // neo4j+s://...
String username = System.getenv("NEO4J_USER");
String password = System.getenv("NEO4J_PASSWORD");

Config config = Config.builder()
    .withMaxTransactionRetryTime(Duration.ofSeconds(15))
    .build();

try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(username, password), config)) {

    driver.verifyConnectivity();

    try (Session session = driver.session(
            SessionConfig.forDatabase("supply"))) {

        session.executeWriteWithoutResult(tx ->
            tx.run("""
                MERGE (o:NetDemoOrder {orderId: $id})
                ON CREATE SET o.status = 'NEW'
                """, Map.of("id", "o501")).consume()
        );

        String status = session.executeRead(tx ->
            tx.run("""
                MATCH (o:NetDemoOrder {orderId: $id})
                RETURN o.status AS status
                """, Map.of("id", "o501"))
              .single().get("status").asString()
        );

        System.out.println(status);
    }
}
```

Here:

1. One `Driver` manages routing and pools; in Spring Boot, keep a single Driver managed over the application lifecycle.
2. `SessionConfig.forDatabase("supply")` specifies the database explicitly, as quorum/writers are per database.
3. `executeWriteWithoutResult` uses a managed transaction; transient errors can be retried.
4. `executeRead` immediately afterward in the **same session** preserves the causal chain.
5. `MERGE` on a key backed by a uniqueness constraint avoids duplicates if the callback re-runs.
6. The 15-second max retry time **is only an example**; tune it against API SLOs, gateway timeouts, and circuit breakers.

### 11.1. Bookmarks Across Two Independent Sessions

When write and read occur in two separate requests/sessions:

```java
import java.util.Collection;
import java.util.Map;
import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

Collection<Bookmark> bookmarks;

// Driver variable already initialized; database supply exists.
try (Session writer = driver.session(
        SessionConfig.forDatabase("supply"))) {

    writer.executeWriteWithoutResult(tx ->
        tx.run("""
            MERGE (:NetDemoOrder {orderId: $id})
            """, Map.of("id", "o502")).consume()
    );

    bookmarks = writer.lastBookmarks();
}

try (Session reader = driver.session(
        SessionConfig.builder()
            .withDatabase("supply")
            .withBookmarks(bookmarks)
            .build())) {

    boolean found = reader.executeRead(tx ->
        tx.run("""
            MATCH (o:NetDemoOrder {orderId: $id})
            RETURN count(o) > 0 AS found
            """, Map.of("id", "o502"))
          .single().get("found").asBoolean()
    );

    System.out.println(found);
}
```

This assumes `driver` is already initialized and both calls succeed. Bookmarks passed across requests must be safely managed and scoped to business boundaries; they are **not** credentials or authorization tokens.

The Driver also provides a default bookmark manager for `driver.executableQuery(...)` chains. For independent sessions or parallel transactions, do not assume causal chaining without coordinating bookmarks.

## 12. Network Errors After Write: Commit Did Not Necessarily Fail

Consider two cases:

1. Raft failed to reach quorum → transaction not acknowledged, client times out.
2. Raft **did commit**, yet the server-to-client response dropped → client also times out.

Therefore, **a client-side timeout never confirms a transaction rolled back**.

Proper design for orders and payments:

- Send a unique **idempotency key/`orderId`**.
- Use constraints and transaction logic to prevent duplicates.
- When write confirmation is ambiguous, query back using the business ID or authoritative state source.
- Never wire email sending, payment charging, or Kafka publishing directly inside a retryable callback.
- Use an outbox, idempotent consumers, and reconciliation for side effects outside Neo4j.
- Set retry limits, backoff, and concurrency caps to avoid a **retry storm**.

Java Driver managed transactions automatically retry eligible transient errors up to the configured limit, but **not all errors are retryable**. Syntax errors, permission errors, and constraint violations require separate handling.

## 13. Spring Data Neo4j and Reactive Applications

Spring Data Neo4j relies on the Java Driver underneath, so routing/transaction/credential choices remain essential:

- Configure `neo4j+s://` or an appropriate deployment URI; never pin to one primary.
- Reuse a shared Driver/connection pool; never create a Driver per HTTP request.
- Keep transactions short and move external API calls outside transactions where possible.
- When writes require business exactly-once effects, enforce unique keys and idempotent workflows.
- For cross-request read-after-write, pass bookmarks/correlation tokens as needed rather than assuming every secondary is caught up.
- With Spring WebFlux/Reactor, never block the event loop in retry callbacks or read pipelines.
- Measure routing errors, p95/p99, and retry counts **at the application layer**, not only on the server.

`@Transactional(readOnly = true)` is a Spring-layer transaction/read semantics hint, **not a guarantee that any secondary holds the latest data**. Verify routing behavior against your transaction manager, driver access mode, and exact framework version.

## 14. Graceful Degradation per Graph Use Case

| Feature | During write quorum loss | During secondary lag |
| --- | --- | --- |
| Product catalog browsing | Can continue if read copies are reachable | Can serve slightly stale data within SLA |
| Creating orders / `PLACED` edges | Never fake success; reject or persist to durable queue per architecture | Primary quorum decides; do not rely on secondaries |
| Viewing a just-placed order | If write unconfirmed, show an appropriate pending state | Use bookmarks or wait for freshness |
| Payment / marking `PAID` | Fail closed or durably queue; reconcile payment status | Never conclude “unpaid” from a stale replica alone |
| Revenue dashboards | Can continue if readable with timestamp shown | Display lag / as-of time |
| User permission checks | Never bypass security controls | Never rely on overly stale permission snapshots to grant access |
| Batch GDS / imports | Defer write-mode jobs or consistency-sensitive batches | Check graph projections and catch-up status |

*Graceful degradation* must be defined **per use case**, rather than flipping a global “read-only for everything” flag that ignores consistency differences.

## 15. Observing Cluster State with Cypher

With appropriate admin privileges in Neo4j Enterprise:

```cypher
SHOW SERVERS;
```

```cypher
SHOW DATABASES;
```

```cypher
SHOW DATABASE supply;
```

These commands inspect servers, topology, and database status. In multi-database clusters, inspect **the exact database reporting errors**. One database having a healthy leader does not prove another database holds quorum.

Also check `neo4j.log`/`debug.log`, application health, and network connectivity. When the database itself is unreachable, inspect host/container diagnostics and authorized status endpoints.

### 15.1. Cluster Status Endpoints

Neo4j Enterprise exposes per-database HTTP endpoints:

```text
/db/supply/cluster/writable
/db/supply/cluster/read-only
/db/supply/cluster/available
/db/supply/cluster/status
/dbms/cluster/status
```

- `writable`: aids routing to write-serving members.
- `read-only`: routes reads to non-writer members.
- `available`: general read availability status.
- `status`: the queried member’s view of status.
- `/dbms/cluster/status`: DBMS status across multiple databases.

Query **multiple primaries** when suspecting a partition: a single member’s view may not reflect the partitioned topology as a whole.

These endpoints enforce authentication/authorization. **Never disable auth or expose them publicly** just to simplify monitoring; restrict management networks and access privileges appropriately.

## 16. Metrics That Prove Network or Cluster Congestion

| Category | Metric or signal | Meaning |
| --- | --- | --- |
| Raft leader | `cluster.raft.is_leader` | Member currently believes it is database leader |
| Raft log | `append_index`, `commit_index`, `applied_index` | Log append, commit, and apply watermarks |
| Raft replication | `replication_attempt`, `replication_success`, `replication_fail` | Replication attempt/success/failure counts |
| Heartbeat | `last_leader_message` | Time elapsed since the leader’s last message |
| Processing | `message_processing_delay` and timers | Delay between receiving and processing messages |
| Transaction lag | `transaction.last_committed_tx_id` per member | Identifies which replicas lag behind |
| Bolt / Driver | Errors/timeouts, routing refreshes, retries, connection waits | Real impact observed by applications |
| Network / OS | RTT, packet loss, TCP retransmits, CPU, GC, I/O | Separates network loss from overloaded servers |

Normal relationship among Raft indices:

```text
append_index >= commit_index >= applied_index
```

If `commit_index - applied_index` grows persistently, a member is applying transactions slowly; if `last_leader_message` climbs continuously, inspect heartbeats/connectivity or the leader; if `replication_fail` rises alongside write p99, investigate network/peers first.

**Never diagnose split-brain from a single snapshot of leader metrics.** During elections, members can briefly report differing views of leadership; correlate time series, multi-member status, and **actual commit success**.

Alert thresholds must follow baselines. For example, a 1,000-transaction lag means vastly different things at 10 tx/s versus 100,000 tx/s. Set thresholds based on **corresponding lag time and business SLOs** wherever possible.

## 17. Symptom Diagnosis Matrix

| Symptom | Possible cause | Evidence to gather | Avoid doing immediately |
| --- | --- | --- | --- |
| Cannot write, reads still work | Lost primary majority | Quorum, status, leader | Adding secondaries to “add votes” |
| Write p95 rises when a follower drops | Must await ACK from distant primary | Inter-primary RTT, Raft delay | Blindly increasing heap |
| App in zone A fails, zone B works | Client routing / firewall / DNS | DNS, advertised endpoints, TLS/Bolt | Restoring database |
| Secondary reads return stale data | Async catch-up lag | Applied/commit indices, bookmarks | Deleting/rebuilding graph |
| Write times out yet node appeared | Committed, ACK lost in flight | Business key / transaction state | Unconditionally retrying `CREATE` |
| Frequent leader changes | Packet loss/jitter, GC, I/O, CPU | Election logs, heartbeats, host metrics | Arbitrarily lowering election timeouts |
| Server healthy, app cannot connect | Bad endpoints/routing | Client-side Bolt/TLS/DNS | Forcing manual failover |
| Secondary down, writes fine | Reduced read capacity | Read pool, CPU, p95 | Stopping whole cluster |
| Slow queries, normal network | Fan-out, sort, missing index, or GC | `EXPLAIN`/`PROFILE`, Rows, DB Hits | Increasing primary count |
| 1–1–1 split | No side holds quorum | Raft connectivity | Forcing writes on each island |

## 18. Safely Rehearsing Network Delays and Partitions in a Lab

**Never run fault injection in production without formal approval and runbooks.** This exercise assumes a dedicated 3-primary lab cluster, synthetic data, reset privileges, out-of-band management access, and backups.

### 18.1. Pre-Checks

1. Provision database `supply` on 3 primaries; optionally add a secondary.
2. Verify Bolt ports, cluster communication ports, and advertised addresses match your **exact Neo4j version**.
3. Create the `NetDemoOrder(orderId)` constraint and run a read/write workload with unique IDs.
4. Collect 5–15 minutes of baseline: write p95/p99, read freshness, elections, replication metrics, and driver retries.
5. Ensure an **automatic fail-safe removes all network impairments** even if the shell/test session disconnects.
6. Document the rollback plan and operator on duty.

### 18.2. Test A: Increasing Inter-Primary Latency

Inject additional RTT between primaries in the test network (e.g., 40 ms), holding other variables steady.

Observe: how much write p95/p99 shifts, whether leader changes happen, replication success/fail, read locality, and CPU/I/O. **Never assume every write slows by exactly 40 ms.**

### 18.3. Test B: Isolating Follower P3

Cut cluster traffic between P3 and P1/P2 using lab mechanisms **without blocking management access**. Expect P1/P2 to retain quorum and continue writes while P3 cannot commit independently. After healing, measure P3’s **catch-up time**.

### 18.4. Test C: Isolating Writer P1

Keep P2↔P3 connected while isolating P1. Observe new leader election, write outage window, driver routing refresh, and writes with indeterminate outcomes.

### 18.5. Test D: Total Quorum Loss

Partition all 3 primaries so no group holds 2 votes. Confirm no new writes commit without quorum. APIs permitted stale reads may continue from reachable replicas; write APIs must return proper failure states rather than faking success.

**Never apply raw `iptables` or `tc netem` directly to production NICs.** Design lab fault injection carefully so you never lock out management paths or disrupt neighboring services.

## 19. Post-Drill Measurement Table Template

| Metric | Baseline | Delay test | 2–1 Partition | Post-recovery |
| --- | --- | --- | --- | --- |
| Reachable primaries | 3/3 | 3/3 | 2/3 on majority side | 3/3 |
| Write quorum | Yes | Yes | Yes in group of 2 | Yes |
| Write p95/p99 | Measured | Measured | Measured including leader switch | Measured |
| Write error rate | Measured | Measured | Measured | Measured |
| Local read p95 | Measured | Measured | Measured on reachable replicas | Measured |
| Replication/applied lag | Measured | Measured | On isolated member | Measure catch-up |
| Driver retries/errors | Measured | Measured | Measured | Measured |
| Ambiguous commits | Count business IDs | Count | Count | Reconcile |
| Duplicate orders | 0 | 0 | 0 | 0 |
| Outage duration | 0 or baseline | Measured | Measured | Close incident |

This is a **reporting template**, not measured numbers. Keep workload, dataset, read/write ratio, query mix, and client setup equivalent, and mark timestamps of elections or network restoration.

A cluster’s majority side may commit writes while minority-side clients fail: **that does not contradict Raft guarantees**. Reports must specify each client’s zone and network path.

## 20. Topology Choices and Multi-Region Strategies

| Model | Strengths | Weaknesses |
| --- | --- | --- |
| 1 primary | Minimal replication overhead and write latency | No primary fault tolerance |
| 3 primaries in one datacenter | HA for one primary, low LAN RTT | Losing the datacenter halts writes |
| 3 primaries split 2+1 datacenters | Fast writes in the majority zone | Losing the 2-primary zone loses quorum |
| 5 primaries split 2+2+1 | Survives losing any one of three datacenters | WAN/replication and operational complexity |
| 3 primaries + local secondaries | Local reads near clients, offloads primaries | Secondaries add no quorum and can serve stale data |
| Multiple independent clusters with database replication | Separates failure domains across regions | DR/promotion and consistency differ from one Raft group |

Neo4j documentation from **2026.08** describes deploying **multiple independent clusters with database replication**. This is **not** five primaries in one cross-region Raft group. The target cluster’s replica database remains read-only until promoted per procedure; `system` and role/user metadata do not replicate identically like user databases. Never infer that two independent clusters can safely accept concurrent writes during a partition.

If the business requires “every region must keep accepting independent orders even during a total WAN outage,” a Raft cluster prioritizes commit safety and **refuses writes without quorum**. Meeting that requirement demands business-architecture changes (such as durable regional intake queues followed by idempotent sync/conflict resolution), never weakening quorum manually.

## 21. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| “Three powered-on servers means writes work.” | Requires per-database primary quorum and routing to writer |
| “Secondaries can vote when a primary is missing.” | No; secondaries serve read scaling only |
| “An old leader keeps writing when isolated.” | Without quorum, no new commits occur |
| “A successful read means the latest data.” | Secondaries can lag; bookmarks may be needed |
| “Bookmarks make replicas sync faster.” | Bookmarks wait for causal state; they do not speed up replication |
| “Clustering is a backup.” | Accidental deletes replicate too; independent backups are mandatory |
| “Adding primaries makes queries faster.” | Improves fault tolerance, not Cypher/DB Hits efficiency |
| “Host ping succeeds so everything is fine.” | Raft/Bolt/routing/TLS use distinct paths and protocols |
| “Write timeout means it definitely didn’t commit.” | ACK can be lost after commit |
| “Raising retries fixes a partition.” | Retries cannot create quorum and risk retry storms |
| “`bolt://` to one primary is HA.” | Direct connections do not route across writer/readers |
| “Read status endpoint returning 200 means writes are healthy.” | Writable and read availability are different |
| “Raft leadership belongs to the whole server.” | Each database has its own Raft group and leader |
| “Reconnecting the network catches replicas up instantly.” | Must measure transaction catch-up |
| “Some servers failed but quorum holds, so all clients are fine.” | Client routing may be partitioned from the majority side |
| “On quorum loss, promote a secondary to writer.” | Unsafe; follow supported DR workflows |

## 22. Deployment Checklist and Exercises

### 22.1. Checklist

1. Define primary/secondary topology and writer layout for **each database**, including `system`.
2. Define write/read SLOs, freshness, RPO, RTO, and acceptable error rates.
3. Calculate quorum and primary/datacenter loss risks under actual placement.
4. Measure RTT/jitter, packet loss, and bandwidth among primaries; monitor commit p95/p99.
5. Verify routing URIs, DNS/multiple entrypoints, advertised addresses, and TLS.
6. Classify APIs tolerating stale reads vs. APIs requiring bookmarks/read-your-writes.
7. Design business keys, constraints, and idempotent retries for ambiguous writes.
8. Configure timeouts/backoff/retry budgets, circuit breakers, and concurrency caps.
9. Monitor Raft indices, leader, heartbeats, routing errors, and client p99.
10. Rehearse follower loss, writer loss, network partitions, client bootstrap failures, and secondary lag.
11. Maintain backups and DR plans; never edit Raft stores or force quorum arbitrarily.
12. Record observed RTO, duplicate-prevention verification, and post-drill lessons learned.

### 22.2. Self-Practice Exercises

1. A database has 5 primaries. Calculate quorum and analyze a `3+2` partition. Which side can commit?
2. Three primaries sit `2P+1P` across two zones. If the 2-primary zone fails, write out how read and write APIs should behave.
3. Explain why adding 80 ms RTT between two datacenters can raise write p95 while not raising every local secondary read by the same amount.
4. A secondary lags by 10 seconds. Design a “create order then view order” flow guaranteeing read-your-writes with the Java Driver.
5. A client times out right after `MERGE`: state the two commit possibilities and how to verify safely.
6. Why does `bolt://p1:7687` fail when P1 dies even though P2/P3 hold quorum? How do you fix discovery?
7. `SHOW SERVERS` reports healthy servers yet the `writable` endpoint reports unavailable; outline an investigation runbook.
8. Pick six metrics for a fault-injection drill and describe their trajectories during follower loss, writer loss, and recovery.
9. Why does `@Transactional(readOnly=true)` not guarantee a replica always holds the newest data?
10. To survive losing any single datacenter across three zones with five primaries, which layout should you choose? What is the latency trade-off?
11. A `1+1+1` split leaves three replicas able to serve limited reads. Why must you never force all three sides to commit?
12. Draft a drill go/no-go table covering write availability, p95/p99, replication lag, idempotency, and rollback.

## 23. Key Takeaways

- **Per-database primary quorum** determines write availability: `floor(N/2)+1`.
- Primaries confirm writes via Raft; **secondaries replicate asynchronously** to scale reads and hold no voting power.
- Network delay impacts commits, client responses, routing, and secondary catch-up; measure **p95/p99 and actual lag time**.
- Partitions let the majority group keep committing while the minority cannot; reads may become stale.
- Three primaries tolerate one failure and five tolerate two, yet datacenter survival depends on **topology placement**.
- `neo4j://`/`neo4j+s://` supports routing, whereas `bolt://`/`bolt+s://` connects directly to a single member.
- Bookmarks enforce read-your-writes when needed, but may wait for catch-up and add latency.
- **A client-side write timeout does not prove the transaction rolled back**; use idempotency keys/unique constraints and reconcile.
- Monitor status endpoints, `SHOW DATABASES`/`SHOW SERVERS`, Raft metrics, and application routing from multiple members.
- Rehearse delays/partitions in a lab with automated rollback; never tweak production firewalls or election timeouts arbitrarily.

### Official References

- [Neo4j Operations Manual — Clustering architecture](https://neo4j.com/docs/operations-manual/current/clustering/introduction/)
- [Neo4j Operations Manual — Leadership, routing and load balancing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/)
- [Neo4j Operations Manual — Designing resilient multi-region clusters](https://neo4j.com/docs/operations-manual/current/clustering/multi-region-deployment/geo-redundant-deployment/)
- [Neo4j Operations Manual — Multi-data center routing](https://neo4j.com/docs/operations-manual/current/clustering/multi-region-deployment/multi-data-center-routing/)
- [Neo4j Operations Manual — Cluster status endpoints](https://neo4j.com/docs/operations-manual/current/clustering/monitoring/endpoints/)
- [Neo4j Operations Manual — Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
- [Neo4j Operations Manual — Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Operations Manual — Clustering glossary](https://neo4j.com/docs/operations-manual/current/clustering/glossary/)
- [Neo4j Java Driver Manual — Connection and routing](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver Manual — Coordinate transactions with bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Java Driver Manual — Managed transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
