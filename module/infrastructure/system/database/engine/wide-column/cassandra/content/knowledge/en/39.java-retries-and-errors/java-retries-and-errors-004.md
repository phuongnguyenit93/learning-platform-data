# DriverTimeout, AllNodesFailed, and Per-Node Error Details in the Cassandra Java Driver

## 1. Lesson Goals and Context

Apache Cassandra is a distributed **wide-column** database: data is located by **partition key**, distributed by token, and replicated across **replicas** according to the replication strategy. When a Java client executes CQL, a **coordinator** node accepts the request and waits for replica responses per the selected **consistency level (CL)**.

Query failures from Java are not uniform. A request can stall in the application, in the connection pool, in transit to the coordinator, on the coordinator itself, or while replicas read SSTables or write to the commit log. When an error occurs, we must distinguish:

- **`DriverTimeoutException`**: the client-side Java Driver request budget expired.
- **`AllNodesFailedException`**: the driver failed to execute the request across all candidate nodes; inspect per-node errors via **`getAllErrors()`**.
- **`ReadTimeoutException` / `WriteTimeoutException`**: Cassandra server returned an error regarding read/write conditions and replica responses.
- **`UnavailableException`**: too few replicas are considered available for the CL.
- **CQL/schema/authentication/authorization errors**: usually query or configuration defects, not transient faults to retry.

This lesson belongs to the **Java Retries and Errors** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. After completing it, you will be able to:

1. Distinguish client deadlines from server/coordinator timeouts and replica outages.
2. Inspect the error list for each **candidate coordinator** the Java Driver attempted.
3. Implement exception classification in Java Driver 4.x, both synchronously and asynchronously.
4. Analyze **idempotency** before retrying, especially for counters, LWTs, TTLs, and ambiguous mutations.
5. Correlate metrics, `nodetool`, RF/CL, compaction, repair, and driver telemetry to pinpoint root causes.
6. Design backoff, deadlines, and retry budgets to prevent retry storms.

Examples use **Java Driver 4.x**, package `com.datastax.oss.driver.api.*`. Version 3.x uses different packages as well as different retry and connection APIs. Always verify setting names, default policies, and exception details against your actual release.

## 2. Request Path and Three Places Errors Arise

~~~mermaid
sequenceDiagram
    participant App as Java API
    participant Driver as Java Driver
    participant C as Coordinator
    participant A as Replica A
    participant B as Replica B
    App->>Driver: execute(BoundStatement)
    Driver->>C: CQL request
    C->>A: Read / write
    C->>B: Read / write
    Note over App,Driver: HTTP deadline and driver request timeout
    Note over C,B: Server timeout and CL
    A-->>C: Replica response
    B-->>C: Slow or failed
    C-->>Driver: Success or server error if in time
    Driver-->>App: ResultSet / exception
~~~

A successful request may require multiple replicas, while a failed request does not mean all replicas are dead. In particular, when a **client-side** timeout expires, the coordinator or replicas may still be processing the mutation.

| Scope | Typical symptom | What we know | What we do not know |
|---|---|---|---|
| Driver request deadline | `DriverTimeoutException` | Request exceeded client time budget | Whether the server applied the write |
| Query plan / coordinator connection | `AllNodesFailedException` | No candidate coordinator completed the request under the driver's execution flow | Whether all replicas are down; where mutations landed |
| Server read | `ReadTimeoutException` | Coordinator did not complete the read under server conditions and deadline | Whether the data is actually gone |
| Server write | `WriteTimeoutException` | Coordinator did not complete the write under server conditions and deadline | Whether some replicas already wrote the mutation |
| Server replica availability | `UnavailableException` | Too few replicas are considered available to satisfy CL | When quorum will become reachable again |
| Query/schema/security | Invalid query/syntax/auth errors | Query, permissions, or config have an issue | Whether retrying the same input helps (usually no) |

**Never use a single exception type alone to automatically decide it is safe to re-run a mutation.** Business state may remain uncertain even when Java catches an error.

## 3. `DriverTimeoutException`: Client-Side Deadline Expired

### 3.1. What does this timeout mean?

`DriverTimeoutException` in Driver 4.x indicates that a request exceeded the driver's **request timeout**. This timer lives in the application/driver layer, separate from the Cassandra server's replica wait timer.

Example:

~~~text
T0  Service sends INSERT via driver
T1  Driver picks coordinator, sends request
T2  Replica A applied mutation; B/C are slow
T3  Driver-side deadline expires
T4  Java receives DriverTimeoutException
T5  Server may still continue/complete the request later

What CANNOT be inferred at T4:
  - that no node received the mutation;
  - that the mutation definitely rolled back;
  - that the fault lies in only one specific replica.
~~~

This is an illustrative timeline; Cassandra's write/ACK paths and timeouts vary by operation and version.

### 3.2. Common causes

- Bad query shape, missing partition key, wide partitions, or excessive tombstones/SSTables.
- Slow disks due to compaction, flushes, repair, streaming, or lack of headroom.
- Coordinator/replica overloaded on CPU, GC, thread pools, or commit-log I/O.
- Driver connection pool backed up with excessive in-flight requests.
- Network from app to coordinator suffering high RTT, packet loss, or TLS/connection issues.
- Request timeout configured lower than the time required by the workload.
- Retries/speculative executions and multiple attempts consuming the budget.
- Cluster recently restarted or changed topology, leaving metadata/connections unsettled.

**Increasing timeouts does not fix the root cause.** It may reduce exception counts while requests hold resources longer, API p99 rises, and queues keep growing.

### 3.3. Configuring timeouts

HOCON example for Java Driver 4.x:

~~~hocon
datastax-java-driver {
  basic.request.timeout = 3 seconds
}
~~~

`3 seconds` is purely an **illustrative value**, not a default or universal recommendation. A statement can override it per the version's API:

~~~java
import java.time.Duration;

BoundStatement statement = prepared.bind(deviceId, day)
    .setTimeout(Duration.ofSeconds(3))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
~~~

Budget deadlines end-to-end. If an HTTP API has a 1-second limit, do not set each Cassandra attempt to 3 seconds and expect the API to respond on time. Budgets must cover validation, query, mapping, retries, backoff, and response serialization.

### 3.4. Conclusions to avoid

Never write in an incident report:

- “Driver timeout means Cassandra never received the request.”
- “Deadline expired means every replica is down.”
- “Driver timeout proves the mutation was not written.”
- “Retrying enough times will guarantee success.”
- “Raising the request timeout is definitely the optimal fix.”

Combine diagnostics with **idempotency, operation IDs, server metrics, timeout/latency distributions, and data post-checks**.

## 4. `AllNodesFailedException`: All Candidate Nodes Failed to Execute

### 4.1. Understanding the exception name accurately

`AllNodesFailedException` indicates that the driver could not successfully execute the request across any candidate nodes considered or attempted in the **query plan**. Inside, it may contain diverse failures involving connections, pooling, handshakes, metadata, or coordinator availability.

“ALL” **does not mean**:

- All Cassandra nodes across all DCs are dead.
- Every replica of the partition lost data.
- The driver actually tried **every physical node** in the cluster.
- Cassandra reported a quorum timeout on all replicas.
- The query definitely never reached the server on any attempt.

For example, if an application runs in `dc1`, the driver prioritizes local-DC coordinators. If the network path to those nodes breaks, the app can hit `AllNodesFailedException` even while `dc2` nodes remain UP.

### 4.2. Causes to classify

| Symptom | Possibility | Diagnostic action |
|---|---|---|
| TLS handshake errors across nodes | Truststore/cert rotation, hostname verification | Check security config and deploy timeline |
| Repeated authentication errors | Credentials/role/protocol mismatch | Check secrets, auth/TLS; do not retry infinitely |
| Pool/connection busy | In-flight/concurrency too high, slow node processing | Driver metrics, CPU/GC, disk/p99 |
| Connection reset/refused | Node restart, network/firewall, native transport | Status, logs, network path |
| No eligible coordinator | Local DC, query plan, discovered nodes | Session config, topology metadata |
| Failures limited to specific nodes | Hotspot, node health, routing, network zone | Per-node timeline + token/replica placement |

**Never read only the top-level summary message**; inspect detailed errors by node and error class.

## 5. `getAllErrors()`: Error Details **Per Node**

### 5.1. Driver 4.x API structure

~~~java
Map<Node, List<Throwable>> byNode = exception.getAllErrors();
~~~

For an `AllNodesFailedException`:

- **`Node`** is a candidate node/coordinator recorded by the driver.
- **`List<Throwable>`** contains one or more errors associated with that node during execution.
- Multiple errors on one node do not imply multiple replicas failed.
- A node missing from the map **does not prove that node is healthy**; it may sit outside the query plan or simply not have been tried.
- The entry count **is not the total cluster node count**.

**Crucial boundary:** `getAllErrors()` reflects **driver→candidate coordinator attempts**, not a list of **coordinator→replica ACKs/failures**. Never use this map to deduce which replicas fsynced a mutation.

### 5.2. Illustrative map example

~~~text
AllNodesFailedException
  node-A (coordinator candidate)
    - connection initialization failed
    - connection closed
  node-B (coordinator candidate)
    - pool busy
  node-C (coordinator candidate)
    - transport failure

Node D is absent:
  cannot conclude whether D is UP/DOWN or holds the data.
~~~

This is an explanatory structure, **not the literal `toString()` format**. Concrete exception classes vary by driver/runtime version and connection path.

### 5.3. Inspecting the map in Java without logging sensitive data

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class NodeFailureInspector {
    private NodeFailureInspector() {}

    public static void report(AllNodesFailedException ex,
                              String queryId,
                              Logger log) {
        Map<Node, List<Throwable>> perNode = ex.getAllErrors();

        log.log(Level.WARNING,
                "all_nodes_failed queryId={0} nodeEntries={1}",
                new Object[] {queryId, perNode.size()});

        for (Map.Entry<Node, List<Throwable>> entry
                : perNode.entrySet()) {
            Node node = entry.getKey();
            String nodeId = node == null
                ? "unknown" : String.valueOf(node.getHostId());
            String dc = node == null
                ? "unknown" : String.valueOf(node.getDatacenter());

            for (Throwable error : entry.getValue()) {
                String type = error == null
                    ? "unknown" : error.getClass().getSimpleName();

                log.log(Level.WARNING,
                    "cassandra_node_failure queryId={0} nodeId={1} " +
                    "dc={2} errorType={3}",
                    new Object[] {queryId, nodeId, dc, type});
            }
        }
    }
}
~~~

**`queryId` must be a static query template name**, such as `read_device_day`; never pass raw CQL or tenant/device IDs. Node metadata may be considered internal information, so emit it only to authorized log sinks.

Do not log `error.getMessage()`, `Throwable.toString()`, or full stack traces into public logs by default; messages may expose endpoints, configuration details, TLS info, or query context. Use access-restricted audit/debug channels for deep diagnostics.

### 5.4. Read errors over time, not from a single sample

Example:

~~~text
10:00  node-A handshake error    node-B handshake error
10:01  node-A handshake error    node-B handshake error
10:05  truststore configuration fixed
10:06  errors drop and requests succeed
~~~

The stronger hypothesis is a **TLS mismatch**, not Cassandra data loss. Still verify with logs, config, and endpoints; the error map is **partial evidence**.

Second example:

~~~text
11:00  node-A pool busy          node-B connection okay
11:05  node-A pool busy          node-B timeout
11:10  disk await on node-A rises, read backlog grows
~~~

Inspect traffic, token hotspots, in-flight requests, and disk/GC rather than just increasing pool size. A single `AllNodesFailedException` does not record concurrent successful requests; the timeline above is an **aggregation across observations**.

## 6. Distinguishing Server Timeouts from Availability Errors

### 6.1. `ReadTimeoutException` and `WriteTimeoutException`

`ReadTimeoutException` and `WriteTimeoutException` are typically **server errors** returned by the coordinator when a read or write fails to complete within Cassandra's CL conditions and server-side processing timeout.

- **DriverTimeout:** client deadline expired; the driver may not have received a server response in time.
- **ReadTimeout/WriteTimeout:** the server/coordinator emitted a timeout response based on execution conditions.
- **AllNodesFailed:** the driver failed across candidate coordinators in the query plan; inspect per-node causes.

If the driver deadline is shorter than the server timeout, Java may observe `DriverTimeoutException` even while the coordinator is preparing to return `ReadTimeoutException`.

### 6.2. RF=3 and LOCAL_QUORUM

~~~text
Partition P: replicas A, B, C
LOCAL_QUORUM in dc1: requires 2 valid responses

Case 1: A responds, B/C are slow
  -> coordinator may return server read/write timeout.

Case 2: driver deadline expires early
  -> Java sees DriverTimeoutException.

Case 3: driver has no reachable coordinator
  -> Java may see AllNodesFailedException.
~~~

This outline is conceptual and omits read/write nuances, LWT phases, and speculative executions. **The coordinator node is not necessarily one of the partition's replicas.**

### 6.3. `UnavailableException`

When the server knows too few replicas are available to satisfy the CL, it returns `UnavailableException`. This signals you to check **RF, DC, node UP/DOWN status, topology, and CL**.

If RF=3 and only one replica in the local DC can respond, `LOCAL_QUORUM` cannot be met. Retrying repeatedly or raising deadlines will not turn a down node into a healthy replica.

### 6.4. Query/auth errors must not be retried like timeouts

Wrong partition keys, invalid CQL, missing permissions, bad passwords/TLS, or data type mismatches require **fixing the root cause**. A retry policy should never keep re-running a statement rejected for syntax or permissions.

## 7. Creating a Lab Schema to Tie Errors to CQL

This lab example uses `NetworkTopologyStrategy` and DC name `dc1`; adjust RF to match your actual lab cluster:

~~~cql
CREATE KEYSPACE telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_lab.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

The **partition key** is `(device_id, event_day)`. A query supplying the full partition key:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

A query aligned with the access pattern is **not immune to timeouts**. An overly wide partition, many SSTables/tombstones, or slow replica disks will still drive read p99 up.

If code issues queries missing the partition key or using `ALLOW FILTERING` at scale, revisit the data model rather than relying on retries and token-aware routing.

## 8. Java Driver 4.x: Synchronous Error Classification

### 8.1. Service example using a prepared query

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;
import java.util.logging.Logger;

public final class ReadingService {
    private static final Logger LOG =
        Logger.getLogger(ReadingService.class.getName());

    private final CqlSession session;
    private final PreparedStatement find;

    public ReadingService(CqlSession session) {
        this.session = session;
        this.find = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM telemetry_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 20"
        );
    }

    public Row first(UUID deviceId, LocalDate day) {
        BoundStatement statement = find.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setTimeout(Duration.ofSeconds(3));

        try {
            ResultSet result = session.execute(statement);
            return result.one(); // May be null if no row exists.
        } catch (AllNodesFailedException ex) {
            NodeFailureInspector.report(ex, "read_device_day", LOG);
            throw ex;
        } catch (DriverTimeoutException ex) {
            LOG.warning("read_device_day: driver_timeout");
            throw ex;
        } catch (ReadTimeoutException ex) {
            LOG.warning("read_device_day: server_read_timeout");
            throw ex;
        } catch (WriteTimeoutException ex) {
            LOG.warning("read_device_day: server_write_timeout");
            throw ex;
        } catch (UnavailableException ex) {
            LOG.warning("read_device_day: unavailable");
            throw ex;
        }
    }
}
~~~

`NodeFailureInspector` is the class from Section 5.3 and must be present in the project. The session should be created/closed with the service lifecycle using local DC and auth/TLS—never per HTTP request.

### 8.2. Why catch each type separately?

If code simply does:

~~~java
try {
    return session.execute(statement).one();
} catch (RuntimeException ex) {
    return null; // ANTI-PATTERN.
}
~~~

then the application equates **request failure** with **row not found**. HTTP endpoints may wrongly return `404` instead of reporting an outage, and downstream consumers might recreate records assuming they do not exist.

The right approach is to **record distinct outcomes**, preserve the exception class/cause for upstream handlers, and treat a missing record as not-found only when `SELECT` **succeeded** and `one() == null`.

### 8.3. Limitations of this example

- `setIdempotent(true)` is used for a **simple read `SELECT`**; do not attach it to every mutation.
- A 3-second timeout is illustrative; align it with your API SLO.
- Catching `WriteTimeoutException` in a read service demonstrates classification symmetry; `SELECT`s normally do not throw write timeouts.
- Production systems must handle additional exceptions; do not treat this `catch` list as exhaustive.
- Classifying an error does not by itself authorize a **retry**; evaluate policies and business semantics separately.

## 9. Async: CompletionException Can Wrap Driver Errors

### 9.1. Why not inspect only the wrapper class?

With Java Driver 4.x:

~~~java
CompletionStage<AsyncResultSet> stage =
    session.executeAsync(statement);
~~~

When calling `CompletableFuture.join()` or `Future.get()`, exceptions may be wrapped in `CompletionException` or `ExecutionException`. Unwrap those async wrappers to inspect the underlying driver error.

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

static Throwable unwrapFutureFailure(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
           && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
~~~

Do not blindly strip all cause layers indiscriminately, as that can discard useful context. This helper only unwraps common async wrappers.

### 9.2. Inside the callback

~~~java
stage.whenComplete((result, error) -> {
    if (error == null) {
        recordOutcome("read_device_day", "success");
        return;
    }

    Throwable cause = unwrapFutureFailure(error);

    if (cause instanceof AllNodesFailedException) {
        NodeFailureInspector.report(
            (AllNodesFailedException) cause,
            "read_device_day",
            LOGGER);
    } else if (cause instanceof DriverTimeoutException) {
        LOGGER.warning("read_device_day: driver_timeout");
    } else {
        LOGGER.warning(
            "read_device_day: " + cause.getClass().getSimpleName());
    }

    recordOutcome("read_device_day", "failure");
});
~~~

This is an **illustrative** snippet: `stage`, `LOGGER`, and `recordOutcome` must be defined in your service. Never block callback threads with long I/O; offload to a dedicated bounded-queue executor if needed.

## 10. Retry: Three Conditions That Must All Hold

An error should be retried only when:

1. **The operation is safe to repeat** under business semantics, not merely CQL syntax.
2. **The error is plausibly transient**, not a permanent syntax, auth, or configuration fault.
3. **Deadline, retry budget, and cluster capacity remain**, avoiding piling extra load onto an already congested cluster.

| Operation / error | Safe to auto-retry? | Risk |
|---|---|---|
| `SELECT` by partition key, brief network glitch | Yes, with backoff and limits | Read fanout, load, timeouts |
| `INSERT` with same primary key and fixed values | Must evaluate timestamps/TTLs and concurrent updates | Final state may diverge from expectations |
| Counter increment | **Never retry blindly** | Can double-increment |
| LWT `IF NOT EXISTS` | Handle explicitly with read/verify | Timeout may occur after applying |
| Mutation generating a new UUID per attempt | Never repeat with new IDs | Creates duplicate records |
| Syntax error / invalid query | No | Same statement remains invalid |
| Auth / permission error | Not before fixing configuration | Retries do not grant permissions |
| `AllNodesFailedException` containing TLS errors | Not by default | Permanent failures prolong outage |
| `DriverTimeout` during cluster overload | Usually shed load first | Retry storms worsen p99 |

This table is a **reasoning framework**, not a complete specification of Java Driver 4.x default retry policies.

## 11. Idempotency and Uncertain Write Outcomes

### 11.1. INSERT with stable keys

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (?, ?, ?, ?, ?);
~~~

Retrying with the same primary key and identical values normally avoids creating a distinct row. However:

- A newer mutation timestamp can overwrite a newer concurrent update under timestamp rules.
- Relative TTLs may be recalculated, shifting expiration times.
- External side effects or triggers might fire again.
- A delayed retry arriving much later can clobber newer state.

**Idempotency must be evaluated in business context.** Never set `setIdempotent(true)` on every write assuming `INSERT` is unconditionally safe.

### 11.2. Counters

To run the lab example, first create a valid counter table:

~~~cql
CREATE TABLE telemetry_lab.device_counters (
    device_id uuid PRIMARY KEY,
    samples counter
);
~~~

~~~cql
-- Example: never retry unconditionally when the outcome is ambiguous.
UPDATE telemetry_lab.device_counters
SET samples = samples + 1
WHERE device_id = ?;
~~~

If the first attempt applied the increment but the response was lost, retrying increments twice. Achieving an exactly-once logical effect requires event IDs/deduplication or an alternative data model.

### 11.3. LWTs

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value)
VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

If a request times out after being applied, a retry returns `wasApplied()==false` because the row now exists. That **does not prove the first attempt failed**. Verify the record's ID, invariants, and any external side effects.

### 11.4. DELETE/TTL

`DELETE` creates tombstones. Repeating a delete with a fresh timestamp concurrently with other updates can mask newer mutations. Retrying relative TTLs alters expiration windows. Such operations need explicit timestamp and replay rules rather than naive exception-class retries.

## 12. Retry Budgets, Deadlines, and Backoff

### 12.1. Multi-layer retries multiply load

~~~text
Gateway retries:       max 3 attempts
Application retries:   max 3 attempts
Driver retries:        max 2 attempts

Illustrative uncoordinated worst case:
  3 x 3 x 2 = 18 request attempts
  for a single logical user request.
~~~

Not every policy multiplies identically, yet this calculation highlights **retry amplification**. When a cluster is already overloaded, each layer's retries can trigger a **retry storm**.

### 12.2. Bounded retries

~~~mermaid
flowchart TD
    A["Request failed"] --> B{"Transient?"}
    B -->|No| C["Fail fast or fix config/query"]
    B -->|Yes| D{"Idempotent and budget left?"}
    D -->|No| E["Outcome unknown, reconcile"]
    D -->|Yes| F["Backoff + jitter; cap attempts"]
    F --> G["Retry within remaining deadline"]
    G --> H["Monitor latency, errors, replica load"]
~~~

Do not assume `AllNodesFailedException` is always transient. If the error map shows TLS or credential failures across every node, fixing configuration makes far more sense than retrying.

### 12.3. Coordinating with HTTP deadlines

Illustrative breakdown:

~~~text
HTTP API deadline:          1000 ms
Auth + validation:           100 ms
Cassandra attempts:          700 ms
Mapping + response:          100 ms
Safety margin:               100 ms
~~~

If each Cassandra attempt has a 3-second timeout, the API can no longer honor a 1-second deadline. Budget the **total deadline**, accounting for backoff, in-flight concurrency, and cancellation.

Never raise request timeouts merely to lower exception rates; inspect **end-to-end p99, error budgets, and queue backlogs**.

## 13. Per-Coordinator Errors Are Not Per-Replica ACKs

Suppose:

~~~text
Driver tries coordinator A: connection failed
Driver tries coordinator B: connection failed

getAllErrors():
    A -> connection failure
    B -> connection failure
~~~

This information **does not** tell you:

- Whether replicas R1/R2/R3 hold the target partition.
- Which replicas received mutations from an **earlier request**.
- Whether coordinator C outside the query plan is available.
- Which replicas fsynced their commit logs.
- Whether quorum is reachable from clients on another network segment.

Conversely, a `WriteTimeoutException` returned by a coordinator does not carry a `Node → List<Throwable>` map for every replica. **Per-node client attempts** and **per-replica consistency** measure different scopes.

To assess replica placement, inspect **RF/topology/token metadata, `nodetool status`, and server metrics/logs**. To confirm a write's outcome, **verify business state** or use deduplication/reconciliation—not Java exceptions alone.

## 14. How Routing Keys, Tokens, RF, and Local Datacenter Affect Errors

### 14.1. Candidate coordinators are not necessarily partition replicas

A prepared statement with the full partition key usually lets the Java Driver compute the **routing key** and token, prioritizing coordinators that own the replica set. Still:

- Token-aware load balancing is a **client-side coordinator selection strategy**.
- A coordinator outside the replica set can still execute requests properly.
- RF, datacenter, and rack determine which **replicas** store the data.
- CL determines how many responses are required for success.
- Failing to connect to a coordinator does not prove replicas lack the data.

For instance, a partition may be replicated on A, B, and C while the Java app cannot reach **candidate coordinators** A/B. `AllNodesFailedException.getAllErrors()` will record failures on A and B while C still holds the data. Conversely, if a reachable coordinator returns `ReadTimeoutException`, examine replica responses and CL rather than only the driver connection pool.

### 14.2. Multi-DC and `LOCAL_QUORUM`

Suppose a keyspace uses `NetworkTopologyStrategy`:

~~~cql
-- Multi-DC replication example; replace DC names to match your cluster.
CREATE KEYSPACE multi_dc_demo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

If a Java client runs in `dc1` with `localDatacenter` set to `dc1`, load balancing prioritizes local coordinators. If the app→`dc1` network fails, `AllNodesFailedException` **does not prove `dc2` is down**.

With `LOCAL_QUORUM`, success depends on a quorum within the **local DC** for that request. It does not mean writes were acknowledged by quorums in every DC.

**Never fix timeouts by switching `LOCAL_QUORUM` to `ONE`** without evaluating correctness, stale reads, and unsynchronized-node risks. That is a correctness/availability trade-off.

### 14.3. Topology changes during rolling upgrades

During bootstrap, node replacement, or rolling upgrades:

- Nodes may be `UJ`, `DN`, or restarting.
- Driver metadata and query plans may briefly lag gossip/topology updates.
- Hint delivery, streaming, compaction, and commit-log replay can spike p99.
- Error maps may shift rapidly per node as pools re-establish connections.

Record **UTC timestamps, node/driver versions, DC/rack, and change IDs**. Never hardcode a static pre-bootstrap coordinator list and treat every difference as a bug.

## 15. Correlating Java Exceptions with `nodetool`

### 15.1. Common read-only inspection commands

~~~bash
# Node status, datacenter/rack, token ownership.
nodetool status

# Active/Pending/Completed executors and dropped messages.
nodetool tpstats

# Pending compactions and task progress.
nodetool compactionstats

# SSTable streaming during repair/bootstrap/rebuild.
nodetool netstats

# Per-table read/write and SSTable statistics.
nodetool tablestats telemetry_lab.readings_by_device_day

# Latency histograms when supported by version.
nodetool tablehistograms telemetry_lab readings_by_device_day
~~~

These commands are for **observation**, though output, syntax, and scope can vary by Cassandra version. Check `nodetool help` and release docs. Commands like `flush`, `repair`, or `compact` **generate load**—never run them casually just to gather stats.

### 15.2. Correlation matrix

| Java symptom | What to check in Cassandra / infra | Hypothesis |
|---|---|---|
| Rising `DriverTimeoutException` + read p99 | ReadStage Pending, SSTables per read, disk latency | Read path overload / tombstones / hot partition |
| Rising driver timeouts during backfill | Mutation/flush/compaction queues, free disk | Background jobs contending for resources |
| `AllNodesFailed` with widespread TCP errors | Firewall, DNS, network, status, native transport | App→coordinator connectivity failure |
| `AllNodesFailed` with TLS failures | Cert chain, truststore, expiry, hostname | Security handshake failing |
| Errors concentrated on one node | CPU/GC, disk, pool, partition hotspot | Localized node or app→node path issue |
| Rising `WriteTimeoutException` | Commit-log sync latency, MutationStage, RF/CL | Slow replicas missing ACK deadlines |
| Rising `ReadTimeoutException` after repair | Disk/streaming/network and replica read latency | Repair/streaming competing for I/O |
| `UnavailableException` when nodes are down | `nodetool status`, RF/DC, rack | Insufficient replicas for CL |
| One query times out while others stay healthy | Schema, partition key, page size, LIMIT, tombstones | Query shape or data skew |
| Errors right after driver deploy | Driver config/version, local DC, TLS, profile | Client regression rather than server fault |

### 15.3. Measure deltas rather than raw counters

Suppose `tpstats` on a node shows:

~~~text
Time       ReadStage Pending     Completed     READ Dropped
10:00                 80           500000                5
10:01                980           512000               65

Completion rate over 60 seconds:
    (512000 - 500000) / 60 = 200 tasks/s

Pending grew by 900; READ Dropped grew by 60.
~~~

`Completed` is a **cumulative stage counter**, not raw CQL QPS. `Dropped` counts by message type do not map 1:1 to failed `SELECT`s. If a node restarts between samples, counters reset; exclude that interval from delta math.

**A node showing `UN` does not mean it meets SLOs.** It can have backed-up pending queues or disk stalls causing driver timeouts.

### 15.4. Empty `netstats` does not guarantee healthy networking

`nodetool netstats` focuses mainly on **SSTable streaming**. It does not display all CQL traffic, gossip, native transport, TLS failures, or connection pools. If `netstats` shows no streams while `AllNodesFailedException` reports TCP failures, you still must inspect **app-to-node networking**.

## 16. Safe Logging and Metrics

### 16.1. A structured failure log event

~~~text
event=cassandra_request_failure
query_id=read_device_day
outcome=driver_timeout
error_class=DriverTimeoutException
consistency=LOCAL_QUORUM
request_timeout_ms=3000
elapsed_ms=3005
routing_key_present=true
local_dc=dc1
attempt_count=unknown
~~~

This is an **application-defined format**, not a built-in Cassandra log format. If your instrumentation does not track exact attempt counts, log **unknown** rather than guessing.

For `AllNodesFailedException`, include the node count and error categories:

~~~text
event=cassandra_request_failure
query_id=read_device_day
outcome=all_nodes_failed
node_entries=3
node_error_family.connection=2
node_error_family.handshake=1
~~~

`node_error_family` is an **observability classification label**, not a mandatory driver enum. When grouping causes, keep versioned mappings and preserve raw error classes in authorized debug channels.

### 16.2. Avoid leaks and cardinality explosions

Never put the following into metric labels or public logs:

- Raw `device_id`, `tenant_id`, emails, access tokens, or passwords.
- Bind values or raw CQL with interpolated sensitive data.
- Full exception messages or stack traces on **every** failed request.
- Raw routing key bytes or per-partition tokens as metric labels.
- Internal IPs/hostnames if policy restricts sharing them.

Instead use **static query IDs, outcomes, error classes, controlled node identities, DC, and sampling**. Deep diagnostics belong in access-controlled audit/debug logs with defined retention.

### 16.3. Minimum dashboard

| Layer | What to measure | Why |
|---|---|---|
| HTTP/Java | QPS, p50/p95/p99, timeouts, 5xx, request cancellations | Shows user impact |
| Driver | Errors by class, retry/speculative attempts, in-flight, connection failures | Separates client budget from connectivity |
| Per-node errors | Node metadata, counts per error class | Distinguishes single-node vs. local-DC patterns |
| Cassandra | Read/write p99, `tpstats` pending/dropped | Detects coordinator/replica overload |
| Storage | Free disk, fsync/write/read latency, pending compactions | Pinpoints I/O bottlenecks |
| Network | RTT, retransmits, packet loss, TLS handshakes | Separates transport from query issues |
| Topology | Nodes UP/DOWN, RF/CL, DC/rack, streaming/repair | Assesses quorum capacity |

**Never average per-node p99s to compute a cluster-wide p99.** Percentiles must come from proper histograms/distributions, and you must track **timeout/error rates** because timed-out requests may be excluded from success-latency histograms.

## 17. Runbook A — Rapid Surge in `DriverTimeoutException`

**Scenario:** a read API's p99 jumps from 90 ms to 1,800 ms. Driver request timeout is 3 seconds, `DriverTimeoutException` spikes, and nodes still report `UN`.

1. **Scope the impact:** query ID, keyspace/table, CL, tenant/operation group, DC, start time. Never expose bind values in tickets.
2. **Measure client and server:** read QPS, in-flight requests, connection pools, p99, retries, timeout rates; `tpstats`, disk/GC, and `compactionstats`.
3. **Inspect query shape:** full partition key present, `ALLOW FILTERING`, SSTable/tombstone counts, partition width, page size, and total pages.
4. **Check background work:** repair/streaming, backfill, compaction, bootstrap, volume throttling, or disk I/O errors.
5. **Shed load safely:** pause non-urgent backfills, enforce bounded concurrency, curb retry amplification; prioritize keeping core APIs alive.
6. **Adjust timeouts only with justification:** if a valid workload genuinely needs more time within SLO, adjust carefully within budget; never use it as a substitute for fixing hotspots or disk saturation.
7. **Verify recovery:** queues drain, p99/error/timeout rates fall, disk has headroom, and CL correctness remains intact.

**Never turn timeouts into “no row found”.** For `SELECT`, only `ResultSet.one() == null` **after a successful query** indicates no matching row.

## 18. Runbook B — `AllNodesFailedException` After Certificate Changes

**Scenario:** a newly deployed set of Java pods hits `AllNodesFailedException` on every request, while older pods continue talking to Cassandra normally.

1. **Inspect `getAllErrors()`:** summarize error classes per node; look for handshake, connection initialization, and auth failures.
2. **Isolate the rollout:** only new pods, one namespace, one region, or all clients? Compare truststores/secrets/configs against healthy pods.
3. **Inspect TLS:** CA chain, certificate expiration, hostname verification, protocol/ciphers, and rotation timeline.
4. **Check local DC and networking:** contact points, native transport port, DNS, load balancing; `nodetool status` alone does not verify app→node connectivity.
5. **Never disable TLS in production** for a “quick test”; use lab environments and security procedures.
6. **Roll back config if needed:** follow change/incident runbooks and verify new pods reconnect cleanly.
7. **Re-check per-node failures:** handshake errors disappear, query successes recover, p99 stabilizes, and pools rebuild.
8. **Update preventive controls:** automate cert rotation tests, add early expiry alerts, and run driver smoke tests.

When the cause is permanent auth/TLS failure, infinite retries only create log storms and waste resources.

## 19. Runbook C — Write Timeout with Uncertain Outcome

**Scenario:** a service writes an order and receives `DriverTimeoutException` or `WriteTimeoutException`. The API gateway wants to retry the `POST` immediately.

### Step 1 — Check operation ID

Is there a stable `order_id`/`event_id` across all attempts? Are counters, LWTs, TTLs, dynamic timestamps, emails, or payment side effects involved?

### Step 2 — Never treat a timeout as a rollback

Some replicas may have applied the mutation even though the client did not see success. Record outcome **`UNKNOWN`** until proven otherwise.

### Step 3 — Reconcile data

Read by primary key at the proper CL; verify status, version, ID, and invariants. With LWTs, recognize that a retry returning `wasApplied()==false` **may** simply mean the first attempt applied.

### Step 4 — Retry safely only when conditions hold

Replay **the same logical operation** only if idempotency is designed in and deadline/retry budget remain. Never generate a fresh UUID or re-fire non-idempotent external side effects.

### Step 5 — Diagnose server health

Inspect RF/CL, mutation/flush queues, commit-log I/O, disk, network, and available replicas. Distinguish server timeouts from driver deadlines.

### Step 6 — Close the business loop

If an exactly-once logical effect is required, implement deduplication, event logs/outboxes, or reconciliation. **Driver retries alone do not guarantee exactly-once semantics.**

## 20. Runbook D — Errors Concentrated on One Node in the Error Map

**Scenario:** across many requests, `getAllErrors()` repeatedly shows pool-busy or connection-closed errors on node A, while requests through B and C succeed.

1. Compare error counts over time and by class rather than looking at a single exception.
2. Check whether A is disproportionately selected as coordinator due to token-aware routing and a hot partition.
3. Measure per-node in-flight requests and connection pool utilization on the Java client.
4. Check disk latency, CPU/GC, `tpstats` pending/dropped, compaction, commit log, and logs on A.
5. If failures come from only one app region, check network RTT/TCP resets between that region and A.
6. Do not manually pin all traffic to B/C; they may become new hotspots and still must satisfy RF/CL.
7. Shed load or restore network/node capacity per a rollback-safe runbook.
8. Verify error-class frequency, p99, timeouts, CPU/disk, and replica health return to baseline.

**A node missing from one request's error map is not guaranteed healthy.** It may simply not have been in that query plan or attempted.

## 21. Quick Triage Decision Tree

~~~mermaid
flowchart TD
    A["Cassandra exception from Java"] --> B{"Error type?"}
    B -->|DriverTimeoutException| C["Deadline/p99/in-flight/network"]
    B -->|AllNodesFailedException| D["getAllErrors by node/cause"]
    B -->|Read/WriteTimeout| E["Replica responses, CL, I/O"]
    B -->|Unavailable| F["RF/DC, nodes UP/DOWN, quorum"]
    B -->|Invalid/Auth| G["Fix query/config/permissions; fail fast"]
    C --> H{"Transient? idempotent? budget left?"}
    D --> H
    E --> H
    F --> H
    H -->|Yes| I["Bounded retry + jitter + observability"]
    H -->|No/unknown| J["No blind retry; reconcile"]
    I --> K["Re-measure API SLO + backend load"]
    J --> K
~~~

This flowchart is a **triage framework** and does not replace version- and domain-specific retry policies. An `AllNodesFailedException` caused by permanent TLS misconfiguration must follow the config-fix path, not the retry branch.

## 22. Common Programming Anti-Patterns

| Anti-pattern | Consequence | Correct practice |
|---|---|---|
| Catch `RuntimeException` and return `null` | Turns timeouts into not-found | Separate zero-row results from request failures |
| Catch all errors and retry immediately | Retry storms, broken semantics | Classify transient/idempotent/budget first |
| Log `AllNodesFailed` as a single generic line | Hides node/cause differences | Use `getAllErrors()`, log error class/node |
| Put full `getMessage()` into metric labels | Leaks PII, explodes cardinality | Use query ID, error type, and sampling |
| Set `setIdempotent(true)` on counters | Double-counting | Design deduplication; never retry blindly |
| Use `IF NOT EXISTS` and retry without checking row | Misinterprets `wasApplied` | Verify operation identity and invariants |
| Increase driver timeout indefinitely | Holds queues/heap too long | Fix bottlenecks; enforce bounded deadlines |
| Create a new `CqlSession` per request | Connection churn and latency | Reuse a long-lived session |
| Use `ONE` to hide quorum errors | Breaks consistency guarantees | Fix replicas, topology, or capacity |
| Let gateway, app, and driver retry independently | Multiplies attempt counts | Enforce an end-to-end retry budget |
| Forget to unwrap async `CompletionException` | Misclassifies root exceptions | Unwrap future wrappers cleanly |
| Treat `AllNodesFailed` as whole cluster DOWN | Mis-scopes incidents | Inspect query plan, DC, and per-node map |
| Treat per-node map as replica ACK map | Misjudges write persistence | Verify consistency and business state |

## 23. Controlled Fault Testing in a Lab Environment

### 23.1. Before testing

- Use an **isolated Cassandra lab cluster** and synthetic data; never run fault injection in production.
- Record driver/server versions, RF/CL, topology, request timeouts, and retry policies.
- Ensure clean lab teardown/recovery and keep test apps disconnected from real clusters.
- Define whether each test targets **client deadlines**, **node connectivity**, or **replica timeouts**.
- Cap QPS and concurrency so fault tests do not become destructive load tests.

### 23.2. Test scenarios

| Scenario | What to verify |
|---|---|
| Low request deadline under controlled load | App classifies driver timeouts properly rather than reporting missing rows |
| App blocked from reaching some coordinators | `AllNodesFailedException` if no candidate succeeds; `getAllErrors()` reflects affected nodes |
| Broken TLS truststore in lab | Connection/handshake error classified properly; no infinite retries |
| Insufficient replicas for `LOCAL_QUORUM` | Distinguishes unavailable/server timeouts from client deadlines |
| `SELECT` validly returns 0 rows | `one()==null` records `outcome=success`, never counted as a timeout |
| Simulated counter write timeout | Policy avoids blind retries to prevent double-counting |
| LWT timeout after apply | Reconciliation distinguishes an already-applied first attempt from a false condition |
| Node restart and recovery | Driver reconnects, error rates drop, no log storm |
| Multiple callers retrying concurrently | In-flight count, QPS, and retry amplification remain bounded |
| Async failure wrapper | Handler unwraps and classifies the root cause without swallowing exceptions |

In practice, simply setting a very short timeout **does not guarantee** reproducing the exact same exception class on every run; OS scheduling, network timing, and server load can shift outcomes. Tests should verify **classification logic and guardrails**, not force a brittle millisecond-specific exception type.

### 23.3. Log security testing

Send requests with test UUIDs/tenants and verify:

- App logs record only the query template ID, never bind values.
- Metric labels contain no raw partition keys.
- Per-node failure logs contain no secrets or TLS private material.
- Error storms are sampled or rate-limited.
- Debug traces, if enabled, enforce access controls and retention limits.

## 24. Practice Questions with Answers

### Question 1 — Does a timeout roll back?

Java receives `DriverTimeoutException` after an `INSERT`. Can you conclude the mutation was not written?

**Answer:** No. The client deadline expired, yet the coordinator or replicas may have applied the mutation. Verify the outcome and check idempotency before retrying.

### Question 2 — Two map entries mean how many nodes are DOWN?

`AllNodesFailedException.getAllErrors()` contains nodes A and B in a six-node cluster. Does that mean all six nodes are DOWN?

**Answer:** No. The map only lists nodes and causes recorded by the driver in its query plan; it does not probe every physical node.

### Question 3 — Meaning of `getAllErrors` values

What does `Map<Node, List<Throwable>>` represent?

**Answer:** For each candidate coordinator, the list of errors encountered while the driver attempted the request. It is not a count of replica ACKs.

### Question 4 — Server read timeout vs. driver timeout

The coordinator fails to collect enough replica responses for `LOCAL_QUORUM` and returns `ReadTimeoutException`. Is this a `DriverTimeoutException`?

**Answer:** No. Server/coordinator timeouts and client driver deadlines are two distinct layers.

### Question 5 — Null from `SELECT`

`ResultSet.one() == null` after a successful `SELECT`. Is this a timeout?

**Answer:** No. The query succeeded, and no live row matched the predicate.

### Question 6 — TLS

All candidate coordinators report handshake errors after certificate rotation. Should you retry infinitely?

**Answer:** No. Inspect the CA/truststore/certificate/hostname and fix the security configuration.

### Question 7 — Local DC

An app configures the wrong local DC and receives `AllNodesFailed`. Does this prove data loss?

**Answer:** No. The query plan may simply lack usable coordinators; verify local DC settings and metadata.

### Question 8 — Counters

A counter increment times out; the app retries and the counter increases twice. Why?

**Answer:** The first attempt may have applied despite the lost response; counter increments are not idempotent. Use deduplication or a different data model.

### Question 9 — LWTs

The first `INSERT ... IF NOT EXISTS` times out; the retry returns `wasApplied() == false`. Is it certain the first attempt failed?

**Answer:** No. The retry may be seeing the row created by the first attempt; reconcile IDs and invariants.

### Question 10 — Logging

Should you put `device_id` or full CQL with bind values into Prometheus labels?

**Answer:** No. Use static query IDs, error types, DCs, and approved metadata to avoid high cardinality and data exposure.

### Question 11 — Retry amplification

Gateway allows 3 attempts, app allows 3 attempts, driver allows 2 attempts, uncoordinated. What is the illustrative worst case?

**Answer:** `3 × 3 × 2 = 18` attempts for one logical request. Enforce an end-to-end retry budget.

### Question 12 — Missing quorum

RF=3, only one replica is available, and CL is `LOCAL_QUORUM`. Will raising the timeout to 30 seconds guarantee success?

**Answer:** No. Quorum requires two replicas; timeouts cannot create missing replicas.

### Question 13 — P99 after raising timeouts

`DriverTimeoutException` rates drop, but API p99 triples. Is this definitely an improvement?

**Answer:** No. The system may simply be holding requests longer. Evaluate SLOs, error budgets, in-flight counts, queues, and load.

### Question 14 — Invalid query

CQL is rejected due to a missing partition key predicate. Will retrying the same statement help?

**Answer:** No. Fix the query shape, schema, or access path; do not retry invalid queries.

### Question 15 — Multiple errors on one node

Per-node error maps across many requests show pool-busy errors on node A. Does A definitely have broken hardware?

**Answer:** No. It could be a hotspot, overload, connection limit, disk stall, GC, or network issue. Examine all supporting evidence.

### Question 16 — Async wrapper

`join()` throws `CompletionException` wrapping `AllNodesFailedException`. What should the handler do?

**Answer:** Unwrap the future wrapper, classify the underlying cause, inspect `getAllErrors()`, and preserve trace context cleanly.

### Question 17 — Retrying `SELECT`

An idempotent `SELECT` hits a transient network error. Can it retry infinitely as long as the caller waits?

**Answer:** No. Enforce bounded attempts, backoff, deadlines, and load monitoring; excessive retries can congest the cluster.

### Question 18 — Coordinators and replicas

`getAllErrors()` shows connection errors on A and B. Can you assert that none of the three replicas persisted an earlier write?

**Answer:** No. That is a map of candidate coordinators, not replica states or commit logs.

## 25. Production Readiness Checklist for Java Services

### 25.1. Java application

~~~text
[ ] CqlSession is reused; auth/TLS and local DC are configured properly.
[ ] Java Driver 4.x version, protocol, and retry policy are verified.
[ ] Prepared/bound statements, partition keys, and CL match business needs.
[ ] DriverTimeout, AllNodesFailed, Read/WriteTimeout, and Unavailable
    have distinct outcomes, logs, and metrics.
[ ] AllNodesFailed inspects getAllErrors() by node and error class.
[ ] Per-node error maps are never mistaken for per-replica ACK maps.
[ ] Driver timeouts fit inside end-to-end API deadlines.
[ ] Multi-layer retries share an end-to-end budget, backoff, and rate limits.
[ ] Mutation idempotency is evaluated case by case, never assigned blindly.
[ ] LWTs, counters, TTLs, and DELETEs have dedicated outcome/reconciliation logic.
[ ] Async wrappers are unwrapped cleanly and errors are propagated properly.
[ ] Error logging omits PII, credentials, and raw query values.
[ ] Log storms are rate-limited; p99, timeouts, retries, and in-flight counts are tracked.
~~~

### 25.2. Cassandra cluster

~~~text
[ ] RF, NetworkTopologyStrategy, DC/rack, and CL align with SLOs.
[ ] nodetool status/topology shows no unassessed outages.
[ ] tpstats Pending/Dropped are measured as deltas over intervals.
[ ] compactionstats, memtable flushes, and commit-log I/O have headroom.
[ ] netstats/repair/streaming do not cause unexpected saturation.
[ ] Free disk, read/write disk latency, and CPU/GC remain stable.
[ ] App-to-node TLS/network paths are monitored.
[ ] Node latencies are correlated with coordinator and replica roles.
[ ] Backup/restore, outage, and rolling-upgrade runbooks are clear.
[ ] Timeouts/concurrency are never raised to mask data issues or full disks.
~~~

## 26. Summary

When the Java Driver reports an error, distinguish these three layers clearly:

1. **`DriverTimeoutException`:** the driver's request deadline expired. It does not prove the server never received or applied the mutation.
2. **`AllNodesFailedException`:** the request failed across candidate coordinators; use **`getAllErrors()`** to inspect per-node causes. Never assume the entire cluster is DOWN.
3. **`ReadTimeoutException`, `WriteTimeoutException`, `UnavailableException`:** returned by Cassandra servers regarding replicas, CL, and availability.
4. **Nodes in the map are not replica ACKs:** a client-side per-node error map differs from replica data state and commit-log durability.
5. **Retries are safe only with business understanding**, error classification, and deadlines; for counters, LWTs, TTLs, or concurrent updates, verify outcomes explicitly.
6. **Prevent retry storms:** use bounded attempts, exponential backoff with jitter, rate limits, circuit breakers, and backpressure.
7. **Correlate multi-layer metrics:** driver, coordinator, replicas, disk/GC, compaction, streaming, network, and query shape.
8. **Protect sensitive data:** log static query IDs, error classes, and permitted node metadata; never log raw bind values or secrets.
9. **Follow evidence-driven runbooks:** scope the failure, restore nodes/config/queries, and verify p99, error rates, and correctness.

The core question is not **“how many times should we retry on timeout?”**, but rather **“which deadline expired, which candidate coordinators failed and why, how far might replicas have processed the mutation, and is retrying consistent with correctness and system load budgets?”**. Answering with telemetry and business invariants lets you handle failures without turning a single slow request into a cluster-wide outage.
