# Default Retry Policy, Trigger Conditions, and Separately Handled Errors in the Cassandra Java Driver

> **Chapter:** Java Retries and Errors  
> **Audience:** Java developers and Apache Cassandra operators who want to distinguish server errors, network errors, driver-side timeouts, `UNAVAILABLE` responses, and retry mechanics. Content focuses on Java Driver **4.x** (specifically 4.17/4.18), using CQL/Java 17 and lab examples. Callback APIs with the `Verdict` suffix apply starting in driver **4.10**; earlier releases use different APIs. Any fault configuration or simulation in this lesson must only be executed on an **approved lab or staging cluster**.

## 1. Learning Objectives

After completing this lesson, learners will be able to:

1. Explain the role of `DefaultRetryPolicy` in the `CqlSession.execute` lifecycle and the difference between **one logical request** and multiple **node attempts/messages**.
2. State the exact default response to `UNAVAILABLE`, `READ_TIMEOUT`, `WRITE_TIMEOUT`, pre-response connection drops, and other server errors.
3. Distinguish branches that **do not require the idempotent flag** from branches that **retry only when the statement is idempotent**, avoiding the false rule of thumb “every retry requires `idempotence=true`”.
4. Understand `BATCH_LOG` in `WriteTimeoutException`, distinguishing it from `BATCH`, `UNLOGGED_BATCH`, `SIMPLE`, and batch atomicity.
5. Recognize cases the driver **handles directly outside `RetryPolicy`**: unsent network writes, `UNPREPARED` requiring re-preparation, and bootstrapping nodes.
6. List errors that are **never retried**: query validation, function failures, protocol errors, and business errors that resending cannot resolve.
7. Distinguish **server-side timeouts** from `DriverTimeoutException`, Java deadlines, cancellation, network ambiguity, and unknown write outcomes.
8. Use `basic.request.default-idempotence`, `Statement.setIdempotent`, `advanced.retry-policy.class`, execution profiles, and driver metrics safely.
9. Write Java exception handling with exact exception classes, return sensible application errors, and apply **bounded application retries/backoff** only after evaluating idempotency and deadlines.
10. Run CQL/Java labs observing successes, validation errors, and simulated retry decision matrices **without breaking the cluster**.

**Context of `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra is a distributed wide-column database; the partition key determines tokens/natural replicas, while replication factor (RF) and consistency level (CL) govern read/write requirements. The Java Driver includes retries to cope with certain transient faults—it **does not** automatically fix schemas, partition hotspots, missing replication, compaction backlogs, or domain design flaws. Sound retries must respect both **data correctness** and SLOs.

## 2. Where Does Retry Sit in the Request Path?

~~~text
Java Application
    |
    |  session.execute(statement)
    v
    Logical CQL request + deadline + profile + idempotence
    |
    v
Load balancing: query plan [node A, node B, node C, ...]
    |
    +--> Attempt #1: coordinator A
    |         |
    |         +-- Success -> ResultSet / ACK
    |         |
    |         +-- Error response from A
    |         |       -> RetryPolicy receives matching error type
    |         |          -> retry SAME / retry NEXT / RETHROW / IGNORE
    |         |
    |         +-- Failure before network write was attempted
    |         |       -> driver transparently moves to next node
    |         |
    |         +-- UNPREPARED
    |                 -> driver transparently reprepares and resends
    |
    +--> Attempt #2 (only if eligible and deadline remains)
    |         |
    |         +--> node A or node B
    |
    v
Application ultimately sees: success, server error, or client timeout
~~~

A single **request** in session metrics can generate **multiple node messages/attempts** due to retries or speculative executions. This impacts latency, CPU, network, and Cassandra coordinators. Never celebrate a rising “application success rate” while ignoring attempt counts and cluster pressure.

### 2.1. Three error layers to separate

| Layer | Examples | Who decides whether to retry? |
|---|---|---|
| **Application** | Invalid input, invalid state transition, quota/tenant authorization | Domain code; usually **do not retry** |
| **Driver transport/request** | Connection pool exhaustion, connection reset, query deadline | Some hard-coded branches; `RetryPolicy` in eligible branches; app may decide further |
| **Coordinator/replicas** | `UNAVAILABLE`, `READ_TIMEOUT`, `WRITE_TIMEOUT`, `READ_FAILURE`, `OVERLOADED` | Coordinator returns server error; driver policy acts by type; app catches if rethrown |

**Important:** A `WriteTimeoutException` proves **the write CL was not sufficiently acknowledged**, **not** that the mutation never touched any replica. Resending can duplicate side effects if the operation is not idempotent.

### 2.2. Four verdicts of a retry policy

| Verdict | Meaning | Risk if misused |
|---|---|---|
| `RETRY_SAME` | Resend via the **same coordinator** | Repeats load against a slow node |
| `RETRY_NEXT` | Send via the next node in the query plan | Can spread load across coordinators; does not guarantee healthy nodes remain |
| `RETHROW` | Surface the error to the caller / fail the future | Application must classify, return an error, and potentially reconcile |
| `IGNORE` | Treat the error as success, returning an empty result | **Masks consistency guarantees / unknown outcomes** |

`DefaultRetryPolicy` relies mainly on `RETRY_SAME`, `RETRY_NEXT`, and `RETHROW` in specific cases. **Never choose `IGNORE` in a custom policy to “stop seeing errors”**: an empty result does not prove data was adequately written or read.

## 3. Default Configuration of Java Driver 4.x

Java Driver 4.x uses `DefaultRetryPolicy` by default without extra config:

~~~hocon
datastax-java-driver {
  advanced.retry-policy {
    class = DefaultRetryPolicy
  }

  basic.request {
    timeout = 2 seconds
    default-idempotence = false
  }
}
~~~

This is an **illustrative skeleton**: check actual timeout defaults in your release/application's effective config rather than treating `2 seconds` as a production rule. More importantly, `basic.request.default-idempotence=false` is the default in driver 4.17, blocking retry callbacks for errors where **a mutation may already have executed** on statements not marked safe. See [Java Driver 4.18 — Retries](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) and [Idempotence](https://apache.github.io/cassandra-java-driver/4.18.1/core/idempotence/).

### 3.1. Retry policy is not reconnection policy

- **Retry policy** governs how a single failed CQL request is handled when contacting coordinators.
- **Reconnection policy** governs how the driver periodically re-establishes connections to disconnected nodes.
- **Load balancing policy** builds the query plan and selects coordinators.
- **Speculative execution policy** can send **parallel** requests to additional nodes on slow responses without waiting for an error; only for statements marked idempotent.
- **Application retry/backoff** starts a fresh logical execution from the application, potentially *after* the driver already retried; budget total time end-to-end.

Some errors are handled in **hard-coded paths before reaching the policy**, and a driver-retried request can succeed without the application ever seeing an exception. Never write an outer retry loop solely because requests occasionally take longer.

### 3.2. `retryCount` is not the number of API calls made by the application

In `onXxxVerdict(..., retryCount)`, `retryCount=0` indicates the policy's first evaluation for that request; it counts prior policy invocations for the request, not source event indices, cluster-wide attempts, or application re-invocations of `session.execute`. `DefaultRetryPolicy` typically performs at most **one policy-driven retry** per logical request in supported branches.

**Do not assume** every request produces at most two network messages: hard-coded re-prepare/unsent paths, speculative executions, and **outer application retries** can generate more traffic. Deadlines and exhausted query plans can also prevent retries before they fire.

## 4. `DefaultRetryPolicy` Behavior Matrix

| Error type / callback | Primary condition | Default verdict | Requires idempotent statement? |
|---|---|---|---|
| `UNAVAILABLE` / `onUnavailableVerdict` | First policy decision; coordinator reports insufficient live replicas | **RETRY_NEXT at most once**; then RETHROW | **Not required** for this callback |
| `READ_TIMEOUT` / `onReadTimeoutVerdict` | First decision, `received >= blockFor`, **`dataPresent=false`** | **RETRY_SAME once**; otherwise RETHROW | **Not required** for this callback |
| `WRITE_TIMEOUT` / `onWriteTimeoutVerdict` | First decision, `writeType=BATCH_LOG` | **RETRY_SAME once**; other write types RETHROW | **Yes**, gated before entering callback |
| Request aborted / `onRequestAbortedVerdict` | `ClosedConnectionException` or `HeartbeatException` | **RETRY_NEXT** if connection closed; abnormal decode errors RETHROW | **Yes** |
| Other server error / `onErrorResponseVerdict` | `OverloadedException`, `ServerError`, etc. | **RETRY_NEXT** for errors where trying another node may help; `ReadFailure`/`WriteFailure` RETHROW | **Yes** |
| `QueryValidationException` and subclasses | Invalid CQL/schema/authorization/syntax | **RETHROW immediately**, outside policy | Not applicable |
| `FunctionFailureException`, `ProtocolError` | Server UDF/protocol failure | **RETHROW immediately**, outside policy | Not applicable |
| Errors **before sending request** | Pool/node failed prior to network write | Driver transparently tries next node | Policy/idempotence not needed |
| `UNPREPARED` | Coordinator does not recognize prepared statement ID | Driver transparently **reprepares and retries SAME** | Dedicated mechanism |
| Sent to bootstrapping node | Node cannot yet serve CQL requests | Driver transparently tries next node | Dedicated mechanism |
| `DriverTimeoutException` | Driver-side deadline expired without a final response | **Does not** invoke `onReadTimeout/WriteTimeout` callbacks | App handles deadline / unknown outcome |

**Two crucial idempotence exceptions:** `onUnavailableVerdict` and `onReadTimeoutVerdict` are branches that do not require `isIdempotent=true` because they represent scenarios where a mutation has not completed per the coordinator's response; write timeout, aborted, and other-error callbacks do require it. Distinguish **policy callbacks** from outer application code retrying after an exception. See [DataStax — Retry policies](https://docs.datastax.com/en/astra-db-classic/drivers/retry-policies.html) and [Apache Java Driver — Retries](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/).

### 4.1. No “infinite retries while nodes remain”

Even with RF=3 and multiple nodes in the query plan, `DefaultRetryPolicy` does not loop endlessly across all coordinators. It enforces **strict retry limits** and request timeouts. If the app sees recurring errors, measure node/replica availability, CL, timeouts, and attempt counts rather than changing policies to retry infinitely.

### 4.2. Retries never downgrade consistency by default

`DefaultRetryPolicy` preserves the **request's consistency level** when retrying. If a `LOCAL_QUORUM` request lacks replicas, trying another node helps only when the first coordinator had a stale topology view or network isolation; it never downgrades to `ONE`. Changing CL alters the **data contract**, not a safe universal recovery trick.

## 5. `UNAVAILABLE` — Coordinator Sees Insufficient Replicas

### 5.1. Why does it occur?

The coordinator received a request at a specific CL, yet based on its liveness view it **knows** too few replicas are alive to satisfy it:

~~~text
Keyspace NetworkTopologyStrategy: dc1 RF=3
Read CL: LOCAL_QUORUM       => requires 2 full replicas in dc1

  Replica A: UP          Replica B: DOWN     Replica C: DOWN
         \                      |                   /
          \------------------- coordinator ----------/
                             |
                     known live replicas=1
                     required responses=2
                             |
                      UNAVAILABLE
~~~

Unlike `READ_TIMEOUT`: in `UNAVAILABLE`, the coordinator recognizes **before executing** that CL cannot be met under current liveness; in `READ_TIMEOUT`, it initially saw enough replicas, but responses failed to arrive in time.

### 5.2. `DefaultRetryPolicy` behavior

Per [Apache Java Driver retries](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/):

- On the first retry evaluation (`retryCount=0`), the driver **tries the next node in the query plan** once.
- Rationale: coordinator A might suffer a **network partition/isolation** and think remaining replicas are dead, whereas coordinator B has an intact view.
- If the retry fails or the budget is spent, the policy **rethrows**. If the query plan is exhausted or the deadline expires, the request also fails.
- This callback **does not require** `idempotent=true`, unlike write timeouts or post-send disconnects.
- **CL is never lowered** on retry.

### 5.3. Inspecting exception details

~~~java
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;

try {
    session.execute(request);
} catch (UnavailableException ex) {
    System.err.printf(
        "UNAVAILABLE coordinator=%s cl=%s required=%d alive=%d%n",
        ex.getCoordinator(),
        ex.getConsistencyLevel(),
        ex.getRequired(),
        ex.getAlive());
    throw ex;
}
~~~

This snippet illustrates **when the exception reaches the application directly**. If the driver tried multiple coordinators, the application may receive `AllNodesFailedException` wrapping per-node errors; inspect the inner causes. Never log raw bind values, credentials, or tenant IDs for debugging.

### 5.4. What **not** to do

- Do not automatically switch `LOCAL_QUORUM` to `ONE` just to make requests “succeed”.
- Do not call `session.execute` 10 more times immediately while replicas remain DOWN.
- Do not raise `basic.request.timeout` to fix an explicit lack of replicas.
- Do not assume “nodes UP” from one client proves sufficient **natural replicas** exist for every token range.

**Remediation:** check `nodetool status`, keyspace RF/DC, inter-node networking, gossip/liveness, bootstrapping/replacing/repairing nodes, and token ownership. If your architecture includes intentional DC failover, route traffic via an **active runbook**, not hidden inside a retry policy.

## 6. `READ_TIMEOUT` — Enough Responses Without Data, or Too Few Responses

### 6.1. Callback parameters

~~~text
onReadTimeoutVerdict(
  request,
  cl,
  blockFor,
  received,
  dataPresent,
  retryCount
)
~~~

| Parameter | Meaning |
|---|---|
| `cl` | Original CL, such as `LOCAL_QUORUM` |
| `blockFor` | Number of replica responses required for CL |
| `received` | Number of replica responses received |
| `dataPresent` | Whether **actual data** arrived in the responses or only digests/checksums |
| `retryCount` | Number of prior policy invocations for this request |

Cassandra optimizes reads by requesting **full data** from one replica while asking others only for **digests** to reconcile consistency. Thus, `received >= blockFor` can occur **without a full data response**—enough responses arrived to count toward quorum on paper, yet no full data row arrived to return to the client.

### 6.2. `DefaultRetryPolicy` decision tree

~~~text
READ_TIMEOUT from coordinator
           |
   retryCount > 0? --- YES ---> RETHROW
           |
           NO
           |
   received >= blockFor?
         /      \
       NO       YES
        |        |
     RETHROW   dataPresent?
                  /       \
                YES        NO
                 |          |
              RETHROW    RETRY_SAME
                           (once)
~~~

**Why the same coordinator?** Usually the coordinator picked an unresponsive replica for the full-data read; on the retry, gossip may have updated liveness so the coordinator picks a different data replica. Switching coordinators is unnecessary if the current coordinator already has enough visibility to adjust its replica choice.

### 6.3. Four examples to test yourself

| `blockFor` | `received` | `dataPresent` | `retryCount` | Default verdict |
|---:|---:|---|---:|---|
| 2 | 2 | false | 0 | **RETRY_SAME** |
| 2 | 1 | false | 0 | **RETHROW** |
| 2 | 2 | true | 0 | **RETHROW** |
| 2 | 2 | false | 1 | **RETHROW** |

Never write a custom policy like “always retry `READ_TIMEOUT`” ignoring `dataPresent`, replica counts, and `retryCount`. Retrying when storage is saturated prolongs congestion.

### 6.4. Inspecting the exception in Java

~~~java
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;

try {
    session.execute(statement);
} catch (ReadTimeoutException ex) {
    System.err.printf(
        "READ_TIMEOUT cl=%s received=%d blockFor=%d dataPresent=%s%n",
        ex.getConsistencyLevel(),
        ex.getReceived(),
        ex.getBlockFor(),
        ex.wasDataPresent());
    throw ex;
}
~~~

`ReadTimeoutException` is a **server-side timeout**. `DriverTimeoutException` is a **client-side request deadline** and lacks `getReceived()`/`wasDataPresent()`. When the driver tried multiple nodes, the error may be wrapped inside `AllNodesFailedException`.

### 6.5. Why not drop CL automatically?

If the application requires `LOCAL_QUORUM` for sufficiently fresh reads, a custom retry falling back to `LOCAL_ONE` can return syntactically valid **stale data** that breaks business invariants. Start tuning on the read path: partition sizes, SSTables-per-read, tombstone scans, disk/GC, repair, and replica liveness. Only change CL under an approved domain decision.

## 7. `WRITE_TIMEOUT` — Why Only `BATCH_LOG` Retries by Default

### 7.1. A write timeout is not a rollback

~~~text
Client -> Coordinator A
              |
          RF=3, CL=QUORUM
         /      |      \
     Replica1 Replica2 Replica3
       ACK      slow      slow
         \       |        /
          \--- server timeout
                     |
             WRITE_TIMEOUT
                     |
Client DOES NOT KNOW whether replicas 2/3 persisted the mutation
~~~

A replica that sent an ACK likely persisted the mutation. Others may finish **after** the deadline. If the client retries a counter increment or list append, the final state can diverge from a single execution.

### 7.2. `WriteType` and default verdicts

| `WriteType` | Typical meaning | `DefaultRetryPolicy` on first retry & idempotent |
|---|---|---|
| `SIMPLE` | Standard single mutation | **RETHROW** |
| `BATCH` | Write phase of a logged batch | **RETHROW** |
| `UNLOGGED_BATCH` | Unlogged batch | **RETHROW** |
| **`BATCH_LOG`** | Writing the distributed batchlog for a logged batch | **RETRY_SAME once** |
| `COUNTER` | Counter mutation | **RETHROW** |
| `CAS` / others | Conditional mutation / LWT | **RETHROW** |

**Why is `BATCH_LOG` special?** That failure occurs while the coordinator is still writing the **batchlog** to a small group of nodes; retrying on the same coordinator has a fair chance of succeeding after updated liveness. It **does not** mean the driver unconditionally retries a partially applied logged batch.

### 7.3. The idempotence gate

`onWriteTimeoutVerdict` is invoked only when the request is marked **idempotent**. If a statement is not idempotent, the driver **never consults the policy** and rethrows directly to the client. This is an outer safeguard before the policy even checks `WriteType`.

~~~java
// Assumes "status = PAID" with fixed PK, no new TTL/ID generated,
// and business logic permits mutation replay.
BoundStatement safeUpsert = prepared.bind(
        "tenant-a",
        java.util.UUID.fromString(
            "11111111-1111-1111-1111-111111111111"),
        "PAID")
    .setIdempotent(true);

// Do not blindly mark counter += 1,
// list append/prepend, or retry-dependent timestamps/TTLs as idempotent...
~~~

Even when a statement is marked idempotent, `DefaultRetryPolicy` still **does not retry `SIMPLE` write timeouts**. **`Idempotent=true` merely allows the policy to be consulted**; it does not promise a retry will occur.

### 7.4. Separating `BATCH_LOG`, `BATCH`, and `UNLOGGED_BATCH`

~~~text
Logged batch:
  1. Coordinator writes batchlog          -> can fail as BATCH_LOG
  2. Applies mutations to natural replicas -> can fail as BATCH
  3. Cleans up batchlog on success

Unlogged batch:
  No distributed batchlog,
  but still dispatches mutations to replicas.
  A subset of mutations may have applied when timing out.
~~~

**Never use multi-partition logged batches as a bulk import accelerator.** They carry coordination and batchlog overhead and do not provide global SQL transactions. For exactly-once business events, use event IDs, versioning, deduplication, or an outbox.

### 7.5. Inspecting `WriteTimeoutException`

~~~java
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

try {
    session.execute(writeStatement);
} catch (WriteTimeoutException ex) {
    System.err.printf(
        "WRITE_TIMEOUT cl=%s received=%d blockFor=%d writeType=%s%n",
        ex.getConsistencyLevel(),
        ex.getReceived(),
        ex.getBlockFor(),
        ex.getWriteType());

    // Do not immediately re-write when the outcome is uncertain.
    // Reconcile by eventId/version in the domain system.
    throw ex;
}
~~~

`getWriteType()` reflects the **write execution phase** in Cassandra, not merely the CQL statement syntax. Never assume a batch statement in source code always produces `WriteType.BATCH_LOG`.

## 8. `onRequestAbortedVerdict` — Disconnected **Before a Response**

### 8.1. Two cause groups

| Cause | Examples | `DefaultRetryPolicy` |
|---|---|---|
| Unexpected connection closure | `ClosedConnectionException` on network drop, `HeartbeatException` on missed heartbeat | **RETRY_NEXT**, within policy bounds |
| Unexpected response decoding error | Bug / invalid protocol decoding | **RETHROW**; do not assume another coordinator fixes it |

This callback is consulted only when the request is **idempotent**. For **non-idempotent** requests, the driver rethrows because the connection dropped after bytes may already have been sent; nobody knows for sure whether the coordinator applied the mutation. “Sending to node B” does not guarantee node A did not finish.

### 8.2. Ambiguous timeline

~~~text
Java                   Network                   Coordinator A
 |                        |                            |
 |---- INSERT ------------|--------------------------->|
 |                        |                     applies mutation
 |                        X  connection dropped        |
 |<--- no response -------X                            |
 |                                                     |
 |  request idempotent?                                |
 |      YES -> policy may RETRY_NEXT                   |
 |      NO  -> rethrow                                 |
 |                                                     |
 |  Coordinator A MAY already have persisted the write |
~~~

Only the application knows whether a mutation carries side effects outside Cassandra: e.g., generating a fresh order ID on retry, incrementing a counter, or sending an email afterward. **Calling `setIdempotent(true)` does not magically make those side effects safe.**

### 8.3. Transport failures **before** a network write are different

If a selected node goes DOWN right after query-plan selection, the pool has no connection, or the request fails before the driver **attempts to write** to the socket, the driver knows the coordinator **never received** the request. It can transparently try the next node **without invoking `RetryPolicy`**, even for non-idempotent statements. This is far safer than losing a connection **after sending bytes**.

Example:

~~~text
Request created
   |
Pool borrow fails BEFORE network write
   |
Driver knows "not sent"
   |
Try next node transparently
   |
No RetryPolicy.onRequestAbortedVerdict invocation
~~~

Never lump `errors.request.unsent` and `errors.request.aborted` together as “safely retryable network errors”, because their outcome guarantees differ.

## 9. `onErrorResponseVerdict` — Server Errors Other Than READ/WRITE_TIMEOUT or UNAVAILABLE

Server responses routed here include:

- `OverloadedException` — coordinator/server reports overload.
- `ServerError` — server-side error.
- `TruncateException` — failure during `TRUNCATE`.
- `ReadFailureException` — replica-level read failure (distinct from slow replicas).
- `WriteFailureException` — replica-level write failure (distinct from slow replicas).

### 9.1. Default behavior by group

| Error | Default verdict when eligible | Why? |
|---|---|---|
| `ReadFailureException` | **RETHROW** | Replica/read-path error occurred; immediate retry rarely helps |
| `WriteFailureException` | **RETHROW** | Partial write side effects may already have occurred |
| `OverloadedException`, `ServerError`, and other eligible server errors | Usually **RETRY_NEXT** once | Another coordinator may be healthy |
| `TruncateException` | Falls under other server errors; **never** treat `TRUNCATE` as safely replayable from apps | Destructive operation requiring version/policy review and a runbook |

**This branch requires the statement to be idempotent** for the policy to be called. If non-idempotent, the driver rethrows without consulting the policy. Never force `TRUNCATE` or schema DDL to be marked idempotent just to trigger retries.

**Distinguish `ReadFailure`/`WriteFailure` from timeouts:** Failure exceptions can carry failed-replica counts, response counts, and reason maps; timeouts indicate insufficient responses in time. Root-cause actions differ: read/write failures often point to disk, corruption, or node exceptions—not merely needing higher timeouts.

### 9.2. `Overloaded` does not mean “retry harder”

When one node returns `OverloadedException`, trying the next coordinator once can succeed. However, if shared replicas are already saturated on disk or network:

~~~text
Request -> A overloaded
             |
           retry B
             |
             +--> B also overloaded
                       |
                       v
               Continuous app retries
                       |
                  RETRY STORM
                       |
               Cluster clogs further
~~~

Operational fixes require reducing concurrency, applying backpressure, resolving hot partitions, tuning compaction/disks, and balancing load. Never wrap “transient” exceptions in tight application retry loops.

### 9.3. Why shouldn't `ReadFailureException` be forced to `RETRY_NEXT`?

A replica may fail due to SSTable read errors, corruption, tombstone limits, or coordinator exceptions. Switching coordinators repeatedly when the same **natural replicas** are failing only increases I/O and latency. Inspect Cassandra server logs, disks, compaction/repair, schema mismatches, and token ownership before retrying.

## 10. Errors Handled Directly by the Driver **Without** Calling `RetryPolicy`

### 10.1. Before sending a message: safe retries because execution never happened

The driver applies hard-coded safe transitions when it knows the request was never sent:

~~~text
Query plan A -> B -> C
    |
    A pool saturated / node unavailable BEFORE network write
    |
    driver skips to B
    |
    RetryPolicy callback is NOT invoked
~~~

**The key condition is “before a network write was attempted”**, not “no ACK received”. Once bytes hit the wire without a response, the outcome becomes ambiguous.

### 10.2. `UNPREPARED`: re-prepare, then resend

Prepared statements are cached server-side by ID; when a node restarts, a new node joins, or the prepared cache evicts entries, the coordinator can return `UNPREPARED`. The Java Driver retains query text and metadata to:

1. Detect `UNPREPARED` for a prepared ID.
2. Send `PREPARE` again to the **same coordinator**.
3. Once prepared, re-send `EXECUTE` with the valid prepared ID.

This is a **dedicated mechanism**, not `DefaultRetryPolicy.onErrorResponseVerdict`. Do not build “catch `UNPREPARED` and re-prepare in an app loop” when the driver handles it natively. If `UNPREPARED` spikes heavily, check node restarts/churn, schema agreement, prepared-cache pressure, and driver version.

~~~text
Java -> node B: EXECUTE prepared-id=abc
node B -> Java: UNPREPARED abc
Java -> node B: PREPARE "SELECT ... WHERE pk=?"
node B -> Java: prepared-id=abc
Java -> node B: EXECUTE abc (values)
node B -> Java: ResultSet
~~~

### 10.3. Bootstrapping node

In an edge case where a contact point targets a bootstrapping node not yet serving CQL requests, the driver can move to the next node. This is not a way to “speed up bootstrapping”: monitor cluster topology and configure policies to avoid unready nodes.

### 10.4. Errors that **always rethrow** without consulting `RetryPolicy`

| Error class | Examples | Action |
|---|---|---|
| `QueryValidationException` and subclasses | `InvalidQueryException`, `SyntaxError`, `UnauthorizedException`, `AlreadyExistsException` | Fix query/schema/authorization; **do not retry** |
| `FunctionFailureException` | Server-side UDF/function error | Fix function/data; do not retry blindly |
| `ProtocolError` | Incompatible/invalid protocol framing | Check versions/network/config; never loop infinitely |
| Java bind/codec errors | `IllegalArgumentException`, missing codec, wrong marker/Java type | Fix code/DTO before `execute` |

Never treat validation errors as transient even during rolling schema deployments: verify DDL, schema agreement, and backward compatibility. Retrying `Unknown column` endlessly will not create the column.

### 10.5. `AllNodesFailedException` is not a single server error

When the driver tries multiple nodes and all fail, the application typically receives `AllNodesFailedException` holding a **node → errors map**. It is a composite exception and does not mean every node failed identically. You might see:

~~~text
Node A -> UnavailableException
Node B -> ClosedConnectionException
Node C -> ReadTimeoutException
Application -> AllNodesFailedException
~~~

To diagnose accurately, inspect every cause in the map; never catch `AllNodesFailedException` and assume “the whole cluster is dead”. `NoNodeAvailableException` is a special case where **no coordinator was even attempted**, typically because no usable node or connection existed.

**API note:** How `getAllErrors()` is accessed depends on the driver version; consult the exact 4.x Javadoc rather than flattening errors into a single `getCause()` and losing node context. [AllNodesFailedException Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/AllNodesFailedException.html).

## 11. Idempotence: The Safety Gate for Ambiguous Retries

### 11.1. Pragmatic definition

**Idempotent** means executing the same operation multiple times yields the **same final state** as executing it once, under stated application assumptions. Example:

~~~sql
-- Can be idempotent if PK/values and timestamp/TTL policies are stable:
UPDATE payments_by_id
SET status = 'PAID'
WHERE tenant_id = 'tenant-a'
  AND payment_id = 11111111-1111-1111-1111-111111111111;

-- Not idempotent:
UPDATE counters_by_key
SET processed = processed + 1
WHERE tenant_id = 'tenant-a';
~~~

An `UPDATE status='PAID'` looks idempotent, yet if the application triggers **workflow side effects** such as sending emails, emitting duplicate events, minting newer write timestamps, or resetting relative TTLs, the full business operation may **not be idempotent**. Audit every layer, not CQL syntax alone.

### 11.2. Matrix of commonly confused operations

| Operation | Assessment | Conditions |
|---|---|---|
| Point `SELECT` | Usually idempotent | No accompanying app side effects |
| `INSERT` with fixed PK and identical values | Conditional | Timestamps, TTLs, and version logic do not shift across attempts |
| `UPDATE` setting regular column to a fixed literal | Conditional | Does not violate event ordering against newer concurrent writes |
| `DELETE` by fixed PK | Conditional | Tombstone timestamps and retention must remain sound |
| `COUNTER UPDATE` `x = x + 1` | **No** | Repeats increment multiple times |
| `LIST` append/prepend `list = list + [...]` | **No** | Repeats duplicate list elements |
| `INSERT` calling `UUID.randomUUID()` per attempt | **No** | Creates multiple primary keys |
| LWT `IF NOT EXISTS` | Needs business-level handling | `[applied]=false` on retry can mean the prior attempt succeeded |
| API writing payment then sending email | Not naturally idempotent | Needs payment ID + outbox/deduplication |

**Stronger safeguards than flags:** maintain deterministic `event_id`/`payment_id`, source-provided versions/sequences, proper schemas, and duplicate resolution rules; use an outbox or idempotency store whenever external side effects exist.

### 11.3. Driver 4.x defaults to `default-idempotence=false`

~~~hocon
datastax-java-driver {
  basic.request.default-idempotence = false
}
~~~

You can set it per statement:

~~~java
PreparedStatement select = session.prepare(
    "SELECT status FROM retry_lab.orders_by_id " +
    "WHERE tenant_id = ? AND order_id = ?");

BoundStatement safeRead = select.bind(
        "tenant-a",
        java.util.UUID.fromString(
            "11111111-1111-1111-1111-111111111111"))
    .setIdempotent(true);

// For other statements, never assume by default:
// BoundStatement updateCounter = ... .setIdempotent(true);
~~~

**Never flip `default-idempotence` to `true` globally on a mixed read/write service** without auditing every statement. The flag merely **informs the driver** for retry/speculation decisions—it provides no transactional or deduplication mechanism.

### 11.4. Idempotence gating by callback

~~~text
onReadTimeoutVerdict / onUnavailableVerdict:
  -> can enter callback even if statement is not marked idempotent.

onWriteTimeoutVerdict:
onRequestAbortedVerdict:
onErrorResponseVerdict:
  -> requires idempotent=true; if false -> rethrow directly.

Hard-coded unsent/reprepare/bootstrap:
  -> bypasses RetryPolicy; relies on proof of non-execution
     or prepared-statement recovery.
~~~

This detail is often misunderstood from summaries claiming “retry policy only runs on idempotent queries”: **the safety of `READ_TIMEOUT` and `UNAVAILABLE` is evaluated separately**. For application-level retries, still check whether **the request is read-only and what the outcome could be**; never turn an exception class into a mindless rule.

### 11.5. `PreparedStatement` and `BoundStatement`

In Java Driver 4.x, the idempotence attribute on a `SimpleStatement` passed to `prepare` is inherited by `BoundStatement` and can be overridden when binding:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

PreparedStatement p = session.prepare(
    SimpleStatement.builder(
        "SELECT status FROM retry_lab.orders_by_id " +
        "WHERE tenant_id = ? AND order_id = ?")
        .setIdempotence(true)
        .build());

BoundStatement b = p.bind(
    "tenant-a",
    java.util.UUID.fromString(
        "11111111-1111-1111-1111-111111111111"));

System.out.println("idempotent=" + b.isIdempotent());
~~~

Note that setters on built-in statements are **immutable** and return a new instance. Calling `b.setIdempotent(true);` without assigning the return value leaves the original `b` unchanged.

## 12. `DriverTimeoutException`: Client Deadline vs. Cassandra Timeout

### 12.1. Two clocks

~~~text
                  JAVA DRIVER                        CASSANDRA
             request timeout budget             coordinator timeout
           (basic.request.timeout)            (cassandra.yaml ...)
                      |                                |
Client ---- request ---- network ---- coordinator ---- replicas
                      |                                |
             Can expire first             Can return READ/WRITE_TIMEOUT
             before server errors         if server times out first
                      |                                |
             DriverTimeoutException          ReadTimeoutException /
                                             WriteTimeoutException
~~~

**`DriverTimeoutException`** fires when the driver-side deadline expires. It is **not** `ReadTimeoutException` or `WriteTimeoutException`, lacks `received/blockFor` metadata, and **does not** invoke the corresponding `DefaultRetryPolicy` callbacks. See [DriverTimeoutException Javadoc 4.17](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/DriverTimeoutException.html).

### 12.2. Why is a client timeout still dangerous for writes?

~~~text
T0: Java sends INSERT payment_id=P, status=PAID
T1: Coordinator forwards mutation to replicas
T2: Client hits 2s limit, throws DriverTimeoutException
T3: Some replicas finish; ACK arrives too late
T4: App runs business retry -> may duplicate side effects
~~~

**There is no automatic rollback at T2.** Classify as **`UNKNOWN_OUTCOME`**; reconcile against domain sources and Cassandra state by PK/event ID rather than minting a new ID to “avoid collisions”, which causes worse business duplication.

### 12.3. A single request deadline is not the whole workflow deadline

Consider an API reading 30 sequential Cassandra pages or running 3 statements in one business call:

~~~text
GET /orders/history
  -> page 1: timeout budget 2s
  -> page 2: timeout budget 2s
  -> ...
  -> page 30: timeout budget 2s

This does NOT mean the whole API is automatically capped at 2s.
~~~

Enforce an **end-to-end deadline** for the HTTP request/job along with page/row caps. Application retries must fit **inside** the remaining deadline; never schedule three `session.execute` attempts at 5 seconds each when the API SLA is 3 seconds.

### 12.4. Reading effective config from the session

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import java.time.Duration;

Duration requestTimeout = session.getContext().getConfig()
    .getDefaultProfile()
    .getDuration(DefaultDriverOption.REQUEST_TIMEOUT);

boolean defaultIdempotent = session.getContext().getConfig()
    .getDefaultProfile()
    .getBoolean(DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE);

System.out.printf("requestTimeout=%s defaultIdempotent=%s%n",
    requestTimeout, defaultIdempotent);
~~~

These are the **effective values in the default profile**, not necessarily every request's settings: named/derived execution profiles or explicit `Statement.setTimeout()`/`setIdempotent()` calls can override them. When debugging retries, always record **the active profile and statement options**.

## 13. Application-Level Retries: Retry Budget, Backoff, Jitter, Circuit Breakers

### 13.1. When is a retry layer outside the driver needed?

`DefaultRetryPolicy` is intentionally conservative; occasionally an application needs a **workflow-level retry** after transient recovery. For example:

- A read-only `GET` retrying after tens of milliseconds **still within deadline** if the cluster had a brief network blip.
- An idempotent batch job checkpointing and retrying **after** cluster overload clears.
- A payment service reconciling a write timeout before deciding whether to return `PENDING_RECONCILIATION` to the caller.

Never implement:

~~~java
// WRONG: infinite loop, retries all errors, no deadline or backoff.
while (true) {
    try { session.execute(statement); break; }
    catch (Exception ignored) { }
}
~~~

### 13.2. Combined budget

~~~text
API deadline  = 1.5s
   |
   +-- Attempt 1: Java Driver (may include an internal retry)
   |
   +-- Check remaining time
   |
   +-- Backoff with jitter (if read/idempotent & transient)
   |
   +-- Attempt 2: Java Driver (may again include an internal retry)
   |
   +-- Return result OR explicit timeout/failure
~~~

If the driver performs 1 internal retry per `execute`, **2 application attempts can become more than 2 network attempts**. Speculative execution adds further physical attempts. Budget by **physical load and wall-clock deadline**, not just outer loop counts.

### 13.3. Exponential backoff with jitter

Sample delay formula for retries outside the driver:

\[
d_n = \min(d_{\max},\, d_0 \cdot 2^n),\qquad
\text{jitter}_n \sim U(0,d_n).
\]

For example `d0=50ms`, `dmax=400ms`, max 2 application attempts—these are purely **illustrative values**, not optimal for every SLO. Wait only if sufficient deadline budget, CL, and cluster health remain. **Never call `Thread.sleep` inside a `RetryPolicy` callback**: callbacks run on driver I/O threads and block asynchronous driver processing. Use an external scheduler or non-blocking delay in the application layer.

### 13.4. Circuit breakers and bulkheads

| Mechanism | Purpose | Limitation |
|---|---|---|
| Bounded retries | Prevents infinite error amplification | Requires error classification and deadlines |
| Exponential backoff + jitter | Desynchronizes retry waves | Cannot restore missing quorum nodes |
| Circuit breaker | Pauses calls to an unhealthy dependency | Requires well-tuned half-open probes |
| Bulkhead / concurrency limit | Prevents one query family from exhausting the pool | Needs bounded queues, backpressure, and fairness |
| Adaptive rate limit | Sheds load when p99/errors/GC degrade | Can raise ingress latency if poorly tuned |
| Idempotency key / outbox | Prevents duplicate business effects | Needs a source of truth and dedup retention |
| Reconciliation | Resolves unknown write outcomes | Requires reliable audit/event logs |

Do not assign `RetryPolicy` the responsibility of an entire resilience architecture. It is only **one step** in the Cassandra request pipeline.

## 14. Configuring `RetryPolicy` and Execution Profiles with HOCON

### 14.1. Minimal `application.conf` for lab use

~~~hocon
datastax-java-driver {
  basic {
    contact-points = [ "127.0.0.1:9042" ]
    load-balancing-policy.local-datacenter = "datacenter1"
    request {
      timeout = 2 seconds
      consistency = ONE
      default-idempotence = false
      page-size = 500
    }
  }

  advanced.retry-policy.class = DefaultRetryPolicy

  profiles {
    read_only {
      basic.request.timeout = 1 second
      basic.request.consistency = ONE
      basic.request.default-idempotence = true
    }

    critical_write {
      basic.request.timeout = 3 seconds
      basic.request.consistency = ONE
      basic.request.default-idempotence = false
    }
  }
}
~~~

**Use `CL=ONE`/`DC=datacenter1` only in a single-node RF=1 lab.** Multi-DC production must declare proper contact points, local DC, RF/CL, and TLS/auth matching topology; e.g., RF=3 in a local DC typically requires `LOCAL_QUORUM` when business rules demand it. `read_only` is safe only for **genuinely read-only** statements; sharing a `default-idempotence=true` profile across `SELECT`, LWT, and `UPDATE` is dangerous.

### 14.2. Profiles set defaults; statements can still override

~~~java
SimpleStatement read = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfileName("read_only")
    .setIdempotent(true)
    .build();
~~~

If a statement selects `read_only`, it inherits a 1s request timeout and `default-idempotence=true` **unless explicitly overridden**. `setIdempotent(false)` on the statement overrides the profile. Similarly, `advanced.retry-policy.class` can be defined inside a named profile; whichever policy runs depends on **the request's effective profile**.

### 14.3. Using multiple retry policies

~~~hocon
datastax-java-driver {
  advanced.retry-policy.class = DefaultRetryPolicy

  profiles {
    read_only {
      basic.request.default-idempotence = true
      # If advanced.retry-policy is omitted,
      # the profile inherits the default policy.
    }

    operations {
      basic.request.default-idempotence = false
      # A tested custom policy class can be configured here.
      # advanced.retry-policy.class = my.package.MySafePolicy
    }
  }
}
~~~

The driver reuses policy instances when configurations match across profiles; do not assume a separate instance per request. For stateful custom policies, ensure **thread safety**, clean `close()` lifecycles, and safe instance sharing.

### 14.4. Do not invent a `max-retries` option for `DefaultRetryPolicy`

~~~hocon
# NOT a supported option by default:
# datastax-java-driver.advanced.retry-policy.max-retries = 10
~~~

`DefaultRetryPolicy` uses built-in rules and limits; there is no standard HOCON knob to “retry every exception N times”. Changing policy logic requires a tested custom `RetryPolicy`; backoff scheduling belongs in an **application scheduler**, never blocking the policy's I/O thread.

## 15. Java Driver 4.x: Catching Exceptions and Classifying Outcomes Properly

### 15.1. Common exception classes

| Class | Typical package | Fields to inspect |
|---|---|---|
| `DriverTimeoutException` | `com.datastax.oss.driver.api.core` | Client deadline |
| `AllNodesFailedException` | `...api.core` | `getAllErrors(): Map<Node,List<Throwable>>` |
| `NoNodeAvailableException` | `...api.core` | No coordinator could be tried |
| `ReadTimeoutException` | `...api.core.servererrors` | `received, blockFor, dataPresent, CL` |
| `WriteTimeoutException` | `...api.core.servererrors` | `received, blockFor, writeType, CL` |
| `UnavailableException` | `...api.core.servererrors` | `alive, required, CL` |
| `ReadFailureException` | `...api.core.servererrors` | Failed replica count / reason map |
| `WriteFailureException` | `...api.core.servererrors` | Failed replica count / write type |
| `InvalidQueryException` | `...api.core.servererrors` | Invalid query or schema |
| `UnauthorizedException` | `...api.core.servererrors` | Missing permission |
| `RequestThrottlingException` | `...api.core` | Rejected by client request throttler |

`AllNodesFailedException` is a **wrapper** around per-node errors and is not the same subclass as the inner failures. Catching `ReadTimeoutException` at the top level **does not replace** inspecting `getAllErrors()`.

### 15.2. Java 17 — a read-only helper with error handling

~~~java
package example;

import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.NoNodeAvailableException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.QueryValidationException;
import java.util.UUID;

public final class SafeOrderRead {
    private final CqlSession session;
    private final PreparedStatement lookup;

    public SafeOrderRead(CqlSession session) {
        this.session = session;
        this.lookup = session.prepare(
            "SELECT status FROM retry_lab.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?");
    }

    public String findStatus(String tenantId, UUID orderId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null) {
            throw new IllegalArgumentException("Invalid primary key");
        }

        BoundStatement statement = lookup.bind(tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setIdempotent(true);

        try {
            Row row = session.execute(statement).one();
            return row == null ? null : row.getString("status");
        } catch (NoNodeAvailableException e) {
            System.err.println("No coordinator candidate available");
            throw e;
        } catch (AllNodesFailedException e) {
            // May contain multiple errors per node; preserve context.
            e.getAllErrors().forEach((node, failures) -> {
                for (Throwable failure : failures) {
                    System.err.printf(
                        "node=%s errorType=%s%n",
                        node.getHostId(),
                        failure.getClass().getSimpleName());
                }
            });
            throw e;
        } catch (DriverTimeoutException e) {
            System.err.println("Client deadline expired");
            throw e;
        } catch (ReadTimeoutException e) {
            System.err.printf(
                "Read timed out: received=%d required=%d dataPresent=%s%n",
                e.getReceived(), e.getBlockFor(),
                e.wasDataPresent());
            throw e;
        } catch (WriteTimeoutException e) {
            // In principle SELECT does not throw write timeout;
            // kept here solely to demonstrate API error classification.
            System.err.println(
                "Unexpected write timeout: " + e.getWriteType());
            throw e;
        } catch (UnavailableException e) {
            System.err.printf(
                "Unavailable: alive=%d required=%d cl=%s%n",
                e.getAlive(), e.getRequired(),
                e.getConsistencyLevel());
            throw e;
        } catch (QueryValidationException e) {
            System.err.println("Permanent query/permission/schema error");
            throw e;
        }
    }
}
~~~

**This is an educational example of exception classification**, not a complete retry framework, and it does not assume every error surfaces at the top level. In production applications:

- Never catch and immediately re-invoke inside each `catch`.
- Never log raw CQL bind values or PII.
- Some errors appear only inside `AllNodesFailedException.getAllErrors()`, so **classify nested causes**.
- `NoNodeAvailableException` extends `AllNodesFailedException`, so catch it **before** `AllNodesFailedException`.
- Read-only APIs can return HTTP 503/504 with an appropriate `Retry-After`; mutations with uncertain outcomes should return **`PENDING`/`UNKNOWN`** or trigger reconciliation rather than asserting the write failed.
- `ONE` is used here for a lab with RF=1; production must set CL per business contract.

### 15.3. In async Java — exceptions may be wrapped

~~~java
import java.util.concurrent.CompletionException;

session.executeAsync(statement).whenComplete((result, error) -> {
    if (error == null) {
        System.out.println("CQL succeeded");
        return;
    }

    Throwable cause = error;
    while (cause instanceof CompletionException
            && cause.getCause() != null) {
        cause = cause.getCause();
    }
    System.err.println("CQL failed: " +
        cause.getClass().getSimpleName());
});
~~~

In `CompletionStage`, `join()` typically wraps errors in `CompletionException`, while `get()` wraps them in `ExecutionException`. Never inspect only `getMessage()` text to decide retries; preserve exception types, metrics, and node context.

### 15.4. Extracting per-node errors from `AllNodesFailedException`

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;

static void inspect(AllNodesFailedException e) {
    for (Map.Entry<Node, List<Throwable>> entry :
            e.getAllErrors().entrySet()) {
        Node node = entry.getKey();
        for (Throwable failure : entry.getValue()) {
            System.err.printf("node=%s type=%s%n",
                node.getHostId(),
                failure.getClass().getSimpleName());
        }
    }
}
~~~

`getAllErrors()` is the Driver 4.17 API. It exposes multiple errors per node; avoid the deprecated `getErrors()` API that returns only the first error per node and hides context. [Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/AllNodesFailedException.html).

## 16. Custom `RetryPolicy`: When to Consider One and Implementation Pitfalls

### 16.1. Nature of the interface

From driver 4.10 onward, callbacks prefer the `Verdict`-suffixed API:

~~~text
onUnavailableVerdict(Request, ConsistencyLevel, required, alive, retryCount)
onReadTimeoutVerdict(Request, ConsistencyLevel, blockFor, received,
                     dataPresent, retryCount)
onWriteTimeoutVerdict(Request, ConsistencyLevel, WriteType,
                      blockFor, received, retryCount)
onRequestAbortedVerdict(Request, Throwable, retryCount)
onErrorResponseVerdict(Request, CoordinatorException, retryCount)
~~~

Older methods without the `Verdict` suffix were deprecated in **4.10**; custom policies copied from driver 3.x or 4.4 may fail or misbehave on upgrade. Read the [RetryPolicy API 4.18](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/retry/RetryPolicy.html) and verify your exact library version.

### 16.2. Safety rules for custom policies

- **Never block Netty/I/O threads.** Policy callbacks run on I/O threads; `Thread.sleep`, REST calls, extra DB queries, or lock contention inside callbacks stalls the entire driver.
- **Never hold unprotected mutable state.** One policy instance can be shared across concurrent requests, threads, and identically configured execution profiles.
- **Never silently lower CL** when business logic requires quorum.
- **Never return `IGNORE`** simply because `>= 1` ACK arrived: that can turn an under-CL write into a fake “success”.
- **Never retry validation/auth errors**; the driver hard-rethrows those anyway.
- **Never allow unbounded retries**; cap `retryCount`, request timeouts, query plans, and application budgets.
- **Never retry non-idempotent writes** once network bytes may have been sent.
- **Never emit excessive per-request logs/exceptions**; track metrics by error class and omit PII.

### 16.3. When is a custom policy genuinely needed?

Only when:

1. Observed failures/recovery behavior show `DefaultRetryPolicy` misses a justified SLO.
2. Mutations are proven business-idempotent with proper CL/replica semantics.
3. Staging load tests and fault injection have measured retries, write amplification, and tail latency.
4. Source code and driver-version compatibility tests exist, with policy decisions fully observable.
5. Canary rollouts, rollback plans, and an owner familiar with Cassandra coordinators/replicas are in place.

For most applications, **keeping `DefaultRetryPolicy` + idempotence guards + bounded application backoff** is simpler and safer.

### 16.4. Comparing with `ConsistencyDowngradingRetryPolicy`

The driver includes `ConsistencyDowngradingRetryPolicy`, which is **not recommended by default** for workloads requiring consistency:

| Scenario | Default | Consistency downgrading |
|---|---|---|
| `UNAVAILABLE` at `QUORUM`, 1 replica missing | Tries another coordinator **at the same CL** | May retry at a lower CL on the same node |
| `READ_TIMEOUT` with insufficient responses | RETHROW | May lower CL if enough responses arrived for the weaker level |
| `WRITE_TIMEOUT` with 1 ACK | RETHROW (except `BATCH_LOG`) | May **`IGNORE`** the error for certain write types |
| Consistency guarantee | Never weakened automatically | **Can weaken**, causing stale reads / silent failures |

Hazard example:

~~~text
Payment write at QUORUM; policy downgrades write to ONE;
app receives "success"; other replicas have not caught up.

Subsequent read at QUORUM from another thread
  -> may not observe the payment yet.

Business read-your-writes / quorum invariant is broken.
~~~

**Never apply `ConsistencyDowngradingRetryPolicy` to payments, transaction states, or critical invariants** merely to suppress error alerts. If a use case genuinely permits degradation, define the relaxed guarantee, DC locality, audit trail, and client signal explicitly.

## 17. Observability: Separating Errors, Retries, and Speculative Executions

### 17.1. Driver 4.x metrics

Per the reference configuration, many session/node metrics are **disabled by default** and take effect only when a metrics registry/reporter is configured. Example:

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      connected-nodes,
      cql-requests,
      cql-client-timeouts
    ]

    node.enabled = [
      cql-messages,
      pool.in-flight,
      errors.request.unsent,
      errors.request.aborted,
      errors.request.read-timeouts,
      errors.request.write-timeouts,
      errors.request.unavailables,
      errors.request.others,
      retries.total,
      retries.read-timeout,
      retries.write-timeout,
      retries.unavailable,
      retries.aborted,
      retries.other,
      ignores.total,
      speculative-executions
    ]
  }
}
~~~

These are **driver metric option names** in HOCON. Exported metric names in Prometheus/Dropwizard/Micrometer depend on your integration; enabling HOCON alone does not set up exporters or dashboards. Avoid enabling high-cardinality metrics in production without evaluating overhead.

### 17.2. Session vs. node-level metrics

| Metric | Scope | Primary meaning |
|---|---|---|
| `cql-requests` | Session | Latency/throughput of **logical CQL requests** |
| `cql-client-timeouts` | Session | Requests exceeding driver deadline |
| `cql-messages` | Node | Individual requests/messages to a **coordinator**; can exceed logical requests |
| `errors.request.unsent` | Node | Failures **before** a network write occurred |
| `errors.request.aborted` | Node | Requests disconnected before response; outcome may be unknown |
| `errors.request.read-timeouts` | Node | Server returned `READ_TIMEOUT` |
| `errors.request.write-timeouts` | Node | Server returned `WRITE_TIMEOUT` |
| `errors.request.unavailables` | Node | Server returned `UNAVAILABLE` |
| `retries.*` | Node | Retries triggered by **policy**, broken down by category |
| `ignores.*` | Node | Errors returned as `IGNORE` by policy |
| `speculative-executions` | Node | Extra attempts triggered by speculative policy |
| `pool.in-flight` | Node | Messages currently awaiting responses |

**Never sum `retries.total` and `errors.request.unsent` and call it “application retries”**: `unsent` is handled by the driver outside `RetryPolicy`, and application retries are a separate layer. A timed-out client request can also leave the server still executing the mutation.

### 17.3. Measuring retry amplification

Define:

\[
A = \frac{\text{Total CQL messages sent to nodes}}
         {\text{Total logical CQL requests from application}}.
\]

`A≈1` when retries and speculative executions are minimal; `A>1` can stem from retries, speculative executions, multi-page fetches, or metric aggregation. Treat this as a **metric-scoped estimate**, not an exact retry formula. Align the service, cluster, and time window, account for multi-page endpoints, and check driver version.

60-second sample:

~~~text
logical CQL requests = 10,000
node cql-messages     = 11,200
nominal amplification = 1.12

Do NOT claim:
  "all 1,200 extra messages are DefaultRetryPolicy retries".

Instead inspect:
  retries.total
  errors.request.unsent
  speculative-executions
  pool.in-flight
~~~

If errors and timeouts rise alongside attempts while Cassandra CPU/disk hits saturation, retries may be **sustaining the incident**, not solving it.

### 17.4. Corresponding Cassandra server metrics

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool tablestats retry_lab.orders_by_id
nodetool netstats
~~~

| Client symptom | Server observation | Investigation path |
|---|---|---|
| Rising `UNAVAILABLE` | Nodes DOWN, wrong RF/DC, unstable gossip/ring | Replica liveness and placement |
| Rising `READ_TIMEOUT` | Read latency, SSTables-per-read, tombstones | Query shape, compaction, repair |
| Rising `WRITE_TIMEOUT` | Commitlog/memtable flushes, disk await, blocked writers | Write path, disk/GC |
| `OVERLOADED` across nodes | Rising CPU/GC/queues | Admission control / backpressure |
| Rising `ABORTED` | Network drops, heartbeat/connection logs | Network, TLS, thread stalls |
| Unusual `UNPREPARED` spikes | Node restarts/rollouts, schema churn | Prepared cache / session lifecycle |
| Driver timeouts without matching server timeouts | Network RTT, client pool, I/O loops, throttler | Client deadlines vs. server handling |

**Never subtract two percentile metrics** (driver minus server) to compute exact network latency, as the two histograms may cover different request populations. Use tracing, time-correlated events, and network telemetry for root cause.

### 17.5. Useful logs vs. hazardous logs

Emit **allowlisted labels**:

~~~text
query_family=orders.byId
profile=read_only
consistency=LOCAL_QUORUM
idempotent=true
exception_type=ReadTimeoutException
coordinator_dc=dc1
retry_verdict=RETHROW
latency_ms=...
~~~

Never place raw CQL bind values, passwords, tokens/PII, emails, or customer names into metric labels. Logging full request payloads on hot paths can also increase allocations/GC and worsen timeouts. Aggregate counters suffice for most diagnostics.

## 18. Lab A — CQL + Java: Distinguishing Success from Validation Errors

**Goal:** Use Java Driver 4.x with default `DefaultRetryPolicy` to test a PK-based CQL read and observe errors that **must not be retried**. This lab does not bring nodes DOWN, block firewalls, or overload servers. `READ_TIMEOUT` and `WRITE_TIMEOUT` branches are practiced via the **simulated decision table** in Lab B to avoid destabilizing clusters.

### 18.1. Prerequisites

- Single-node **lab** Cassandra 4.1/5.0 with port 9042 accessible.
- `cqlsh` and Java 17 + driver 4.17 (or compatible 4.x release).
- CQL privileges to create keyspaces/tables, or a pre-created lab keyspace.
- If the local DC name is not `datacenter1`, update `withLocalDatacenter(...)` accordingly.
- Lab commands use **synthetic data** only; never run in production.

### 18.2. Preparing schema and sample data

~~~sql
CREATE KEYSPACE IF NOT EXISTS retry_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS retry_lab.orders_by_id (
  tenant_id text,
  order_id uuid,
  status text,
  amount decimal,
  PRIMARY KEY ((tenant_id), order_id)
);

CONSISTENCY ONE;

INSERT INTO retry_lab.orders_by_id (
  tenant_id, order_id, status, amount
) VALUES (
  'tenant-a',
  11111111-1111-1111-1111-111111111111,
  'PAID',
  1200.50
);

SELECT order_id, status, amount
FROM retry_lab.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

The read should return `PAID`/`1200.50`. `SimpleStrategy`/RF=1 and `ONE` are strictly for **understanding exception handling**, not multi-DC production modeling.

### 18.3. Java 17: valid read and intentional query error

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.servererrors.QueryValidationException;
import java.net.InetSocketAddress;
import java.util.UUID;

public final class RetryLab {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                    "127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            // Test a valid read-only statement.
            PreparedStatement prepared = session.prepare(
                "SELECT status, amount FROM retry_lab.orders_by_id " +
                "WHERE tenant_id = ? AND order_id = ?");

            BoundStatement read = prepared.bind(
                    "tenant-a",
                    UUID.fromString(
                        "11111111-1111-1111-1111-111111111111"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            Row row = session.execute(read).one();
            if (row == null
                    || !"PAID".equals(row.getString("status"))) {
                throw new IllegalStateException(
                    "Business verification failed");
            }
            System.out.println("VALID_READ_PASS");

            // Intentional nonexistent column: server returns query validation error.
            SimpleStatement invalid = SimpleStatement.builder(
                    "SELECT non_existing_column " +
                    "FROM retry_lab.orders_by_id " +
                    "WHERE tenant_id = 'tenant-a'")
                .setIdempotent(true)
                .build();

            try {
                session.execute(invalid);
                throw new AssertionError(
                    "Expected a query validation failure");
            } catch (QueryValidationException expected) {
                System.out.println(
                    "VALIDATION_NOT_RETRIED=" +
                    expected.getClass().getSimpleName());
            }

        } catch (DriverException ex) {
            // Unhealthy session/node or unexpected failure.
            System.err.println("DRIVER_FAILURE=" +
                ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
~~~

**Expected output:**

~~~text
VALID_READ_PASS
VALIDATION_NOT_RETRIED=InvalidQueryException
~~~

This is the **expected form**, not pre-executed output. If your Driver 4.x version throws another `QueryValidationException` subclass depending on query/version, check the **exception class hierarchy** rather than matching raw error messages. The goal of this lab is not to verify retries by firing thousands of syntax errors.

### 18.4. Proving why validation errors must not retry

A query referencing a nonexistent column fails whether routed to coordinator A or B: the defect is in the **schema/query definition**, not a slow replica. That is why the driver **skips `RetryPolicy`** for `QueryValidationException`. If an app retries it 10 times, logs and server parsing load multiply 10x with identical failure.

### 18.5. Post-lab questions

1. Does `setIdempotent(true)` make a query with a nonexistent column retryable? — **No.**
2. If the app receives `AllNodesFailedException` instead of `QueryValidationException`, where should you inspect? — The per-node error map and underlying causes.
3. Does a successful `SELECT` here validate RF=3/quorum production behavior? — **No**, this lab uses RF=1/`ONE`.
4. Could `session.execute(read)` have been retried internally by the driver without the app noticing? — **Yes**, if an eligible failure/retry branch fired; check metrics/tracing to tell.

## 19. Lab B — Simulating the Deterministic `DefaultRetryPolicy` Decision Table

**Goal:** Learn exact retry branch conditions **without** stopping Cassandra or injecting disruptive timeouts. The code below is an **educational model** based on documentation—**not the driver's actual implementation**—and does not replace policy tests against the exact binary release you deploy.

### 19.1. Decision functions for read, write, and unavailable

~~~java
import java.util.Objects;

public final class RetryDecisionModel {
    enum Verdict { RETRY_SAME, RETRY_NEXT, RETHROW }
    enum WriteType { SIMPLE, BATCH, UNLOGGED_BATCH,
                     BATCH_LOG, COUNTER, CAS }

    static Verdict unavailable(int retryCount) {
        return retryCount == 0
            ? Verdict.RETRY_NEXT
            : Verdict.RETHROW;
    }

    static Verdict readTimeout(
            int blockFor, int received,
            boolean dataPresent, int retryCount) {
        if (retryCount == 0
                && received >= blockFor
                && !dataPresent) {
            return Verdict.RETRY_SAME;
        }
        return Verdict.RETHROW;
    }

    static Verdict writeTimeout(
            WriteType type, boolean idempotent, int retryCount) {
        if (!idempotent) {
            return Verdict.RETHROW;
        }
        if (retryCount == 0 && type == WriteType.BATCH_LOG) {
            return Verdict.RETRY_SAME;
        }
        return Verdict.RETHROW;
    }

    static void expect(Verdict actual, Verdict expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(
                "expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        expect(unavailable(0), Verdict.RETRY_NEXT);
        expect(unavailable(1), Verdict.RETHROW);

        expect(readTimeout(2, 2, false, 0),
            Verdict.RETRY_SAME);
        expect(readTimeout(2, 1, false, 0),
            Verdict.RETHROW);
        expect(readTimeout(2, 2, true, 0),
            Verdict.RETHROW);
        expect(readTimeout(2, 2, false, 1),
            Verdict.RETHROW);

        expect(writeTimeout(WriteType.BATCH_LOG, true, 0),
            Verdict.RETRY_SAME);
        expect(writeTimeout(WriteType.BATCH_LOG, false, 0),
            Verdict.RETHROW);
        expect(writeTimeout(WriteType.SIMPLE, true, 0),
            Verdict.RETHROW);
        expect(writeTimeout(WriteType.UNLOGGED_BATCH, true, 0),
            Verdict.RETHROW);

        System.out.println("DECISION_MODEL_PASS");
    }
}
~~~

This snippet can be run standalone with Java 17 **if** learners create and compile the lab file in their own environment; Content QA does not execute Java/Gradle. At runtime, the real driver also evaluates idempotence gating, query plans, deadlines, hooks/retry state, and server metadata—this model intentionally illustrates **a subset of those decisions**.

### 19.2. Decision table drill

| Input | Question before deciding | Result |
|---|---|---|
| `UNAVAILABLE`, `retryCount=0` | Could another coordinator have a better liveness view? | `RETRY_NEXT` |
| `READ_TIMEOUT`, `blockFor=2`, `received=2`, `dataPresent=false` | Was full data received? | `RETRY_SAME` |
| `READ_TIMEOUT`, `blockFor=2`, `received=1` | Were enough responses received? | `RETHROW` |
| `WRITE_TIMEOUT`, `BATCH_LOG`, `idempotent=true` | First decision? | `RETRY_SAME` |
| `WRITE_TIMEOUT`, `SIMPLE`, `idempotent=true` | Is it `BATCH_LOG`? | `RETHROW` |
| `WRITE_TIMEOUT`, `BATCH_LOG`, `idempotent=false` | Is the policy invoked? | No; rethrow |
| Connection closed after send, `idempotent=false` | Is it certain nothing was written? | `RETHROW` |
| Invalid CQL column | Would retrying change query or schema? | `RETHROW` outside policy |

### 19.3. Non-destructive labs cannot validate every runtime failure

Testing `READ_TIMEOUT`, `WRITE_TIMEOUT`, disconnects, and overload realistically requires a **dedicated fault-injection lab** with recovery procedures, metrics, and test oracles. Never kill production nodes, block networks, or fill disks just to “capture an error screenshot”. This lab proves **understanding of the decision rules**; full integration tests and failure drills belong in dedicated QA/staging phases.

## 20. Real-World Scenarios — Retry vs. Root-Cause Investigation

### Case 1 — RF=3, `LOCAL_QUORUM`, two replicas DOWN

**Scenario:** An NTS keyspace in `dc1` has RF=3; a `LOCAL_QUORUM` request needs 2 responses, yet only one natural replica is UP. The coordinator returns `UNAVAILABLE`.

**Default:** Tries the next coordinator once, **still at `LOCAL_QUORUM`**. Since the cluster truly lacks replicas, the request still fails.

**Handling:** Restore/rebuild/repair the replicas per runbook and inspect the ring and token ownership. Do not immediately drop `LOCAL_QUORUM` to `ONE` and break data consistency.

### Case 2 — `READ_TIMEOUT`, `blockFor=2`, `received=2`, `dataPresent=false`

**Scenario:** Two replica/digest responses arrived, but the full data response did not.

**Default:** `RETRY_SAME` once, if `retryCount=0`.

**Handling:** If errors repeat, check which replica the coordinator chose for full data, node disk/read latency, SSTables/tombstones, and network. Never assume all data is lost.

### Case 3 — `READ_TIMEOUT`, `blockFor=2`, `received=1`

**Default:** `RETHROW`; too few responses arrived, so retrying immediately on the same node has little chance.

**Handling:** Measure `ReadLatency`, replica liveness, tombstones, and GC; prevent application retry storms.

### Case 4 — `WRITE_TIMEOUT` after one ACK

**Scenario:** Updating order status with `SIMPLE`, `CL=LOCAL_QUORUM`, `received=1`/`blockFor=2`.

**Default:** `RETHROW` even if marked `idempotent=true` (not `BATCH_LOG`).

**Handling:** Outcome is **`UNKNOWN`**; query again by PK/event version once CL recovers, reconcile with audit/outbox, and never assert “the write did not happen”.

### Case 5 — `BATCH_LOG` timeout in a logged batch

**Scenario:** The coordinator failed to persist the batchlog fast enough and returned `writeType=BATCH_LOG`.

**Default:** If `idempotent=true`, the first callback returns `RETRY_SAME`. If not idempotent, the callback is not entered.

**Handling:** Check batchlog host availability, logged batch sizes, and node disk/GC. Never treat this as an excuse to stuff thousands of unrelated partitions into a single batch.

### Case 6 — `UNLOGGED_BATCH` timeout

**Default:** `RETHROW`; never assume `BATCH_LOG` simply because source code says `BATCH`.

**Handling:** Some mutations may have applied; classify idempotency per operation and reconcile by PK/event ID. Never blindly retry an entire batch containing increments or list appends.

### Case 7 — Disconnect after sending `INSERT`

**Scenario:** The driver wrote bytes, then the TCP connection reset before receiving a response.

**Default:** For idempotent requests, may retry the next node; for non-idempotent requests, rethrows.

**Handling:** Check network/heartbeats and ambiguous outcomes. Generating a new UUID inside `catch` risks duplicates. Keep the business ID stable and reconcile.

### Case 8 — No pool connection before network write

**Default:** The driver tries the next node outside `RetryPolicy` because nothing was sent; `errors.request.unsent` may increment.

**Handling:** Check pool saturation, client throttling, and node health; do not confuse “no connection” with a half-applied write.

### Case 9 — `UNPREPARED` spike after a rolling restart

**Default:** The driver transparently re-prepares on the coordinator and retries `EXECUTE`.

**Handling:** If brief right after restart, monitor. If sustained, check node churn, prepared-cache pressure, schema agreement, CQL text consistency, and driver version. Never wrap `UNPREPARED` in custom retry loops.

### Case 10 — `InvalidQueryException` from a wrong column name

**Default:** `RETHROW` immediately without invoking `RetryPolicy`.

**Handling:** Fix the code, schema migration, or column type, and add CI contract tests. Retrying 100 times burns CPU without creating the column.

### Case 11 — `UnauthorizedException` when role lacks `SELECT`

**Default:** `RETHROW` immediately as query validation/authorization.

**Handling:** Fix roles/grants using least privilege. Never swap credentials or downgrade auth inside retry logic.

### Case 12 — `OverloadedException` from reading a hot partition

**Default:** If idempotent, tries the next node per policy; otherwise rethrows.

**Handling:** A hot partition still hits the **same natural replicas** regardless of coordinator. Reduce concurrency, fix the data model/bucketing, and check disk/compaction instead of increasing retries.

### Case 13 — `ReadFailureException` due to replica error

**Default:** `RETHROW` in the policy branch rather than cycling coordinators endlessly.

**Handling:** Inspect server logs, disk corruption/I/O, repair, schema/codec mismatches, and per-node metrics. Re-run workflows only after fixing the underlying fault.

### Case 14 — `DriverTimeoutException` without server `READ_TIMEOUT`

**Default:** Client deadline expired; does not invoke the server `READ_TIMEOUT` callback.

**Handling:** Check driver pool in-flight counts, request throttlers, Netty event loops, networking, app thread contention, and timers. Raising timeouts may cut error metrics while blowing API p99; measure end-to-end SLOs.

### Case 15 — App retries `COUNTER UPDATE` twice

**Risk:** The increment may apply twice if the first attempt succeeded and the ACK dropped.

**Handling:** Never mark `idempotent=true`; if an exactly-once business counter is needed, use event deduplication/aggregation with stable IDs or recompute from a source of truth. `RetryPolicy` cannot fix counter semantics.

### Case 16 — Read-only API runs speculative execution and retries together

**Scenario:** Many requests slow down due to high network latency in one rack.

**Risk:** **Concurrent** speculative attempts plus error retries multiply messages, CPU, and replica work, risking secondary overload.

**Handling:** Compare `cql-requests` vs. `cql-messages`, `speculative-executions`, retry counters, and p99. Enable speculation only for **genuinely idempotent** queries with sufficient replica headroom.

### Case 17 — Catching `AllNodesFailed` and prematurely declaring “Cassandra is down”

**Risk:** Node A might return `UNAVAILABLE`, B drop its connection, and C report a read failure—heterogeneous distributed causes.

**Handling:** Log sanitized `getAllErrors()` by node and error class, inspect RF/DC/ring, and only then declare an outage. `NoNodeAvailableException` means zero coordinators were even tried.

### Case 18 — Changing the policy to `IGNORE` on write timeouts

**Risk:** The API reports success when mutations missed CL; payment/order workflows trust unconfirmed state.

**Handling:** Roll back the custom/downgrading policy, file a correctness incident, reconcile by event ID, and audit records. Never call weakening invariants “availability optimization”.

## 21. GO / HOLD / STOP Runbook When Retries Spike

### 21.1. Baseline before changing policies

~~~text
SERVICE/CLUSTER:
  service, build, driver version:
  local datacenter, keyspace RF:
  application SLO:
  default/named retry policy:
  request timeout:
  default/statement idempotence:
  speculative execution enabled?:

OBSERVABILITY:
  app success/error/p95/p99:
  cql-requests and cql-client-timeouts:
  node cql-messages:
  retries.total and retries by error type:
  unsent / aborted / read-timeouts / write-timeouts:
  node liveness, p99 read/write, GC/disk:
~~~

### 21.2. Workflow

~~~text
             Detect abnormal retry/error rate
                          |
                  Which error type?
                     /           \
                  Permanent     Transient/ambiguous
                     |                 |
                STOP retries     Inspect exception data
                fix query        + idempotence
                                      |
                       Write outcome unknown?
                          /                  \
                        YES                   NO
                         |                     |
                    Reconcile before       Deadline left?
                    resending                  |
                         |                 Yes / No
                         |                     |
                    Business source       Throttle/backoff
                    /version/outbox       or return error
                          \                  /
                           \                /
                         Monitor cluster health
                                  |
                         GO / HOLD / STOP
~~~

### 21.3. Action matrix

| Signal | Action | Rationale |
|---|---|---|
| Query validation/auth error | **STOP retries** and fix config/code | Retries cannot fix logic/permissions |
| RF/DC lacks quorum | **STOP/HOLD**, restore replicas | Retrying another node cannot create replicas |
| Write timeout with unknown outcome | **HOLD mutation replay**, reconcile | Avoids duplicate side effects |
| Errors rise alongside node CPU/disk/GC | **THROTTLE/HOLD**, never raise retries | Prevents amplification |
| One coordinator network-isolated, others healthy | **Controlled GO** with default policy | Trying another node can succeed |
| Client p99 exceeds SLO even as errors fall | **HOLD/ROLLBACK** timeout hike | Avoids masking root causes with long waits |
| Non-idempotent counter/LWT/outbox side effects | **STOP auto-retries** | Risk of business corruption |
| Staging fault-injection passes with telemetry | **Canary GO** per service/profile | Evidence-backed rollout |

There is no universal threshold like “stop if `retries.total > 20`” for every cluster. Use **ratios against QPS, baselines, and SLOs**, separating session-level errors from node-level attempts.

### 21.4. After canary / rollback

- Verify the **effective retry policy** and idempotence profile from the live JVM, not just source `application.conf`.
- Check both driver logical success **and** Cassandra p99, pending compactions, disk/GC, and replica liveness.
- Classify writes with unknown outcomes and schedule reconciliation; never report success without verification.
- Record rollback owner, change ID, config version, and UTC timestamp. If restarting sessions, stagger restarts to prevent a connection storm.
- Lock policy config in centralized management so stale `-D` flags or programmatic overrides do not reintroduce bad settings on redeploy.

## 22. Development and Operations Checklist for `DefaultRetryPolicy`

### 22.1. Java / CQL design

- [ ] Know the exact **Java Driver 4.x version** used by `CqlSession` and its effective metadata/options.
- [ ] Keep `DefaultRetryPolicy` unless documented evidence justifies changing it.
- [ ] Prepare and bind CQL aligned with partition keys, clustering keys, and access patterns.
- [ ] Verify RF per DC and CL per query family.
- [ ] Never treat `LOCAL_ONE`/`ONE` as a blanket fix for timeouts on critical data.
- [ ] Distinguish `READ_TIMEOUT`, `WRITE_TIMEOUT`, `UNAVAILABLE`, and driver deadlines.
- [ ] Understand which callbacks (`onUnavailable`/`onReadTimeout`) differ in idempotence requirements.
- [ ] Audit idempotency for every statement marked `true`.
- [ ] Never mark `COUNTER`, `LIST` append/prepend, random UUID generation, LWTs, or multi-system side effects as `true` blindly.
- [ ] Bound application retries by attempt count, remaining deadline, backoff+jitter, and circuit-breakers/bulkheads where needed.
- [ ] Never call `Thread.sleep` or blocking network I/O inside a custom retry policy.
- [ ] Never wrap query-validation, auth, or codec errors in retry loops.
- [ ] When exactly-once business effects are needed, implement event IDs, versioning, outboxes, or deduplication.
- [ ] Return `UNKNOWN/PENDING_RECONCILIATION` on uncertain write timeouts/outcomes.
- [ ] Never use `IGNORE` or CL downgrades to mask failures.
- [ ] Maintain contract tests for statements, typed bindings, and consistency/idempotence flags.

### 22.2. Fault-handling verification

- [ ] Distinguish **pre-write failures** from **sent-but-no-response disconnects**.
- [ ] Never re-implement `UNPREPARED` retry loops when the driver already reprepares.
- [ ] Do not confuse pre-network-write or bootstrapping skips with policy retries.
- [ ] For `READ_TIMEOUT`, log `received`, `blockFor`, and `dataPresent`.
- [ ] For `WRITE_TIMEOUT`, log `writeType`, `received`, `blockFor`, and non-sensitive business IDs.
- [ ] For `UNAVAILABLE`, log `required`, `alive`, `CL`, and check RF/ring.
- [ ] For `AllNodesFailedException`, inspect `getAllErrors()` instead of only the top-level message.
- [ ] Verify `QueryValidationException`, `ProtocolError`, and `FunctionFailureException` are not retried.
- [ ] Never raise concurrency/retries while `OverloadedException`, disk saturation, or GC spikes are climbing.
- [ ] Run staging fault tests and keep rollback plans whenever custom policies alter defaults.
- [ ] Never run destructive operations (`DROP`/`TRUNCATE`/node shutdown) outside authorized environments.

### 22.3. Production observability

- [ ] Dashboards separate session `cql-requests`/`cql-client-timeouts` from node `cql-messages`.
- [ ] Track `errors.request.unsent`, `aborted`, `read/write-timeouts`, `unavailables`, and `retries.*`.
- [ ] Account for `speculative-executions` in physical load budgets.
- [ ] Track p95/p99 latency and error rates by query family, profile, and CL.
- [ ] Monitor Cassandra node CPU, GC, disk, compaction, and replica liveness.
- [ ] Ensure logs and sampled traces omit raw bind values, credentials, PII, and high-cardinality IDs.
- [ ] Define GO/HOLD/STOP thresholds against baselines/SLOs rather than arbitrary numbers.
- [ ] Document incident owners, rollback runbooks, config commits, and timelines.
- [ ] Reconcile unknown write outcomes against domain sources after incidents.

## 23. Self-Assessment Questions and Suggested Answers

**Q1.** Is `DefaultRetryPolicy` the default in Java Driver 4.x?  
**Guidance:** Yes; no explicit declaration is required to enable it—override only with clear justification.

**Q2.** Can one logical CQL request send more than one message to Cassandra?  
**Guidance:** Yes; retries, speculative executions, and hard-coded recovery paths can generate extra attempts.

**Q3.** Does `RETRY_NEXT` target the next replica or the next coordinator in the query plan?  
**Guidance:** The **next coordinator** selected by the load-balancing plan; natural replicas are still governed by token/RF.

**Q4.** Does `RETRY_SAME` change the consistency level?  
**Guidance:** No in `DefaultRetryPolicy`; it keeps the original coordinator and CL.

**Q5.** Is `IGNORE` safe to use instead of `RETHROW` to boost API success rates?  
**Guidance:** No; it can report success/empty results even though CL was missed or state is unknown.

**Q6.** How does `UNAVAILABLE` differ from `READ_TIMEOUT`?  
**Guidance:** `UNAVAILABLE`: the coordinator knows too few live replicas exist before proceeding; `READ_TIMEOUT`: enough replicas initially appeared alive, but responses missed the deadline.

**Q7.** With `UNAVAILABLE` and `retryCount=0`, what does `DefaultRetryPolicy` decide?  
**Guidance:** `RETRY_NEXT` once, preserving the original CL.

**Q8.** Does `UNAVAILABLE` require `idempotent=true` to enter the policy callback?  
**Guidance:** No; it is not required for this callback.

**Q9.** `READ_TIMEOUT` has `received=2, blockFor=2, dataPresent=false, retryCount=0`. What happens?  
**Guidance:** `RETRY_SAME` once.

**Q10.** Why can `dataPresent=false` occur even when `received >= blockFor`?  
**Guidance:** Only digest/checksum responses may have arrived without the full data response.

**Q11.** `READ_TIMEOUT` receives 1/2 responses at `retryCount=0`. What is the default verdict?  
**Guidance:** `RETHROW`, because insufficient responses arrived.

**Q12.** `READ_TIMEOUT` has 2/2 responses with `dataPresent=true`. Does default retry?  
**Guidance:** No; `RETHROW`.

**Q13.** Does `WRITE_TIMEOUT` prove the mutation was not written on any replica?  
**Guidance:** No; the outcome is ambiguous and partial writes may exist.

**Q14.** A `SIMPLE` `WRITE_TIMEOUT` occurs on a statement marked `idempotent=true`. Does default retry?  
**Guidance:** No; the policy returns `RETHROW`.

**Q15.** A `BATCH_LOG` `WRITE_TIMEOUT` occurs with `idempotent=true` on the first callback. What does default do?  
**Guidance:** `RETRY_SAME` once.

**Q16.** Does `BATCH_LOG` mean any logged-batch error is safely retried?  
**Guidance:** No; `BATCH_LOG` covers only writing the batchlog, distinct from `BATCH`/`UNLOGGED_BATCH` and partially applied mutations.

**Q17.** When a connection closes before a response arrives, does `DefaultRetryPolicy` retry-next a non-idempotent request?  
**Guidance:** No via `onRequestAborted`; it rethrows due to the ambiguous outcome.

**Q18.** When zero bytes were sent because pool borrowing failed, is `RetryPolicy` invoked?  
**Guidance:** No; the driver handles it via a hard-coded path and tries another coordinator if available.

**Q19.** How is `UNPREPARED` handled after a node restart?  
**Guidance:** The driver transparently re-prepares on the coordinator and resends `EXECUTE`.

**Q20.** How many times should `InvalidQueryException` from a misspelled column name be retried?  
**Guidance:** Zero times; fix the CQL or schema.

**Q21.** Can `OverloadedException` cause default to try another node?  
**Guidance:** Yes for idempotent requests within policy rules; still guard against retry storms if the whole cluster is overloaded.

**Q22.** How do `ReadFailureException`/`WriteFailureException` differ from `READ_TIMEOUT`/`WRITE_TIMEOUT`?  
**Guidance:** Failures reflect explicit replica errors, whereas timeouts reflect insufficient responses in time; default rethrows read/write failures.

**Q23.** Does `DriverTimeoutException` invoke `onReadTimeoutVerdict`?  
**Guidance:** No; it is a client-side request deadline.

**Q24.** Why should a write timeout be modeled as `UNKNOWN_OUTCOME`?  
**Guidance:** Replicas may have persisted the write while ACKs were delayed or lost, requiring reconciliation before retrying.

**Q25.** Why is enabling `basic.request.default-idempotence=true` across a mixed workload dangerous?  
**Guidance:** Counters, list appends, LWTs, relative TTLs, and side effects are non-idempotent and could be retried or speculatively executed unsafely.

**Q26.** Does `setIdempotent(true)` force `DefaultRetryPolicy` to retry every write timeout?  
**Guidance:** No; it merely allows the policy to evaluate the error, and `DefaultRetryPolicy` still rethrows `SIMPLE`/`BATCH`/`UNLOGGED_BATCH`.

**Q27.** What is dangerous about `ConsistencyDowngradingRetryPolicy`?  
**Guidance:** It can weaken CL or ignore errors, breaking invariants, read-your-writes, and DC locality.

**Q28.** Does `retryCount=0` count application calls to `session.execute` or prior policy invocations?  
**Guidance:** Prior policy invocations before the current callback.

**Q29.** Why must `Thread.sleep` never be called inside `RetryPolicy`?  
**Guidance:** Callbacks run on driver I/O threads; blocking stalls other concurrent requests.

**Q30.** What must you inspect to diagnose `AllNodesFailedException`?  
**Guidance:** `getAllErrors(): Map<Node,List<Throwable>>`, not just the top-level message.

**Q31.** How does driver metric `cql-requests` differ from `cql-messages`?  
**Guidance:** Logical session requests vs. physical messages/attempts sent per node.

**Q32.** Can `errors.request.unsent` and `errors.request.aborted` be merged as “not written”?  
**Guidance:** No; `unsent` was never transmitted, while `aborted` may have crossed the wire with an ambiguous outcome.

**Q33.** Does `RetryPolicy` enforce the overall deadline of a 30-page API?  
**Guidance:** No; enforce an end-to-end deadline and page/row limits in the service layer.

**Q34.** If `LOCAL_QUORUM` lacks enough replicas, will raising timeout from 2s to 30s guarantee success?  
**Guidance:** No; timeouts do not bring missing replicas or quorum back online.

**Q35.** Does reducing error rates by raising timeouts always improve user experience?  
**Guidance:** No; p99 latency and in-flight requests can climb—evaluate SLOs and resources.

**Q36.** During an incident where retries climb alongside disk await and GC, should you raise max retries or throttle?  
**Guidance:** Prioritize shedding load and diagnosing capacity rather than amplifying physical messages.

## 24. Summary

~~~text
               JAVA DRIVER 4.x CQL REQUEST
                           |
                    Classify error
                           |
         +-----------------+-------------------+
         |                 |                   |
   UNSENT/UNPREPARED   Policy callbacks    PERMANENT ERROR
         |                 |                   |
   Driver handles      UNAVAILABLE           QueryValidation
   separately          READ_TIMEOUT          FunctionFailure
         |             WRITE_TIMEOUT         ProtocolError
         |             REQUEST_ABORTED           |
         |             ERROR_RESPONSE        RETHROW
         |                 |
         |           Is this branch gated
         |             by idempotence?
         |                 |
         |           Default decision
         |        SAME/NEXT/RETHROW
         |                 |
         +-----------------+-------------------+
                           |
                     Deadline remains?
                           |
                   Result or Exception
                           |
              Application decides based on:
          business idempotency / RPO / SLO / CL
                  |                   |
              Reconcile           Stop/backoff
              unknown writes      within budget
                  |                   |
                  +---------+---------+
                            |
                    Correct outcome
                   with useful metrics
~~~

A quick-reference summary—always pair it with the full matrix in Section 4:

- **`UNAVAILABLE`:** tries another coordinator at most once without lowering CL.
- **`READ_TIMEOUT`:** retries same once only when enough responses arrived without **full data**.
- **`WRITE_TIMEOUT`:** retries only `BATCH_LOG` by default, and the callback requires an idempotent statement.
- **Post-send disconnect:** considers retries only for idempotent statements; **unsent** failures take a safer hard-coded path.
- **Other server errors:** distinguish `Overloaded`/`ServerError` from `ReadFailure`/`WriteFailure`.
- **`UNPREPARED`:** driver transparently re-prepares; **query validation/function/protocol** errors never retry.
- **`DriverTimeoutException`:** client deadline expired—never infer “the server did not write”.
- **Application retries:** always budget attempts, deadlines, and backoff, and reconcile unknown outcomes.

**Key takeaway:** `DefaultRetryPolicy` in Cassandra Java Driver 4.x is a **conservative, error-specific policy**, not “retry until it succeeds”. Safety comes from **server-reported conditions, whether mutations may have applied, true idempotence, RF/CL, and load limits**. Business correctness must be verified **outside** `RetryPolicy`, especially when write errors leave replica state uncertain.

## References

- [Apache Cassandra Java Driver 4.18 — Retries](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — callback defaults, hard-coded paths, consistency downgrading, and profiles.
- [Apache Cassandra Java Driver 4.18 — Idempotence](https://apache.github.io/cassandra-java-driver/4.18.1/core/idempotence/) — `setIdempotent`, `default-idempotence`, retries/speculation, and unsafe mutations.
- [Apache Cassandra Java Driver — RetryPolicy Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/retry/RetryPolicy.html) — `onXxxVerdict`, I/O thread callbacks, and return verdicts.
- [DataStax Java Driver 4.17 — Retries](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/retries/) — manual for the 4.17 Java Driver branch.
- [DataStax Java Driver 4.17 — Reference configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/) — `advanced.retry-policy.class`, request timeouts, metrics, and profile inheritance.
- [DataStax Java Driver 4.17 — AllNodesFailedException](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/AllNodesFailedException.html) — `getAllErrors()` / `NoNodeAvailable`.
- [DataStax Java Driver 4.17 — ReadTimeoutException](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/servererrors/ReadTimeoutException.html) — `received`, `blockFor`, `wasDataPresent()`.
- [DataStax Java Driver 4.17 — WriteTimeoutException](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/servererrors/WriteTimeoutException.html) — `getWriteType()`, timeout semantics.
- [DataStax Java Driver 4.17 — DriverTimeoutException](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/DriverTimeoutException.html) — client-side timeout.
- [DataStax Java Driver 4.17 — DefaultDriverOption](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DefaultDriverOption.html) — request timeout, idempotence, and policy options.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — `cql-requests`, `cql-messages`, `errors.request.*`, `retries.*`, `ignores.*`.
- [DataStax Java Driver 4.17 — Speculative execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/speculative_execution/) — extra attempts and idempotency.
- [DataStax Java Driver 4.17 — Prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — caching, `UNPREPARED`, and re-prepare.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — ring, tokens, replication, consistency, and coordinators.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — server read/write latency, compaction, and request failures.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-first schema, partition keys, and hot-partition risks.
