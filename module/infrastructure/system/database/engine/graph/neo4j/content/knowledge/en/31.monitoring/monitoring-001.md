# Monitoring Neo4j Server Health, Connectivity, and Availability

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between **process health**, **Bolt connectivity**, **database state**, and **business query capability**.
- Design **startup**, **liveness**, **readiness**, and **synthetic transaction** checks to avoid reporting "healthy" when Neo4j cannot serve the application.
- Observe CPU, heap, GC, page cache, disk, transaction logs, transaction counts, Bolt connections, and errors in both Neo4j and the Java Driver.
- Check online databases, cluster member roles, and read/write routing without confusing an **open port** with **successful write capability**.
- Establish **SLIs/SLOs, dashboards, alerts, and runbooks** based on latency, error rate, resources, and actual symptoms.
- Operate monitoring differently for **self-managed Neo4j**, Docker/Kubernetes, and **Aura**, paying attention to version, edition, privileges, and metrics access limitations.
- Build procedures for handling incidents such as offline databases, disk exhaustion, connection pool saturation, TLS connection loss, or cluster write unavailability.

The **Monitoring** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module focuses on determining whether the graph system is **truly ready** to serve queries. Neo4j stores nodes, relationships, properties, and indexes, supporting Cypher for querying connections and paths; the Java Driver and Spring Data Neo4j connect over Bolt. Therefore, monitoring must not only check whether a Java process is still running, but also verify that the specifically named database is online, can authenticate, read/write according to permissions, and meet latency requirements under load.

> **Compatibility note:** The examples below use modern Java Driver APIs and common administrative commands in Neo4j 5.x / newer Neo4j releases. Setting names, metrics, DBMS privileges, administrative commands, and managed service dashboards may vary by **version, edition, and deployment model**. Check the documentation for your exact running environment before enabling exporters or automating restarts.

## 1. Four Health Layers Not to Conflate

A service may pass a ping test yet still fail to handle requests. Break it down into four layers:

| Layer | Question | Typical Check | Limitation |
| --- | --- | --- | --- |
| **Host/process** | Is the Neo4j process running? Are CPU/RAM/disk sufficient? | Process status, host/container metrics, OS health | A running process does not mean the database is online |
| **Transport/Bolt** | Can the client open a connection to the Bolt port? Does the TLS handshake succeed? | TCP probe, TLS verification, Driver `verifyConnectivity()` | An open port does not prove privileges or business query success |
| **Database** | Is the target database `online`? Are there members serving the required access mode? | `SHOW DATABASES`, cluster state, routing/read-write checks | An online database may still be slow or lack privileges |
| **Application operation** | Do `MATCH`, `MERGE`, or path queries complete within SLO? | Controlled synthetic read/write, API metrics, query log | A small synthetic query does not represent every workload |

Examples:

- Port 7687 is open, but the **TLS certificate has expired** → the driver cannot connect securely.
- TLS and authentication are valid, but the `orders` database is offline → `MATCH` cannot run against `orders`.
- The database is online and `RETURN 1` is fast, yet querying customers across many relationships has p99 = 8 seconds → users still experience performance failures.
- Reads succeed on the cluster, but no **writer** server is available → APIs that perform writes fail.

**Preliminary conclusion:** Health indicators must be tied to a **specific usage goal**: reads, writes, administrative operations, or analytical algorithms.

~~~mermaid
flowchart TD
    A["HTTP / Java Driver request"] --> B{"Network + TLS + Auth OK?"}
    B -->|No| X["Connection error"]
    B -->|Yes| C{"Target database ONLINE?"}
    C -->|No| Y["Database unavailable"]
    C -->|Yes| D{"Suitable read/write route?"}
    D -->|No| Z["Operation unavailable"]
    D -->|Yes| E{"Cypher completes within SLO?"}
    E -->|No| W["Degraded / slow"]
    E -->|Yes| F["Application ready"]
~~~

## 2. From Infrastructure Signals to User Experience

A Neo4j system serving an e-commerce website handles different types of operations:

| Request Type | Cypher Example | What Users Expect |
| --- | --- | --- |
| **Lookup** | `MATCH (c:Customer {customerId:$id}) RETURN c` | Customer information returned accurately and quickly |
| **Traversal** | `(c)-[:PLACED]->(o)` | Complete list of orders/relationships within the requested scope |
| **Path query** | Find paths between `Person` nodes | No timeouts on graphs with high fan-out |
| **Write transaction** | `MERGE` Order + `PLACED` in `executeWrite` | Atomic order creation, never reporting success when commit fails |
| **Import/batch** | `UNWIND` many records across multiple transactions | Does not starve online APIs |

A good dashboard must include **four core signals**:

1. **Traffic:** how many read/write requests and completed transactions per second?
2. **Errors:** how many requests failed, timed out, violated constraints, or failed to connect?
3. **Latency:** p50/p95/p99 from the **application's perspective**, along with database processing time if observable.
4. **Saturation:** CPU, heap/GC, page cache misses, disk I/O, queued pool connections, and lock contention.

A single graph showing high CPU is **not enough** to prove you need to scale up. You must correlate CPU with traffic, latency, queues, and errors on the **same timeline** to know whether the system is doing useful work or is bottlenecked.

## 3. Startup, Liveness, Readiness, and Synthetic Probes

### 3.1. Startup Probe

**Startup** answers: "Has Neo4j started up to the point where normal checks can begin?". After a restart, the database may need to recover transaction logs, validate the store, or begin building indexes.

If startup legitimately takes a long time while the liveness probe is too strict, the orchestrator may **kill/restart in an infinite loop** before the DB finishes recovery. Use an appropriate startup budget/initial delay and inspect startup logs instead of setting a few-second timeout for every environment.

### 3.2. Liveness Probe

**Liveness** answers: "Is the process severely stuck and in need of a restart?". Liveness should be a **lightweight, stable** check, avoiding dependencies on external systems that could experience transient failures.

A port/TCP check may be suitable for evaluating the **transport layer** of the process, but it is **not sufficient for database readiness**. Never automatically restart Neo4j just because a single synthetic read query was slow or a cluster node did not hold write capability at that moment.

### 3.3. Readiness Probe

**Readiness** answers: "Can this instance/endpoint currently receive the workload traffic assigned to it?". For read APIs:

- The client connects and authenticates successfully.
- The required database is online.
- A lightweight query executes under the application role.
- Latency does not exceed the short-term threshold of the health probe.

For **write services**, readiness also requires a route to a member capable of handling write transactions. A follower/secondary may still have **good readiness for READ** while unable to accept all direct WRITES.

### 3.4. Synthetic Transaction

A synthetic probe runs a user-like action, such as `RETURN 1` and a representative parameterized lookup query. It provides additional proof that "the service is doing useful work" beyond process signals.

~~~cypher
// Minimal read check; verifies privileges and the Cypher execution path.
RETURN 1 AS ok;
~~~

~~~cypher
// Lightweight business read on a fixture permitted to exist.
MATCH (c:HealthCheck {checkId: $checkId})
RETURN c.checkId AS checkId;
~~~

**Note:** The second snippet is only meaningful if the system already has a valid `HealthCheck` fixture and you control its lifecycle. A missing fixture does not necessarily mean a database failure; monitoring data issues must be distinguished from platform failures.

**Do not use** `CREATE` or `DELETE` in a liveness probe running every few seconds: it increases transaction logs, locks, and can cause data bloat. If you need to prove **end-to-end write availability**, use a separate synthetic workflow on an infrequent schedule, with its own namespace, stable ID, and cleanup/reconciliation mechanism.

## 4. Checking Database State with Administrative Cypher

In environments and with accounts that have appropriate privileges, Neo4j supports inspecting databases via `SHOW` commands.

~~~cypher
SHOW DATABASES
YIELD name, requestedStatus, currentStatus, statusMessage
RETURN name, requestedStatus, currentStatus, statusMessage
ORDER BY name;
~~~

In versions that expose these columns, `requestedStatus` reflects the **desired** state, while `currentStatus` reflects the current state on the inspected member/context. Always inspect **statusMessage** rather than just checking the DB name. In a cluster, results can vary by server and privilege; do not assume a single `SHOW DATABASES` call to one endpoint has surveyed every member.

How to interpret the results:

| Condition | Interpretation | Next Check |
| --- | --- | --- |
| Both requested and current are `online` | Database appears ready in the queried scope | Still run a synthetic query under application privileges |
| Requested `online` but current is not `online` | Database has not reached its desired state | Check statusMessage, logs, disk, recovery/cluster |
| Requested `offline` | May have been intentionally taken offline by an administrator | Check operational changes; do not restart arbitrarily |
| DB does not appear | Wrong name, missing privileges, not yet created, or environment hides details | Check database name/role and management system |

If you only need to list databases:

~~~cypher
SHOW DATABASES;
~~~

**Note:** Do not run `START DATABASE`, `STOP DATABASE`, or `DROP DATABASE` just to "test monitoring". They perform real state mutations, require administrative privileges, and can cause an outage.

### 4.1. Checking Version/Edition

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Run this when privileges and deployment allow. It helps identify which metrics, roles, cluster procedures, or detailed observability features the environment supports. When automating, do not treat column names or procedures as immutable across all versions.

### 4.2. Cluster: Inspecting Servers and Roles

In systems supporting multi-server deployments and administrative privileges, the command:

~~~cypher
SHOW SERVERS;
~~~

can provide information about known servers in the topology. Availability and output of this command depend on **version/edition and cluster configuration**; a standalone instance or Aura may not expose it in the same way.

Do not equate:

- **Server process healthy:** the Neo4j server is still running.
- **Database available:** the target database has an active serving copy.
- **Read route available:** the application can perform reads.
- **Write route available:** the application can commit write transactions.
- **Causal read satisfied:** a dependent read session observes a prior write transaction via bookmark.

In a consensus-based Neo4j cluster, **losing quorum or lacking a suitable primary** can prevent writes from succeeding even while many members still respond to pings. Monitor topology/roles, out-of-sync members, and routing errors together.

## 5. Checking Connectivity from the Java Driver: Don't Stop at an Open Port

In a Java application, `Driver` is a shared object holding a connection pool. `Session` should be used per request/unit of work and never shared across multiple threads.

### 5.1. Initializing the Driver and Verifying Connectivity

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

public final class Neo4jConnectivity {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();
            System.out.println("Neo4j driver connectivity OK");
        }
    }
}
~~~

This example requires setting three environment variables before running; never hard-code URIs/secrets in source code. `verifyConnectivity()` is useful for detecting **network/TLS/auth/routing** issues early, but it **does not prove a business write transaction will succeed**, nor does it prove all databases are online.

### 5.2. Running a Synthetic Read on the Target Database

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jReadHealth {
    public record HealthResult(boolean ready, long latencyMillis) {}

    public static HealthResult check(
            Driver driver, String databaseName) {
        long started = System.nanoTime();

        try (Session session = driver.session(
                SessionConfig.forDatabase(databaseName))) {
            int result = session.executeRead(tx ->
                    tx.run("RETURN 1 AS ok")
                      .single()
                      .get("ok")
                      .asInt());

            long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);
            return new HealthResult(result == 1, elapsedMillis);
        }
    }
}
~~~

This snippet covers the **success check**, not a complete readiness endpoint. Callers must **catch exceptions and classify errors** (e.g., timeout, authentication, service unavailable) to report an appropriate health status, while avoiding exposing secret details to HTTP clients.

**Important:** `executeRead` may retry the callback on eligible transient errors. Externally measured latency reflects the time users wait including those retries; a fast `RETURN 1` after a retry does not mean the system is free of intermittent instability.

### 5.3. Routing URIs and TLS

| URI Scheme | Usage Meaning | Notes |
| --- | --- | --- |
| `neo4j://host:7687` | Routing via routing driver | Suitable when the client needs to discover read/write routes |
| `neo4j+s://host:7687` | Routing with TLS and trusted CA certificate verification | Typically suitable for production connections with a trusted CA |
| `neo4j+ssc://host:7687` | Routing TLS accepting self-signed certificates per driver semantics | Use only after reviewing security policy; not a substitute for full verification |
| `bolt://host:7687` | Direct connection to a single Bolt endpoint | Does not automatically provide the routing benefits of `neo4j://` |

Scheme selection depends on the environment and driver version; never switch to an unverified TLS connection just to "resolve" certificate errors. Check hostname, SAN, CA chain, certificate expiration, port, and proxy/LB.

In a cluster, a `bolt://` URI pointing directly to a read-only member will cause writes to fail; with a routing URI, the driver can pick an appropriate target based on the routing table. Observe **READ/WRITE operation types**, not just connection counts.

## 6. Java API Readiness vs. Neo4j Readiness

With Spring Boot, an application can expose `/actuator/health` via Spring Boot Actuator when configured. Some versions/frameworks provide a Neo4j health indicator; auto-configuration behavior and result details depend on dependencies, versions, settings, and account privileges.

You should separate at least:

- **App liveness:** the HTTP server and process are alive, without waiting on the database in every probe.
- **App readiness:** dependencies **required to handle requests** are ready, including Neo4j if the API relies on it.
- **Neo4j synthetic operations:** read checks and, if needed, write checks on a separate channel/cadence.

Architecture example:

~~~mermaid
flowchart TB
    K["Kubernetes / Load Balancer"] --> L["App /health/liveness"]
    K --> R["App /health/readiness"]
    R --> C["Neo4j Driver + lightweight query"]
    M["Monitoring job"] --> W["Controlled Read/Write synthetic"]
    W --> N[("Neo4j cluster")]
    C --> N
~~~

Do not share an expensive readiness endpoint that probes Neo4j continuously across hundreds of pods. If 200 pods call Neo4j every second, health checking itself can generate heavy load. You can cache health results briefly, size the connection pool appropriately, and run a separate scheduled synthetic job.

**Never expose** internal server names, stack traces, credentials, routing tables, or sensitive query results in public health responses. Restrict access or detailed output exclusively to internal monitoring systems.

## 7. Resource Metrics to Observe

### 7.1. CPU, Heap, GC, and Native Memory

| Metric | When Abnormal | Possible Causes |
| --- | --- | --- |
| Neo4j process / host CPU | Sustained high usage without throughput growth | Cypher expanding too many relationships, high load, query/GC contention |
| Heap used/committed/max | Near limit with frequent GC | Large queries, large result sets/transactions, GDS or plugins consuming heap |
| GC pause/time | Long pauses, p99 spikes | Object allocation pressure, poorly sized heap, large allocations |
| Native/direct memory | Growth outside the heap | Memory mapping, network/driver buffers, off-heap structures depending on runtime |
| OS memory pressure / swap | Swapping or OOM | Combined RAM for heap + page cache + OS is too high |

A Java process whose heap is not yet full can still be OOM-killed if **page cache, native memory, and other containers** exhaust total RAM. Never watch only `jvm.heap.used` and assume the system has enough memory.

### 7.2. Page Cache

Neo4j uses the **page cache** to back storage reads and writes. Key concepts to watch:

- **Page cache hits/misses:** whether data pages are found in cache.
- **Page faults / I/O:** how many pages must be loaded from storage, and under which workloads.
- **Configured page cache size** relative to RAM and actual working set.

A high hit ratio can be good, but it **does not mean queries are optimal**. Unnecessary traversal across millions of relationships can generate massive cache touches, causing high CPU and DB Hits even when all data is already in RAM.

### 7.3. Disk, Store, and Transaction Logs

Monitor:

- **Free space and growth rate** of filesystems holding databases, transaction logs, and backups/staging.
- **Read/write I/O latency**, queue depth, throughput, and IOPS as workload grows.
- **Checkpoints**, write transaction volume, and import/batch bursts.
- **Log volume** and corresponding retention/pruning policies.

A database may reject writes or become unstable when the disk approaches capacity. Alerts should combine **percentage used** and **absolute free space**: 5% remaining on a 10 TB disk is very different from 5% remaining on a 20 GB disk. Calculate **estimated time to threshold** from the growth rate while watching backups/imports at the same time.

### 7.4. Bolt Connections, Transactions, and Locks

Useful metric groups:

- Open/busy Bolt connections, new connections, and connection errors.
- Active transactions, commits/rollbacks, execution duration, and transient errors.
- **Application-side Java Driver** connection pool: in-use connections, waiting requests, excessive wait times, and timeouts (when instrumentation supports it).
- Query latency, query count, READ/WRITE breakdown, and wait time/lock contention when available.

**Server Bolt connection count is not the same as the client pool queue.** If the application-side pool is exhausted, many requests may queue before a query even starts; the database may show low CPU during this time. Conversely, sizing the pool too large can increase contention and saturate the server.

## 8. Collecting Metrics: Self-Managed, Prometheus, and Aura

In **self-managed Neo4j**, Enterprise Edition and supported versions provide built-in metrics export mechanisms. A common configuration in Neo4j 5.x uses:

~~~properties
# neo4j.conf - illustrative on editions/versions supporting these settings
server.metrics.enabled=true
server.metrics.prometheus.enabled=true
server.metrics.prometheus.endpoint=127.0.0.1:2004
~~~

This is an **illustrative example**, not a configuration guarantee across every version/edition. Check the setting names in [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/) for your exact version. Before enabling an exporter, verify ports, bind addresses, permissions, and **edition-level metrics support**.

**Exporter security:** Never expose the Prometheus endpoint to the public Internet. Prefer internal bind addresses, network policies/firewalls, or an authenticated/TLS proxy depending on your network architecture. Metrics can leak topology and operational metadata.

Example collection architecture:

~~~mermaid
flowchart LR
    N1[("Neo4j node A")] -->|metrics endpoint| P["Prometheus scraper"]
    N2[("Neo4j node B")] -->|metrics endpoint| P
    APP["Java / Spring API"] -->|Micrometer metrics| P
    OS["Node exporter / cAdvisor"] --> P
    P --> D["Dashboard / alert rules"]
    D --> ON["On-call / Incident response"]
~~~

### 8.1. Why Combine Metrics from Multiple Sources?

Neo4j database metrics can show page cache misses, but they do not directly tell you the application's HTTP p99. OS metrics show that disk is nearly full, but cannot identify which `MATCH` query caused the load. App metrics show timeout counts, but do not explain whether the server is hitting heap limits or the connection pool is queued.

Combine three scopes:

1. **Application:** request type, latency, errors/timeouts, client-side pool.
2. **Neo4j process/database:** Bolt, transactions, CPU/heap/page cache, query logs, state/routing.
3. **Host/container/network:** RAM, disk, I/O, OOM events, TLS, DNS, packet loss/latency.

If the system has multiple databases/clusters, attach appropriate metric labels such as **environment, instance, database, operation**; avoid using `customerId`/`orderId` as labels due to high cardinality and data exposure risks.

### 8.2. Aura: Managed Environment

With **Neo4j Aura**, infrastructure and parts of internal monitoring are managed by the provider. Tenants typically use the **dashboards/metrics/logs exposed by Aura or supported tier integrations**, rather than editing `neo4j.conf` directly or opening host exporter ports.

What the application must still measure itself:

- API read/write latency, error rate, and retries.
- Driver connection/routing/TLS failures.
- Freshness of read models or synchronization jobs with other systems.
- Synthetic queries under application roles and access status after network/permission changes.

Do not assume every Aura tier has the same access to detailed metrics, cluster views, or custom exporters. Check the actual dashboards and APIs provided by your deployment tier.

## 9. Tracking Queries, Logs, and Performance Incidents

Slow queries do not necessarily crash the process or take the database offline. When a traversal API misses its deadline:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId
LIMIT 20;
~~~

`EXPLAIN` generates the execution plan **without running the main query**, making it suitable for inspecting `NodeIndexSeek`/`NodeByLabelScan`/`Expand` and estimated row counts.

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId
LIMIT 20;
~~~

`PROFILE` **actually executes the query**, adding `Rows`/`DB Hits` and runtime details depending on version. Do not run `PROFILE` on a write query in production just to "inspect the plan"; the write operations will still be executed.

### Typical Symptoms

| Symptom | Hypothesis | Next Check |
| --- | --- | --- |
| p99 spikes while Neo4j CPU is low | Clients waiting on pool, network, locks, or routing | Driver pool pending, lock wait, TLS/network |
| CPU rises without throughput growth | Queries scanning/expanding many rows or saturation | `PROFILE`, `Rows`/`DB Hits`, traffic mix |
| GC pauses grow and heap nears max | Graph projection/batch queries too large | Heap, allocation, plugins/GDS, query memory |
| Page cache misses and disk latency rise together | Working set does not fit in cache | Page cache sizing, I/O, query patterns |
| Writes time out while reads remain healthy | Writer unavailable, lock contention, disk/log bottleneck | Routing, cluster, write transaction errors |
| Only requests for a few customers are very slow | Supernodes (high-degree nodes), skewed data | Fan-out, query plan with actual parameters |
| Many `ServiceUnavailable` errors after rollout | Wrong URI, cert, DNS, or routing | TLS handshake, driver config, logs |

**Do not enable unbounded verbose query logging**: it can increase I/O and store parameters containing sensitive data. Use thresholds, sampling, redaction, and retention according to your version/edition configuration.

## 10. SLIs, SLOs, and Service-Driven Alerting

### 10.1. Defining Well-Scoped SLIs

A **Service Level Indicator (SLI)** measures the quality of experience for an operation. For example:

\[
\text{Availability SLI} =
\frac{\text{Valid requests meeting success criteria}}
{\text{Total valid recorded requests}}
\]

A request may need to meet **both a correct result and a latency deadline** to count as successful. Never exclude all timeouts from the denominator and publish an artificially inflated availability figure.

Define separately:

- **Read availability SLI:** critical lookups/traversals return accurate results within the deadline.
- **Write availability SLI:** critical write transactions commit properly and are confirmed by the application within the deadline.
- **Latency SLI:** end-to-end p95/p99 per operation.
- **Data freshness SLI:** time from source commit to graph projection when using CDC/outbox.

A server with nearly 100% uptime but low write availability **fails user expectations**.

### 10.2. Illustrative SLOs

| Operation | Example SLO | How to Measure |
| --- | --- | --- |
| Lookup Customer | 99.9% of valid requests complete successfully within 200 ms | HTTP/APM + query result |
| Create Order | 99.95% of valid requests commit properly within 500 ms | API metrics + transaction result |
| Read graph traversal | p95 under 400 ms at target load | Load test + production metrics |
| Graph projection freshness | 99% of events appear within 10 seconds | Source commit timestamp + apply timestamp |

These thresholds are **hypothetical for learning**, not guarantees provided by Neo4j. Choose them based on product requirements, system capacity, and error budget calculations.

### 10.3. Good Alerting Rules

- **Impact-based alerts:** read/write error rates or p95/p99 breaching SLO over a window with sufficient samples.
- **Saturation alerts:** disk approaching full, continuous GC, sustained pool pending, page cache/memory pressure.
- **Topology alerts:** no write route available or a database desired to be online is not online.
- **Silent failure alerts:** metrics stop arriving at the monitoring system, synthetic jobs stop running, or no valid samples remain.
- **Recovery alerts:** after a member returns, backlog/read model lag continues growing or reconciliation detects missing data.

Avoid alerting on a **single sample** of CPU > 80% because it is noisy. Use time windows, sustained thresholds, impact scope, request ratios, and correlated symptom groups. Alert severity can be tiered:

| Level | Example | Action |
| --- | --- | --- |
| **Critical** | Widespread write failures, database offline, full disk halting writes | Page on-call immediately, prioritize recovery |
| **Warning** | Rising page cache misses, disk approaching threshold, degrading p95 | Investigate / capacity planning |
| **Info** | Planned restart or version upgrade | Annotate dashboard to explain metric shifts |

## 11. Periodic Health Checks Without Creating Dangerous Load

Probe frequency is an architectural decision:

- **Liveness:** lightweight, non-writing, cadence matched to the orchestrator.
- **Readiness:** tiny query against required databases, short timeout, and caching when instance count is large.
- **Business synthetics:** longer intervals; controlled fixtures/data, recording latency and errors.
- **Deep diagnostics:** `PROFILE`, detailed query logs, heap dumps, cluster inspection only when needed and authorized—**never run every few seconds**.

Example check schedule:

~~~text
Every 10s: app liveness (process)
Every 15s: app readiness (Driver read probe, cached briefly)
Every 60s: central synthetic lookup (read + latency)
Every 5m: dedicated synthetic write/delete workflow (if permitted)
Every 1m: scrape host/process metrics
Every 1h: reconcile selected business graph counts/freshness
~~~

These intervals are an **illustrative suggested schedule**, not mandatory. Base them on pod count, SLOs, DB scale, startup time, and check cost. If a company runs 500 API replicas, probing Neo4j every 5 seconds from each replica generates 100 queries/s **from health checks alone**.

A synthetic write must:

1. Use an approved **dedicated canary database/namespace/label** and a least-privilege service account.
2. Write with a **stable ID** and monitored TTL/cleanup; never modify user data.
3. Verify the commit succeeded and optionally read it back as required.
4. Never rely on a write transaction "rolling back automatically" when the callback succeeds.
5. Include a circuit-breaker/backoff mechanism if Neo4j is overloaded so monitoring does not worsen an outage.

## 12. Docker/Kubernetes: Don't Use One Probe for Every Responsibility

In containers, automatic restarts help recover from some process hangs but can make matters worse when failures stem from **disk, configuration, or quorum loss**.

### 12.1. Probe Architecture Pattern

~~~mermaid
flowchart TD
    K["Kubernetes probes"] --> ST["startupProbe: recovery window"]
    K --> LV["livenessProbe: lightweight process/transport"]
    K --> RD["readinessProbe: database/role + lightweight query"]
    RD --> TRAFFIC["Allow traffic routing"]
    MON["Prometheus / Monitoring"] --> MET["Neo4j + JVM + host metrics"]
    MON --> SY["Synthetic app read/write"]
~~~

**Startup** protects the recovery phase; **liveness** detects hung processes; **readiness** stops routing requests to members that cannot yet serve them. Prevent an intentionally offline database from causing the orchestrator to endlessly restart containers whose processes are operating normally.

### 12.2. A TCP Socket Probe Is Necessary but Insufficient

A Kubernetes configuration illustrating a **transport check**:

~~~yaml
# Illustrative fragment in a container spec only;
# tcpSocket does not verify TLS, auth, database, routing, or queries.
livenessProbe:
  tcpSocket:
    port: 7687
  periodSeconds: 30
  timeoutSeconds: 3
  failureThreshold: 5
~~~

This is not a complete manifest, and values must be tuned to startup/recovery durations. **Do not copy this TCP probe to readiness and conclude Neo4j is ready for all APIs.** For clusters, implement read/write workload health at the application layer or use official mechanisms provided by your chart/edition.

### 12.3. Don't Use Health Checks to "Self-Heal" with Dangerous Changes

A standard automated response on failure is **removing from load balancing** or **restarting the process when there is evidence of a hang**. Never automate:

- `DROP` database or deleting transaction logs.
- Switching the entire cluster to writable without understanding roles/quorum.
- Disabling TLS verification, escalating role privileges, or disabling security.
- Dropping an index currently being built because readiness looks slow.
- Restarting all primaries simultaneously, causing a broader service outage.

Automated recovery must be grounded in approved runbooks and safety preconditions.

## 13. Runbooks: Application-to-Neo4j Connectivity Incidents

### Scenario A — Unable to Establish a Bolt Connection

Symptoms: `ServiceUnavailable`, connection refused, DNS failure, or TLS handshake error.

Procedure:

1. **Determine scope:** all clients or a subset of pods/hosts? Do Neo4j Browser, the Java API, and synthetic probes fail together?
2. **Check network:** DNS, routing, firewall/network policy, endpoint/port, and load balancer.
3. **Check TLS:** `neo4j+s`/`bolt+s` scheme, hostname, CA certificate, expiration, recent rotations.
4. **Check auth:** user, secret rotation, DB access privileges, authentication failures; never print passwords into logs.
5. **Check server:** process, database `currentStatus`, and logs.
6. **Recover:** fix config/deployment/secret/route according to root cause, retry a safe synthetic read, and watch p95/error rate.

Do not "fix" the error by switching from verified TLS to plaintext before identifying the root cause.

### Scenario B — Reads Succeed but Writes Fail

Symptoms: `executeRead` works, while `executeWrite` returns unavailable, read-only, or routing errors.

Investigate:

- Is the client connecting via direct `bolt://` to a read-only member or via a routing URI?
- Does the database/cluster have a writable route and quorum?
- Does the user have WRITE privileges on the relevant labels/relationships/properties?
- Do disk and transaction logs have enough space to commit?
- Are there long-running transactions, lock contention, or constraint violations?

**Never grant admin privileges directly to an API** just because of a permission error. Identify the exact required privileges and inspect the transactions.

### Scenario C — Connectivity OK but p99 Spikes Sharply

1. Review traffic/rate, error/timeout counts, pool pending, and Bolt connections.
2. Correlate CPU, GC, heap, page cache, and disk I/O over the exact same window.
3. Identify the load-generating query family via controlled logging/tracing.
4. Run `EXPLAIN` and, when safe, `PROFILE` with **representative** parameters.
5. Check fan-out, indexes, `Sort`, `Expand`, long transactions, and read/write ratio.
6. Consider shedding offered load, throttling batches, limiting results, or improving Cypher/indexes; measure again before raising pool limits indefinitely.

### Scenario D — Disk Nearly Full

1. Identify **which partition** is filling up: data store, transaction logs, backups, or imports.
2. Check growth rate and recently launched jobs (imports, CDC, backups, GDS writes).
3. Pause non-essential workloads per the runbook; expand storage if necessary.
4. Never manually delete transaction logs or store files while the database is running.
5. Restore compliant configuration/retention/backup policies, then verify consistency and write capability.

### Scenario E — Cluster Member Disconnected

1. Identify the affected server, database, and role.
2. Check network between members, certificate changes, and cluster logs.
3. Assess whether **enough members/majority remain** for write operations.
4. Avoid simultaneous restarts or unplanned membership changes.
5. Once the member rejoins, monitor routing, replication/sync, latency, and synthetic read/write results.

## 14. Common Misdiagnoses Reference Table

| Symptom | Do Not Jump to Conclusions | Proper Verification |
| --- | --- | --- |
| TCP 7687 is open | "Database is definitely healthy" | TLS, auth, database online, Cypher read/write |
| `verifyConnectivity()` succeeds | "All write operations will succeed" | WRITE privileges, write route, transaction commit |
| `RETURN 1` is fast | "All graph traversals are fast" | p95/p99 and `PROFILE` of real queries |
| CPU is low | "There is no bottleneck" | Pool, lock wait, disk, network, routing |
| High page cache hit ratio | "No query tuning needed" | DB Hits, fan-out, sort, actual rows |
| One cluster node is online | "Cluster can accept writes" | Topology, quorum, writer, roles |
| Driver retry succeeds | "No outage occurred" | Retry count, end-to-end latency, error budget |
| `SHOW DATABASES` returns online | "No application monitoring needed" | SLIs from real HTTP/transactions |
| Heavy GDS job is running | "Database is broken" | Protect online workloads, resources, analytics schedule |

A **ready** system is one that can deliver its **promised functionality** under target load, not merely one that avoids throwing an exception on a single ping.

## 15. Hands-On Lab: Building a Neo4j Health Dashboard

### Context

A Spring Boot application manages `Customer` and `Order` in Neo4j; one API reads by `customerId` and another writes `Order`/`PLACED`. The system may run self-managed or on Aura.

### Step 1 — Define SLIs

Set two **separate** measurements:

1. `GET /customers/{id}/orders`: success rate and p50/p95/p99 latency.
2. `POST /orders`: transaction commit success rate and latency from API entry to commit.

Explicitly document timeouts, which client errors are excluded from the SLI under what criteria, and which server errors must still count. Do not hide timeouts or retries on the dashboard.

### Step 2 — Implement a Synthetic Read

Use `Neo4jReadHealth.check(driver, databaseName)` from Section 5, with exception handling in the caller. Run a `RETURN 1` query on a safe cadence and record status/latency. If a canary node exists, add a lookup using an indexed/constrained key.

### Step 3 — Check Database State

When the environment allows:

~~~cypher
SHOW DATABASES
YIELD name, requestedStatus, currentStatus, statusMessage
RETURN name, requestedStatus, currentStatus, statusMessage;
~~~

Compare the business DB state with the synthetic read outcome. Record "DB online but synthetic read hit permission denied" as an **access/config error**, not a reason to restart.

### Step 4 — Build a Three-Source Dashboard

Display on the same time axis:

- **Application:** HTTP traffic, errors, p50/p95/p99 latency, and driver pool.
- **Neo4j:** transactions, Bolt, page cache, heap/GC, query latency or slow queries when supported.
- **Host/container:** CPU, RAM, disk space/latency, restarts/OOM, network.

Annotate the timeline for code deploys, index changes, plugin updates, cluster restarts, or large data imports. These events explain metric shifts.

### Step 5 — Controlled Failure Testing

In a **lab** environment, choose scenarios that do not corrupt data:

| Test Scenario | Expected Outcome |
| --- | --- |
| Temporarily change URI to an unreachable mock endpoint | Synthetic connectivity fails, error is classified |
| Use invalid credentials | Distinguish authentication error from offline database |
| Target a nonexistent database name | DB unavailable / not found, no new DB auto-created |
| Cap load-generator concurrency | Dashboard reflects throughput, latency, pool pending |
| Run a traversal query on a high-degree customer | p95 rises, data available to diagnose the plan |
| Run a small batch import | Observe write transaction rate, heap/CPU, and disk |

Do not test by **filling the disk**, **deleting transaction logs**, **killing cluster quorum**, or **changing production roles** just to prove alerts fire.

### Step 6 — Propose Alerts

Try creating three rules:

1. **Critical:** read or write success rate drops below SLO over an appropriate window.
2. **Warning:** disk usage and growth rate project hitting threshold before expected remediation time.
3. **Warning:** p95 rises concurrently with rising pool pending or GC pauses across multiple windows.

Every alert must include **owner, impact severity, dashboard link, runbook, and recovery verification steps**.

### Self-Check Questions

**1. Is a running Neo4j process enough to mark the service healthy?**

No. You must verify connectivity, target database, privileges, routes, and required business operations.

**2. Why shouldn't a heavy traversal query be used as a liveness probe?**

Because high load/GC/network jitter can cause temporary probe timeouts, prompting the orchestrator to restart a working database and worsen the situation.

**3. Does `Driver.verifyConnectivity()` replace `executeRead` on the business database?**

Not completely. `verifyConnectivity` checks connection establishment; a synthetic transaction verifies execution on the target database under specific privileges.

**4. If a secondary/follower handles reads well but cannot write, is that necessarily an error?**

No. That may be expected according to its topology role. Check the application's write route and cluster state before concluding there is an incident.

**5. Why do we need both driver pool pending metrics and server CPU?**

Because requests can queue in the application-side pool before the server even receives a query; low Neo4j CPU does not rule out latency failures.

**6. Can `PROFILE` replace measuring API p99?**

No. `PROFILE` analyzes query operators but does not cover HTTP, pooling, routing, retries, or actual response delivery time.

**7. After a restart, is `SHOW DATABASES` returning online enough to close an incident?**

Not yet. You must verify traffic, read/write synthetics, error rates, p95/p99, backlogs, and business data within the incident scope.

## 16. Operations Checklist

- [ ] Distinguish **process, Bolt, database state, and operation availability**.
- [ ] Separate startup, liveness, readiness, and synthetic probes; avoid restart loops during valid startup/recovery.
- [ ] Run `Driver.verifyConnectivity()` and a lightweight `executeRead` on the **exact database** using the application role.
- [ ] Monitor the **write route** separately when the service executes critical write transactions.
- [ ] Collect CPU, heap, GC, native memory, page cache, disk I/O/space, and transaction logs.
- [ ] Collect Bolt connections, driver pool pending, transaction counts, retries, errors, and timeouts.
- [ ] Identify where metrics are sourced by **version/edition**: self-managed exporters vs. Aura dashboards.
- [ ] Never expose metrics endpoints, health diagnostics, URLs/credentials, or sensitive query parameters publicly.
- [ ] Set SLIs/SLOs by **read and write operations**; include failed/timed-out requests.
- [ ] Alert on **impact and time windows**, avoiding noisy single-sample CPU triggers.
- [ ] When queries slow down, combine `EXPLAIN`/`PROFILE` with Rows/DB Hits and actual load.
- [ ] Inspect topology, writer/quorum, and networking when clusters fail only on write operations.
- [ ] Keep probes lightweight so monitoring does not become a major source of load.
- [ ] Maintain runbooks for TLS/auth, database offline, pool exhaustion, disk nearly full, slow queries, and cluster disruption.
- [ ] Rehearse failures in a lab, reconcile after recovery, and track deploy/config history for investigations.

## References

- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Neo4j Operations Manual — Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/)
- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Cypher Manual — Database administration](https://neo4j.com/docs/cypher-manual/current/database-administration/)
- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Neo4j Aura Documentation](https://neo4j.com/docs/aura/)

**Conclusion:** Monitoring Neo4j health does not stop at checking whether the process is alive or Bolt port 7687 is open. **Availability** must be verified against the exact database, privileges, secure connections, read/write routes, and ability to complete business queries under load. Combining **synthetic probes, infrastructure/database/application metrics, SLIs/SLOs, contextual alerting, and runbooks** helps pinpoint true bottlenecks, avoid dangerous restarts, and recover the graph system in a controlled manner.
