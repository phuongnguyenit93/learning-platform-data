# Gathering Evidence, Isolating Root Causes, and Verifying Fixes in Neo4j

## Learning Objectives

After this lesson, you will be able to:

- Troubleshoot Neo4j incidents using a structured flow: **detect → preserve evidence → hypothesize → verify → mitigate → fix root cause → verify → conduct postmortem**.
- Distinguish issues across **Java/Spring applications**, **network/Bolt/TLS**, **Neo4j DBMS**, **database/indexes/Cypher**, **cluster/routing**, **OS/storage**, and **external data sources**.
- Collect timelines, logs, metrics, active transactions, database states, query plans, and configuration changes with **controlled scope and sensitivity**.
- Read `SHOW TRANSACTIONS`, `SHOW DATABASES`, `SHOW INDEXES`, `EXPLAIN`, and `PROFILE` to gather hard evidence instead of guessing root causes from a single error message.
- Form and falsify hypotheses by cross-checking **symptoms, distinguishing signals, low-risk tests, and falsification criteria**.
- Choose mitigations that reduce impact without losing transaction logs, breaking cluster quorum, or deleting graph data by mistake.
- Verify fixes across **four independent gates: availability, data correctness, performance, and stability**, while producing a repeatable incident report.

This lesson belongs to the **Troubleshooting** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Neo4j models data as a **property graph** (nodes, relationships, properties) and evaluates relationship/path queries via **Cypher**. Applications using the Neo4j Java Driver or Spring Data Neo4j can fail at multiple layers even when the surface error only says “query timeout”, “database unavailable”, or “order not found”. Sound investigation relies on **timestamped, scoped evidence**, not changing multiple settings at once and hoping the error vanishes.

> **Version scope:** Examples apply to Neo4j 5.x and modern `2025.x–2026.x` releases where the corresponding commands are supported. Logging, metrics, RBAC, clustering, and filesystem access vary across **Community/Enterprise/Aura**. Check `--help` and documentation for your exact version/edition, especially before enabling verbose logging, generating support reports, or running administrative commands.

## 1. Evidence-Based Troubleshooting Model

A responsible debugging investigation answers these questions in order:

1. **What is impacted?** Reads or writes, which database, which endpoints, how many users, total outage or slowdown on one query group?
2. **Since when?** Start time, recent changes, traffic spikes, backups/imports/index population, or failovers?
3. **What verifiable evidence exists?** Logs, metrics, query IDs/transaction IDs, traces, DB/index states, query plans, data comparisons?
4. **What are the hypotheses?** Ordered from easiest/lowest-risk to test to more complex.
5. **Which test differentiates them?** For example, if only one pod fails, do not start by restarting the whole cluster.
6. **How do we mitigate impact?** Isolate heavy queries, pause imports, fix routing/TLS, or roll back a release with supporting evidence.
7. **Is the issue truly resolved post-fix?** APIs return accurate data, writes commit cleanly, p95/p99 meets SLOs, and stability holds over time.

~~~mermaid
flowchart TD
    A["Error signal: API, alert, user"] --> B["Triage: scope, severity, timeline"]
    B --> C["Preserve logs, metrics, IDs, changes"]
    C --> D["Testable hypotheses"]
    D --> E["Low-risk test"]
    E --> F{"Does evidence support it?"}
    F -->|No| D
    F -->|Yes| G["Mitigate / fix root cause"]
    G --> H["Verify functionality, data, SLOs"]
    H --> I{"Meets closure criteria?"}
    I -->|No| C
    I -->|Yes| J["Postmortem + preventive actions"]
~~~

**Crucial distinction:**

- **Symptom:** `executeWrite` times out.
- **Hypothesis:** Cluster writer is unavailable, or transactions are waiting on locks.
- **Evidence:** `SHOW DATABASES` confirms a writer exists with healthy quorum; `SHOW TRANSACTIONS` shows high `waitTime` on transactions updating the same node.
- **Confirmed root cause:** Two jobs update a hot `Account` node while holding transactions open too long.
- **Remediation:** Adjust batching, lock ordering, and transaction duration bounds.
- **Verification:** Writes commit again, wait time drops, zero duplicate writes occur, and Account balances remain accurate.

Never call a correlation (“CPU rose after deploy”) a **proven root cause** without running checks that rule out alternative explanations.

## 2. First-Minutes Triage: Impact, Priority, and Ownership

Before changing anything:

| Question | Example facts to record |
| --- | --- |
| **User scope** | 15% of `GET /customers/{id}/orders` requests time out; `POST /orders` still works |
| **Operation type** | READ, WRITE, admin, backup, import, GDS job |
| **Database/cluster** | `orders_graph`, Neo4j Enterprise cluster region A; or internal Aura instance ID |
| **Severity** | SEV1 if critical transaction writes fail; SEV2 if a major read feature degrades |
| **Timeline** | Started 09:12 UTC, release at 09:05 UTC, index population at 09:10 UTC |
| **Data risk** | Risk of partial writes? Transactions committed while HTTP timed out? |
| **Temporary mitigation** | Pause batch import, route reads to trusted endpoint, roll back app if justified |

These are **illustrative severity levels**, not a mandatory Neo4j SEV framework. Organizations need their own escalation criteria: data corruption or lost financial transactions usually outrank a delayed analytics dashboard.

### 2.1. Incident Roles

- **Incident commander:** sets priorities and coordinates mitigations.
- **DBA / Neo4j operator:** inspects databases, clusters, logs, metrics, locks, and stores/indexes.
- **Application owner:** inspects Java Driver, SDN, API errors/traces, actual Cypher, and deployments.
- **SRE / platform:** inspects CPU/RAM/disk, containers, DNS, TLS, network, and storage.
- **Data / domain owner:** verifies business invariants, reconciliations, and data repair plans.

In small teams, one person may wear multiple hats, yet still separate **who authorizes remediation** from **who signs off on data correctness** in severe incidents.

### 2.2. When Must Evidence Preservation Come First?

Before restarting or rolling back, capture **lightweight, safe** snapshots as long as doing so does not worsen the outage:

- Metric charts covering **before–during–after** the incident.
- Logs with exact timestamps and original error messages.
- Active and blocked transaction lists while still observable.
- Database, index, topology, and active config/release states.
- Request IDs/trace IDs, database names, and query hashes or query IDs.

State such as **running transactions**, routing tables, and lock waits vanishes on restart. Still, never delay service recovery endlessly just to collect every artifact; balance against live user impact.

## 3. Timeline: Normalize Clocks Before Correlating Events

A Neo4j incident often spans multiple clocks:

~~~text
09:04:32.100Z  Application deploy completes
09:07:12.550Z  Query p95 rises from 80ms to 900ms
09:07:14.015Z  Neo4j query.log: queryId ..., elapsed=910ms
09:07:15.640Z  SHOW TRANSACTIONS: 18 transactions blocked
09:08:01.420Z  Import job #42 begins large write batch
09:12:00.000Z  Operator pauses import
09:14:20.000Z  p95 drops to 100ms, timeout rate returns to baseline
~~~

These timestamps are hypothetical examples. **Do not declare the import the root cause solely because it appeared near the p95 spike**: compare lock waits, transaction counts, query IDs, and controlled load-shedding results.

Timeline guidelines:

1. Record timestamps in **UTC or ISO 8601 with offsets**; never mix local time and UTC.
2. Note **log time zones**. In containers, log collectors can stamp different times than in-app logs.
3. Check for **NTP/clock skew** across servers, apps, and brokers; never treat client-supplied `occurredAt` as absolute proof if clocks are unverified.
4. Record **deploy/change events**: app releases, queries, indexes, plugins, DB settings, DNS/TLS, and backup/GDS jobs.
5. Keep **original timestamps** alongside normalized UTC values for comparison.
6. For recurring incidents, build a timeline for **each occurrence** and look for common triggers.

An “incident worksheet” should include:

| Field | Example | Security |
| --- | --- | --- |
| `incidentId` | `INC-2026-114` | No PII |
| `firstSeenAt` | `2026-11-25T09:07:12Z` | Use UTC |
| `environment` | `prod-asia` | Keep private if sensitive |
| `database` | `orders_graph` | Exact database name, not ambiguous aliases |
| `operation` | `createOrder` | Never log payment payloads |
| `appTraceId` | `trace-...` | Correlates across layers |
| `queryId / transactionId` | Value observed at error time | Ephemeral ID; never treat as a business key |
| `changeId` | Release, index job, or network change | Link ticket/approval |
| `evidenceRefs` | Log/dashboard snapshot links | Restrict viewing permissions |

## 4. Evidence Source Matrix: What Does Each Layer Prove?

| Layer | Evidence source | What it distinguishes | What it does NOT prove |
| --- | --- | --- | --- |
| **HTTP/API** | APM/traces, request metrics, retries, timeouts | Which endpoint fails and how long callers wait | That the root cause definitely sits inside Neo4j |
| **Java Driver/SDN** | Error codes/classes, connection/pool, database name, session routing | Client-side auth/TLS/timeout/query errors | That stores/indexes are consistent |
| **Cypher/database** | `SHOW TRANSACTIONS`, `SHOW INDEXES`, `SHOW DATABASES` | Active queries, locks, index state, database online | That networking between every node is healthy |
| **Neo4j logs** | `neo4j.log`, `debug.log`, `query.log`, `security.log` per edition | Startup/recovery/errors/slow queries/auth events | That every failed request was logged with full payload |
| **Neo4j metrics** | JVM, page cache, Bolt, transactions, disk I/O | Saturation and trends over time | Which query caused the fault without log/trace correlation |
| **OS/container** | Host/kernel, disk, OOMKill, restarts, network | Resource limits, container lifecycle, storage/network | That business invariants remain intact |
| **Cluster** | Topology/roles, writer/quorum, routing, replication lag | Whether failures affect only READ or WRITE | That data matches external systems |
| **Data/integration** | Checks by business ID, source of truth, CDC/outbox checkpoints | Missing/stale/duplicate nodes or relationships | Full recovery before thorough reconciliation |

**Golden rule:** Collect at least **two independent sources** backing any major conclusion. For example, “database is slow due to a missing index” requires `PROFILE`/DB Hits plus `SHOW INDEXES`; a rising CPU graph alone is never enough.

## 5. Neo4j Logs: Right File, Right Version, Right Sensitivity

Common log files on self-managed Neo4j:

| Log | Contents | Caution |
| --- | --- | --- |
| **`neo4j.log`** | General operational events, startup/shutdown | Depending on packaging, may appear via `journalctl` |
| **`debug.log`** | Detailed diagnostics for ops and Neo4j Support | Can grow large; defaults to JSON starting in 2025.01 |
| **`query.log`** | Slow/executed queries, durations, and related stats | Enterprise feature; may contain query parameters |
| **`security.log`** | Security/authentication events where supported | Do not leak usernames or internal addresses broadly |
| **`gc.log`** | Garbage Collection pauses and activity if enabled | Correlate with JVM heap, p99, and OOMs |
| **Container/system logs** | OOMs, restarts, disk/network events | Timestamps may skew relative to Neo4j logs |

Log paths are governed by `server.directories.logs` or deployment settings. In Docker/Kubernetes, check container stdout/log collectors; on Aura, use **the logs and dashboards provided by the managed service** rather than assuming direct Neo4j filesystem access.

### 5.1. Query Logging for Diagnostics

In self-managed Neo4j Enterprise, a cautious slow-query logging config is:

~~~properties
# neo4j.conf - investigative example; verify version and data policy.
db.logs.query.enabled=INFO
db.logs.query.threshold=200ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
~~~

Meaning:

- `INFO`: logs queries after completion when exceeding the threshold.
- `threshold`: filters for unusual slow queries; `200ms` is merely an example.
- Disable **parameter value logging** unless strictly required for investigation.
- Obfuscating literals limits raw data exposure in query text, yet does not guarantee all sensitive data variants are masked.

**Depending on Neo4j version**, some settings update dynamically while others require a restart/rollout. Never edit production configs without approval. Per current docs, default query logging in newer releases may be `VERBOSE`; never assume every server uses identical defaults.

### 5.2. The Cost of Verbose Logging

Never enable unboundedly:

~~~properties
# DO NOT use in production by default just to debug.
db.logs.query.enabled=VERBOSE
db.logs.query.plan_description_enabled=true
db.logs.query.parameter_logging_enabled=true
~~~

Plan logging adds overhead, and parameters can expose **PII, tokens, and query payloads**. Enable only with an explicit purpose, time window, log owner, disk cap, and shut-off plan. Before sharing support bundles, enforce redaction and access controls.

### 5.3. Parsing a Query Log Entry

Suppose you observe:

~~~text
2026-11-25T09:07:14Z  queryId=Q-17  database=orders_graph
elapsed=910ms planning=8ms waiting=650ms pageHits=900
query="MATCH ... MERGE ..."
~~~

**This is a synthetic log line**, not a guaranteed exact format. If `waiting=650ms` and `planning=8ms`, check **lock/transaction contention** before blaming missing indexes. If `pageFaults` and I/O climb, evaluate working set, page cache, and disk. If `planning` spikes after an upgrade, inspect plan caches, replanning, and index states.

Query IDs can reset across restarts; never use log query IDs as permanent identifiers across runs. Combine **timestamp, database, server, query text/hash, and app trace ID**.

Reference: [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/).

## 6. Database State, Edition, and Schema: Read-Only Evidence

### 6.1. Identify the DBMS and Target Database

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

~~~cypher
SHOW DATABASES
YIELD name, requestedStatus, currentStatus, statusMessage
RETURN name, requestedStatus, currentStatus, statusMessage
ORDER BY name;
~~~

Commands require appropriate privileges, and columns depend on version. **`requestedStatus`** is the desired state; **`currentStatus`** is the observed state. If the target database is offline, do not rush to debug a `MATCH` query as an index problem.

In an Enterprise cluster, where supported by version:

~~~cypher
SHOW SERVERS;
~~~

~~~cypher
SHOW DATABASES
YIELD name, address, role, writer, currentStatus
RETURN name, address, role, writer, currentStatus
ORDER BY name, address;
~~~

A database may remain **readable** while lacking a healthy **WRITE route/quorum**. One endpoint's status does not represent every allocation; inspect members per your cluster runbook.

### 6.2. Inspect Indexes and Constraints

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes,
      properties, state, populationPercent
RETURN name, type, entityType, labelsOrTypes,
       properties, state, populationPercent
ORDER BY state, name;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Distinguish:

- **Missing index:** query lacks the expected access path.
- **`POPULATING` index:** schema is defined, not yet ready for traffic.
- **`FAILED` index:** inspect failure reason and resources; do not drop/recreate blindly.
- **Constraint violation:** data or concurrency breaks an invariant; never “fix” by disabling constraints without business review.

A slow query **does not automatically mean a missing index**; the planner may legitimately scan small sets or choose a better plan. Verify with `EXPLAIN`/`PROFILE`.

## 7. Transactions, Locks, and Running Queries

Neo4j provides `SHOW TRANSACTIONS` to inspect live transactions within your privileges:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, database, username, status,
      elapsedTime, waitTime, currentQuery
RETURN transactionId, database, username, status,
       elapsedTime, waitTime, currentQuery
ORDER BY elapsedTime DESC
LIMIT 25;
~~~

To avoid printing query text/PII in wide reports, read only metadata when sufficient:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, database, status,
      elapsedTime, waitTime, activeLockCount
RETURN transactionId, database, status,
       elapsedTime, waitTime, activeLockCount
ORDER BY elapsedTime DESC
LIMIT 25;
~~~

Some columns are **extended columns**, and visibility into other users' transactions depends on RBAC. Per documentation, `SHOW TRANSACTIONS` inspects transactions **on the connected instance**; in clusters, check the appropriate members rather than treating one empty result as proof no server has slow transactions.

### 7.1. Reading Transaction Numbers Properly

| Signal | Possible implication | Next verification |
| --- | --- | --- |
| High `elapsedTime`, high `waitTime` | Lock contention, blocked transaction | `status`, `resourceInformation`, competing transactions |
| High `elapsedTime`, low `waitTime` | Query computing or waiting on I/O/network | CPU, DB Hits, page faults, client consumption |
| High `activeLockCount` | Transaction holds many locks | Actually blocked, or a valid large write workload? |
| Query finished, transaction stays open | App delayed commit/consumption or doing external work | Callback code, session lifecycle, transaction logs |
| Hot `Order`/`Account` written repeatedly | Business-key hotspot | Batch size, update ordering, lock contention |

**Watch out with duration:** `elapsedTime` measures transaction age, not strictly active Cypher runtime. A transaction can sit idle while the app waits on external HTTP calls—an anti-pattern to fix.

### 7.2. Terminating Transactions Is a Risky Mitigation

After recording evidence, identifying the exact target transaction, and getting approval, Neo4j provides:

~~~cypher
// ILLUSTRATION FOR LAB / APPROVED INCIDENT PROCEDURE.
// Replace with the verified live transactionId.
TERMINATE TRANSACTIONS 'neo4j-transaction-123';
~~~

Never blindly pick “the oldest transaction”. Termination rolls back in-flight work, potentially triggering application retries and extra load; if network fails near commit, **the client may not know whether the transaction committed**. Require **business IDs/idempotency** and data verification before replaying requests.

Never auto-terminate every transaction with `elapsedTime > 30s` without understanding legitimate batches, imports, GDS jobs, or traversals. Identify the **request owner** and rollback effects before intervening.

Reference: [Neo4j — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/).

## 8. Cypher Performance: `EXPLAIN`/`PROFILE` to Isolate Root Causes

Suppose an app reports the order-list endpoint jumped from 60 ms to 1,200 ms:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId, o.status AS status
ORDER BY o.orderId
LIMIT 20;
~~~

First **inspect the plan without running data**:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId, o.status AS status
ORDER BY o.orderId
LIMIT 20;
~~~

Where safe, measure execution on a snapshot/lab or under controlled production conditions:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId, o.status AS status
ORDER BY o.orderId
LIMIT 20;
~~~

**`PROFILE` actually executes the query.** For `CREATE`, `SET`, `DELETE`, or side-effecting procedures, running `PROFILE` **mutates data**; never run it in production just to “check the plan”.

### 8.1. Evidence in the Query Plan

| Operator / metric | What to check |
| --- | --- |
| `NodeUniqueIndexSeek` / `NodeIndexSeek` | Does it start from an index on `Customer.customerId`? |
| `NodeByLabelScan` / `AllNodesScan` | Why is the planner scanning many nodes? |
| `Expand(All)` | Does one customer produce 100 or 100,000 `PLACED` rows? |
| `Filter` | Is filtering applied too late after relationship expansion? |
| `Sort` / `Top` | How many rows are sorted before `LIMIT 20`? |
| `Rows` | Actual rows at each operator; any fan-out explosion? |
| `DB Hits` | How much did storage access cost rise vs. baseline? |
| Page hits/faults | Is cache or I/O under pressure? |
| Plan/runtime | Did it shift due to indexes, stats, Cypher version, or runtime? |

**`LIMIT 20` does not guarantee reading only 20 relationships.** If a customer has 80,000 orders, Neo4j may expand and sort huge numbers of rows to find the top 20. Changing the Java DTO will not cut this work if Cypher still pulls the entire subgraph.

### 8.2. Before/After Comparisons

For the same query ID:

- Keep **dataset, indexes, parameters, and concurrency** comparable.
- Compare both low-degree and high-degree customers; averages hide hotspots.
- Distinguish **cold cache** right after restart from **warm cache** steady state.
- Pair DB Hits/Rows with **Java Driver pool wait**, HTTP latency, and network metrics.
- After Neo4j/Cypher upgrades, compare **identical syntax and language versions** before changing multiple variables at once.

Do not force query plans to preserve the **exact same string of operator names** across upgrades. The goal is accurate business results within SLO budgets.

Reference: [Neo4j — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/).

## 9. System Metrics: Proving CPU, Memory, Disk, or Network Bottlenecks

A Neo4j incident typically requires correlating at least **three sources**: Neo4j metrics, host/container metrics, and application metrics.

| Group | Metrics to inspect | Suggested symptoms |
| --- | --- | --- |
| **CPU** | Process/host CPU, load, container throttling | Heavy scans/expansions, saturation, or CPU throttling |
| **JVM heap** | Used/max, allocation rate, GC pause/time | High object churn, giant transactions, OOM pressure |
| **Page cache** | Hits/misses, page faults, configured size | Working set exceeds cache; slow I/O |
| **Disk** | Free bytes, IOPS, read/write latency, FS errors | Store/log write failures, slow checkpoints, backup/import contention |
| **Bolt/network** | Connection errors, handshake/TLS, RTT, packet drops | Driver timeouts, unreachable routing addresses |
| **Transactions** | Active, commits/rollbacks, retries, lock waits | Write hotspots or long transactions |
| **Application** | HTTP p50/p95/p99, error rate, pool pending, retries | Users waiting far longer than server query time |
| **Cluster** | Writer/quorum, member availability, replication lag | `WRITE` unavailable or stale `READ`s |

### 9.1. High CPU Is Not Automatically a Bug

CPU rising alongside higher throughput and steady p99 may simply reflect **valid increased work**. High CPU with falling throughput and surging DB Hits suggests a query regression. Low CPU with high pool pending points toward **client-side** or network bottlenecks.

### 9.2. Unfilled JVM Heap Does Not Guarantee Enough RAM

Total Neo4j RAM also includes **page cache, native/off-heap memory, OS, and co-located processes**. Containers get `OOMKilled` on total memory limits even when Java heap sits below max. With GDS or plugins, budget in-memory graph projections and algorithm state separately per deployment sizing.

### 9.3. Disk Full Is Critical

If the store or transaction log filesystem nears capacity:

1. Identify **which mount/partition** is filling and its growth rate.
2. Check backups/imports, retention, transaction logs, and store growth.
3. Shed non-essential load and expand disk capacity per runbook.
4. **Never manually delete transaction logs or store files on a running server** just to free space.
5. After recovery, verify store consistency, backup readiness, and `WRITE` commits.

### 9.4. Prometheus, NOM, Aura

Self-managed Neo4j Enterprise supports Prometheus/JMX/CSV metrics and Neo4j Ops Manager depending on release. On **Aura**, use the dashboards/metrics provided by the managed tier plus app telemetry; do not assume direct server filesystem log access or custom exporter toggles.

Keep metric label cardinality low (`database`, `instance`, `operation`); never put `customerId`, `orderId`, or sensitive query parameters into dashboard labels.

Reference: [Neo4j Operations Manual — Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/).

## 10. Java Driver and Spring Data Neo4j: Errors Can Happen Before the Database

A Java Driver exception is a **client-side trace**; it does not by itself prove Neo4j Server crashed.

| Error / symptom | Initial hypothesis | Distinguishing evidence |
| --- | --- | --- |
| `ServiceUnavailableException` or failed connection | Network, DNS, TLS, Bolt, server down | TCP/TLS checks, URI, driver logs, server health |
| `SessionExpiredException` | Current server/route cannot serve session (e.g., writer changed) | Cluster writer/routing, failover timeline, retries |
| `AuthenticationException` / authorization failure | Wrong credentials, missing role, rotated secret | Security log, user/role, exact error code |
| `ClientException` from Cypher/constraints | Bad query or data violating an invariant | Neo4j error code/`GQLSTATUS`, redacted query/params |
| `TransientException` | Transient contention, lock/timeout/unavailability | Transaction state, retry policy, resource metrics |
| “HTTP times out while server query is fast” | App pool, serialization, network, external calls | APM spans, connection acquisition, app CPU, payload size |
| “Results missing relationships” | SDN projection/mapping, bounded query, stale cache | Raw Cypher results, DTO mapping, entity fetch scope |

Neo4j error codes span **`Neo.ClientError`**, **`Neo.TransientError`**, and **`Neo.DatabaseError`**, plus GQL status codes in newer releases. Read the **actual exception class and code**; never retry every error blindly. Constraint or Cypher syntax errors cannot be “fixed” by retrying like a fleeting routing hiccup.

### 10.1. Bounded Connectivity Probe

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jDiagnosticProbe {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity(); // Bolt/TLS/auth/routing

            try (Session session = driver.session(
                    SessionConfig.forDatabase("orders_graph"))) {
                long result = session.executeRead(tx ->
                        tx.run("RETURN 1 AS ok")
                          .single()
                          .get("ok")
                          .asLong());
                System.out.println("Read probe: " + result);
            }
        }
    }
}
~~~

This is a **diagnostic CLI example**, not a complete readiness endpoint. Provision environment variables and the real database before running. `verifyConnectivity()` can pass while a specific database is offline or `WRITE` is unavailable. Nor does `RETURN 1` prove a heavy graph traversal will meet its SLO.

### 10.2. Attaching Per-Request Metadata Safely

On Java Driver versions supporting `TransactionConfig`:

~~~java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.TransactionConfig;

var cfg = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of(
                "operation", "lookupCustomerOrders",
                "traceRef", "trace-opaque-123"))
        .build();

var result = session.executeRead(tx ->
        tx.run("""
            MATCH (c:Customer {customerId: $id})
            RETURN c.customerId AS id
            """, Map.of("id", customerId))
          .single()
          .get("id")
          .asString(), cfg);
~~~

This assumes `session` and `customerId` are defined, using **non-PII** metadata. Metadata correlates transactions/query logs with app traces, though logging behavior for these fields varies by version; do not treat it as a replacement for proper distributed tracing.

### 10.3. Application-Layer Mistakes

- Creating a **new `Driver` per request**, defeating connection pooling and multiplying handshakes.
- Sharing a **`Session` across threads** when `Session` is not thread-safe.
- Connecting directly with `bolt://` to a cluster member that cannot accept `WRITE`s instead of using a proper routing URI.
- Omitting database selection, causing queries to hit the wrong default database.
- Sending emails or charging payments inside `executeWrite` callbacks when the driver **may retry the entire callback**, duplicating side effects.
- Timing only `tx.run` instead of **full `Result` consumption, commit, and retries** in end-to-end latency.
- Using full SDN entity graphs for an API needing two properties, triggering over-fetching/fan-out.

**Correctness after errors:** if connection drops near commit, the client may not know whether the `WRITE` committed. Query by **business ID and idempotency key** against the database/source of truth before replaying to avoid duplicates.

References: [Neo4j Java Driver Manual — Connect](https://neo4j.com/docs/java-manual/current/connect/), [Transactions](https://neo4j.com/docs/java-manual/current/transactions/), [Server error classifications](https://neo4j.com/docs/status-codes/current/errors/).

## 11. Clusters, Routing, and Replication: READ vs. WRITE Failures Differ

In a modern Neo4j Enterprise cluster, each standard database has **primary allocations**, one **writer/leader**, and optionally **secondaries** serving `READ`s asynchronously.

Example:

~~~mermaid
flowchart LR
    API["Java Driver routing"] --> R["Routing table"]
    R -->|WRITE| P1["Primary writer"]
    P1 <-->|Consensus| P2["Primary follower"]
    P1 <-->|Consensus| P3["Primary follower"]
    R -->|READ| S["Secondary reader"]
    P1 -.->|Async replication| S
~~~

### 11.1. Failure Patterns

| Symptom | Hypothesis | Evidence |
| --- | --- | --- |
| `WRITE` fails, `READ` works | Missing write route/quorum or wrong role | `SHOW DATABASES` writer/status, topology, driver exceptions |
| Some `READ`s miss recent writes | Secondary lag or missing causal bookmarks | Replication lag, session/bookmarks, source commits |
| Only one app pod times out | That pod's DNS/routing/CA/pool | Compare env/pod metrics, authorized network/TLS logs |
| Errors right after failover | Stale routing table, `SessionExpired`, retries | Election timeline, driver logs, `neo4j://` URI |
| Adding servers does not raise throughput | Servers not enabled/allocated or client skips routing | `SHOW SERVERS`, `SHOW DATABASES`, client routing/traffic |

**Quorum** belongs to the **specific database's primary group**, not the total number of pingable Neo4j processes. Three primaries tolerate losing one primary while preserving 2/3 quorum; never restart all primaries at once to “fix” a transient error.

### 11.2. Bookmarks Solve Causality Only Within Neo4j

The Neo4j Driver provides **bookmarks / causal consistency** so dependent `READ`s wait for prior Neo4j transactions to become visible. A bookmark **cannot** make a commit in PostgreSQL appear instantaneously in Neo4j before CDC/outbox syncs.

When an RDBMS is the source of truth and Neo4j is a read model:

- Measure **source commit → consumer apply → read visible**.
- Inspect event IDs/versions, backlog, DLQ, and checkpoints.
- For missing or stale data, **reconcile** by business key rather than merely restarting Neo4j.

## 12. Data Corruption or Drift: Protect Invariants, Inspect Before Fixing

An incident may throw zero technical errors: queries return HTTP 200 yet **the graph is wrong**. For example, an `Order` exists without its `PLACED` relationship, or two nodes share the same logical ID.

### 12.1. Evidence to Collect

~~~cypher
// Check how many Orders share a business ID.
MATCH (o:Order {orderId: $orderId})
RETURN count(o) AS matches;
~~~

~~~cypher
// Check ownership along PLACED edges.
MATCH (o:Order {orderId: $orderId})
OPTIONAL MATCH (c:Customer)-[:PLACED]->(o)
RETURN o.orderId AS orderId,
       o.status AS status,
       collect(DISTINCT c.customerId) AS ownerIds;
~~~

~~~cypher
// Check real database constraints, never infer from Java annotations alone.
SHOW CONSTRAINTS;
~~~

On large graphs, sample **representative IDs/batches** rather than scanning the entire store during peak hours. If duplicate `Order` nodes exist without a constraint, never delete the “extra” copy before inspecting its relationships and authoritative source data.

### 12.2. Safe Data Repair Principles

1. **Freeze offending writes** if drift continues and invariants must be protected.
2. Take a backup/snapshot or controlled export of the **affected slice** before repairing.
3. Identify the **system of record** and authoritative version by business ID/version.
4. Write a **dry-run** script reporting affected node/edge counts, `WHERE` predicates, and sample outputs.
5. Execute in controlled, idempotent batches/transactions where appropriate.
6. Verify **before vs. after** with identical queries, checking downstream CDC, caches, and search indexes.
7. Retain an audit trail of repair decisions and a rollback path.

**Never run bulk `DETACH DELETE`** in production to clear orphan nodes without assessing impact: it deletes every attached relationship on target nodes. For domain bugs, correctness matters far more than making counts “match” quickly.

### 12.3. Restoring a Backup Does Not Auto-Sync Cross-System Drift

If you restore Neo4j to a 10:00 backup while PostgreSQL committed orders up to 10:30, you must **replay, rebuild, or reconcile** the delta. Never call the restored database “in sync” while the read model lacks 30 minutes of events.

## 13. Isolating Root Causes with a Decision Tree

Instead of guessing randomly, move from **low-cost, high-discrimination checks** onward:

~~~mermaid
flowchart TD
    A["Neo4j request fails or is slow"] --> B{"Driver connect and auth OK?"}
    B -->|No| N["DNS/TLS/Bolt/credentials/routing"]
    B -->|Yes| C{"Target database ONLINE?"}
    C -->|No| O["Recovery/disk/cluster/database state"]
    C -->|Yes| D{"Small READ OK?"}
    D -->|No| P["Role/read route/resources/server error"]
    D -->|Yes| E{"Required WRITE OK?"}
    E -->|No| Q["Quorum/writer/constraints/locks/disk"]
    E -->|Yes| F{"Business query slow?"}
    F -->|Yes| G["PROFILE + indexes + rows + client pool"]
    F -->|No| H["Reconcile data, cache, CDC, DTO"]
~~~

This is a **guide tree**, not strict mutual exclusion. An incident can combine **two simultaneous faults**: a missing index slows queries while one app pod holds an expired secret. A passing `RETURN 1` does not rule out failures on heavy relationship queries.

### 13.1. Every Hypothesis Must Have a Falsifying Signal

| Hypothesis | Supporting evidence | Falsifying evidence |
| --- | --- | --- |
| TLS/Bolt failure | Handshake fails; `verifyConnectivity` fails | Client connects/queries cleanly with the same URI/cert |
| DB offline | `currentStatus` not `online`; recovery logs | DB online; small query succeeds on exact DB |
| Missing index | Planner runs big scan; index absent/`FAILED` | Plan uses right seek; low DB Hits |
| Lock contention | High `waitTime`; blocked transactions | `waitTime` near 0; high CPU/DB Hits |
| Page cache/disk | Faults and disk latency climb together | Cache/I/O healthy; app pool pending high |
| Cluster lost writer | `WRITE` route unavailable / quorum error | `WRITE` succeeds via routing; one role lacks privilege |
| App mapping bug | Raw Cypher accurate; JSON/DTO wrong | Raw result is already wrong |
| CDC backlog | Source version ahead of graph; consumer lag | Versions and checkpoints caught up; only UI cache stale |

Record **confidence** (low/medium/high) for each hypothesis and how new evidence shifted it. Never claim 100% certainty without a decisive test.

## 14. Controlled Support Report Collection

Self-managed Neo4j includes:

~~~bash
# Run on the Neo4j host or an environment with the neo4j-admin binary.
# Run only when authorized with sufficient free disk.
neo4j-admin server report --list
~~~

To capture **a small targeted bundle** for investigation:

~~~bash
# Example: logs + thread dumps only; avoid pulling heap/tx logs blindly.
neo4j-admin server report \
  --to-path=/srv/incident-reports \
  threads logs
~~~

Depending on version, reports can collect logs, configs, metrics, thread dumps, cluster state, and other classifiers. **Never select `all` by default**, and especially avoid blindly adding `heap`, `tx`, or `raft`: they can contain sensitive data, consume huge space, and spike I/O.

Notes:

- The tool does not auto-upload reports to Neo4j Support; share **deliberately** through secure channels.
- Inspect supported classifiers and flags with `--list`/`--help` on your actual version.
- Extra classifiers introduced **from 2026.08** onward require verification; do not copy newer flags onto older 5.x releases.
- Before sharing, review for PII, query parameters, internal hostnames, tokens, configs, and heap contents.
- Enforce tight read permissions, short retention, checksums, and incident IDs on artifacts.
- Never trigger heap dumps on a system already starving for disk/memory without resource safeguards.

**A support report is an evidence-gathering tool, not a fix.** Successfully generating a report does not mean you found the root cause.

Reference: [Neo4j Operations Manual — Generate system report](https://neo4j.com/docs/operations-manual/current/monitoring/neo4j-admin-report/).

## 15. Pick Low-Risk Mitigations First

### 15.1. Intervention Hierarchy

| Level | Examples | When appropriate |
| --- | --- | --- |
| **0 — Observe** | Logs, metrics, `SHOW`, `EXPLAIN`, synthetic reads | Default, lowest risk |
| **1 — Shed load** | Cut concurrency, pause import/GDS jobs, rate-limit heavy queries | Proven saturation or contention |
| **2 — Fix app/query** | Roll back release, tighten `WHERE`/`LIMIT`, tune timeouts/pools with proof | Root cause lies in app/query |
| **3 — Fix DB config/schema** | Create/repair index per runbook, tune config under change control | Plan/index/resource cause verified |
| **4 — Major ops actions** | Server restart, failover, restore/seed, cluster topology change | Only with approval, backups, and blast-radius plan |
| **5 — Repair data** | Fix nodes/relationships, replay CDC, restore backup | Proven data corruption, confirmed by domain owner |

Higher levels are **not automatically better**. If the culprit is an unfiltered `MATCH` emitting 10 million rows, restarting the cluster destroys volatile evidence and fails to fix the query.

### 15.2. Define Stop Criteria and Rollback for Every Action

Every action record should include:

~~~text
Action ID: ACT-17
Hypothesis: Batch import holds locks too long on :Inventory
Evidence: 24 transactions show rising waitTime; query log confirms high waits
Action: Pause import job while keeping READ/WRITE services online
Expected: Write p95 drops; waitTime drops across 3 measurement windows
Risks: Import backlog grows; read model lags slightly
Rollback: Resume job with smaller batches after fixing write logic
Owner/approval: ...
Observed result: ...
~~~

Never mark a mitigation “successful” just because one chart flickered down right afterward; verify across full measurement windows and live traffic.

### 15.3. Actions Never to Take Recklessly

- Deleting `data/databases`, transaction logs, or index files to “free” disk.
- Disabling uniqueness constraints on duplicate-write errors without inspecting data.
- Running `TERMINATE TRANSACTIONS` with unverified IDs or unapproved wildcards.
- Restarting all primaries simultaneously, breaking Neo4j quorum.
- Disabling TLS verification, opening unrestricted procedures, or granting admin to apps to bypass permission errors.
- Running `PROFILE` on production write queries and treating it as read-only observation.
- Restoring straight over a live serving database or downgrading binaries without a migration path.

These actions can turn a temporary performance incident into **data loss or total unavailability**.

## 16. Post-Fix Verification: Four Independent Gates

An action is complete only with **post-fix evidence** across all relevant layers.

### Gate A — Connectivity / Availability

- Java Driver `verifyConnectivity()` succeeds with proper network/TLS/auth.
- `SHOW DATABASES` confirms the target database is `online` where supported.
- Synthetic **READ** succeeds on the right database and role.
- For write workloads: a **controlled synthetic WRITE** or real business transaction commits cleanly.
- In clusters: valid writer/quorum and routing, with replicas recovering as expected.

**`RETURN 1` succeeding is not enough** to declare writes healthy or graph traversals recovered.

### Gate B — Data Correctness

- Reconcile business IDs, counts, and properties across the impacted dataset.
- Zero duplicate nodes/relationships from retries; constraints exist and are `ONLINE`.
- Data missing after any restore is replayed and reconciled against the source of truth.
- For CDC/outbox: verify versions, checkpoints, backlog, and DLQs.
- After deletes/repairs: verify **unrelated** relationships were untouched.

Never check only `count(n)`: the graph may hold the right node count yet miss `PLACED` edges or have inverted directions.

### Gate C — Performance and Resource Health

- Impacted operations' p50/p95/p99 return within **SLOs** under representative load.
- Error, timeout, and retry rates return to baseline.
- `Rows`/`DB Hits`, lock waits, page faults, and pool pending align with the verified fix.
- Heap/GC, CPU, free disk, I/O, and transaction throughput stabilize.
- Zero regressions elsewhere: speeding up `READ` while saturating `WRITE` is not full success.

### Gate D — Durability and Recurrence Resistance

- Improvements hold across **multiple windows** and the next scheduled batch/job run.
- No growing backlogs, no `FAILED` indexes, and cluster fault tolerance meets SLOs.
- Alerts and tracing for recurrence signals are active.
- A long-term fix has an assigned owner, avoiding permanent temporary hacks or permanently disabled jobs.

### 16.1. Sample Incident Closure Criteria

| Gate | Required evidence | Example PASS |
| --- | --- | --- |
| Availability | Synthetic READ and WRITE under app privileges | ≥ 99.9% success across approved window |
| Data | Zero duplicates/missing records on affected IDs | `orderId` and `PLACED` match source |
| Performance | p95/p99 & throughput under load | Lookup p95 ≤ 200 ms, p99 ≤ 500 ms |
| Stability | No recurrence, healthy resources | 30 minutes steady + batch job re-runs cleanly |
| Observability | Alerts/traces detect recurrence | Dashboards and runbooks updated |

**Thresholds are illustrative** and must fit your project's workload and SLOs. For a data-loss incident, 30 minutes of stability is never enough; require **full reconciliation and domain owner sign-off**.

## 17. Real-World Scenario A: Read API Slow After Release

**Context:** `GET /customers/{id}/orders` p95 jumps from 80 ms to 1,100 ms right after a Spring Data Neo4j release. The database stays online with no authentication errors.

### Observations

1. APM shows time concentrated in the repository call, not HTTP serialization.
2. Query logs show a new query returning the **`Customer` node and all `Order` entities** instead of a two-field DTO.
3. `PROFILE` shows `Expand(All)` from a high-degree customer across **50,000** `PLACED` edges; `Rows` and `DB Hits` spike.
4. `SHOW INDEXES` confirms the `Customer.customerId` index is still `ONLINE`; adding it again cannot fix downstream fan-out.

### Hypothesis / Remediation

The release switched from a DTO query with `ORDER BY ... LIMIT 20` to broad entity graph hydration. Roll back the endpoint or switch to `Neo4jClient`/Cypher returning **only the 20 needed orders**, bounding payload to the use case.

### Verification

- Verify the 20 returned orders match IDs and stable ordering.
- Returned `Rows`/bytes drop; API p95/p99 returns within SLO under matching traffic.
- Test customers with **0, 1, and 50,000 orders**.
- Confirm sibling endpoints relying on full entities were not unintentionally altered.

**Lesson:** “Index is online” and “database is healthy” do not rule out **query shape regressions**.

## 18. Real-World Scenario B: WRITE Times Out While READ Stays Healthy

**Context:** `POST /orders` frequently times out, yet list screens continue reading fine.

### Two Easily Confused Possibilities

**Possibility 1 — Cluster lost writer / quorum:**

- Driver reports routing or write-unavailable errors.
- `SHOW DATABASES` on the cluster shows no available writer or primaries lacking quorum.
- `SHOW TRANSACTIONS` shows no abnormal lock waits because requests may **never reach transaction execution**.

**Possibility 2 — Lock hotspot inside the database:**

- Writer remains available; some small `WRITE`s still succeed.
- Transactions writing the same `Inventory` or `Account` show rising `waitTime` and blocked status.
- Query logs/APM show requests stalling after entering the transaction.

### Differentiating Checks

1. Run **READ** and **WRITE canary** checks separately with valid privileges.
2. Inspect writer/quorum state and driver routing.
3. Inspect `SHOW TRANSACTIONS` for status, `waitTime`, `elapsedTime`, and queries.
4. Correlate disk, CPU, GC, pool pending, and write-job timelines.

### Remediation

- If **quorum is lost**, restore network/servers per cluster runbook; **never force a leader** by corrupting cluster state.
- If **lock contention**, shrink batches/concurrency, shorten transactions, and fix update ordering/hotspots; terminate only with approval.

### Verification

Synthetic `WRITE` commits cleanly, error/retry rates return to baseline, zero duplicate orders were created by timeouts/retries, and primaries/secondaries recover within SLOs.

**Lesson:** Two incidents sharing the symptom “write timeout” require completely opposite fixes.

## 19. Practice Lab: Building an Evidence Dossier and RCA Report

### Lab Context

A Java application has two use cases:

- `readCustomerOrders(customerId)` runs `MATCH (c)-[:PLACED]->(o)` and returns orders.
- `placeOrder(orderId, customerId)` runs multiple Cypher statements inside `executeWrite`.

Neo4j has constraints on `Customer.customerId` and `Order.orderId`; the practice database is `graph_lab`. The system simulates rising `READ` p95, occasional `WRITE` timeouts, and a new release deployed 10 minutes earlier.

### Step 1 — Write the Impact Summary

Fill in:

~~~text
Incident ID:
Environment/database:
Start time (UTC):
Affected operations:
Users/traffic affected:
Error messages + driver codes:
Last known good:
Recent changes:
Immediate data risk:
Incident owner:
~~~

Never log passwords, raw tokens, real customer IDs, or sensitive payloads in lab exercises.

### Step 2 — Gather Read-Only Evidence

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, statusMessage
RETURN name, currentStatus, statusMessage;
~~~

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent;
~~~

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, database, status, elapsedTime, waitTime
RETURN transactionId, database, status, elapsedTime, waitTime
ORDER BY elapsedTime DESC
LIMIT 20;
~~~

**Note which columns are supported by your lab version/edition.** If privileges block viewing other users' transactions, report that diagnostic limitation rather than granting admin rights to the app.

### Step 3 — Capture the Plan of a Slow Query

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.orderId
LIMIT 20;
~~~

On a small/lab dataset for a read-only query:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.orderId
LIMIT 20;
~~~

Record primary operators, `Rows`, `DB Hits`, whether an index seek occurred, and any large sorts or fan-out.

### Step 4 — Formulate Three Hypotheses

Example:

| ID | Hypothesis | Differentiating test |
| --- | --- | --- |
| H1 | `Customer.customerId` index is `FAILED` | `SHOW INDEXES` + `PROFILE` showing scan |
| H2 | New release hydrates overly broad entity graphs | Compare generated Cypher/DTO, `Rows`, and response bytes |
| H3 | Batch `WRITE` holds locks blocking `READ`/`WRITE` | `SHOW TRANSACTIONS` `waitTime` and import schedule |

Explicitly state **what evidence would falsify** each hypothesis. Never try to “force-prove” H1 simply because it seems easy to fix.

### Step 5 — Simulate One Low-Risk Mitigation

In the lab environment, use synthetic data and measurable load. For instance:

- Replace the full-entity query with a DTO query carrying an explicit `LIMIT`; or
- Reduce the write job's batch size while preserving business data.

Apply **one change at a time** and re-measure. Never drop indexes, kill random transactions, or restart clusters to fake a “quick win”.

### Step 6 — Verify Through the Gates

Build a table:

| Criterion | Before | After | PASS/FAIL |
| --- | --- | --- | --- |
| Read probe | ... | ... | ... |
| Write transaction commit | ... | ... | ... |
| Order/relationship counts on test IDs | ... | ... | ... |
| p95/p99 under comparable load | ... | ... | ... |
| `Rows`/`DB Hits` | ... | ... | ... |
| Lock waits / pool pending | ... | ... | ... |
| Alerts stable after job cycle | ... | ... | ... |

### Step 7 — Write a Concise Postmortem

~~~text
What happened:
User impact and duration:
Root cause (confirmed) and evidence:
Contributing conditions:
Why alerts/detection were delayed:
Mitigation (time, owner, risk):
Permanent fix:
Verification (data + performance + availability):
Preventive actions (owner, deadline):
Open risks and follow-up:
~~~

**If root cause remains unconfirmed**, state “unconfirmed” alongside open hypotheses. A useful postmortem never fakes certainty.

### Self-Check Questions

**1. Is a passing `verifyConnectivity()` enough to conclude the database is healthy?** No. It does not prove the target database is online, `READ`/`WRITE` privileges are valid, or graph traversals meet SLOs.

**2. Why collect `SHOW TRANSACTIONS` before restarting?** Because running/blocked state, `waitTime`, and transaction IDs change or vanish on restart.

**3. Is `PROFILE` on a write query as safe as `EXPLAIN`?** No. `PROFILE` actually executes the statement; write queries will mutate data.

**4. When `waitTime` spikes, should you immediately create a new index?** No. First separate lock contention from scans/indexes via transaction states and plans, then evaluate solution costs and risks.

**5. If an app times out near commit, can retrying the same request create duplicates?** Yes, if business IDs, idempotency, or constraints are missing. Verify commit status by business key before retrying.

**6. A cluster has 3 primaries; `READ` works while `WRITE` fails. Can you conclude the database lost data?** No. Check writer/quorum, replica states, and network faults; `WRITE` unavailability does not mean the store was deleted.

**7. After a fix, p95 returns to normal, yet 50 orders are missing relationships. Can you close the incident?** No. The **data correctness** gate failed; reconcile and run controlled repairs first.

**8. Why not run `neo4j-admin server report all` for every incident?** Because it can pull huge or sensitive data (heap, transaction logs, configs), stressing I/O and disk. Pick only needed classifiers with proper redaction and permissions.

## 20. Neo4j Troubleshooting Checklist

- [ ] Identified **impact, READ/WRITE scope, database, UTC timestamps, severity, and coordinator**.
- [ ] Separated symptoms, hypotheses, evidence, and confirmed root causes.
- [ ] Recorded **recent changes**: releases, indexes, configs, plugins, backups, imports, GDS, network/TLS.
- [ ] Collected **before–during–after** logs/metrics with synchronized timestamps and protected sensitive data.
- [ ] Captured `SHOW DATABASES`, `SHOW INDEXES`, `SHOW CONSTRAINTS`, and `SHOW TRANSACTIONS` where permissions/versions support them.
- [ ] For clusters, verified writer/quorum, database allocations, lag, and separate READ/WRITE routing.
- [ ] For slow queries, ran `EXPLAIN` first, `PROFILE` only when safe; compared `Rows`, `DB Hits`, index states, and fan-out.
- [ ] Correlated API p95/p99 with pool pending, network, retries, and Neo4j metrics rather than blaming the DB immediately.
- [ ] Checked heap/GC, page cache, free disk/I/O, container restarts/OOMs, and transaction logs.
- [ ] For Java Driver errors, read exception class, Neo4j/GQL status, database name, URI/TLS/auth, and causal bookmarks.
- [ ] For data errors, reconciled by **business IDs and relationships**, not node counts alone.
- [ ] Generated **selective** support reports respecting disk, access, and redaction; never collected `all` blindly.
- [ ] Prioritized **low-risk** mitigations, each with an owner, expected outcome, and rollback plan.
- [ ] Never deleted stores/logs, dropped constraints, mass-terminated transactions, or restarted all primaries by reflex.
- [ ] Verified **availability, data correctness, performance, and stability** post-fix with hard evidence.
- [ ] Confirmed zero **duplicate retry writes**, CDC backlogs, or stale post-restore data.
- [ ] Closed the incident only after meeting SLOs and business invariants with sign-off and preventive actions.
- [ ] Saved the timeline, root cause, lessons learned, runbook updates, and alert improvements.

## References

- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/)
- [Neo4j Operations Manual — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Neo4j Operations Manual — Generate a server report](https://neo4j.com/docs/operations-manual/current/monitoring/neo4j-admin-report/)
- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Cypher Manual — SHOW INDEXES](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Connect](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Status Codes — Server errors](https://neo4j.com/docs/status-codes/current/errors/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)

**Conclusion:** Effective Neo4j troubleshooting starts with **verifiable evidence**: scope and timeline, logs/metrics, running transactions, database/index states, query plans, Java Driver errors, and property-graph reconciliation. From there, formulate falsifiable hypotheses, choose low-risk mitigations, and verify fixes across **four independent gates: availability, data correctness, performance, and stability**. Only when every gate meets business criteria can an incident be declared resolved rather than merely having its error messages temporarily silenced.
