# DriverTimeout/AllNodesFailed and Inspecting Per-Node Errors

> **Chapter:** Troubleshooting  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. When diagnosing Java applications, you must combine **partition keys, query-driven table design, replication, consistency levels, CQL, compaction, repair, replica health**, and driver connectivity.  
> **Focus:** Distinguishing **`DriverTimeoutException`**, **`AllNodesFailedException`**, and Cassandra server timeouts/failures; reading **per-node causes across attempted nodes**, and choosing safe remediations.

## 1. Opening Scenario: Two Similar-Looking Exceptions Pointing to Different Problems

A Spring Boot endpoint queries Cassandra via Java Driver 4.x. During peak hours, two errors appear in monitoring:

~~~text
com.datastax.oss.driver.api.core.DriverTimeoutException:
  Query timed out after PT2S

com.datastax.oss.driver.api.core.AllNodesFailedException:
  Could not reach any contact point ...
~~~

A hasty reading might conclude: "Cassandra is dead, raise the timeout and retry five times." That conclusion is **unsupported** and often makes the incident worse.

- **`DriverTimeoutException`** indicates driver-side execution exceeded the configured request budget. It **does not prove** whether the coordinator processed the query or whether replicas applied a mutation.
- **`AllNodesFailedException`** indicates the driver could not complete the operation across any of the attempted nodes/endpoints. One aggregate exception can wrap **distinct per-node causes**: connection refused on A, TLS handshake failure on B, authentication failure on C, etc.
- **`ReadTimeoutException`/`WriteTimeoutException`** returned by **the Cassandra server** mean insufficient replica responses arrived for the operation's CL within the server timeout. They differ from a driver-only timeout.

The goal is more than catching the right class name. You must identify **which layer failed, whether it happened before or after reaching a coordinator, which nodes were tried, and whether write outcomes remain uncertain**.

### Lesson Objectives

After completing this lesson, you will be able to:

1. Classify **driver-side timeouts**, **server-side timeouts/failures**, **`AllNodesFailed`**, and configuration errors.
2. Use **`getAllErrors()`** to inspect recorded causes for **each attempted node**, rather than reading only the summary message.
3. Recognize DNS/contact points, TLS/auth, local datacenter, network, connection pool, and overload issues from symptoms.
4. Connect **RF/DC, `LOCAL_QUORUM`, partition keys, hot partitions, and compaction/repair** to timeouts.
5. Write Java code that handles sync/async exceptions, unwraps wrappers cleanly, and logs diagnostics without leaking secrets.
6. Apply a **decision tree + runbook** with PAUSE/STOP/ESCALATE gates.
7. Evaluate retries using **idempotency, deadlines, backoff, and cluster headroom** rather than retrying blindly.
8. Test failure modes in staging and recognize inconclusive results lacking sufficient evidence.

> **Versions:** Code targets **Apache Cassandra Java Driver 4.x**, package **`com.datastax.oss.driver.api`**; exact behavior, inner exception classes, and configuration options vary by driver, Cassandra, and JDK version. In real deployments, verify class signatures and configuration references for your **pinned version**. Never inject faults in production just to practice this lesson.

## 2. Which Layers Does a Java Request Traverse?

~~~mermaid
flowchart TD
    A["HTTP/gRPC caller, end-to-end deadline"] --> B["Java service: admission/queue/retry"]
    B --> C["Java Driver: session, routing, connection pool"]
    C --> D{"Eligible node and ready channel?"}
    D -->|No| E["Per-node connection/transport failures"]
    E --> F["AllNodesFailed or other driver error"]
    D -->|Yes| G["Coordinator receives CQL"]
    G --> H["Replicas by partition key + RF/DC"]
    H --> I{"Enough responses per consistency level?"}
    I -->|No| J["Server Read/WriteTimeout, Failure, Unavailable"]
    I -->|Yes| K["CQL response back to driver"]
    G --> L["Network/queue/driver deadline"]
    K --> L
    L --> M{"Client receives response in time?"}
    M -->|No| N["DriverTimeout or transport/caller timeout"]
    M -->|Yes| O["Result/Row returned to app"]
~~~

This diagram is a **reasoning model**, not a guarantee that every exception follows only one path. The driver may try multiple coordinators, retries, or speculative executions per policy; a request can time out at the client while an earlier attempt still runs on the server.

### 2.1. Coordinator Selection Differs from Replica Ownership

Cassandra partitions data by **partition key**; the token map and replication strategy determine which replicas own that data. Java Driver typically uses **token-aware routing** to favor an owning node when a statement carries a valid routing key, yet keep roles separate:

- **Contact point:** initial address used by the driver to bootstrap and discover the cluster, not an exhaustive list of all replicas.
- **Coordinator:** the node receiving the client's CQL request and coordinating relevant replicas.
- **Replica:** a node storing partition data per RF, DC, and token ownership.
- **Local datacenter:** the DC preferred/used by the driver per policy and configuration.
- **Query plan / attempted nodes:** the subset of nodes/endpoints the driver actually tried for an operation; **not necessarily every node in the cluster**.

Therefore, upon seeing **`AllNodesFailed`**, inspect **what each attempted node failed on**, rather than assuming "every Cassandra node is dead".

### 2.2. Nodes Can Be `UN` While Requests Time Out

A node showing **`UN` (Up/Normal)** in `nodetool status` can still suffer from:

- High disk latency or near-full disks.
- Compaction, repair, or streaming saturating I/O.
- JVM GC pauses or off-heap/native memory pressure.
- Connection pool contention and growing pending queues.
- Hot partitions or excessive tombstones.
- Packet loss or cross-DC latency.
- Missing quorum before deadlines despite nodes being "Up".

Hence never treat **`nodetool status`** as sufficient proof for every driver failure.

## 3. Exception Map: Which Layer Detected the Failure?

| Category | Typical Class / Signal | Core Meaning | Do Not Infer |
|---|---|---|---|
| **Driver timeout** | **`DriverTimeoutException`** | Driver-side request budget exceeded | Cassandra never ran the mutation |
| **Driver exhausted attempts** | **`AllNodesFailedException`** | No attempt succeeded across tried nodes; details in **`getAllErrors()`** | Entire cluster is definitely DOWN |
| **Server read timeout** | **`ReadTimeoutException`** | Insufficient read responses for CL within server timeout | Replicas lack the data |
| **Server write timeout** | **`WriteTimeoutException`** | Insufficient write ACKs for CL within server timeout | No replica wrote the data |
| **Server read/write failure** | **`ReadFailureException`**, **`WriteFailureException`** | Explicit server-side execution failure | Single Java network cause |
| **Server unavailable** | **`UnavailableException`** | Insufficient eligible replicas for CL upfront | Lowering CL is safe or right |
| **Server overload** | **`OverloadedException`** | Node reporting processing overload | Immediate retries will help recovery |
| **Session/transport** | Connection closed/refused, TLS/auth/handshake | Connection path unready or rejected | Every node shares the same error |
| **Invalid query/schema** | Syntax/invalid query, codec, unknown keyspace/table/column | CQL/schema/driver mapping needs fixing | Blind retries will fix it |

**Server-side classes** normally reside in **`com.datastax.oss.driver.api.core.servererrors`**. Transport errors often appear as **inner causes inside `AllNodesFailed`**, not necessarily as the top-level exception.

### 3.1. `DriverTimeoutException` Does Not Equal `ReadTimeoutException`

**Driver timeout** is an observation by the **client driver** that a request did not finish within its client budget. It can stem from driver/pool queueing, networking, a busy coordinator, or slow server execution. From that exception alone, the driver cannot determine **write outcome**.

**Server `ReadTimeout`** is returned by the **coordinator** because replica/CL read conditions were not met before the server timeout. It exposes server-side operation and response-count details, without directly diagnosing client-side queues.

**Server `WriteTimeout`** is even more sensitive: one or more replicas may have applied the mutation before timing out. Retrying writes risks duplicate side effects unless the operation is idempotent.

### 3.2. An Exception May Be Wrapped

With async APIs or test Futures, top-level logs sometimes show only:

~~~text
java.util.concurrent.CompletionException
  caused by com.datastax.oss.driver.api.core.DriverTimeoutException

java.util.concurrent.ExecutionException
  caused by com.datastax.oss.driver.api.core.AllNodesFailedException
~~~

Always **unwrap `CompletionException`/`ExecutionException`** before classifying. Still, keep the full cause chain and **suppressed exceptions** in restricted internal incident logs; deep causes often hold decisive evidence about TLS, DNS, networking, or connection pools.

## 4. `AllNodesFailedException`: Do Not Stop at the First Message Line

An `AllNodesFailed` message typically **summarizes** errors for only the first couple of nodes. Java Driver 4.x exposes **`getAllErrors()`** to inspect details for every node the request tried.

**Hypothetical** example:

~~~text
AllNodesFailedException: cannot reach a usable node
  node cassandra-a: java.net.ConnectException (connection refused)
  node cassandra-b: javax.net.ssl.SSLHandshakeException
  node cassandra-c: connection initialization timeout
~~~

**Analysis:**

- **A — Connection refused:** port 9042 not listening, network policy, NAT/service mapping, or process not accepting connections. Do not assume node is DOWN in gossip.
- **B — `SSLHandshakeException`:** truststore, certificate, hostname, or protocol mismatch—raising CQL request timeout will not fix it.
- **C — initialization timeout:** slow path, incomplete auth/TLS handshake or driver init, or overloaded environment; measure at the connection-establishment layer.

A single "aggregate failure" can combine **multiple independent causes**, and a single node may list **multiple Throwables across attempts or channels**. When calling `getAllErrors()`, never inspect only the first cause.

### 4.1. The Map Is Not a List of Every Node in the Cluster

Proper interpretation:

- Map keys represent nodes/endpoints on which the driver **recorded an error** for that operation.
- Absence of a node **does not prove** that node is healthy or was tried.
- Behavior differs when failing during **session initialization / contact point discovery** vs. after full metadata is loaded.
- If a cause list is empty or node metadata is incomplete, diagnostic code must handle nulls defensively.
- Entry/list iteration order is **diagnostic data**, not a stable contract for business logic.

**Never build custom retry loops by iterating the map and picking coordinators manually.** The driver already manages load balancing, node health, pooling, and retry policies. This map is for **diagnostics**, not application-level routing overrides.

## 5. Reading Per-Node Causes from `AllNodesFailed` in Java

The snippet below shows how to inspect **`getAllErrors()`** in Java Driver 4.x, logging error classes and node identifiers without exposing payloads. In production, use structured loggers, normalize internal hostnames, and cap log volume.

~~~java
import java.util.List;
import java.util.Map;

import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;

public final class AllNodesFailureInspector {
    private AllNodesFailureInspector() {}

    public static void inspect(AllNodesFailedException exception) {
        Map<Node, List<Throwable>> perNode =
            exception.getAllErrors();

        if (perNode == null || perNode.isEmpty()) {
            System.err.println(
                "AllNodesFailed: no per-node details available");
            return;
        }

        for (Map.Entry<Node, List<Throwable>> entry
                : perNode.entrySet()) {
            Node node = entry.getKey();
            List<Throwable> causes = entry.getValue();

            String nodeLabel = node == null
                ? "unknown-discovery-node"
                : String.valueOf(node.getEndPoint());

            if (causes == null || causes.isEmpty()) {
                System.err.println(
                    nodeLabel + " -> no nested causes reported");
                continue;
            }

            for (int index = 0; index < causes.size(); index++) {
                Throwable cause = causes.get(index);
                String type = cause == null
                    ? "unknown"
                    : cause.getClass().getName();

                System.err.printf(
                    "attemptedNode=%s causeIndex=%d causeType=%s%n",
                    nodeLabel, index, type);

                // In incidents: add sanitized cause chain,
                // event time, request ID, exception fingerprint.
            }
        }
    }
}
~~~

**Key points in this snippet:**

1. **`getAllErrors()`** is where multi-node and multi-attempt details live—not the top-level message.
2. **`Node.getEndPoint()`** is an infrastructure locator; hosts/IPs can be sensitive. In multi-tenant environments, map to controlled **node aliases** rather than leaking addresses in HTTP responses.
3. Log the class of **every Throwable**, without blindly printing full exception messages that might leak user IDs, keyspaces, hosts, or secrets.
4. When metadata is partial or a cause list is empty, ensure **logging itself never throws `NullPointerException`** and hides the original failure.
5. `System.err` is for lab readability; production should use rate-limited structured logging, correlation IDs, and centralized tracing.
6. During session init failures, known nodes may be fewer than the full cluster; also inspect contact points, DNS, and TLS config.

### 5.1. Walk the Full Cause Chain Instead of Only the Outer Class

A per-node cause often looks like:

~~~text
ConnectionInitException
  caused by SSLHandshakeException
    caused by ValidatorException
      caused by PKIX path building failed
~~~

If a logger records only **`ConnectionInitException`**, operators may mistake it for a pool or timeout problem when the true cause is **an untrusted server certificate in the truststore**.

Depth-bounded helper to prevent cycles and log floods:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class CauseSummary {
    private CauseSummary() {}

    public static String classChain(Throwable root) {
        if (root == null) {
            return "unknown";
        }

        Set<Throwable> seen = Collections.newSetFromMap(
            new IdentityHashMap<>());
        StringBuilder out = new StringBuilder();
        Throwable current = root;
        int depth = 0;

        while (current != null
                && depth < 8
                && seen.add(current)) {
            if (depth > 0) {
                out.append(" <- ");
            }
            out.append(current.getClass().getSimpleName());
            current = current.getCause();
            depth++;
        }

        if (current != null) {
            out.append(" <- ...");
        }
        return out.toString();
    }
}
~~~

This logs **only the class chain**, avoiding raw messages or stack traces with sensitive details. Keep full forensic stack traces inside access-controlled internal logs. Cap emitted nodes/causes during high-volume incidents while preserving summary counts so rare errors aren't hidden.

## 6. Inspecting Per-Node Causes: Investigation Matrix

Once **`getAllErrors()`** is extracted, group causes by **connection and execution stage** instead of lumping everything into "Cassandra unavailable".

| Per-Node Cause / Signal | Check First | Avoid Doing |
|---|---|---|
| **`UnknownHostException` / DNS resolution failed** | FQDN, DNS from the exact Java pod/VM, service discovery, split-horizon DNS, DNS TTL | Raising request timeout and blaming slow cluster |
| **`ConnectException: Connection refused`** | IP/port 9042, CQL listener, firewall/network policy, sidecar/service, node process | Checking `nodetool status` on only one other node |
| **Connect timeout / unreachable / no route** | Network routes/ACLs, DNS, private/public endpoints, NAT, security groups, source IP | Assuming all replicas are DOWN |
| **`SSLHandshakeException`** | Truststore, certificate chain/SAN/expiry, mutual TLS, TLS protocol, hostname verification | Disabling TLS/verification in prod as a "quick fix" |
| **`AuthenticationException` / bad credentials** | Secret rotation, username/password, authenticator, credential source, role state | Retrying infinitely with the same bad secret |
| **Authorization / permission error** | Does the role hold grants on that keyspace/table/query? | Escalating the runtime role to superuser |
| **Connection closed/reset** | Node restart, proxy timeout, keepalive, network reset, idle connection handling | Assuming the server never ran the mutation |
| **Connection initialization failure** | Handshake, protocol/version, TLS/auth, init-phase timeouts | Raising CQL request timeout while ignoring inner causes |
| **Busy / connection pool saturated** | In-flight/channels, pool sizing, app concurrency, p99, GC, coordinator latency | Opening unlimited connections or retry storms |
| **Request rejected / overloaded** | Server CPU/disk/GC, pending threads, hot partitions, maintenance | Retrying immediately or raising max attempts |
| **Invalid query / unknown keyspace** | Schema migration, keyspace name, RF/DC, mapping, CQL | Swapping contact points randomly |
| **Mixed causes across multiple nodes** | Inspect each node and look for a common denominator: DNS/TLS/port/secret | Treating the first error as the sole cause |

**Exception names in this table are illustrative signals**, not an exhaustive list of every Java Driver 4.x class. Underlying errors often sit deep inside **`Throwable.getCause()`**, wrapped differently by driver, Netty, or JDK layers. Record the **actual class chain** and version rather than writing brittle message-substring rules.

### 6.1. Identical Errors Across All Nodes Point to Shared Config

If every contact point fails with **`SSLHandshakeException`**, inspect the client truststore/certificates/protocols or shared TLS config. If some nodes fail TLS while others fail `ConnectException`, you may have **multiple overlapping defects** across a certificate/network rollout.

If only one node throws connection closed while all other nodes serve cleanly, inspect that specific node's disk/GC/restarts/network rather than changing cluster-wide settings.

### 6.2. Contact Points vs. Discovered Nodes

When **`CqlSession.builder().build()`** fails because no contact point connects, `AllNodesFailed` occurs **before the driver discovers the full topology**. Never use that map to claim every replica in the ring was tried.

Conversely, once a session initializes, the driver tracks multi-node metadata; query plans reflect DC, load balancing, and token awareness, so attempted nodes may still be **a subset** of the cluster. To know which nodes were selected, combine:

- Driver execution logs/metrics and query plan info where supported.
- Session topology metadata and node health.
- App request IDs, query shapes, and partition-key classes.
- Timestamp-aligned coordinator logs and server metrics.
- `local-datacenter`, contact points, and pool configuration.

## 7. Separating Timeout and Deadline Layers

Never bump a random timeout just because a message says "timed out".

| Layer | Concept | Symptom | Measure |
|---|---|---|---|
| **Caller** | HTTP/gRPC request deadline | Caller aborts while Java service is still working | Elapsed since ingress, queue wait |
| **Application admission** | Queue/semaphore wait | Budget exhausted before CQL even leaves | Active permits, rejections, wait time |
| **Driver request** | Driver execution timeout | **`DriverTimeoutException`** or driver-side error | Elapsed, retries/speculation, pool state |
| **Connection establishment** | DNS/TCP/TLS/auth handshake | Connection-init/transport cause; often inside `AllNodesFailed` | Per-node connect attempts, handshake time |
| **Server read/write** | Coordinator/replica deadline | **`ReadTimeout`/`WriteTimeout`** | CL, required/received ACKs, node latency |
| **Async paging** | First page vs. all pages | Page 1 OK, page N fails or exceeds deadline | Page count, full-result duration |
| **Downstream** | Persist/broker/cache post-query | DB OK yet API still times out | Sink latency and queues |

Illustrative Java Driver 4.x config:

~~~hocon
datastax-java-driver {
  basic {
    request {
      timeout = 2 seconds
      consistency = LOCAL_QUORUM
    }
  }
}
~~~

**This is an example**, not a universal default. Connect timeouts, TLS, initialization, and requests each have version-specific options and policies. Check the **effective runtime config**, not just a local `application.conf`, since execution profiles or overrides may apply.

### 7.1. End-to-End Deadline Illustration

~~~text
HTTP caller deadline:                     2,000 ms
Java admission wait:                        300 ms
Node selection / pool wait:                 250 ms
Cassandra execution until failure:        1,100 ms
Time already spent:                       1,650 ms
Remaining before deadline:                  350 ms

Planned backoff:                            250 ms
Remaining budget for attempt + reply:       100 ms
~~~

Here, **retrying with a 1-second request timeout** cannot finish inside the caller's 2-second deadline. Even a technically idempotent retry is counterproductive if it adds load after the caller will already have timed out.

### 7.2. `DriverTimeout` Does Not Know Whether a Mutation Applied

For **`INSERT`**, **`UPDATE`**, **`DELETE`**, **`LWT`**, or counters, when the driver times out:

- The request may still be waiting in a pool, never have reached the coordinator, or have reached the server and executed.
- The coordinator may have forwarded writes to some replicas.
- The reply may have dropped on the return network path.
- The caller may have canceled while the server kept executing.

**Write outcome may be `UNKNOWN`.** Never treat a driver timeout as permission to mint a fresh request ID or re-increment a counter.

### 7.3. First-Page Timeout Differs from Full-Result Timeout

**`executeAsync`** returns an **`AsyncResultSet`** for the first page. Multi-page queries fetch subsequent pages via **`fetchNextPage()`**. Reading 10 pages spans **the entire pipeline duration**, not just the 2-second timeout of page one.

Diagnostic questions:

- Did the timeout happen on **page one** or page N?
- Were earlier pages already streamed downstream?
- Did downstream emit side effects from earlier pages?
- Does the pipeline enforce a total deadline, pagination state, and backpressure/demand limits?
- Could the service return **partial results** falsely labeled as complete?

Never restart a multi-page query from page one if earlier pages already triggered downstream side effects without idempotency or checkpoints.

## 8. How RF/DC, Consistency, and Data Model Shape Errors

### 8.1. At Identical RF = 3, Errors Depend on CL

Assume a keyspace uses **`NetworkTopologyStrategy`** with **`RF = 3`** in `dc1`:

| Condition | `LOCAL_ONE` | `LOCAL_QUORUM` |
|---|---|---|
| All 3 replicas healthy and fast | Typically completes quickly after one reply | Requires local quorum (typically 2/3) |
| One replica slow | Minimal impact if others respond fast | Still succeeds if two replicas reply fast |
| Two replicas slow/unreachable | Can succeed while one replica serves | Likely timeouts or `Unavailable` depending on state |
| Nodes UP yet stalled on disk/GC | Can time out | Can time out despite sufficient RF on paper |

This is a **simplified model**; actual read/write behavior, speculative retries, and node failures must be verified against live telemetry. API CL is a **consistency contract**, not a performance knob to turn down mid-incident.

### 8.2. Queries Missing Full Partition Keys Trigger Other Failures

Assume table:

~~~sql
-- Execute only on a lab with three replicas in dc1.
CREATE KEYSPACE IF NOT EXISTS diag_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS diag_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

Valid query matching the access pattern:

~~~sql
SELECT happened_at, event_id, payload
FROM diag_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;
~~~

**Never add `ALLOW FILTERING`** so a keyless query "runs" and then raise timeouts to mask slowness. Build query-driven tables, evaluated indexes (checked for version/cardinality), or bucketing/sharding. Huge scans, tombstone-heavy partitions, or oversized collections stall coordinators/replicas and surface as `DriverTimeout` or `ReadTimeout`.

### 8.3. Hot Partitions Can Cause Errors on Just a Few Nodes

If traffic concentrates heavily on **one `tenant_id` + `event_day`**, only the replicas owning that token range saturate while the rest of the cluster stays idle. `AllNodesFailed` or `DriverTimeout` may show errors concentrated on specific coordinators/query shapes; measure:

- Request rate by **query class / hot key group**.
- Partition size, row counts, tombstones, page size, and SSTable counts.
- Node/token ownership, disk, GC, and pending compactions.
- CL and coordinator routing.
- Retry amplification against already-slow hot keys.

Fixes involve **bucketing, sharding, or query redesign**—not endlessly enlarging pools or timeouts.

### 8.4. Interference from Repair, Compaction, Bootstrap, and Backups

Background operations contend with CQL for **disk I/O, network, CPU, and memory**:

- **Repair** reads/compares SSTables and streams differences across replicas.
- **Compaction** reads/writes SSTables and purges tombstones.
- **Bootstrap/streaming** transfers SSTables during topology changes.
- **Backup copies** read SSTables, compress/encrypt, and upload off-node.

If timeouts spike alongside maintenance, correlate metric timelines instead of guessing causality. **Never trigger `repair` to "fix `DriverTimeout`"**—repair adds I/O pressure and cannot fix DNS, TLS, or connection pools.

## 9. First 5-Minute Triage Runbook

~~~mermaid
flowchart TD
    A["Java operation fails"] --> B{"DriverTimeout or AllNodesFailed?"}
    B -->|DriverTimeout| C["Measure deadline, admission/pool, coordinator latency"]
    B -->|AllNodesFailed| D["getAllErrors(): per-node causes"]
    B -->|Server timeout/failure| E["CL, RF/DC, required/received, replica health"]
    D --> F{"Do nodes share the same cause?"}
    F -->|DNS/TLS/Auth/Port| G["Controlled fix to config/secret/network"]
    F -->|Divergent/transport| H["Inspect per-node network, pool, disk, JVM"]
    C --> I["Compare caller/driver/server timeouts and retries"]
    E --> J["Compare coordinator/replicas, partition key, load"]
    G --> K["Verify on staging/canary"]
    H --> K
    I --> K
    J --> K
    K --> L{"Correctness + SLO met?"}
    L -->|Not yet| M["PAUSE/ESCALATE; never retry blindly"]
    L -->|Yes| N["Gradually restore traffic, monitor"]
~~~

### 9.1. First: Establish Scope

1. **When** did it start—after a deploy, cert rotation, maintenance, or traffic surge?
2. How many **logical requests** failed vs. retries/physical attempts?
3. Isolated to **one service/pod/region/DC** or affecting all clients?
4. Failing during **`CqlSession` startup** or during CQL execution?
5. Failing only on **one query shape/tenant** or across all queries?
6. Are sync/async failures wrapped in **`CompletionException`**?
7. Do server logs/metrics show corresponding `ReadTimeout`, `WriteTimeout`, `Overloaded`, or replica faults?
8. Are there writes with **unknown outcomes** needing reconciliation and protection?

### 9.2. If Failing at `CqlSession` Startup

Focus on:

- Contact points, DNS, CQL port 9042, service/network policies.
- Exact **`local-datacenter`** matching driver requirements.
- TLS truststores, certificate chains, hostname verification, mTLS.
- Auth secrets/roles/passwords and how they are injected.
- Protocol version/driver compatibility, proxy/cloud bundle requirements.
- Connection initialization and node logs.

**Do not tune CQL queries or page sizes** while the session cannot even connect to the cluster.

### 9.3. If Failing After the Session Is Running

Focus on:

- Query shapes, partition keys, and routing keys.
- Driver pools, in-flight counts, instance counts, and connection concurrency.
- Coordinator/replica health, RF/CL, and DC routing.
- Compaction, repair, backups, disk, GC, and network.
- Request timeouts, HTTP deadlines, and retry policies.
- Whether a single node is failing inside `getAllErrors()`.

### 9.4. Separating Action Branches

| Primary Observation | Action Direction |
|---|---|
| All node causes show **TLS certificate expired** | Rotate certs/truststores cleanly; verify rollout; never weaken security |
| One node refuses connections while others are reachable | Check listener/network/process on that node; route traffic via healthy nodes per policy |
| Most errors show pool saturation | Shed/throttle incoming concurrency, measure latency and pool/connections; avoid retry storms |
| Server `ReadTimeout` spikes on hot partitions | Diagnose SSTables, tombstones, partition/data model, and CL |
| Server `Unavailable` after node DOWN | Restore quorum/topology; never downgrade CL outside contract |
| `DriverTimeout` while server metrics look normal | Inspect client queues, CPU, GC, network, connections, and timeout layers |
| Recent schema or driver upgrade | Check version matrix, schema agreement, contact points, and protocol/codecs |
| `WriteTimeout` on payments or orders | Record `UNKNOWN`, reconcile by business request ID, never mint duplicate writes |

## 10. Java Driver 4.x: Classifying Sync and Async Failures

A clean diagnostic helper should: **unwrap** `CompletionException`/`ExecutionException`, classify `DriverTimeout`/`AllNodesFailed`/server errors, inspect **`getAllErrors()`** on `AllNodesFailed`, preserve unknown write outcomes, and log **query shape / correlation IDs** instead of sensitive bind data.

### 10.1. Cause Classifier

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;
import com.datastax.oss.driver.api.core.servererrors.ReadFailureException;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

public final class CassandraFailureClassifier {
    private CassandraFailureClassifier() {}

    public enum Kind {
        ALL_NODES_FAILED, DRIVER_TIMEOUT,
        SERVER_READ_TIMEOUT, SERVER_WRITE_TIMEOUT,
        SERVER_READ_FAILURE, SERVER_WRITE_FAILURE,
        SERVER_UNAVAILABLE, SERVER_OVERLOADED, OTHER
    }

    public static Throwable unwrap(Throwable t) {
        while ((t instanceof CompletionException
                || t instanceof ExecutionException)
                && t.getCause() != null) {
            t = t.getCause();
        }
        return t;
    }

    public static Kind classify(Throwable error) {
        Throwable cause = unwrap(error);
        if (cause instanceof AllNodesFailedException) {
            return Kind.ALL_NODES_FAILED;
        }
        if (cause instanceof DriverTimeoutException) {
            return Kind.DRIVER_TIMEOUT;
        }
        if (cause instanceof ReadTimeoutException) {
            return Kind.SERVER_READ_TIMEOUT;
        }
        if (cause instanceof WriteTimeoutException) {
            return Kind.SERVER_WRITE_TIMEOUT;
        }
        if (cause instanceof ReadFailureException) {
            return Kind.SERVER_READ_FAILURE;
        }
        if (cause instanceof WriteFailureException) {
            return Kind.SERVER_WRITE_FAILURE;
        }
        if (cause instanceof UnavailableException) {
            return Kind.SERVER_UNAVAILABLE;
        }
        if (cause instanceof OverloadedException) {
            return Kind.SERVER_OVERLOADED;
        }
        return Kind.OTHER;
    }

    public static void diagnose(Throwable error) {
        Throwable root = unwrap(error);
        System.err.println("failureKind=" + classify(root));
        if (root instanceof AllNodesFailedException) {
            AllNodesFailureInspector.inspect(
                (AllNodesFailedException) root);
        }
        System.err.println(
            "causeClasses=" + CauseSummary.classChain(root));
    }
}
~~~

This snippet uses standard Java Driver 4.x types. When pinning a dependency, **compile** and verify exact package/class names. Other errors (auth, invalid query, codec, connection, cancellation) fall under `OTHER`; real services should extend the taxonomy with explicit classes and cause chains. Never drive a retry policy solely from this summary enum.

### 10.2. Synchronous: Classify Without Swallowing

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class ReadDiagnostics {
    private final CqlSession session;
    private final PreparedStatement select;

    public ReadDiagnostics(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT happened_at, event_id, payload " +
            "FROM diag_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? LIMIT ?");
    }

    public ResultSet read(UUID tenantId, LocalDate day) {
        BoundStatement statement = select
            .bind(tenantId, day, 20)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        try {
            return session.execute(statement);
        } catch (RuntimeException error) {
            CassandraFailureClassifier.diagnose(error);
            throw error;
        }
    }
}
~~~

Reuse **sessions and prepared statements** across the service lifecycle—never create a new `CqlSession` per HTTP request. The sample assumes TLS, auth, contact points, and local DC are properly configured; never log real `tenantId` or payloads.

### 10.3. Async: Never Turn Timeouts into Empty Results

~~~java
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class AsyncReadDiagnostics {
    private final CqlSession session;
    private final PreparedStatement select;

    public AsyncReadDiagnostics(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT event_id, payload " +
            "FROM diag_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? LIMIT ?");
    }

    public CompletionStage<AsyncResultSet> read(
            UUID tenantId, LocalDate day) {
        BoundStatement query = select
            .bind(tenantId, day, 50)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        return session.executeAsync(query)
            .whenComplete((page, error) -> {
                if (error != null) {
                    CassandraFailureClassifier.diagnose(error);
                }
            });
    }
}
~~~

**`whenComplete`** only observes; failures continue propagating down the stage. Avoid:

~~~java
// WRONG: caller interprets null as no data found.
return session.executeAsync(query)
    .exceptionally(error -> null);
~~~

For multi-page queries, `executeAsync` returns **only page one**; failures during **`fetchNextPage()`** must be tracked with page index and total pipeline timing. Never measure only first-page latency and assume all data was read.

### 10.4. Deadline Profiles by Workload Class

- Interactive point reads: end-to-end deadline from the HTTP caller covering admission, driver, and serialization.
- Paging queries: total deadline plus downstream demand control; never reset a fresh timer per page while promising an end-to-end SLA.
- LWT: budget for serial consensus and CAS contention; track both regular and serial CLs.
- DML writes: handle **`UNKNOWN`** after timeouts before retrying.
- Background jobs: split into checkpointed units rather than holding HTTP futures for hours.
- Migrations/bootstrap/backups: manage via dedicated runbooks and monitoring, not by bumping API timeouts.

## 11. Metrics and Inspection Commands to Prove Root Cause

### 11.1. Read-Only Commands

On an authorized node, verify exact syntax for your Cassandra version:

~~~bash
# Node states and DC/rack/tokens.
nodetool status

# Node metadata and heap/uptime.
nodetool info

# Pending/dropped messages and thread pools.
nodetool tpstats

# Compaction progress and SSTable backlog.
nodetool compactionstats

# Streaming/network tasks where supported.
nodetool netstats

# Workload table statistics.
nodetool tablestats diag_lab.events_by_tenant_day

# Partition size/row histograms per version.
nodetool tablehistograms diag_lab events_by_tenant_day
~~~

These commands do not replace **driver metrics, client CPU/GC, OS disk/network latency, and server JMX/Prometheus**. Never run **repair, cleanup, rebuild, decommission, or RF changes** as a knee-jerk timeout fix; those alter load and topology and require runbooks and approval.

### 11.2. Limits of Driver Metadata

**`session.getMetadata()`** reflects the cluster view discovered by the session, which may lag briefly behind topology changes, and knowing a node exists does not mean its connection pool is usable. When `CqlSession` **fails to build**, there is no usable session metadata; start with contact points, DNS/TLS/auth, and startup `AllNodesFailed` causes.

### 11.3. Mapping Metrics Across Layers

| Layer | Signal | Question |
|---|---|---|
| **HTTP/gRPC** | Offered/completed RPS, p95/p99, 5xx, deadline exceeded | What does the caller see? |
| **Application** | Active permits, admission queue, rejections, retries | Did the request even reach the driver? |
| **Driver** | Pool usage, in-flight, timeouts, retries/speculation, coordinator | Waiting on connections or the server? |
| **Server coordinator** | Read/write latency, timeouts, overload | Did the request reach a coordinator? |
| **Replica** | Local latency, pending/dropped, RF/CL, GC/disk | Which replica missed the deadline? |
| **Storage/JVM** | Disk await, SSTables, compaction, repair, heap/native, GC | Resource pressure or tombstones? |
| **Correctness** | Missing/duplicate events, request ID/version | Did retries or timeouts corrupt state? |

**`DriverTimeout`** can occur with zero rise in server `ReadTimeout` counters if requests never reached a coordinator. Conversely, rising server `ReadTimeout` paired with replica disk await points to a slow read path. Use **timelines and request correlation** to distinguish them.

### 11.4. Structured Logging While Limiting Data Exposure

~~~json
{
  "event": "cassandra_operation_failed",
  "request_id": "req-lab-084",
  "operation": "events_by_tenant_day.read",
  "failure_kind": "ALL_NODES_FAILED",
  "attempted_nodes_count": 3,
  "per_node_cause_classes": {
    "node-alias-a": ["ConnectException"],
    "node-alias-b": ["SSLHandshakeException"],
    "node-alias-c": ["ConnectionInitException", "TimeoutException"]
  },
  "local_dc": "dc1",
  "consistency": "LOCAL_QUORUM",
  "driver_timeout_ms": 2000,
  "logical_attempt": 1,
  "deadline_remaining_ms": 300,
  "reconciliation_required": false
}
~~~

This is an application-defined format, **not default Java Driver output**. Never log raw bind values, user IDs, credentials, private keys, tokens, or secret-bearing messages. Cap emitted nodes/causes and log volume during incidents while keeping summary aggregates so rare errors remain visible.

## 12. Misconfigurations Causing `AllNodesFailed` on Healthy Clusters

### 12.1. Contact Points, DNS, and Ports

**Symptom:** A Java app in Kubernetes throws `AllNodesFailed`, while DBAs connect cleanly from another VM.

Check:

1. Do contact points target the right cluster and environment?
2. Does the Java Pod resolve the FQDN accurately? Any split-horizon DNS or service mesh?
3. Are resolved IPs routable from the Pod's namespace/VPC?
4. Is the CQL native transport port (typically **9042**) listening and allowed by network policies?
5. Is a proxy, LB, or NAT returning endpoints incompatible with driver peer discovery?
6. Is the node actually accepting CQL connections even while `nodetool status` shows `UP`?
7. Are errors across all Pods or isolated to one AZ/region?

**A successful host ping never proves CQL TCP/TLS/auth works.** Test from **the Java client's exact network location** along the real path.

### 12.2. Wrong Local Datacenter

The driver uses **`local-datacenter`** in its load-balancing policy to select nodes. A wrong DC name leaves the query plan with no eligible nodes even when contact points are reachable.

Cross-check the cluster's real DC name against **`withLocalDatacenter`** or effective runtime properties. Inspect environment overrides, contact points, metadata, and driver version behavior.

**Never route to a remote DC** just to "find a node" when the application requires local data residency, `LOCAL_QUORUM`, or strict latency bounds.

### 12.3. TLS and Certificate Rotation

**Symptom:** Multiple cause chains show `SSLHandshakeException`/PKIX.

- Are server certificates unexpired with valid hostnames/SANs?
- Is the JDK/Pod truststore properly mounted and loaded?
- Are mTLS client certs/keys valid and unexpired?
- Do TLS protocols and cipher suites align across driver, JDK, and server?
- Did some nodes miss the new certificate during a rolling rotation?

**Never disable TLS or hostname verification in production.** Fix trust/certificates and validate on a canary before rolling out.

### 12.4. Authentication vs. Authorization

**Bad secrets/credentials** fail authentication when opening connections. **Missing `SELECT`/`MODIFY` grants** fail authorization when executing CQL.

Never retry infinitely with the same bad secret and never promote the runtime role to superuser to bypass errors. Audit **authenticators, secret rotation, and role grants** under least privilege.

### 12.5. Driver/Server Version or Protocol Mismatch

After upgrading Cassandra, the driver, or the JDK, check compatibility matrices, native protocol versions, TLS/codecs, schema migrations, and mixed-version states. Never force arbitrary protocol versions or disable security to hide errors. When cross-checking with another driver/tool, test against **the exact same endpoint and security model**.

## 13. Three Diagnostic Scenarios by Per-Node Errors

### 13.1. Case A — `AllNodesFailed` After Certificate Rotation

**Hypothetical scenario:** Half of newly started Spring Boot pods fail after rotation while older pods continue running.

~~~text
AllNodesFailedException
  node-a: ConnectionInitException <- SSLHandshakeException <- PKIX...
  node-b: ConnectionInitException <- SSLHandshakeException <- PKIX...
  node-c: ConnectionInitException <- SSLHandshakeException <- PKIX...
~~~

**Investigation:**

1. Compare old vs. new pods: truststore, secret image, volume mounts, and effective TLS config.
2. Check server certificate chains, SANs, and CQL node rollout progress.
3. Validate the fix on an authorized canary, verifying session build and a read-only `SELECT`.
4. Monitor post-rollout; never restart the whole Cassandra cluster without evidence.

**Conclusion:** Nested causes point to **client TLS/trust issues**, not cluster-wide Cassandra downtime.

### 13.2. Case B — `DriverTimeout` Spikes During Repair

**Hypothetical scenario:** An interactive read API sets a 2-second driver timeout. Repair/compaction overlaps with a p99 spike.

~~~text
Read p99: jumps from 180 ms to 2,400 ms
DriverTimeoutException: spikes on read queries
Replica disk await: rises sharply
Compaction pending: elevated
nodetool status: all nodes remain UN
~~~

**Investigation:**

1. Align error/p99 timelines with repair phases, disk I/O, and GC.
2. Inspect partition keys, tombstones, SSTables, page size, and hot tenants.
3. Measure driver pools, in-flight requests, retries, and attempted nodes.
4. If stop gates breach, throttle maintenance per runbook; never kill nodes arbitrarily.
5. Measure post-repair recovery and verify data correctness.

**Conclusion:** Driver timeouts are a **symptom**. Resource contention or hot partitions are **hypotheses needing proof**; raising timeouts swells queues without adding server capacity.

### 13.3. Case C — `AllNodesFailed` in Only One App Region

**Hypothetical scenario:** Region A Java service works cleanly; newly deployed Region B fails to build a session.

~~~text
region-A: CqlSession connected; SELECT OK
region-B: AllNodesFailed; per-node ConnectTimeout
Cassandra nodes: UN in DC
~~~

**Investigation:**

1. Compare subnets, route tables, firewalls, and security groups between A and B.
2. Test DNS/contact-point resolution from Pod B.
3. Check `local-datacenter`, proxies/address translation, and TLS.
4. Do not alter RF/CL or run repair—none of those fix client network paths.
5. Admit traffic to B only after fixing the path and passing a CQL canary.

**Conclusion:** Evidence points to a **single-region client connectivity failure**, not a cluster-wide outage.

## 14. Retries, Idempotency, and Uncertain Write Outcomes

### 14.1. Retry Only When All Conditions Hold

A failed request does not mean **it must be retried**. Require all four simultaneously:

1. **Safe to re-execute:** primary key, payload, write timestamp, TTL, LWT, and downstream side effects evaluated.
2. **Likely transient error:** not a permanent DNS/TLS/auth misconfig, syntax error, or schema mismatch.
3. **Budget and deadline remain:** accounting for backoff and cumulative attempts across driver, app, and gateway.
4. **Cluster has headroom:** not `Overloaded`, growing queues, or tripped circuit breakers.

~~~mermaid
flowchart TD
    A["Exception caught"] --> B{"Config or non-transient failure?"}
    B -->|Yes| X["Do not retry; fix root cause"]
    B -->|No| C{"Mutation proven idempotent?"}
    C -->|No / unclear| U["UNKNOWN / reconcile; never retry blindly"]
    C -->|Yes| D{"Deadline and retry budget remain?"}
    D -->|No| F["Fail fast"]
    D -->|Yes| E{"Server overloaded?"}
    E -->|Yes| G["Shed load; await recovery"]
    E -->|No| H["Backoff + jitter, bounded retry"]
~~~

Point `SELECT`s by partition key **can usually retry** within budget, though results may shift under concurrent writes or TTLs. `INSERT`/`UPDATE`/`DELETE`, counters, list appends, and LWTs demand stricter semantic checks.

### 14.2. `DriverTimeout` After `INSERT` Can Cause Duplicate Events

~~~text
First attempt:
  INSERT event_id = X
  Cassandra may have applied it
  Java receives DriverTimeout

Wrong:
  Generate event_id = Y and INSERT again
  => Can create two logical events

Better:
  Keep event_id = X and identical bind values
  Read/reconcile by primary key
  Retry only if idempotent and budget remains
~~~

For **counter `+1`**, **list append**, or payment/email triggers, **`setIdempotent(true)`** does not make repetition safe. Setting it false only restricts driver-managed automatic retries per policy; the application must still prevent uncontrolled manual retries.

### 14.3. LWT `false` After Retry Does Not Prove Another Client Won

If **`INSERT ... IF NOT EXISTS`** applied on the server before its reply dropped, a retry with the same business key can return **`[applied] = false`**. Do not immediately assume a conflict. Read back the row and compare **`request_id`, owner/fingerprint, and workflow state**. If reads also fail due to quorum/network errors, keep **`UNKNOWN`**.

Regular consistency and serial consistency (**`SERIAL` / `LOCAL_SERIAL`**) are separate choices. Never relax serial consistency arbitrarily when business invariants span multiple DCs.

### 14.4. Driver Flag Differs from Retry Policy

**`setIdempotent(true)`** is metadata certifying an operation is safe to replay according to application logic. It does not configure `maxAttempts` or change CQL semantics.

~~~text
One logical HTTP request
  -> HTTP client/gateway retry (if any)
    -> Spring service retry (if any)
      -> Java Driver retry/speculative execution (if any)
        -> Cassandra physical CQL attempts
~~~

An application retry count of 0 **does not mean** the driver or gateway didn't retry. Measure logical requests, physical attempts, p99, retries, and speculative executions. Use backoff/jitter and admission control; never call `Thread.sleep` inside driver callbacks or reactive event loops.

### 14.5. Domain Outcomes Must Stay Distinct

| Outcome Category | Condition | Handling |
|---|---|---|
| **`SUCCESS`** | Valid response, business invariants satisfied | Complete workflow |
| **`BUSINESS_FALSE`/`CONFLICT`** | LWT false or business rule violation with proof | Return conflict or handle duplicate |
| **`UNKNOWN`/`ERROR`** | `DriverTimeout`/`WriteTimeout`/reset with unverified state | Reconcile, checkpoint, or return contract error |

Never turn `UNKNOWN` into false or "data not found" just to simplify code. For orders and payments, use idempotency keys and reconciliation before issuing a fresh mutation.

## 15. Diagnostic Testing in Staging

### 15.1. Controlled Fault-Injection Matrix

| Case | Lab Setup | What to Observe | Do Not Infer |
|---|---|---|---|
| **T0 — baseline** | Healthy session, keyed `SELECT` | CQL succeeds, p95/p99, node health | Production behaves identically |
| **T1 — bad DNS** | Unresolvable test contact point | DNS/init cause per driver/version | Cassandra cluster is DOWN |
| **T2 — wrong port** | CQL endpoint targets closed port | Refused / connect timeout per network | Mutation reached coordinator |
| **T3 — wrong truststore** | Client rejects lab cert | Nested TLS/PKIX cause | Raising request timeout fixes it |
| **T4 — bad credentials** | Intentionally wrong lab secret | Auth failure and init path | Infinite retries are appropriate |
| **T5 — local DC mismatch** | Non-existent/mismatched DC config | No eligible node / config fault | Lower RF/CL to fix |
| **T6 — pool saturation** | Bounded load above baseline | Pool/in-flight/queues, driver timeout | Server is definitely broken |
| **T7 — slow replica** | Network/disk shaping on RF3 lab | Client vs. server timeouts, CL | `UN` nodes must always respond fast |
| **T8 — hot partition** | Heavy traffic to one bucket/partition | Replica skew, p99, tombstones | Raising timeout fixes data model |
| **T9 — lost response** | Test adapter drops ACK after write | `UNKNOWN`, reconciliation by same ID | Timeout = write never occurred |
| **T10 — LWT contention** | N writers racing `IF NOT EXISTS` | `true`, `false`, `unknown` differ | `false` is an exception |

**There is no guarantee every fault produces one fixed top-level class.** Driver/server timing and versions determine whether you see Authentication, connection-init, `AllNodesFailed`, or timeout. Record **class chain, init vs. execute stage, node causes, and versions**.

### 15.2. Three Gates Before Injecting Faults

1. **Isolation:** dedicated lab/staging cluster, synthetic data, recoverable, never production.
2. **Safety:** matching RF/CL, capacity headroom, authorized network shaping, change owner, stop gates.
3. **Observability:** Java structured logs, coordinator/replica metrics, disk/GC/network, and exact inject/restore timestamps.

If fault injection misfires or telemetry is missing, mark the test **`INCONCLUSIVE`** rather than forcing a PASS.

### 15.3. JUnit Test Verifying Unwrap Preserves Root Cause

This unit test covers the helper in section 10; it does not replace integration tests against real Cassandra:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

import org.junit.jupiter.api.Test;

public class CassandraFailureClassifierTest {
    @Test
    void keepsRootCauseFromCompletionException() {
        IllegalStateException root =
            new IllegalStateException("simulated");
        CompletionException wrapper =
            new CompletionException(root);

        assertSame(
            root, CassandraFailureClassifier.unwrap(wrapper));
        assertEquals(
            CassandraFailureClassifier.Kind.OTHER,
            CassandraFailureClassifier.classify(wrapper));
    }

    @Test
    void unwrapsNestedFutureExceptions() {
        IllegalArgumentException root =
            new IllegalArgumentException("simulated");
        Throwable wrapped = new ExecutionException(
            new CompletionException(root));

        assertSame(
            root, CassandraFailureClassifier.unwrap(wrapped));
    }
}
~~~

This confirms Java Future wrappers do not mask root causes. It **does not** generate real `DriverTimeoutException` or validate cluster `getAllErrors()`. Testing those requires a fault lab inspecting actual per-node errors.

### 15.4. Simulated Lost Response vs. Server `WriteTimeout`

~~~text
Lost-response test double:
  Cassandra applies write cleanly
  Test adapter intentionally drops ACK
  Service sees UNKNOWN and reconciles by request ID

Server WriteTimeout in lab:
  Coordinator misses enough replica ACKs per CL
  Some replicas may already have written
  Requires checking node logs/metrics and post-fault data
~~~

These two cases exercise distinct branches. Never change the request ID when retrying a logical operation simply because the prior attempt lost its reply.

## 16. Limitations of `AllNodesFailedException.getAllErrors()`

### 16.1. Before `CqlSession` Initializes

- Contact points may be the only endpoints the driver knows.
- Node metadata may be missing or incomplete.
- `session.getMetadata()` is unavailable when session creation fails.
- DNS/TLS/auth errors may sit beneath multiple wrapper layers.
- Some diagnostics appear only in driver logs at sufficient verbosity.

### 16.2. Once the Session Is Active

- Query plans reflect token awareness, load balancing, and local DC.
- The driver may try only a subset of the cluster, not every node.
- An **attempted coordinator** is not necessarily a **replica** owning the partition.
- Retries and speculative executions complicate attempt counts and error ordering.
- Node addresses are infrastructure metadata that must be kept out of user-facing APIs.

### 16.3. Evidentiary Value of Each Signal

| Evidence | Shows | Does Not Show |
|---|---|---|
| `ConnectException` on node A | Attempt failed to open TCP to endpoint A | All operations on A are failing |
| `SSLHandshakeException` on node B | That attempt's TLS handshake failed | Cassandra replication is broken |
| `AllNodesFailed` with 3 entries | Errors recorded for 3 keys/attempted nodes | Cluster has only 3 nodes or all nodes are DOWN |
| `DriverTimeout` | Request missed driver deadline | Server did not write |
| Server `WriteTimeout` | Insufficient CL ACKs before server timeout | Zero replicas wrote |
| `nodetool status UN` | Node liveness normal in gossip | CQL p99 always meets SLO |
| One succeeding `SELECT` | That query succeeded at that instant | All tables and DCs are healthy |

**`getAllErrors()` never replaces distributed tracing, server logs, or application metrics.** Its error map is meaningful only alongside the query plan and cluster state at that exact moment.

### 16.4. Protecting Data in Logs

Exception messages and stack traces can leak endpoints, CQL strings, schemas, or auth details. Standard telemetry should log **cause classes, node aliases, and operation IDs**; retain full forensic logs under strict access controls, retention limits, and rate caps.

## 17. Actionable Incident Report Template

~~~yaml
incident:
  id: "cassandra-java-failure-lab-2026-11-21"
  first_seen_at_utc: "<timestamp>"
  environment: "staging-isolated"
  affected_service: "event-api"
  affected_operation: "events_by_tenant_day.read"
versions:
  cassandra: "<exact-version>"
  java_driver: "<exact-version>"
  jdk: "<exact-version>"
topology:
  local_dc: "dc1"
  replication_strategy: "NetworkTopologyStrategy"
  replication_factor_dc1: 3
client:
  contact_point_group: "internal-cql"
  request_timeout_ms: 2000
  regular_consistency: "LOCAL_QUORUM"
  logical_error_rate_percent: "<measured>"
  physical_attempts: "<measured>"
error:
  top_level_kind: "ALL_NODES_FAILED"
  at_stage: "execute"
  attempted_node_causes:
    node_a: ["ConnectException"]
    node_b: ["SSLHandshakeException"]
    node_c: ["ConnectionInitException", "TimeoutException"]
server:
  node_health: "<observed>"
  disk_gc_compaction: "<observed>"
  read_write_timeouts: "<observed>"
assessment:
  hypothesis: "mixed network and TLS failures"
  outcome_ambiguous: false
  confidence: "requires staging validation"
  decision: "PAUSE rollout"
evidence:
  driver_logs: "<controlled-log-reference>"
  node_metrics: "<dashboard-reference>"
  change_record: "<change-id>"
~~~

This is a **report template**, not Cassandra configuration. If a metric wasn't collected, write `NOT_MEASURED` instead of inventing numbers. Never paste secrets, raw bind values, sensitive endpoints, or user data into broadly shared reports.

### 17.1. Prerequisites Before Declaring Root Cause

- Exact onset time, separating **session init vs. query execute**?
- Cause chains per **attempted node** inside `AllNodesFailed`?
- Verified local DC, DNS/contact points, and TLS/auth?
- Measured client pools, in-flight requests, retries, and deadlines?
- Telemetry for RF/CL, replicas, disk/GC, and compaction/repair?
- Known query shape and partition key?
- Could write outcomes be `UNKNOWN`? Is idempotency/reconciliation active?
- Verified remediation via canary plus SLO/correctness checks?

A single `AllNodesFailed` or `DriverTimeout` log line **is never enough to declare root cause**.

## 18. Phase-by-Phase Incident Runbook

### 18.1. Minutes 0–5: Classify, Isolate, Protect Data

1. **Confirm symptom:** is the app failing session init, failing queries, or hitting caller HTTP timeouts?
2. **Capture versions and effective config:** Cassandra, driver, JDK, local DC, CL, timeouts, retry profiles.
3. **Classify top-level exception** and unwrap Future wrappers.
4. On `AllNodesFailed`, **dump per-node cause classes + nested cause chains** and check if nodes share a cause.
5. Record **timestamps** of deploys, TLS rotations, network changes, bootstraps, repairs, or backups.
6. **Measure scope:** one pod/region/DC or all; one query/partition or every API.
7. For timed-out writes, mark **`UNKNOWN`** and avoid minting new request IDs or retrying counters/list appends.
8. If data corruption, lost quorum, or secret leaks are suspected, trigger **incident/STOP** per policy.

Never restart the whole cluster or downgrade CL merely because one log reports failing to reach a node.

### 18.2. Minutes 5–15: Correlate Client vs. Server Causes

| If Top-Level Is | Next Checks | Do Not Do Immediately |
|---|---|---|
| **`AllNodesFailed` at startup** | Contact points, DNS, CQL port, local DC, TLS/auth/versions | Run repair or rewrite CQL queries |
| **`AllNodesFailed` at execute** | `getAllErrors`, pool/health/routes of attempted nodes, retry policy | Declare every replica DOWN |
| **`DriverTimeout`** | Client queues/pools, timeout layers, coordinator/replica p99, retries | Merely bump timeout from 2s to 20s |
| **Server `ReadTimeout`** | CL/RF/replica speed, tombstones, partition size, disk/GC | Add `ALLOW FILTERING` to "test" a scan |
| **Server `WriteTimeout`** | Replica ACKs, write type, idempotency, data outcome | Mint a new mutation with a new ID |
| **`Unavailable`** | Node UP/DOWN, RF/DC, CL, topology/streaming | Downgrade CL outside contract |
| **`Overloaded`** | In-flight/queues, disk, GC, hot partitions, traffic bursts | Retry immediately or raise max attempts |
| **Unknown CQL column** | Schema migration/agreement, code/driver versions | Mass-restart nodes |

### 18.3. Minutes 15–30: Controlled Hypothesis Testing

1. Change **one variable at a time** where possible: DNS mapping, truststore, rate limit, pool/circuit breaker, or data model.
2. Test on staging or an authorized canary—never mutate multiple layers simultaneously.
3. Enforce **GO/PAUSE/STOP gates** for error rate, p95/p99, quorum, disk headroom, and data correctness.
4. Observe **full recovery time**, not just a one-minute dip in errors.
5. If maintenance is the cause, coordinate with the repair/streaming/backup owner—never kill processes arbitrarily.
6. If an app deploy caused the bug, weigh rolling back **application code** against any schema/data writes already applied; code rollback does not undo database mutations.
7. Preserve controlled raw evidence, maintain the timeline, and revise hypotheses whenever new data refutes earlier guesses.

### 18.4. Post-Incident

- **Root cause vs. contributing factors:** e.g., bad truststore was the root cause while gateway retry storms amplified impact.
- **Detection gap:** did logs print only the top-level message without per-node `getAllErrors()`?
- **Safety gap:** were timeouts converted into false or writes retried under new IDs?
- **Capacity gap:** did disk/GC/hot partitions, pool saturation, and early p99 lack early alerts?
- **Prevention:** staging integration tests, certificate rotation rehearsals, bounded retries/limits, schema/version checks.
- **Recovery evidence:** reconciled data, stable quorum/CL, and p99/throughput within SLO.

## 19. Distinguishing Config Errors, Single-Node Faults, and Query Issues

### 19.1. Quick Classification Rules

~~~text
AllNodesFailed + identical SSLHandshakeException across multiple nodes
    => Prioritize checking client trust / TLS rollout.

AllNodesFailed + identical ConnectTimeout from one region
    => Prioritize routes / firewalls / endpoints from that region.

AllNodesFailed + one node refused, another timed out
    => Inspect each node individually; do not lump into "Cassandra down".

DriverTimeout + high app queue + normal server latency
    => Prioritize admission / pool / client CPU/GC/network.

DriverTimeout + high server read p99 + high disk await
    => Investigate read path, hot partitions, compaction/repair.

WriteTimeout + insufficient RF/CL ACKs
    => UNKNOWN outcome; reconcile by request ID.

Unavailable + missing replicas for CL
    => Topology/quorum; never downgrade CL casually.

InvalidQuery or unknown column
    => Schema/mapping/version; normal retries will not help.
~~~

These are **investigation heuristics**, never definitive verdicts from an exception name alone. Always verify cause chains, timestamps, configurations, and metrics.

### 19.2. When to Engage the Cassandra Owner

- Node health, token placement, or RF/DC mismatches.
- Rising server `Read`/`WriteTimeout`, `Unavailable`, or `Overloaded`.
- Disk, GC, compaction, repair, or streaming impacting SLOs.
- Suspected lost/corrupt data or inconsistent query results.
- Changes needed to topology, RF, repair, compaction, auth, or server TLS.

### 19.3. When to Engage the Java/Platform Owner

- Session init fails on contact points, DNS, TLS/truststores, or local DC.
- Driver request timeouts rise while server metrics stay flat.
- Pool/connection setup, circuit breakers, admission, in-flight/queues.
- HTTP client/gateway stacking retries or speculation.
- Async callbacks swallowing exceptions or broken deadline propagation.
- Spring Boot configs/profiles or secret rotations not taking effect.

**Both teams must collaborate:** driver errors can originate on servers, and server faults can be amplified by client retries. Never bounce tickets based solely on exception class names.

## 20. Scenario Exercises and Suggested Answers

### Exercise 1 — Does `AllNodesFailed` Mean Every Node Is DOWN?

The app throws `AllNodesFailed`, `getAllErrors()` has three entries, and `nodetool status` shows five nodes `UP`.

**Question:** Can you assert all five nodes are broken?

**Suggested answer:** No. The map lists errors for attempted nodes, not every node in the cluster. Check the query plan, local DC, per-node causes, and client connection health.

### Exercise 2 — Multiple Identical TLS Causes

Three causes all show `SSLHandshakeException` wrapping `PKIX path building failed` after deploying new pods.

**Question:** What do you inspect first?

**Answer:** The new pods' truststores, certificate chains, SANs, hostnames, JDK TLS policies, and certificate rotation state. Never bump CQL timeouts or disable TLS verification in production.

### Exercise 3 — `DriverTimeout` vs. Server `ReadTimeout`

Driver throws `DriverTimeoutException` after 2 seconds, yet Cassandra metrics show zero increase in server `ReadTimeout` while app queue waits spike sharply.

**Question:** Where does the cause likely sit?

**Answer:** Likely admission control, connection pools, driver/client CPU/GC, or networking upstream of the coordinator. Align timelines and attempted-node metrics rather than blaming slow replicas everywhere.

### Exercise 4 — Server `WriteTimeout` and Retrying with a New ID

An `INSERT` event hits `WriteTimeout`. The service generates a fresh `event_id` and resends.

**Question:** What is the hazard?

**Answer:** The initial mutation may have applied on some replicas; generating a new ID risks creating two distinct business events. Keep a stable ID, idempotency contract, and reconciliation.

### Exercise 5 — Mixed Per-Node Errors

`AllNodesFailed` wraps `ConnectException` on node A, `SSLHandshakeException` on B, and init timeout on C.

**Question:** Can tuning `request.timeout` fix all three?

**Answer:** No basis for that. Three distinct errors require checking listener/network on A, truststore/certs on B, and init/pool/network on C. A single bad rollout could trigger multiple symptoms, which must be proven.

### Exercise 6 — Misspelled Local DC

Cluster DC is `DC-EAST-1`, while Java sets local DC = `east`. App reports no eligible nodes.

**Question:** What do you fix?

**Answer:** Verify the real DC name and effective config; fix `local-datacenter` and canary it. Never silently redirect to a remote DC outside contract.

### Exercise 7 — Nodes `UP` Yet Poor p99

`nodetool status` shows `UN` on every node, yet read p99 spikes once repair starts, with high disk await and pending compactions.

**Question:** Can you declare Cassandra completely healthy?

**Answer:** No. Liveness differs from latency and capacity. Align repair timelines, disk/GC, partition distribution, CL, and throttle/stop gates per runbook.

### Exercise 8 — Retrying a Counter

Driver times out after a counter increment. A developer adds `setIdempotent(true)` and retries three times.

**Question:** Is this safe?

**Answer:** That flag does not make counters idempotent; retries can increment multiple times. Never retry counters blindly—use an event/deduplication model or proper reconciliation.

### Exercise 9 — LWT `false` After Retry

An initial `INSERT IF NOT EXISTS` applied, yet its reply dropped. A retry returns `[applied]=false`.

**Question:** Does that guarantee another client won?

**Answer:** No. Your own first attempt may have created the row. Read back by key and compare request ID/fingerprint and state; if reads fail too, keep `UNKNOWN`.

### Exercise 10 — Top-Level `CompletionException`

A Java Future fails with `CompletionException` wrapping `AllNodesFailedException`.

**Question:** What should the logger do?

**Answer:** Unwrap Future wrappers, recognize `AllNodesFailed`, walk `getAllErrors()` per node/cause, and preserve root causes and correlation IDs—never log only `CompletionException` and stop.

### Exercise 11 — Empty Node Map

A log shows `AllNodesFailed` with an empty per-node map or minimal metadata during startup.

**Question:** Does that prove Cassandra has zero nodes?

**Answer:** No. The driver may have failed before discovering topology; check contact points, DNS, TLS/auth, and init stage. Loggers must handle empty maps safely.

### Exercise 12 — Pool Saturation from a Retry Storm

Client has low max in-flight, the server slows down, and both gateway and driver retry. `AllNodesFailed` or `DriverTimeout` spikes.

**Question:** Should you raise max connections to infinity?

**Answer:** No. Measure logical vs. physical attempts, in-flight/queues, cut stacked retries, shed load, and inspect server/disk/GC. Pool sizing must follow capacity and load testing.

### Exercise 13 — Lowering CL to Reduce Errors

An endpoint commits to `LOCAL_QUORUM`, yet an incident workaround auto-retries at `LOCAL_ONE`.

**Question:** What is wrong with that?

**Answer:** It alters the consistency guarantee and can violate business contracts. Keep the approved CL and fix replicas/topology, or obtain explicit approval for degraded mode.

### Exercise 14 — Failures Scoped to One Query Shape

Point reads on table A stay fast, while historical queries lacking a partition key and scanning wide ranges often throw `DriverTimeout`.

**Question:** Is this a contact-point failure?

**Answer:** Unlikely without evidence. It points to a query/data-model mismatch causing read amplification, tombstones, or hot partitions. Redesign the table for the query instead of adding `ALLOW FILTERING` and bumping timeouts.

### Exercise 15 — One Succeeding `SELECT`

A new pod runs one test `SELECT` against node A and succeeds, so the team declares all nodes, all CLs, and writes healthy.

**Question:** Is that conclusion valid?

**Answer:** No. One point-in-time query proves only that single path. Validate across RF/DC, CLs, write paths, node/error distributions, and SLOs.

### Exercise 16 — Paging Fails on Page 6 of 10

Java reads five pages, then `fetchNextPage()` times out on page six; the API still returns HTTP 200 with the partial list collected so far.

**Question:** What is the bug?

**Answer:** Presenting an incomplete result as complete. Enforce partial/incomplete failure semantics, overall deadlines, checkpoints/continuation tokens, and idempotent sinks if earlier pages triggered side effects.

## 21. Checklist for Handling `DriverTimeout`/`AllNodesFailed`

### 21.1. Identification and Evidence Collection

- [ ] Distinguished **`DriverTimeoutException`**, **`AllNodesFailedException`**, and server `Read`/`WriteTimeout`/`Failure`/`Unavailable`/`Overloaded`.
- [ ] Unwrapped **`CompletionException`/`ExecutionException`** before classifying.
- [ ] On `AllNodesFailed`, inspected **`getAllErrors()`** across every attempted node and **all nested causes**.
- [ ] Walked cause chains down to DNS, TLS, auth, transport, or pooling rather than stopping at the top-level message.
- [ ] Did not conclude "all nodes DOWN" solely from entry counts in `AllNodesFailed`.
- [ ] Captured timestamps/correlation IDs, driver/server/JDK versions, and query shape.
- [ ] Distinguished **`CqlSession` startup** from **CQL execution**.
- [ ] Excluded secrets, raw bind values, customer IDs, and sensitive endpoints from public responses/logs.

### 21.2. Client/Network and Cluster Verification

- [ ] Contact points, DNS, CQL port, routes, network policies, and proxies checked from **the Java client's exact environment**.
- [ ] **`local-datacenter`** matches live topology and effective driver config.
- [ ] TLS truststores, certs, SANs, hostnames, auth, and role permissions verified.
- [ ] Connection pools, in-flight requests, admission, retries, and speculative executions measured.
- [ ] Driver request timeout, connection init, caller deadline, and server timeout clearly separated.
- [ ] Node health, RF/DC, regular CL, and serial CL (if LWT) verified.
- [ ] Server read/write latencies, pending/dropped threads, disk I/O, GC, and networking aligned on a timeline.
- [ ] Checked overlapping compaction, repair, streaming, backups, and deployments.
- [ ] Evaluated partition keys, hot partitions, tombstones, page sizes, and CQL query shapes.
- [ ] Did not run repair, cleanup, rebuild, or downgrade consistency blindly to mask symptoms.

### 21.3. Remediation and Recovery Verification

- [ ] Timed-out writes and transport drops never assumed **definitely uncommitted**.
- [ ] Request IDs, idempotency keys, payloads, timestamps, and versions kept stable across attempts.
- [ ] Counters, list appends, LWTs, and side effects reviewed before allowing any retry.
- [ ] Retry budgets, backoff/jitter, end-to-end deadlines, and load shedding active when `Overloaded`.
- [ ] Eliminated uncoordinated stacked retries across driver, service, and gateway.
- [ ] Reconciliation / `UNKNOWN` workflow handles ambiguous write outcomes.
- [ ] Validated fixes in staging/canary against reproduced evidence rather than experimenting on production.
- [ ] Defined PAUSE/STOP/ESCALATE thresholds for data correctness, quorum, p99, and error budgets.
- [ ] Post-fix verification covers session startup, authorized CQL reads/writes, p95/p99, and error rates.
- [ ] Observed through a recovery window instead of closing after one green `SELECT`.
- [ ] Incident report captures root cause, amplifiers, blast radius, and preventive actions.

## 22. Summary

**`DriverTimeoutException`** signals the driver ran out of its client-side request time budget; **`AllNodesFailedException`** is an aggregate wrapper indicating no attempted node/endpoint succeeded. Neither is equivalent to **`ReadTimeoutException`/`WriteTimeoutException`** returned by a Cassandra coordinator when replicas miss consistency deadlines.

For **`AllNodesFailed`**, the decisive diagnostic clue lives in **`getAllErrors()`**: inspect **which nodes were tried, every cause recorded, and deep cause chains pointing to DNS, TCP, TLS, auth, pooling, or overload**—remembering this map is **not every node in the cluster**. For **`DriverTimeout`**, correlate caller deadlines, driver queues/pools, networking, coordinator/replica p99, RF/CL, hot partitions, and background compaction/repair/streaming. An `UN` node does not guarantee low latency; a timeout exception does not prove a mutation wasn't applied.

A durable workflow is **classify by layer → inspect per-node causes → correlate client/server telemetry → check CQL and data semantics → apply controlled retries/shedding/config fixes → verify in staging/canary**. Retry only when the operation is idempotent, deadlines/budgets remain, and the cluster has headroom; protect **`UNKNOWN` write outcomes** with stable request IDs and reconciliation.

Applying Cassandra's distributed architecture, partition keys, query-driven tables, replication/consistency, CQL, and Java Driver internals lets you troubleshoot failures using **per-node, per-layer evidence** rather than blindly raising timeouts or restarting entire clusters.
