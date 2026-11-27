# Configuring Timeouts, Retries, and Pools for Application Load

## 1. Why Must Timeouts, Retries, and Connection Pools Be Designed Together?

In the **SPRING_DATA_MONGODB** module, Spring Data MongoDB is used to connect, map documents, and operate on MongoDB via **MongoTemplate** or **repositories**. Alongside query design, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics, applications must also handle traffic spikes and connection failures. This is the focus of the **Security and Operations** chapter.

Suppose an order service uses a MongoDB replica set. When traffic spikes suddenly, requests wait for connections from the pool; some queries hold connections too long; MongoDB may be electing a new primary. If timeouts are too long, requests occupy threads and connections long after the caller has given up. If timeouts are too short, valid requests fail. If retries are too aggressive, the system multiplies load at the exact moment the server is already slow.

A sound design must answer:

1. How long is a request allowed to wait for a server, a connection, and a result?
2. Which operations may be retried, which errors must stop immediately, and when is write outcome uncertain?
3. How many connections does each instance/pod need within MongoDB's total connection budget?
4. Which metrics prove that configuration changes actually improve latency and stability?

**Learning objectives:** distinguish timeout types, understand CSOT, configure retryable reads/writes, estimate pool sizes from concurrency, configure the driver via Spring Data MongoDB, verify via metrics, and test failover.

## 2. Which Stages Does a MongoDB Operation Pass Through?

~~~mermaid
flowchart LR
  A[HTTP request] --> B[Server selection]
  B --> C[Checkout connection]
  C --> D[Send command]
  D --> E[MongoDB processing]
  E --> F[Read result]
  F --> G[Return connection to pool]
  G --> H[HTTP response]
~~~

| Stage | What can cause slowness? | Signals |
| --- | --- | --- |
| Server selection | Primary unavailable, DNS/topology error, read preference has no candidate | MongoTimeoutException and cluster description |
| Opening TCP/TLS connection | Network, firewall, TLS handshake | Socket open/connect or SSL exception |
| Checkout from pool | Many operations holding connections, pool reached maxPoolSize | Checkout wait and checkout timeout |
| Sending/receiving data | Slow network, large response, unresponsive server | Socket I/O/operation timeout |
| Query execution | Missing index, blocking sort, CPU/I/O, or lock contention | Slow queries, explain, server metrics |
| Retry | Driver/app retrying transient errors | Attempt count and tail latency |

**A single timeout is not necessarily the deadline for the entire HTTP request.** Many legacy timeouts apply to distinct stages or per attempt. You must account for gateway time, business processing, MongoDB, retries, and serialization together.

## 3. Timeout Types in the MongoDB Java Driver

### 3.1. Common options

| Option | What it bounds | Key point to remember |
| --- | --- | --- |
| serverSelectionTimeoutMS | Time to find a server matching topology/read preference | Not how long a query is allowed to run |
| connectTimeoutMS | Time to open a socket connection | Does not bound command execution once connected |
| socketTimeoutMS | Legacy socket I/O wait time | Does not guarantee the server stopped the command |
| waitQueueTimeoutMS | Legacy wait to obtain a connection from the pool | Current Java drivers mark this option deprecated |
| maxTimeMS | Time server is permitted to process supported commands | Excludes client-side overheads |
| wtimeoutMS | Legacy wait to satisfy write concern | Timing out does not mean the write did not happen |
| timeoutMS | Client-side operation deadline under CSOT | Covers server selection, checkout, and execution under the new model |

Per **Java Sync Driver 5.x** documentation, typical defaults are serverSelectionTimeoutMS **30,000 ms**, connectTimeoutMS **10,000 ms**, socketTimeoutMS **0** (legacy unlimited), and maxPoolSize **100**. Values can depend on driver version; always check the exact driver your application uses.

Example configuration using the **traditional** timeout group:

~~~text
mongodb://db1.example.internal:27017,db2.example.internal:27017/shop?replicaSet=rs0&tls=true&serverSelectionTimeoutMS=3000&connectTimeoutMS=1500&socketTimeoutMS=7000&waitQueueTimeoutMS=1200
~~~

These numbers only illustrate syntax. Never copy them into production without measuring HTTP SLOs, network latency, failover duration, and MongoDB processing speed.

### 3.2. Three easily confused timeouts

**Server selection timeout:** if a replica set has only secondaries left while the application must write to primary, the driver may wait until a primary is available; the command has not even been sent. Raising socketTimeoutMS does not fix this case.

**Connect timeout:** limits TCP socket creation to the server. New connections can time out due to firewalls/networking; a query running on an already-open connection can run longer than this value.

**Socket timeout:** legacy I/O bound on the socket; not a dedicated tool to cancel a server query at exactly N milliseconds. The client can time out waiting while the server continues executing, especially for writes. You must handle uncertain write outcomes.

Example:

~~~text
serverSelectionTimeoutMS = 3000 ms
connectTimeoutMS         = 1500 ms
socketTimeoutMS          = 7000 ms
HTTP gateway timeout     = 3500 ms
~~~

The application can still be waiting on a MongoDB operation after the gateway has already returned a timeout to the client. To meet a 3.5-second HTTP SLO, reserve time for authentication, downstream service calls, and response rendering; the database must fit inside a reasonable sub-budget.

### 3.3. CSOT: `timeoutMS` for an entire operation

Modern MongoDB Java Drivers support **Client-Side Operation Timeout (CSOT)** via the timeoutMS parameter. Per Java Driver 5.x documentation, CSOT applies an overall cap across operation steps, including server selection, connection checkout, and command execution. CSOT was introduced in Java Driver 5.3 and is still documented as **experimental**; verify compatibility with your exact driver version.

~~~text
mongodb://db1.example.internal:27017/shop?tls=true&timeoutMS=4000
~~~

When timeoutMS is set, the driver ignores corresponding legacy timeout options such as **waitQueueTimeoutMS, socketTimeoutMS, wtimeoutMS, maxTimeMS, and maxCommitTimeMS**. Therefore, do not combine timeoutMS with those options expecting them to add up. connectTimeoutMS remains a connection parameter; consult your driver version's docs for interactions with the deadline.

| Approach | Configuration | Trade-off |
| --- | --- | --- |
| Traditional | serverSelectionTimeoutMS, connectTimeoutMS, socketTimeoutMS, waitQueueTimeoutMS | Separate timeout per stage; hard to enforce one end-to-end deadline |
| CSOT | timeoutMS, alongside relevant connection/pool options | Easy to align with operation budgets, but alters retry behavior and disables legacy timeouts |

Never set timeoutMS = 0 on online APIs just to eliminate timeout errors. That disables the CSOT operation limit and can allow requests to hang indefinitely.

### 3.4. `maxTimeMS` and write concern timeout

Without CSOT, you can cap server-side query execution time using maxTimeMS:

~~~javascript
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .maxTimeMS(1200)
  .limit(50);
~~~

In Spring Data MongoDB:

~~~java
import java.time.Duration;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-A")
        .and("status").is("PAID")
);
query.maxTime(Duration.ofMillis(1200));
query.limit(50);
~~~

maxTimeMS is a server-side limit for supported commands; it excludes server selection, pool wait, network overhead, and HTTP response rendering. When using timeoutMS, remember legacy timeouts may be ignored by the driver.

**A write concern timeout does not prove a write was rolled back**: data may already be written on the primary yet not yet acknowledged at the requested write concern level. Especially for payments or order creation, query state back or use an idempotency key rather than blindly issuing a fresh request after every timeout.

## 4. Retryable Reads and Retryable Writes

### 4.1. Which operations can the driver retry?

Modern Java Drivers normally enable **retryReads=true** and **retryWrites=true** by default. Under the traditional mechanism, for eligible commands, the driver typically retries **once** upon encountering a retryable error. Under CSOT, attempt counts may differ as retries follow the timeoutMS deadline.

~~~text
mongodb://db1.example.internal:27017,db2.example.internal:27017/shop?replicaSet=rs0&tls=true&retryReads=true&retryWrites=true
~~~

| Operation group | Driver retry capability | Limitations |
| --- | --- | --- |
| Certain read commands like find | Retryable reads on eligible errors | Not every read or every error category |
| insertOne, updateOne, replaceOne, deleteOne | Retryable writes when topology/acknowledgment requirements are met | Does not apply to all write operations |
| updateMany, deleteMany | Excluded from standard single-document retryable writes | Must design custom retries only if truly safe |
| Writes inside multi-document transactions | Not retried individually by retryWrites | Must handle transaction/commit errors separately |
| Email, payment APIs, REST side effects | Outside MongoDB Driver scope | Require business-level idempotency mechanisms |

Retryable writes require a **replica set or sharded cluster**; standalone servers lack the same mechanism. Writes must use an acknowledged write concern, not **w:0**. After a lost-connection error, write status may be unknown, so never equate an error with "nothing happened".

### 4.2. Driver retries differ from retrying the whole HTTP request

Suppose POST /api/orders performs three steps:

~~~text
1. Write order to MongoDB
2. Send payment request to provider
3. Send confirmation email
~~~

The driver can only retry eligible MongoDB commands. If the API gateway retries POST and the service retries the entire method, payment/email may be invoked multiple times even though the order write happened only once.

Recommended design:

1. Every order-creation request carries an **idempotency key** sent by the client or generated by the service per contract.
2. Persist a unique record keyed by that key using a unique index.
3. Write using a deterministic identifier; never generate a fresh ObjectId on each retry attempt.
4. If write outcome is uncertain, query the key before invoking subsequent business actions.
5. For payment/email, use the outbox pattern with idempotent consumers or an equivalent system mechanism.

Example repeatable upsert using a stable key:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class RequestReceiptStore {
    private final MongoTemplate template;

    public RequestReceiptStore(MongoTemplate template) {
        this.template = template;
    }

    public void ensureReceived(String requestId) {
        Query query = Query.query(Criteria.where("_id").is(requestId));
        Update update = new Update()
            .setOnInsert("status", "RECEIVED")
            .setOnInsert("requestId", requestId);
        template.upsert(query, update, "request_receipts");
    }
}
~~~

MongoDB automatically creates a unique index on _id, so the same requestId cannot produce two distinct documents. This example **illustrates only one idempotent write step**; it does not by itself resolve full concurrent request state machines or external side effects outside MongoDB.

### 4.3. Cases where retries should NOT happen

Do not blindly retry these errors:

- **Authentication or authorization:** bad credentials or missing privileges will not heal by waiting.
- **Validation, schema, duplicate key, or malformed command errors:** usually require fixing data/contracts rather than resending.
- **Writes with uncertain outcomes:** reconcile state/keys before re-executing side effects.
- **Prolonged outages, saturated backend:** continuous retries add load and delay recovery.

If implementing service-layer retries, verify operations are safe to repeat, enforce an overall deadline, cap attempts, and use exponential backoff plus **jitter**. Never write unbounded retry loops simply because an exception is network-related.

### 4.4. Transactions have dedicated retry logic

Writes inside a transaction are not retried individually by retryWrites=true. With MongoDB transactions, errors may carry **TransientTransactionError** or **UnknownTransactionCommitResult** labels. Depending on the label, either the entire transaction or the commit must be retried per driver/transaction rules.

When Spring Data MongoDB uses MongoTransactionManager or ReactiveMongoTransactionManager, understand how your application handles exceptions and commit states. Never wrap an entire service method with external side effects inside a blind retry loop. Long transactions also hold connections longer and increase pool pressure.

## 5. Retry Budgets and Preventing Retry Storms

### 5.1. Why are multi-layer retries dangerous?

Suppose three layers independently allow retries:

~~~text
HTTP client: max 3 attempts
API service: max 3 attempts
MongoDB driver: max 2 attempts

Worst-case amplification: 3 x 3 x 2 = 18 attempts
~~~

This is an illustrative calculation when each layer operates independently, not a guarantee that the driver always retries exactly twice. Multi-layer retries can amplify traffic to MongoDB right when the server is failing over or overloaded.

A sound design:

- Designate one primary layer responsible for retries; know which commands the driver already retries.
- Enforce an overall request deadline and cap total attempts.
- Retry only errors classified as transient.
- Use exponential backoff with jitter to avoid synchronized retries across pods.
- Apply rate limiting, bounded queues, or load shedding when the system is congested.
- Guarantee idempotency, especially for order creation, fund transfers, or webhooks.

~~~mermaid
flowchart TD
  A[Mongo operation fails] --> B{Transient error?}
  B -->|No| C[Return error or handle in business logic]
  B -->|Yes| D{Safe to repeat?}
  D -->|No| E[Reconcile state by idempotency key]
  D -->|Yes| F{Deadline and attempts left?}
  F -->|No| G[Fail fast and record metrics]
  F -->|Yes| H[Backoff + jitter]
  H --> I[Controlled retry]
  I --> A
~~~

Circuit breakers or bulkheads should also be configured based on real needs. Never let one slow reporting query starve critical requests; isolate concurrency or resource pools for long-running workloads.

## 6. MongoDB Driver Connection Pools

### 6.1. Pools are managed per server

One **MongoClient** maintains a pool for **each server in the topology**. In a replica set, pools to primary and secondaries can experience different utilization depending on read preferences. The driver also opens dedicated connections for topology monitoring.

Key points to remember:

1. Reuse the Spring Boot-managed MongoClient for the lifetime of the application. **Never create a new client per request**.
2. maxPoolSize limits one pool of one MongoClient to one server, not the whole cluster.
3. When a pool runs out of connections, new operations must wait to check out or time out.
4. Multiple pods/instances mean multiple independent pools; total server connections can grow rapidly.
5. An application using both sync MongoClient and reactive MongoClient maintains separate pools for each.

### 6.2. Parameters to measure

| Parameter | Role | Configuration risk |
| --- | --- | --- |
| maxPoolSize | Max connections in the pool per server | Too small causes waiting; too large can overload MongoDB |
| minPoolSize | Minimum connections kept warm | Too high wastes idle connections across many pods |
| maxConnecting | Concurrent connections allowed to establish simultaneously in a pool | Too high risks connection storms; too low slows pool ramp-up |
| maxIdleTimeMS | Closes connections idle too long | Too low causes churn; too high risks abrupt firewall/proxy idle drops |
| maxLifeTimeMS | Maximum lifetime of a connection | Too low increases TLS handshake/CPU overhead |
| waitQueueTimeoutMS | Legacy checkout timeout | May be ignored when timeoutMS is set |
| timeoutMS | Overall operation limit under CSOT | Requires evaluating separate budgets for long tasks |

Per Java Sync Driver 5.x documentation, **maxPoolSize=100**, **minPoolSize=0**, and **maxConnecting=2** are typical defaults. Treat these as reference points, not optimal formulas for every deployment.

### 6.3. Example URIs with pool and timeout settings

A test configuration using traditional timeouts:

~~~text
mongodb://db1.example.internal:27017/shop?tls=true&maxPoolSize=40&minPoolSize=4&maxConnecting=2&maxIdleTimeMS=60000&serverSelectionTimeoutMS=2500&connectTimeoutMS=1500&socketTimeoutMS=6500&retryReads=true&retryWrites=true
~~~

A separate configuration using CSOT, where supported by the driver and verified by the application:

~~~text
mongodb://db1.example.internal:27017/shop?tls=true&maxPoolSize=40&minPoolSize=4&maxConnecting=2&maxIdleTimeMS=60000&timeoutMS=4000&retryReads=true&retryWrites=true
~~~

**Do not mix the two timeout models** without understanding which options the driver actually honors. URIs containing real usernames/passwords must be supplied via a secret manager, never committed to repositories or logged.

### 6.4. Configuring via Spring Boot and `MongoClientSettings`

In **Spring Boot 3.x**, application.yml can read the URI from an environment variable:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

MONGODB_URI is supplied by the deployment platform. In Spring Boot 4, MongoDB properties are organized differently (e.g., spring.mongodb.uri); verify against your exact version. If the app manually instantiates MongoClient or runs multiple clients, inspect beans and configuration precedence.

A **Spring Boot 3.x** example customizing the pool in code:

~~~java
package example.mongo;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MongoPoolConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer mongoPoolCustomizer() {
        return settings -> settings.applyToConnectionPoolSettings(pool ->
            pool.maxSize(40)
                .minSize(4)
                .maxConnecting(2)
                .maxConnectionIdleTime(60, TimeUnit.SECONDS)
        );
    }
}
~~~

These numbers are illustrative values for load testing. If the URI also specifies pool options, check **precedence order** and final driver settings so code does not silently override operational config. Never instantiate a new MongoClient inside HTTP handlers.

## 7. Estimating Pool Size from Load

### 7.1. RPS does not equal connection count

An HTTP request holds a MongoDB connection only while database operations are actively using it. Use Little's Law as a starting estimate:

~~~text
Average concurrent checked-out connections
≈ MongoDB operations/second x Average connection hold time (seconds)
~~~

Suppose **each pod**:

- Receives 150 HTTP requests/second.
- Performs on average 0.8 MongoDB operations per HTTP request.
- Holds a connection on average for 50 ms = 0.05 seconds.

Then:

~~~text
MongoDB ops/s = 150 x 0.8 = 120
Average concurrent connections ≈ 120 x 0.05 = 6
~~~

The value **6** is an average, not the optimal maxPoolSize. Traffic bursts, transactions, cursor streaming, p95/p99 queries, and background jobs push concurrency higher. You can test maxPoolSize=20 as a **benchmarking candidate**, then tune based on checkout wait, timeout rates, and server capacity.

With 8 pods, each having maxPoolSize=20, the potential connection ceiling to the primary from these pools alone is:

~~~text
8 x 20 = 160 connections
~~~

This is a potential ceiling, not always-open sockets. Also count monitoring connections, secondary pools, and clients from other services/jobs. Because pools are maintained per server, **one pod's maxPoolSize is not a cluster-wide connection limit**.

### 7.2. When should you increase pool size?

| Observed state | Action to test |
| --- | --- |
| Pool full, high checkout p95, MongoDB CPU/I/O still has headroom | Measure incremental pool increases; check if cursors/transactions hold connections too long |
| Pool full and MongoDB CPU/I/O also saturated | Optimize queries/indexes, shed load, or scale the server first |
| Pool not full yet command duration is high | Investigate explain, query plans, networking, locks, and MongoDB resources |
| Fast checkout yet high HTTP latency | Inspect non-DB steps in the HTTP request and downstream services |
| Frequent connection creation/closure | Check maxIdleTimeMS, maxLifeTimeMS, TLS, and proxy idle timeouts |
| Many pods starting simultaneously | Cap maxConnecting, manage warm-up, and check total connection budget |

**Increasing maxPoolSize does not speed up an unindexed query.** If a large collection scan holds a connection for 3 seconds, enlarging the pool just lets more expensive queries run simultaneously, worsening overload.

### 7.3. Data to gather before sizing pools

| Input | Example | Source |
| --- | --- | --- |
| Typical / peak pod count | 4 / 8 | Deployment, HPA |
| Peak RPS per pod | 150 | HTTP metrics |
| MongoDB ops/request | 0.8 | Tracing, command metrics |
| Average checkout hold time | 50 ms | Driver pool metrics |
| Checkout wait p95 | Target under 20 ms | Driver telemetry |
| Command duration p95 | 120 ms | Driver/server metrics |
| MongoDB CPU/I/O/connection limit | Cluster-specific | Server metrics |
| Candidate maxPoolSize | 20 | Load test |

Size for **peak** load and mixed tenant sizes; daily averages hide bursts. Do not set a high minPoolSize just to keep many connections warm if you run many pods.

## 8. Sync and Reactive Spring Data Under Load

With **MongoTemplate** or synchronous repositories, the calling thread blocks until the MongoDB operation finishes. When the pool runs out of connections, servlet threads pile up waiting on checkout, degrading HTTP throughput.

With **ReactiveMongoTemplate** or reactive repositories, I/O avoids traditional thread blocking, yet MongoDB pools, CPU, bandwidth, and server capacity remain finite. Reactive does not mean infinite concurrency.

Guidelines:

- Bound the concurrency of independent parallel operations, especially when using flatMap across thousands of items.
- Prefer batched queries over N separate queries when business logic allows.
- Never call block() on event-loop threads to turn reactive pipelines synchronous.
- Close cursors/streams and handle cancellation properly so resources are not leaked.
- If an application runs both sync and reactive MongoClients, account for their combined pools/connections.

Example bounding concurrency in a reactive service:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Order> loadOrders(
        ReactiveMongoTemplate template, List<String> orderIds) {
    return Flux.fromIterable(orderIds)
        .flatMap(id ->
            template.findOne(
                Query.query(Criteria.where("orderId").is(id)),
                Order.class
            ),
            8 // Experimental concurrency cap for concurrent queries.
        );
}
~~~

This assumes the Order class and string orderId field exist. The number **8** caps concurrent inner publishers in this operator, **not maxPoolSize**. Measure and consider switching to a batched query when orderIds is large.

## 9. Metrics and Diagnostics

### 9.1. Minimal metric set

| Metric | Question answered | Anomaly signs |
| --- | --- | --- |
| Checked-out / available connections | How full is the pool? | Continuously pinned near maxPoolSize |
| Checkout wait p50/p95/p99 | How long do requests wait for a connection? | p99 spikes sharply during bursts |
| Checkout failures/timeouts | Are requests failing to borrow connections? | Pool saturation, operations holding connections too long |
| Created/closed connections | Is connection churn high? | Misconfigured idle/lifetime or network drops |
| Server selection timeout | Can the driver find a server? | Failover, DNS, read preference issues |
| Command duration p95/p99 | How slow are actual queries? | Missing indexes, high CPU/I/O |
| Retry/error counts | Are there retry storms or transient failures? | Sudden jump in attempts |
| HTTP p95/p99 and 5xx | How are end users impacted? | Misaligned deadlines between gateway and DB |
| DB connections/CPU/I/O | Does the server have headroom? | Increasing pools would overload the backend |

The MongoDB Java Driver offers **ConnectionPoolListener** for checkout, checkin, and create/close events, and **CommandListener** for command events. Combine them with Micrometer or your monitoring stack. Avoid writing raw commands containing customer data, tokens, or URIs/credentials into logs and traces.

### 9.2. Two contrasting diagnoses

**Scenario A** (illustrative figures):

~~~text
HTTP p95:                  2800 ms
MongoDB command p95:        180 ms
Pool checkout p95:         1700 ms
Checked-out connections:   40 / 40
MongoDB CPU:                45%
~~~

The pool is saturated while the server still has headroom. Check whether requests/cursors hold connections too long or transactions run overly long, then test a controlled pool increase.

**Scenario B** (illustrative figures):

~~~text
HTTP p95:                  3500 ms
MongoDB command p95:       3000 ms
Pool checkout p95:           20 ms
MongoDB CPU:                95%
~~~

The bottleneck is query/server execution, not checkout. Raising pool size here can push MongoDB CPU and internal queues even higher. Investigate slow queries, explain plans, indexes, aggregations, locks, and cluster capacity.

## 10. Load Testing and Chaos/Failure Testing

### 10.1. Scenarios to test

| Scenario | Evidence to gather |
| --- | --- |
| Steady load and 2–5x bursts | Throughput, HTTP p95/p99, checkout wait |
| maxPoolSize 10/20/40 under same load | Benefit vs impact on MongoDB CPU/I/O |
| Simultaneous multi-pod scale-out | Total connections, maxConnecting, warm-up time |
| Unindexed query or heavy aggregation | Command duration, pool occupancy, timeouts |
| Replica set failover | Server selection, retries, recovery time |
| Packet loss or slow sockets | Connect/socket/operation timeouts behave as designed |
| Driver retries plus service/HTTP retries | Attempt counts, idempotency, duplicate prevention |
| Uncertain transaction commit | Handling of UnknownTransactionCommitResult |
| Reactive fan-out | Concurrency, backpressure, pool checkout behavior |
| Cancelled long cursor/stream | Resource and connection release upon cancellation |

Execute on a **test** replica set with representative data and query distributions. Use load generators and network fault proxies to simulate failovers/latency; never kill a production primary solely for testing.

### 10.2. Configuration tuning workflow

1. **Lock SLOs:** e.g., HTTP p95, 5xx rate, acceptable failover recovery time, and request concurrency bounds.
2. **Capture baseline:** record driver version, MongoDB version, indexes, p95/p99, checkout wait, and server health.
3. **Change one thing:** timeout, pool size, or retry budget; never change everything at once.
4. **Replay the same workload:** compare metrics to baseline and verify business correctness.
5. **Test failures:** failovers, bad credentials, slow queries, and request cancellations.
6. **Evaluate total connection budget:** factor in max pod count, background jobs, all MongoClients, and target servers.
7. **Document the decision:** record config version, measurements, and trade-offs; never store passwords.

### 10.3. Acceptance criteria

A configuration is acceptable when:

- HTTP p95/p99 and error rates meet SLOs at target load.
- Connection checkout wait has headroom with minimal unexpected timeouts.
- MongoDB server retains CPU/I/O/connection budget for sibling workloads.
- Retries never duplicate orders, payments, emails, or related side effects.
- The system recovers from failovers within bounds without futilely retrying validation/auth errors.
- Connection pool and command events are observable via metrics without leaking sensitive data.

## 11. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Raising all timeouts very high to stop error alerts | Requests tie up threads/pools and mask root causes | Break down stages and align deadlines to SLOs |
| Treating socketTimeoutMS as an absolute query cap | Client errors while server keeps running | Distinguish socket, maxTimeMS, and CSOT |
| Setting timeoutMS alongside legacy timeouts expecting them to sum | Legacy options are ignored by the driver | Use one consistent driver timeout model |
| Treating write timeouts as rollbacks | Retries can trigger duplicate side effects | Enforce idempotency and state reconciliation |
| Unbounded retries on all errors | Retry storms, inflated latency | Enforce deadlines, finite attempts, backoff, and jitter |
| Using default maxPoolSize on every pod without measuring | Cluster-wide connections can grow too large | Budget connections across all instances and servers |
| Increasing maxPoolSize whenever the pool fills | Can worsen an already saturated server | Inspect CPU/I/O, indexes, and slow queries |
| Creating a MongoClient per HTTP request | Connection churn and pool fragmentation | Share Spring-managed client across app lifecycle |
| Setting minPoolSize too high across many pods | Idle connections waste server resources | Tune to warm-up behavior and real load |
| Unbounded reactive fan-out | Pool queues, memory, and latency spike | Cap concurrency and batch queries |
| Measuring only mean latency | Misses p99 tail and burst incidents | Track histograms and per-stage timings |

## 12. Practice Lab

Set up a Spring Boot + Spring Data MongoDB application connected to a test MongoDB replica set with an orders dataset spanning multiple tenants and statuses.

1. Run baseline MongoTemplate queries; record throughput, HTTP p95/p99, command duration, checkout wait, and connection counts.
2. Pick a traditional timeout configuration and measure behavior when the primary becomes unavailable or sockets are throttled. If your driver supports CSOT, create a separate config with timeoutMS and compare.
3. Test maxPoolSize 10, 20, and 40 under identical load; explain why one setting outperforms the others.
4. Implement an upsert with a deterministic requestId, simulate transient errors, and verify only one record exists.
5. Run an unindexed query on test data, measure its impact on the pool, then add the index and re-verify.
6. Scale pod replicas and inspect total connections to primary, checkout p95, and MongoDB CPU.
7. If using reactive access, bound flatMap concurrency and compare against unbounded fan-out.
8. Write a report documenting chosen config, SLOs, driver version, workload, and before/after measurements.

**Self-assessment questions:**

- How does serverSelectionTimeoutMS differ from connectTimeoutMS and socketTimeoutMS?
- When timeoutMS enables CSOT, how are legacy timeouts handled?
- Why does a write timeout not prove that data was not written?
- Why can retries across HTTP, service, and driver layers multiply MongoDB load?
- Does maxPoolSize=40 cap the entire cluster at 40 connections?
- When checkout wait is high and MongoDB CPU is 95%, should you immediately enlarge the pool?
- ReactiveMongoTemplate reduces thread blocking, yet what pool limits still apply?

Designing timeouts, retries, and pools must rely on **real workloads, SLOs, and metrics**. Setting meaningful deadlines, retrying only safe operations, and sizing pools to measured concurrency allow services to handle heavy traffic without compounding failures when MongoDB degrades.

## 13. References

- [MongoDB Java Sync Driver – Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/): per-server pool configuration and limits.
- [MongoDB Java Sync Driver – Socket Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/socket-settings/): connectTimeoutMS and socketTimeoutMS.
- [MongoDB Java Sync Driver – Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/): serverSelectionTimeoutMS.
- [MongoDB Java Sync Driver – Limit Server Execution Time](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/): timeoutMS and CSOT.
- [MongoDB Server – Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): conditions and limits of retryable writes.
- [MongoDB Server – Retryable Reads](https://www.mongodb.com/docs/manual/core/retryable-reads/): retryable read commands.
- [MongoDB Server – Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): URI options for timeouts, pools, and retries.
- [Spring Boot 3.x – Working with NoSQL Technologies](https://docs.spring.io/spring-boot/3.4/reference/data/nosql.html): MongoClient and auto-configuration.
- [Spring Data MongoDB – Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): Query.maxTime and MongoTemplate.
