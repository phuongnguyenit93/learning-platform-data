# Sessions, Connection Management, and the Java Spanner Client

An order API on **Cloud Run Java/Spring Boot**, a worker on **GKE**, and a **Spanner** database all run smoothly at low load. As traffic rises, p99 latency spikes even though application CPU still has headroom. Someone suggests creating a new client for every HTTP request; someone else wants to bump `maxSessions` into the thousands. Solving this properly requires distinguishing a **Spanner server-side session**, a **gRPC channel**, a **transaction**, and the running Java SDK version.

This lesson belongs to the **Spanner** chapter of the **CLOUD_PROVIDERS_GCP** module. It connects IAM/VPC, Compute Engine, Cloud Run, GKE, deployment automation, reliability management, and cost. Examples use the **Spanner GoogleSQL dialect** (`@name` parameter syntax)—do not apply the raw SQL directly to a PostgreSQL-dialect database.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish a session, multiplexed session, gRPC channel, `Spanner`, `DatabaseClient`, JDBC connection, and transaction.
2. Explain why modern Java Spanner SDKs **do not need legacy session pool tuning** out of habit.
3. Instantiate the client once per application lifecycle; close `ResultSet`, read-only transactions, and the service cleanly.
4. Read/write data in Java, understanding `ABORTED` and callback re-execution on retries.
5. Control concurrency as Cloud Run/GKE scale, and diagnose client/server latency and resource errors.
6. Operate with least-privilege IAM, observe metrics, run performance tests, and estimate costs.

**Important version note:** current documentation states that **multiplexed sessions are enabled by default in `google-cloud-spanner` Java starting in 6.98.0**. In recent Javadocs, **`SessionPoolOptions` is deprecated**, and legacy pool options have no effect under the multiplexed model. Older articles recommending `minSessions=100`, `maxSessions=400` apply only to **regular session pools** in legacy clients/configurations. See [Spanner sessions](https://cloud.google.com/spanner/docs/sessions) and [SessionPoolOptions API](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.SessionPoolOptions).

## 2. A Session Is Not a TCP Connection

| Object | Nature | Required Lifecycle |
| --- | --- | --- |
| **Regular session** | Server-allocated context for a database; typically handles **one concurrent transaction**. | Reused inside a legacy client pool. |
| **Multiplexed session** | One server session supporting **multiple concurrent operations/transactions**. | Managed automatically by modern Java SDKs. |
| **gRPC channel** | Network channel from the Java process to the Spanner API, serving multiple RPCs. | Reused and monitored for concurrency. |
| **`Spanner` service** | Java object managing resources, channels, and the session mechanism. | Usually one instance per JVM process, closed on shutdown. |
| **`DatabaseClient`** | Interface to operate on a database via `Spanner`. | Created at startup and reused across requests. |
| **`ResultSet`/`ReadOnlyTransaction`** | Stream/context for a read operation. | Closed immediately after processing. |
| **JDBC `Connection`** | JDBC abstraction with its own pooling semantics. | Do not map one-to-one with native `DatabaseClient` or sessions. |

~~~mermaid
flowchart LR
    WEB["HTTP requests / worker threads"] --> DB["Shared DatabaseClient"]
    DB --> SERVICE["Shared Spanner service"]
    SERVICE --> SESSION["Multiplexed session"]
    SERVICE --> CHANNELS["gRPC channel pool"]
    SESSION --> CLOUD["Spanner database"]
    CHANNELS --> CLOUD
    TX["Short-lived transaction/read contexts"] -. "Created by DatabaseClient" .-> DB
~~~

A session is a Spanner server-side resource—**each session is not a separate socket**. With regular sessions, creating a session requires an RPC and can bottleneck when many operations borrow from the same pool. With multiplexed sessions, **one session executes many concurrent transactions**, lowering overhead and eliminating session-pool exhaustion from borrowing.

| Question | Regular Sessions (Legacy) | Modern Multiplexed Java SDK |
| --- | --- | --- |
| Need many sessions for concurrent transactions? | Usually **yes**. | **No** one-to-one ratio. |
| Need to raise `minSessions/maxSessions` for higher load? | Possibly, after measuring. | **No**; these options are deprecated. |
| Which resources must be monitored? | Session pool, streams, and gRPC channels. | Streams/transactions, concurrency, and **gRPC channels**. |
| Does `ListSessions` list this session type? | Can be used to inspect regular sessions. | **Does not list multiplexed sessions**. |

**Important:** using multiplexed sessions does not mean you can skip `ResultSet.close()`, leave transactions open indefinitely, or instantiate a new `Spanner` object per request. Stream leaks, CPU, gRPC channels, and application lifecycle concerns still apply.

## 3. Initializing the Java Spanner Client with the Right Lifecycle

### 3.1. Dependency and Identity

The native Java library Maven coordinates are:

~~~text
com.google.cloud:google-cloud-spanner
~~~

Use a version pinned and tested via the **Google Cloud Libraries BOM** or project dependency management; choose **6.98.0 or later** for default multiplexed sessions. On Cloud Run, use a **runtime service account** with **Application Default Credentials (ADC)**; on GKE, prefer **Workload Identity Federation for GKE**. Never bake service-account JSON keys into container images or repositories. See the IAM and networking section near the end of this lesson.

### 3.2. Java Example: Shared Client and Parameterized Queries

Suppose a GoogleSQL database has this schema:

~~~sql
CREATE TABLE Orders (
  OrderId STRING(64) NOT NULL,
  Status STRING(32) NOT NULL
) PRIMARY KEY (OrderId);
~~~

This is **illustrative DDL**, not a command to run in production. In a Java application, create one process-scoped repository:

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.ResultSet;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.google.cloud.spanner.Statement;

public final class OrdersRepository implements AutoCloseable {
    private final Spanner spanner;
    private final DatabaseClient db;

    public OrdersRepository(String project, String instance, String database) {
        SpannerOptions options = SpannerOptions.newBuilder()
                .setProjectId(project)
                .enableDynamicChannelPool() // Benchmark before production.
                .build();
        spanner = options.getService();
        db = spanner.getDatabaseClient(DatabaseId.of(project, instance, database));
    }

    public String findStatus(String orderId) {
        Statement statement = Statement.newBuilder(
                        "SELECT Status FROM Orders WHERE OrderId = @id")
                .bind("id").to(orderId)
                .build();
        try (ResultSet rows = db.singleUse().executeQuery(statement)) {
            return rows.next() ? rows.getString("Status") : null;
        }
    }

    public long markPaid(String orderId) {
        Statement update = Statement.newBuilder(
                        "UPDATE Orders SET Status = @status WHERE OrderId = @id")
                .bind("status").to("PAID")
                .bind("id").to(orderId)
                .build();
        return db.readWriteTransaction().run(txn -> txn.executeUpdate(update));
    }

    @Override
    public void close() {
        spanner.close();
    }
}
~~~

In a short CLI demo, `OrdersRepository` can be created and closed via `try-with-resources`:

~~~java
try (OrdersRepository repo =
         new OrdersRepository("retail-lab", "retail-spanner", "orders")) {
    System.out.println(repo.findStatus("O-1001"));
}
~~~

**In Spring Boot:** register the repository as a **singleton bean** and use a destroy/shutdown lifecycle hook to invoke `close()` **once** when the instance stops. Never instantiate it inside a controller method or call `close()` at the end of a request. If multiple repositories share a single `Spanner` service, define **one owner responsible for closing it**.

`markPaid()` merely demonstrates the DML API; do not treat it as a complete safe payment flow. Production requires authorization checks, valid state transitions, idempotency, and handling side effects outside the DB.

## 4. Read Contexts and Closing Resources

### 4.1. Single-Use Read

`db.singleUse()` suits a standalone query. Reading a large result set can stream rows, but always close the stream—even on early return:

~~~java
Statement q = Statement.newBuilder(
        "SELECT OrderId, Status FROM Orders WHERE Status = @state LIMIT 10")
    .bind("state").to("PENDING")
    .build();

try (ResultSet rs = db.singleUse().executeQuery(q)) {
    while (rs.next()) {
        System.out.println(rs.getString("OrderId"));
    }
}
~~~

### 4.2. Multiple Consistent Reads at One Timestamp

`db.readOnlyTransaction()` fits when multiple queries must observe **the same snapshot**, and must be closed once done:

~~~java
import com.google.cloud.spanner.ReadOnlyTransaction;

try (ReadOnlyTransaction tx = db.readOnlyTransaction()) {
    try (ResultSet r1 = tx.executeQuery(
            Statement.of("SELECT COUNT(*) AS Cnt FROM Orders"))) {
        if (r1.next()) {
            System.out.println("all=" + r1.getLong("Cnt"));
        }
    }
    try (ResultSet r2 = tx.executeQuery(
            Statement.of("SELECT COUNT(*) AS Cnt FROM Orders WHERE Status = 'PAID'"))) {
        if (r2.next()) {
            System.out.println("paid=" + r2.getLong("Cnt"));
        }
    }
} // Close transaction immediately after both reads.
~~~

Spanner supports **strong reads** and intentional **staleness** bounds. Reporting that tolerates slightly older data can consider stale reads; inventory/balance checks require appropriate consistency semantics. Never hold a read-only transaction open while calling external HTTP APIs or awaiting user input.

## 5. Read-Write Transactions, `ABORTED`, and Safe Retries

### 5.1. A Transaction Callback May Run Multiple Times

Spanner can **abort** a read-write transaction under contention. Java's `DatabaseClient.readWriteTransaction().run(...)` handles retries for `ABORTED` transactions within the library. Therefore, callbacks must be **safe to re-execute**, bounded by timeouts, and never hold resources too long.

~~~java
long affected = db.readWriteTransaction().run(txn -> {
    Statement update = Statement.newBuilder(
            "UPDATE Orders SET Status=@state WHERE OrderId=@id")
        .bind("state").to("CONFIRMED")
        .bind("id").to("O-1001")
        .build();
    return txn.executeUpdate(update);
});
~~~

**Do not send emails, call payment gateways, publish to Pub/Sub, or create Cloud Tasks inside a transaction callback.** An `ABORTED` retry can rerun the callback and trigger external side effects twice. Keep only transactional reads/writes and side-effect-free logic inside the callback. To coordinate downstream work after commit, consider a **transactional outbox**.

~~~mermaid
flowchart LR
    REQ["POST /orders"] --> TX["Read-write transaction"]
    TX --> O["Write Orders + Outbox"]
    O --> C["Commit"]
    C --> PUB["Dedicated publisher"]
    PUB --> PS["Pub/Sub"]
    PS --> W["Idempotent consumer"]
~~~

If the publisher sends an event successfully and crashes before marking it sent, the message may be redelivered. Use an **event ID** and an idempotent consumer—never promise that one Spanner transaction commits atomically with Pub/Sub or an external API.

### 5.2. Distinguishing Retriable Errors from Business Errors

| Status | Likely Meaning | How to Handle |
| --- | --- | --- |
| `ABORTED` | Transaction aborted due to contention/conflict. | Use transaction runner; shorten transactions, check hotspots and abort rate. |
| `UNAVAILABLE` | Service/network temporarily unreachable. | Backoff/jitter per client policy; retry only when safe. |
| `DEADLINE_EXCEEDED` | Exceeded deadline; commit outcome may be unknown. | Look up by operation ID/idempotency key; avoid duplicate writes. |
| `RESOURCE_EXHAUSTED` | Quota/capacity, gRPC queueing, or legacy regular pool exhausted. | Inspect error details and metrics; don't blindly grow pools. |
| `PERMISSION_DENIED` | Principal/Spanner IAM/database role lacks permission. | Check ADC, IAM/FGAC; do not retry infinitely. |
| `INVALID_ARGUMENT` | Invalid SQL, query parameter, or request. | Fix code/data. |
| `NOT_FOUND` | Instance, database, table, or legacy regular session missing. | Verify resource/schema/session mode. |

`DEADLINE_EXCEEDED` does not guarantee the database **did not commit**. For charging or order creation, store a business operation ID durably and check the state before retrying.

### 5.3. Long Transactions Hurt Concurrency

Keep transactions short to cut contention, lock hold times, and aborts. If processing 100,000 records, consider batching/partitioned DML or targeted jobs; **never** open one giant transaction holding locks across external API calls. Partitioned DML has different semantics from standard read-write transactions and requires evaluating idempotency and unit atomicity.

## 6. Managing gRPC Channels in Modern Java Clients

### 6.1. Start from Defaults and Measure

Since `google-cloud-spanner` 6.98.0:

- **Multiplexed sessions are enabled by default**; there is no need to tune `minSessions/maxSessions`.
- **Dynamic gRPC channel pooling is disabled by default**; to test enabling it, call `SpannerOptions.Builder.enableDynamicChannelPool()`.
- Without dynamic pooling, the Java client uses **4 gRPC channels** by default, or **8 channels** when the gRPC-GCP extension is enabled; verify your exact version/config.
- One gRPC channel handles **roughly up to 100 concurrent requests** per Spanner guidance, though actual capacity depends on RPC types, latency, and traffic.
- Calling **`setNumChannels(...)` disables** dynamic channel pooling, even if `enableDynamicChannelPool()` was called earlier.

The example in section 3 enables dynamic channels:

~~~java
SpannerOptions options = SpannerOptions.newBuilder()
    .setProjectId("retail-lab")
    .enableDynamicChannelPool()
    .build();
~~~

This is **one performance experiment variable**, not mandatory. For small workloads, the default pool can be preferable; for fluctuating RPC volumes, dynamic pooling can prevent congestion without guessing a static channel count.

### 6.2. Legacy SessionPoolOptions Is Deprecated

Some legacy guides set `minSessions=100`, `maxSessions=400`, assuming every concurrent transaction requires its own session. That math only applies when the client uses a **regular session pool**.

In modern multiplexed clients, Javadoc marks `SessionPoolOptions` as deprecated, and those pool options no longer have effect. Therefore:

1. Verify your exact dependency version instead of copying an old blog post verbatim.
2. Confirm the active session mode before proposing session pool tuning.
3. Inspect **gRPC channels, outstanding RPCs, query plans, Spanner CPU, and aborts** first.
4. Even with multiplexed sessions, still **close `ResultSet` and read-only transactions**, and call `Spanner.close()` on shutdown.

For legacy clients still using regular pools, size `minSessions/maxSessions` by **per-JVM concurrency**, monitor session acquire wait, held resources, and `ListSessions`, and plan an SDK upgrade. Huge pools across hundreds of Cloud Run instances can also inflate total session footprint needlessly.

### 6.3. Not Every Bottleneck Is Channel Congestion

~~~text
End-to-end request latency
  = app CPU/queueing
  + client connection/gRPC/retry
  + Spanner server processing/locking
  + response serialization
~~~

If **client p99 is high while server processing latency is low**, investigate channels, networking, retries, and queueing. If **server latency is also high**, inspect Spanner compute, CPU, query plans, indexes, and **hot keys**. Only add channels with evidence of channel congestion; if the database itself is the bottleneck, more channels can pile on extra load.

## 7. Cloud Run/GKE Autoscaling and Backpressure

### 7.1. One Shared Client per Process

~~~text
Cloud Run instance A (Java process)
  OrdersController, PaymentsController
            ↓
  Shared OrdersRepository → Shared DatabaseClient/Spanner

Cloud Run instance B (separate process)
  Process B's own client, does not share memory with A.
~~~

The same applies on **GKE per Pod/JVM**. In Spring Boot, controllers must not instantiate new service objects per request. Close the client via a lifecycle hook during graceful shutdown, while not relying on shutdown callbacks running during abrupt VM/Pod kills.

### 7.2. Estimating Concurrent DB Operations

Hypothetical load example:

~~~text
Cloud Run max instances:            30
HTTP concurrency per instance:      40
Theoretical max concurrent requests: 30 × 40 = 1,200

If ~25% of requests are executing a Spanner RPC:
Estimated concurrent Spanner operations ≈ 1,200 × 0.25 = 300
~~~

This **does not mean creating 300 multiplexed sessions**. Actual RPC/transaction concurrency also depends on DB call duration, statements per HTTP request, retries, and session mode. For steady workloads, estimate using Little's Law:

~~~text
Concurrent operations ≈ arrival rate (ops/s) × average DB latency (s)
Example: 800 ops/s × 0.1 s = 80 concurrent operations.
~~~

During bursts, instantaneous load and p99 can exceed averages. Test together with **max instances, HTTP concurrency, connection/channel pools, Spanner CPU**, and downstream capacity. Never raise `max instances` unboundedly just because API latency rose.

### 7.3. Controlling Load and Hotspots

- Bound outstanding DB operations with short queues and clear deadlines to prevent memory blowups.
- Retry `ABORTED` only through the transaction runner; never write infinite outer retry loops.
- Keep transactions short and **do not perform external network I/O inside callbacks**.
- Design primary keys to avoid writing sequentially to a single key/range (e.g., monotonically increasing IDs).
- For Pub/Sub workers on GKE, ack **after commit** and use business idempotency keys.
- Use parameterized queries and appropriate indexes to minimize scans and CPU.

## 8. IAM, Networking, and Inspection Commands

### 8.1. Distinct Identities per Workload

| Principal | Need | Roles to Consider |
| --- | --- | --- |
| Cloud Run runtime SA | Read/write orders. | `roles/spanner.databaseUser` at appropriate scope plus database roles/FGAC if used. |
| GKE worker identity | Process related events. | Workload Identity Federation for GKE and least-privilege Spanner permissions. |
| CI/deployer | Deploy apps, assign runtime SA. | Deploy role and `iam.serviceAccounts.actAs`; no DB Admin by default. |
| DBA/platform | DDL and instance/database changes. | Separate admin role, approvals, and auditing. |
| Auditor | View configs/metrics. | Appropriate Reader/Monitoring roles; no data write permissions. |

Local ADC may authenticate a completely different principal than Cloud Run/GKE runtime identities. If local runs succeed while production throws `PERMISSION_DENIED`, verify **which principal actually calls Spanner**, IAM allow/deny policies, and database-level roles. Never embed JSON keys in JARs.

### 8.2. The Endpoint Is a Google API, Not a Cloud SQL Private IP

The native Spanner Java SDK connects to the **Spanner API** via supported endpoints, not directly to a database VM. With Cloud Run/GKE private networking, check **Google APIs egress**, DNS, Private Google Access / Private Service Connect where applicable, and VPC Service Controls. Cloud NAT/VPC routing, IAM, and database authorization are separate layers. Never assign external IPs to every GKE node just to troubleshoot `PERMISSION_DENIED`.

### 8.3. Read-Only `gcloud` Examples

~~~bash
PROJECT_ID="retail-lab"
INSTANCE_ID="retail-spanner"
DATABASE_ID="orders"

# READ-ONLY: confirm CLI principal and project.
gcloud auth list
gcloud config get-value project

# READ-ONLY: Spanner instance and database config.
gcloud spanner instances describe "$INSTANCE_ID" \
  --project="$PROJECT_ID" --format=yaml
gcloud spanner databases describe "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID"

# READ-ONLY: GoogleSQL query when principal has read access.
gcloud spanner databases execute-sql "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID" \
  --sql="SELECT COUNT(*) AS Cnt FROM Orders"
~~~

Resource IDs are illustrative; no real instances or databases are created by these commands. For PostgreSQL-dialect databases, adjust DDL/parameter syntax accordingly.

## 9. Observing Sessions, Client Latency, and Server Latency

| Layer | Helpful Signal / Metric | Purpose |
| --- | --- | --- |
| Spanner | `spanner.googleapis.com/instance/session_count` | Server-side session count; **do not** interpret as gRPC connection count. |
| Spanner server | CPU utilization, request latencies, transaction aborts, query stats. | Distinguish compute shortage, expensive queries, or contention. |
| Spanner client | `spanner.googleapis.com/client/operation_latencies` | End-to-end client operation latency including attempts/retries. |
| Spanner client | `spanner.googleapis.com/client/attempt_latencies` | Latency per individual RPC attempt. |
| Connectivity | `spanner.googleapis.com/client/gfe_connectivity_error_count` | Errors before client receives response headers from Google Front End. |
| Application | Request p50/p95/p99, RPC counts, concurrent DB calls, error codes. | Analyze user impact. |
| Cloud Run/GKE | Container/Pod count, CPU, memory, throttling, restarts. | Check whether autoscaling drives RPC/resource spikes. |

Client-side metrics may require enabling the **Cloud Monitoring API** and granting `roles/monitoring.metricWriter` to the exporting principal. Server metrics have sampling lag, so inspect matching time windows and load rather than judging from a single data point.

**`ListSessions`** can help find leaked sessions in **regular session pools** via `createTime` and `approximateLastUseTime`. The API **does not list multiplexed sessions**, so an empty list does not mean the client is not using sessions. For multiplexed sessions, inspect **client/server latency, gRPC channel utilization, RPC queueing, and CPU**.

## 10. Operational Scenario: Retail API Suffers a p99 Spike

### 10.1. Symptoms

A Java service on Cloud Run uses Spanner to view and update orders. During a sale:

| Signal | Pre-Load Level | Under-Load Level | Hypothesis |
| --- | ---: | ---: | --- |
| HTTP requests/s | 100 | 900 | Heavy Cloud Run scale-out. |
| p99 HTTP latency | 180 ms | 2,100 ms | Queueing or slow queries present. |
| Spanner server p99 | 70 ms | 85 ms | Server did not slow proportionally with client. |
| Client operation p99 | 100 ms | 1,600 ms | Client/network/queueing/retry worth investigating. |
| Java library | 6.124.0 | 6.124.0 | Multiplexed sessions by default. |

**Hypothetical numbers** for analytical practice, not a Spanner benchmark. Because server p99 barely moved while client p99 jumped sharply, **do not rush to increase Spanner processing units or `maxSessions`**.

### 10.2. Investigation Plan

1. Verify the Java client version, confirm `Spanner` is a per-process singleton, and check stream/transaction closure.
2. Inspect Cloud Run instance count, concurrency, thread pools, CPU/memory, and RPCs per request.
3. Compare client operation/attempt latencies, retries, GFE connectivity errors, and server processing latency.
4. Check whether dynamic channel pooling is enabled or static channels are used; inspect channel congestion and logs.
5. Test enabling **dynamic channel pooling** in staging or canary traffic under identical load without changing CPU, max instances, or query code simultaneously.
6. Observe p95/p99, aborts, 5xx errors, cost, and resource usage; roll back if it does not improve.

If both client and server slow down together, pivot to **Spanner CPU, query scans/indexes, hot keys, and read-write lock contention**. Networking tweaks cannot fix a SQL query scanning excessive rows.

### 10.3. Cost Is Not Just About Sessions

Spanner billing mainly ties to **compute capacity, database storage, backups, network/data transfer, and priced features**, not a fixed fee per created session. However, excessive sessions/channels still consume resources and degrade efficiency; Cloud Run/GKE scale-out also incurs CPU/RAM and traffic costs.

Measure **cost per successful order** alongside p99 and error rates. Never double database compute when the real bug is instantiating a new client on every request.

## 11. Symptom-Based Troubleshooting

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| First request slow, subsequent ones fast | ADC/JVM/client/gRPC warm-up or Spanner query initialization. | Startup traces, client creation, channel initialization. |
| Raising HTTP concurrency raises p99 | Client RPC queueing, channel congestion, Spanner CPU, or app thread contention. | Client/server latencies, channels, CPU, queue lengths. |
| `minSessions` changes nothing | Modern Java SDK uses multiplexed sessions; legacy pool options deprecated. | Dependency version, session mode, gRPC channels. |
| Legacy app reports session pool exhausted | Small regular pool, unclosed `ResultSet`/read-only transactions. | Session acquire wait, leak traces, `ListSessions` if applicable. |
| Rising `ABORTED` errors | Read-write contention, long transactions, or hotspots. | Abort rate, hot keys, duration; `TransactionRunner`. |
| `DEADLINE_EXCEEDED` on writes | Tight deadline, network issue, or uncertain commit state. | Traces, operation ID, and idempotency before retrying. |
| `RESOURCE_EXHAUSTED` | Quota/capacity, client channels, or legacy session pool. | Error details, compute, channels, and quotas. |
| `PERMISSION_DENIED` only on GKE | Workload identity/database role differs from local ADC. | Effective principal, Spanner IAM/FGAC, audit logs. |
| `NOT_FOUND` | Wrong database/table, or regular session deleted in legacy client. | Resource IDs, schema, version/mode. |
| Read stream never finishes | Unclosed `ResultSet`, huge query, or slow consumer. | Try-with-resources, streaming/paging, and memory. |
| Low session count yet high p99 | Multiplexed sessions handle many concurrent transactions. | gRPC capacity, app queueing, server CPU, query latency. |
| Missing client-side metrics | Monitoring API/metric export disabled or missing IAM. | Telemetry config, `roles/monitoring.metricWriter`. |

**Short runbook:** confirm exact project/instance/database and principal → verify Java client version/mode → confirm singleton lifecycle and resource closure → compare client vs. server latency → inspect autoscaling/CPU/query plans → change **one variable** and verify SLOs. Never "fix" `PERMISSION_DENIED` by raising channel counts, or "fix" timeouts by granting project Owner.

## 12. Practice Exercises

### Exercise 1 — Session or Channel?

An application runs 80 concurrent transactions. Must it open 80 TCP connections or 80 sessions? Explain the difference between **regular** and **multiplexed sessions**.

### Exercise 2 — Finding Resource Leaks

A controller calls `SpannerOptions.getService()` on every HTTP request and opens a query `ResultSet` without closing it. List three resource or latency consequences. Propose a Spring singleton lifecycle and proper resource closure.

### Exercise 3 — Parameterized Queries

Write `getStatus(String orderId)` using `db.singleUse()`, a `Statement` with a named parameter, and `try-with-resources`. Why should you never concatenate `orderId` directly into a SQL string?

### Exercise 4 — Transaction Retries

A `readWriteTransaction().run(...)` callback both updates Spanner and calls an email provider. If the first attempt hits `ABORTED`, what happens when the runner retries? Fix the design using **outbox + idempotent consumer**.

### Exercise 5 — Legacy Pool Config

The codebase uses `google-cloud-spanner` 6.124.0, yet an internal doc mandates `SessionPoolOptions.setMinSessions(100)`. What should you check first, and which metrics should guide tuning instead of following the outdated doc?

### Exercise 6 — Calculating Concurrent RPCs

Cloud Run `max instances=24`, `concurrency=50`. Suppose 30% of requests are executing a Spanner RPC at a given moment. Estimate the maximum concurrent Spanner operations. Should you set the session count equal to that number on modern Java SDKs?

**Hint:** 24 × 50 × 0.30 = **360 concurrent operations** under those assumptions, which does **not** imply needing 360 multiplexed sessions.

### Exercise 7 — Comparing Consistency

A dashboard accepts data one minute old, whereas checkout must update order state consistently. When should you pick a single-use strong read, a read-only transaction with an appropriate bound, or a read-write transaction? Which operations must stay out of a retry callback?

### Exercise 8 — IAM

Local ADC accesses Spanner fine, while the Cloud Run service returns `PERMISSION_DENIED`. List the inspection order across runtime service account, Spanner IAM, database role/FGAC, VPC Service Controls, and network path.

### Exercise 9 — Benchmarking the gRPC Pool

Design an A/B experiment: A uses the default gRPC pool, B enables `enableDynamicChannelPool()`. Hold workload, Java version, database compute, Cloud Run concurrency, and schema constant; measure **client p95/p99, server processing latency, errors, CPU, RPC throughput, and cost** before choosing.

## 13. Production Checklist and Official Documentation

| Item | What to Verify |
| --- | --- |
| **Version/mode** | Java SDK pinned and tested; know whether multiplexed sessions are enabled by default. |
| **Client lifecycle** | Shared `Spanner`/`DatabaseClient` per process; close `Spanner` on shutdown. |
| **Resource closure** | `ResultSet`/read-only transactions closed promptly; no long-lived contexts. |
| **Transaction retry** | `ABORTED` handled by runner; callbacks free of external DB side effects; business idempotency. |
| **Concurrent load** | Cloud Run/GKE autoscaling, outstanding DB ops, deadlines, and backpressure aligned. |
| **gRPC channels** | Default or dynamic channels benchmarked; not accidentally overridden by `setNumChannels`. |
| **Identity/network** | ADC, runtime SA/Workload Identity, Spanner IAM/FGAC, Google APIs egress. |
| **Monitoring** | Client/server p95/p99, session count by mode, CPU, aborts, errors, and channel pressure. |
| **SLO/cost** | Compute, storage, client CPU/memory, network, and cost per transaction evaluated. |
| **Recovery** | Runbooks for IAM, network, quotas, `ABORTED`, timeouts, and Java dependency/config rollback. |

Official sources to verify version-specific APIs:

- [Spanner sessions and multiplexed sessions](https://cloud.google.com/spanner/docs/sessions)
- [Spanner sessions — Multiplexed sessions section](https://cloud.google.com/spanner/docs/sessions)
- [Getting started with Spanner in Java](https://cloud.google.com/spanner/docs/getting-started/java)
- [Spanner Java `Spanner` lifecycle](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.Spanner)
- [Spanner Java `DatabaseClient`](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.DatabaseClient)
- [Spanner Java `TransactionRunner`](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.TransactionRunner)
- [Spanner Java `SessionPoolOptions` (deprecated)](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.SessionPoolOptions)
- [Spanner client-side metrics](https://cloud.google.com/spanner/docs/view-manage-client-side-metrics)
- [Spanner metrics](https://cloud.google.com/spanner/docs/metrics)
- [Spanner error codes](https://cloud.google.com/spanner/docs/error-codes)
- [Spanner IAM](https://cloud.google.com/spanner/docs/iam)
- [Spanner pricing](https://cloud.google.com/spanner/pricing)

**Remember:** a session is a Spanner server resource; a gRPC channel is an RPC transport path; neither **is synonymous with an HTTP request or a JDBC connection**. Modern Java clients use multiplexed sessions and **do not need legacy session pool tuning**, yet you must still reuse the client with the proper lifecycle, close streaming resources, keep transaction callbacks safe to retry, and manage concurrency. **Measure p99 from client to server before adding resources** to protect both reliability and cost.
