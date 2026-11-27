# Consistency, Latency, and Partial Failure When Calling Remote Services

A Spring Boot application writes an order to a database, sends an event to a queue, and saves an invoice to object storage. All three managed services may be operating normally, yet errors still occur: the API commits successfully while the caller receives a timeout; a consumer processes the same message twice; a database replica does not yet show the latest update; or one slow service exhausts HTTP worker threads.

That is the nature of **distributed systems**: components communicate over a network, do not share a single synchronized point of observation, and can fail independently. Within the **Cloud Platforms** chapter, this lesson helps learners in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module practice integrating Spring Boot with managed storage, messaging, databases, and secrets on **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries—while configuring identities, permissions, timeouts, retries, failure tests, and evaluating differences across providers.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **consistency** levels and select appropriate expectations for each read/write flow.
- Explain network latency, tail latency, deadlines, timeouts, and the impact of synchronous call chains.
- Recognize **partial failures**: one component succeeds while another fails, or the client cannot determine the outcome.
- Design retries, exponential backoff, jitter, circuit breakers, bulkheads, and conditional concurrency limits.
- Use **idempotency keys**, transactional outbox/inbox, deduplication, and acknowledgements to prevent duplicate business side effects.
- Compare consistency and delivery semantics of Amazon S3/SQS/RDS, Azure Blob/Service Bus/SQL, and Google Cloud Storage/Pub/Sub/Cloud SQL.
- Build integration tests covering network errors, slow responses, duplicate messages, read-replica lag, and misconfigured permissions.

## 2. What Steps Does a Remote Request Actually Go Through?

Calling a REST API, sending a message, or querying a cloud database is never just invoking a Java method. For example, a request may go through:

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Spring Boot
    participant S as Managed service
    participant R as Data replica
    U->>A: POST /orders
    A->>S: Write order status
    S->>S: Commit succeeds
    S--xA: Response lost on network
    Note over A: Timeout, unknown if committed
    A-->>U: 504 / transient error
    S-->>R: Replicate if configured
    Note over R: May lag per replica model
    U->>A: Retry same business request
~~~

From Spring Boot's perspective, **a timeout only means no result arrived within the wait window**; it **does not prove** the target service failed to process the request. Retrying an operation with side effects without safeguards can create two orders, two payments, or two messages.

Similarly, reading from a replica right after writing to the primary may return stale data while reading the primary already reflects the new state. This is an issue of **consistency and read routing**, not necessarily data loss.

## 3. Types of Partial Failure

A *partial failure* occurs when **some components or calls fail while others continue operating**. Even a monolith can fail, but network boundaries and independently managed resources make the following scenarios far more common in the cloud:

| Situation | What the Application Observes | What May Actually Have Happened |
|---|---|---|
| Cannot connect | Connection refused, DNS error, or timeout | Service down, network blocked, wrong DNS, wrong endpoint |
| Connected, but reading response expires | Read timeout | Server may not have processed yet, is processing, or already committed |
| API A succeeds, API B fails | Failure at second step | Data written at A; overall state is left incomplete |
| Sent to queue, publisher misses ACK | Timeout/transport error | Message may have been accepted and will be delivered |
| Worker finishes processing, ACK is lost | Message reappears | Business action completed; broker redelivers due to missing ACK |
| Primary updated, replica lags behind | Reads return stale value | Asynchronous replication still catching up |
| One AZ/Region degrades | Some requests slow or fail | Other zones/regions may still serve traffic |
| IAM/token expired or permissions revoked | 401/403/PermissionDenied | Network is fine; request blocked by authentication or authorization |
| Quota or throttling | 429/ResourceExhausted/Throttling | Service is protecting capacity; aggressive retries worsen the situation |

Do not lump every remote failure into "service unavailable". Distinguish **transient errors**, **configuration/permission errors**, **invalid request errors**, **indeterminate outcomes**, and **permanent business errors**.

## 4. Consistency: How Fresh Is the Data You See?

### 4.1. Not Every System Offers the Same Consistency Level

**Strong consistency** is a general term meaning certain reads reflect the results of completed writes as committed by the service. Speaking strictly about single objects, **linearizability** requires operations to appear to take effect atomically at some point between invocation and completion, respecting the real-time order of completed operations.

**Eventual consistency** allows replicas to diverge temporarily and converge if no new updates occur, subject to system conditions and service commitments. It **does not guarantee a fixed number of seconds** that an application can blindly assume. Inspect SLAs, bounds, and replica-lag observability if available.

**Session consistency** and related guarantees such as read-your-writes allow a session or client to observe its own writes under applicable conditions (e.g., passing a session token, routing to primary, or providing a session token). **Bounded staleness** limits how stale data can be in terms of time or version lag where supported. Guarantees around **observation ordering** and **transaction commit ordering** must be evaluated separately.

| Model | Typical Experience | Watch Out For |
|---|---|---|
| Strong/linearizable for supported operations | Reading the same object after a write completes returns the new committed result | Does not automatically create cross-resource transactions |
| Eventual | Replicas or indexes may return stale values after a write | Design to tolerate stale reads or wait for convergence |
| Read-your-writes/session | Clients in the same session see their own updates under service rules | Session tokens, read routing, and client lifecycle matter |
| Bounded staleness | Reads have bounded lag per service mode | Trade-offs across latency, availability, throughput, and deployment scope |
| Snapshot/transactional isolation | Multiple operations in a transaction read a consistent state per isolation level | Must understand isolation levels, transaction scope, and conflict handling |

**Strong consistency on a single object** does not mean atomic transactions across objects, databases, and queues. **Durability**, **availability**, and **read consistency** are distinct properties.

### 4.2. Phenomena Applications Must Handle

- **Stale read:** order was just updated, yet the detail page reading from a replica returns the old status.
- **Read skew:** within one flow, reads from different timestamps/replicas combine states that never existed simultaneously.
- **Lost update:** two requests read the same old version and overwrite each other without optimistic locking or concurrency control.
- **Out-of-order events:** a "Delivered" event reaches a consumer before "In Transit"; blind updates can move status backward.
- **Phantom or non-repeatable reads:** inside a database transaction, result sets or values may change on re-read depending on isolation level.
- **Duplicate side effect:** the same command runs twice due to retries, even though each attempt succeeds technically.

Example using optimistic locking for orders:

~~~sql
UPDATE orders
SET status = :new_status, version = version + 1
WHERE id = :order_id
  AND version = :expected_version;
~~~

If zero rows are updated, the application must **re-read and resolve the conflict** or reject the change; never blindly retry with the stale version. This guards updates within **a single database transaction** and does not solve publishing events to a message broker.

## 5. Practical Differences Across AWS, Azure, and Google Cloud Services

You cannot label entire providers as "AWS eventual, Azure strong, GCP strong". **Each service, operation type, replica mode, and configuration** dictates the actual guarantees.

### 5.1. Object Storage

| Provider | Behavior to Know | What Not to Infer |
|---|---|---|
| **Amazon S3** | For S3 general purpose buckets, object PUT/GET/LIST operations and related metadata/tag updates provide strong consistency per service docs; specialized variants have distinct traits | No atomic multi-object transactions; cross-region replication can be asynchronous |
| **Azure Blob Storage** | Primary endpoints provide strong consistency for operations per Blob commitments; ETags/conditional requests support concurrency control | Reads from geo-replicated secondary endpoints can lag behind primary; redundancy does not stop accidental deletion |
| **Google Cloud Storage** | Object read-after-write, updates/deletes, and object listing have strong consistency within published service scope | No distributed SQL transactions across multiple objects; replication across locations follows its own timeline |

For instance, downloading the same invoice and seeing stale contents may come from a **cache/CDN, client cache, geo-replica, proxy, or application layer**, not necessarily the primary object store's consistency model. Verify the exact endpoint and caching layers.

Object storage provides ETags or generations/versions in many cases. For concurrent writes, consider **conditional writes**, versioning, or generation checks per service; do not rely solely on "last write wins" for critical correctness.

### 5.2. Databases and Replicas

| Service | Consistency Example | What to Design in Spring Boot |
|---|---|---|
| **Amazon RDS** | Engine transactions and isolation on primary; read replicas typically replicate asynchronously | Read-after-write flows must route to primary or tolerate replica lag |
| **Amazon DynamoDB** | Eventual reads by default for many operations; strongly consistent reads selectable for tables and local secondary indexes where supported; GSIs and global tables have distinct behavior | Select ConsistentRead where supported; do not assume instant reads on GSIs/global replicas |
| **Azure SQL Database** | SQL engine transactions; geo-secondaries/read scale-out can exhibit sync lag depending on mode | Understand primary/read-only endpoints, isolation, and failover |
| **Azure Cosmos DB** | Offers selectable levels such as Strong, Bounded Staleness, Session, Consistent Prefix, Eventual, with configuration limits | Choose the right level and pass session tokens when read-your-writes is needed |
| **Google Cloud SQL** | Engine transactions on primary; read replicas can lag | Avoid using replicas for decisions requiring latest data unless verified |
| **Cloud Spanner/Firestore** | Dedicated consistency guarantees, strong for published operation categories | Read using the product's exact modes and transaction semantics |

**Example:** after payment, the API updates the orders table on primary. An order history page reading from a read replica may still show "Unpaid". Solutions include reading from primary for a window after writes, tracking versions to indicate syncing state, or designing UI flows that tolerate eventual consistency. Do not assume increasing timeouts fixes replica lag.

### 5.3. Messaging and Delivery Semantics

| Service | Typical Design Need | Notes |
|---|---|---|
| **Amazon SQS Standard** | At-least-once delivery; duplicates and out-of-order deliveries can occur | Idempotent consumers, visibility timeout, DLQ |
| **Amazon SQS FIFO** | Ordering within a message group, deduplication within service scope/window | Does not make the entire business flow exactly-once; retries beyond the dedup window still need handling |
| **Azure Service Bus** | Peek-lock/complete-abandon, retries, DLQs, sessions, and duplicate detection if configured | Locks can expire or ACKs can fail; duplicate detection does not replace business dedup |
| **Google Cloud Pub/Sub** | Typically at-least-once; ordering keys and exactly-once delivery are conditional features | Exactly-once delivery does not mean DB side effects execute only once |

The label **exactly-once** in a service usually describes a **narrow delivery or API boundary**. Never expand it mentally into "every DB update, HTTP call, email send, and payment executes once". Consumers must actively handle duplicates, and producers must handle cases where publish succeeded but the response was lost.

### 5.4. Secrets and Distributed Configuration

Secret rotation can create transition windows: instance A caches the old credential, instance B fetches the new version, while the database accepts one or two versions depending on the rotation workflow. Rotation designs should support **controlled transition periods**, cache refreshes, retiring old secrets, and connection validation. AWS Secrets Manager, Azure Key Vault, and Google Cloud Secret Manager expose different APIs/version states; avoid fetching secrets on every single request or assuming cached values are instantaneously consistent everywhere.

## 6. Latency: Measure the Full Journey Instead of Just Server Processing Time

Cloud request latency can include DNS, connection establishment, TLS, network transit between locations, connection pool wait, server queueing, business processing, durable storage writes, and response transmission.

~~~mermaid
flowchart LR
    A["Spring Boot"] --> P["Pool / DNS / TLS"]
    P --> N["Network"]
    N --> Q["Queueing"]
    Q --> S["Service processing"]
    S --> R["Response"]
    R --> A
~~~

Many SDKs keep persistent connections alive to avoid setup overhead. If request volume exceeds connection pool capacity, the application stalls **before even sending the request**. When one synchronous call slows down, threads/connections are held longer, queues grow, and cascading failures can ensue.

### 6.1. Averages Are Not Enough

If most requests are fast while a small percentage are very slow, **average latency** hides poor user experience. Track **p50, p95, p99**, timeout rates, error rates, and saturation (queued requests, pool usage, CPU, queue depth). Break down metrics by service, operation, Region, and caller.

**Tail latency** climbs sharply when multiple independent calls must all succeed before an API responds. One slow call can dictate the latency of the entire request. Synchronous call chains accumulate delays additively; parallel fan-outs suffer from the slowest call and increase total load on downstreams.

### 6.2. Geographic Placement and Network Paths

- If Spring Boot runs in one Region while the managed database is in another, every round-trip increases latency and data-transfer costs.
- Private endpoints/PrivateLink/Private Service Connect change access paths and network security posture, yet do not automatically guarantee lower latency in every topology.
- TLS, proxies, gateways, NAT, DNS, load balancing, and quotas all impact wall-clock latency.
- Retrying across Regions or failing over to another Region can alter both response times and consistency behavior.

**Design rule:** place operations requiring transactions or synchronous reads/writes as close to the data as permitted by residency rules; measure from the real runtime environment before optimizing.

## 7. Timeouts and Deadlines: Never Wait Forever

A **timeout** bounds the wait for a single phase or operation. A **deadline** is the expiration timestamp for **the entire business request**. A request traversing API Gateway → Spring Boot → database → queue cannot let every hop spend the entire time budget and still expect to respond on time.

Common timeout types:

| Limit | What It Protects | When Misconfigured |
|---|---|---|
| Connection/acquire timeout | Waiting for a connection pool slot or connection setup | Threads stall while pool is exhausted or network cannot reach target |
| Connect timeout | Waiting for network connection establishment | Long hangs when target refuses/drops connections |
| Read/response timeout | Waiting for response bytes or operation completion | Fails to detect hung servers or runaway requests |
| Per-attempt timeout | Bounds each SDK/API attempt | One attempt burns the whole budget, leaving no time for recovery |
| Overall operation deadline | Bounds all attempts, backoff, and related work | Retries keep running after caller has already given up |
| Message visibility/lock timeout | Window a consumer holds a message before redelivery | Message redelivered mid-processing, or held too long when a worker crashes |

For example, an API with a **2-second** deadline (illustrative figure) must budget for authentication, DB queries, event publishing, and response formatting, plus safety margin. If the DB step consumed nearly the whole budget, do not keep retrying event publishing synchronously in the same request. Instead, write an outbox row inside the transaction and let a worker publish asynchronously.

Sensible timeouts must rely on **latency measurements**, downstream traits, safe retryability, and SLOs. Setting timeouts too low causes false failures; too high causes thread/pool exhaustion. Ensure overall timeouts are not accidentally shorter than valid long-polling, streaming, or batch operations.

**Client-side cancellation does not roll back server-side state.** This is the cornerstone rule when designing retries for side effects.

## 8. Retries: Requiring Conditions, Bounds, and Idempotency

### 8.1. When Retries Make Sense

Retrying is reasonable for certain **transient** failures such as brief connection drops, 429/throttling, 503/service unavailable, or fleeting network glitches—**if the operation can be retried safely**. Distinguish carefully:

| Error | Recommended Handling |
|---|---|
| 429 / throttling | Back off, honor Retry-After if present, reduce concurrency |
| Transient 502/503/504 | Bounded retry if deadline remains and side effects are safe |
| Connect timeout before sending request | Often retryable if confirmed no side effect occurred; SDKs handle specifics |
| Read timeout after request sent | Outcome is **unknown**; require idempotency keys or status checks |
| 400 / validation error | Fix input data; never retry the exact same request |
| 401/403 / permission denied | Check token, audience, role, IAM/RBAC, and network; never retry blindly |
| 404 / resource missing | Check ID/Region/endpoint; some APIs have propagation delays, verify specifically |
| Concurrency conflict / 409 | Use optimistic concurrency, re-read, and recompute; never loop blindly |

HTTP status is only one signal. SDKs define their own exception hierarchies and retry modes; a 500 error can still accompany a succeeded side effect. For databases, inspect SQLState, transaction error classes, and commit/rollback state before repeating a command.

### 8.2. Exponential Backoff and Jitter

Instead of hammering a service continuously, increase wait intervals exponentially and add **jitter** so multiple clients do not burst simultaneously onto a recovering service. Conceptual model:

~~~text
backoff_k = min(maxDelay, baseDelay * 2^k)
sleep_k   = random(0, backoff_k)  # full jitter, illustrative

stop when:
  - total attempts exceeded;
  - overall deadline expired;
  - non-retryable error;
  - side-effect safety cannot be guaranteed.
~~~

This formula is explanatory only; production should use the SDK's retry policy or a battle-tested library. AWS SDKs, Azure SDKs, and Google Cloud client libraries each have **different default retry behaviors per API**, handling throttling, status codes, and backoff differently. Before wrapping calls in external Spring Retry/Resilience4j, inspect SDK settings to avoid **nested retries** (SDK retries multiple times and the service layer retries on top), causing a retry storm.

### 8.3. Idempotency: The Safety Check for Retries

An operation is **idempotent** if repeating it with the same intent causes no further change to business state beyond the effect of the first execution. Examples:

- Reading an object with GET normally produces no business side effects.
- Updating an order status to **PAID** can be idempotent if keyed by an event ID ensuring single application.
- **Creating a new order without an idempotency key** is typically not idempotent: retries can create a second order.
- Re-sending a message can create duplicate messages; broker dedup features only mitigate this within defined scopes.
- Uploading identical bytes to the same key yields identical read content, yet still creates **new object versions or billing/side effects** if bucket versioning is enabled; do not treat that as "exactly-once".

For HTTP POST order creation or payment provider calls, clients send a stable **idempotency key** per business intent. The server persists the key alongside a payload fingerprint and outcome, rejects cases where the same key carries a different payload, and replays the stored result on retries. Choose TTL and uniqueness scope per business workflow; keys must never live solely in one instance's RAM.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring Boot API
    participant D as Transactional database
    C->>A: POST /orders (idempotency-key = K)
    A->>D: Write K + order + result in one transaction
    D-->>A: Commit
    A--xC: Response lost
    C->>A: Retry POST /orders (same K)
    A->>D: Check K, payload fingerprint
    D-->>A: K already completed, prior result
    A-->>C: Return original order result
~~~

Handle **two concurrent requests sharing the same key** using appropriate unique constraints/transactions/locking; a naive "SELECT to check existence then INSERT" without concurrency protection suffers from race conditions.

## 9. Circuit Breakers, Bulkheads, and Backpressure

Retries cannot fix a downstream that has lost capacity. Three complementary patterns:

**Circuit breaker** monitors failures/slowness and temporarily blocks new requests once a threshold trips; after an interval, it permits a few probe requests to test recovery. It sheds load, yet can reject valid requests during recovery if thresholds and metrics are poorly tuned.

**Bulkhead** partitions thread, connection, or concurrency limits per downstream type. If the invoice-storage service slows down, it must not exhaust shared resources and take down an endpoint that merely reads order status.

**Backpressure/rate limiting** caps work production or consumption speed so downstreams can keep up. For messaging, cap concurrency/prefetch and watch queue depth/age and retries/DLQs. For synchronous APIs, return controlled 429/503 responses instead of building unbounded queues.

~~~mermaid
flowchart LR
    API["Spring Boot API"] --> L["Concurrency limit"]
    L --> CB["Circuit breaker"]
    CB --> RT["Retry with deadline + jitter"]
    RT --> S["Managed service"]
    CB -. "Open" .-> F["Fallback / controlled error response"]
    S --> M["Metrics: latency, errors, saturation"]
    M -. "Adjust thresholds" .-> L
~~~

Fallbacks only make sense when **business-valid**: showing "updating" from cache may be acceptable on a listing screen, whereas claiming payment succeeded without payment-provider confirmation is never acceptable.

## 10. Messaging: At-Least-Once, ACKs, and Duplicates

### 10.1. ACKs Can Fail After Processing Succeeds

A typical consumer flow:

1. Receive message along with delivery identifier.
2. Open a database transaction, apply the business change, and record the processed event ID.
3. Commit the transaction.
4. ACK/Complete/Delete the message after step 3 succeeds.

If the worker crashes between step 3 and step 4, the broker may redeliver the message. Then **the database must recognize the event was already applied** and skip repeating side effects.

~~~mermaid
sequenceDiagram
    participant Q as Queue / PubSub
    participant W as Spring Boot consumer
    participant DB as Database
    Q->>W: Event E delivery 1
    W->>DB: Commit business change + processed(E)
    DB-->>W: OK
    W--xQ: ACK lost
    Q->>W: Event E delivery 2
    W->>DB: Check processed(E)
    DB-->>W: Already processed, skip re-execution
    W->>Q: ACK succeeds
~~~

**Broker-assigned message IDs are not necessarily stable across separate publish attempts for the same business event.** If a producer retries publishing and creates a new message, include an **application-generated eventId** inside the payload/attributes so consumers deduplicate across publish retries as well.

### 10.2. Provider Differences to Remember

- **SQS Standard:** at-least-once; duplicates and global out-of-order deliveries can occur. Visibility timeouts must reasonably cover processing time, yet idempotency is still mandatory.
- **SQS FIFO:** ordered per message group; deduplication follows SQS FIFO's specific scope and window. Using an event ID as the dedup ID helps, yet beyond the dedup window or across downstream side effects, business-layer deduplication is still required.
- **Azure Service Bus:** Peek-Lock has a lock duration; long processing requires renewal via SDK/service mechanisms. Lost Complete calls trigger redelivery. Duplicate detection and sessions are opt-in features per requirements and do not replace DB dedup.
- **Google Cloud Pub/Sub:** ack deadlines can be extended by the client library within supported limits; unacknowledged messages can be redelivered. Exactly-once delivery has product-specific conditions, scope, and limits; systems must still protect DB side effects.

DLQs isolate **poison messages** after repeated failures for controlled investigation and replay. Never retry infinitely on schema-invalid payloads, missing-permission records, or unrecoverable business errors. When event ordering matters, use sequences/versions and state-machine validation; broker ordering alone does not guarantee update ordering across all consumers and downstreams.

## 11. Distributed Transactions: Why @Transactional Alone Is Not Enough

Spring's **@Transactional** annotation typically wraps a single **transaction manager** (for instance, one database). It does not magically create an atomic transaction spanning PostgreSQL and SQS, Azure Service Bus, Pub/Sub, S3, or HTTP APIs. Example:

~~~text
BEGIN DATABASE TRANSACTION
  UPDATE orders SET status = 'CONFIRMED'
COMMIT

PUBLISH OrderConfirmed TO QUEUE
~~~

If commit succeeds yet publish fails, the database holds a confirmed order without an emitted event. Reversing order to publish before commit lets events be processed even if the DB transaction later rolls back. **No simple ordering of two separate calls makes both systems atomic.**

### 11.1. Transactional Outbox

**Transactional outbox** writes both the business state change and an outbox row **inside the same database transaction**. A separate worker reads unsent rows, publishes them to the broker, and marks them sent:

~~~mermaid
flowchart TD
    API["Spring Boot API"] --> TX["Single database transaction"]
    TX --> ORD["Update orders"]
    TX --> OUT["Insert outbox_event"]
    OUT --> PUB["Outbox publisher"]
    PUB --> MQ["SQS / Service Bus / PubSub"]
    MQ --> CON["Idempotent consumer"]
    PUB -. "Publish ACK lost: retry" .-> OUT
~~~

When publish succeeds yet updating the outbox status fails, the publisher may resend. Thus, outbox improves **reliable event delivery**, yet **does not eliminate duplicates**. Consumers still need **inbox/dedup** or idempotent operations. Outbox workers need locking/claiming so multiple instances do not over-process the same rows, alongside retries/backoff and stuck-record monitoring.

### 11.2. Saga / Compensation

For workflows spanning multiple independent services (order placement, inventory reservation, payment, shipping), you can use a **Saga**: each step is a local transaction, and if a later step fails, **compensating** steps run per business rules. Compensation is not necessarily a clean physical undo; for example, restocking inventory and issuing refunds are stateful business actions themselves that can fail and require retries/auditing.

Sagas need explicit state tracking, idempotency on both forward and compensating actions, out-of-order event handling, and partner timeouts. Do not replace this with distributed locks or assume every API supports XA/2PC.

## 12. Spring Boot Example: Database-Backed Idempotent Consumer

Suppose the application receives **OrderStatusChanged** events via SQS, Service Bus, or Pub/Sub. Each event contains a unique producer-generated **eventId**, orderId, and status. The idea is to store the processed event key together with the status update **in a single transaction**.

**PostgreSQL** DDL example:

~~~sql
CREATE TABLE processed_message (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(200) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Spring Boot service (Java 17+, using Spring JDBC and a transaction manager on the same datasource):

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderStatusChanged(
        String eventId, long orderId, String newStatus) {}

@Service
public class OrderEventHandler {
    private final JdbcTemplate jdbc;

    public OrderEventHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void handle(OrderStatusChanged event) {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }

        int newlyRecorded = jdbc.update(
                "INSERT INTO processed_message (consumer_name, event_id) " +
                "VALUES (?, ?) ON CONFLICT DO NOTHING",
                "order-status-consumer",
                event.eventId());

        if (newlyRecorded == 0) {
            return; // Event was already committed previously.
        }

        int updated = jdbc.update(
                "UPDATE orders SET status = ? WHERE id = ?",
                event.newStatus(), event.orderId());
        if (updated != 1) {
            // Exception rolls back the transaction including the dedup record.
            throw new IllegalStateException("Order not found");
        }
    }
}
~~~

Key takeaways:

- This snippet illustrates **PostgreSQL** because it uses **ON CONFLICT DO NOTHING**; adapt the syntax for SQL Server, MySQL, or other engines.
- The **unique key** prevents two parallel consumers from applying the same event ID simultaneously. Both the `orders` update and the dedup insert must share **the same transaction/datasource**.
- The broker listener/adapter must **ACK only after the handler method and database commit succeed**. Exact ACK configuration varies across Spring Cloud AWS, Spring Cloud Azure, Spring Cloud GCP versions, and client libraries.
- Never catch exceptions and return success after a DB rollback, as the broker might mistakenly ACK and drop work.
- This logic guards against **duplicate eventIds**, not **out-of-order events**. If statuses have sequence/versions, add sequence checks or valid state-transition checks; if an order is permanently missing, handle it via a poison-message policy rather than infinite retries.
- Do not store sensitive payloads in the dedup table merely for duplicate detection; store an appropriate fingerprint with retention rules instead.

Real-world systems also need transaction timeouts, lock-duration controls, cleanup strategies for `processed_message`, and protection against the same `eventId` being reused with different payloads.

### 12.1. Why Broker Locks Do Not Replace Database Deduplication

Visibility timeouts (SQS), Peek-Lock (Service Bus), and ack deadlines (Pub/Sub) manage **message delivery leases**, not business database transaction locks. A consumer can commit and crash right before ACKing; the message gets redelivered to another consumer. Designs must therefore tolerate at least **redelivery after commit**.

## 13. Designing Timeouts and Retries in Spring

Property names in Spring Cloud AWS, Spring Cloud Azure, and Spring Cloud GCP **vary across versions**, and many operations rely directly on the AWS SDK, Azure SDK, or Google Cloud client's own retry policies. Rather than assuming one property name covers everything, identify which layer actually governs each timeout:

1. **HTTP/Web client:** connect timeout, response timeout, max connections, pool acquisition, TLS.
2. **Managed service SDK:** per-attempt timeout, overall timeout, retry conditions, backoff/jitter, API deadlines.
3. **Message listener:** concurrency, prefetch, visibility/lock/ack deadline, exception handling, and DLQ.
4. **Business flow:** end-to-end deadline, idempotency, circuit breaker, bulkhead, fallback.

The values below are purely an **application-defined configuration sample**, not Spring Cloud auto-configured properties:

~~~yaml
integration:
  orders:
    overall-deadline: 2s
    max-attempts: 3
    backoff-base: 100ms
    backoff-cap: 1s
    max-concurrent-requests: 40
  consumer:
    max-concurrency: 8
    dead-letter-after-failures: 5
~~~

These numbers are **illustrative values**, not recommendations to copy verbatim. Each application must bind and enforce them via code or appropriate libraries; properties do nothing by themselves. Tune them using SLOs, message sizes, measured latency, throughput, quotas, and service limits.

If using **Resilience4j/Spring Retry**, place retries at **one or a few controlled layers**, knowing whether the SDK already retries internally. Never let the API layer retry 3 times, the service layer 3 times, and the SDK 3 times unintentionally, multiplying downstream load. When a single overall deadline propagates down the call stack, all attempts must stop once the budget expires.

For operations with **side effects**, enforce idempotency or business reconciliation before allowing retries. Even for idempotent read calls, use backoff and caps to avoid overwhelming downstreams.

## 14. Integration Testing: Fault Injection in an Isolated Environment

Testing "write and read succeed" is necessary but insufficient. Verify **correct failure behavior** in a test environment isolated from production:

| Scenario | How to Trigger | Expected Outcome |
|---|---|---|
| Delayed response | Test proxy/fault injection adds latency | Times out within budget; no unbounded thread hold |
| Server commits, ACK/response lost | Test adapter simulates indeterminate outcome after commit | Retries with same idempotency key; single business side effect |
| Two requests with same idempotency key | Send concurrently in test environment | Unique constraint/locking permits only one execution |
| Message redelivery | Skip initial ACK or let lock expire in test | Consumer receives again without applying DB changes twice |
| Publisher fails after DB commit | Interrupt publish in outbox worker test | Outbox retains record; retries publish and consumer dedups |
| Read replica lag | Read from test replica right after primary write | UI/API tolerates stale read or routes to primary when needed |
| API throttling 429 | Controlled quota mock/trigger in test | Backoff, jitter, no retry storm, metrics emitted |
| IAM 403 / wrong endpoint | Under-privileged test identity or wrong test endpoint | Fails at right layer, reports root cause, no auto-escalation |
| Prolonged slow downstream | Throttle throughput and slow test service | Circuit breaker/bulkhead protects unrelated endpoints |
| Out-of-order events | Publish out-of-order sequence in test | Version/state machine blocks backward state transitions |
| Poison message | Schema-invalid payload or invariant violation | Routed to DLQ/quarantine per policy with alerts |
| Recovery/DR | Rehearse node/zone loss or service failover | Recovery flow meets designed RTO/RPO |

**Mocks** can verify retry code and idempotency logic, yet cannot replace cloud tests for IAM, quotas, networking, replica consistency, dead-letter behavior, or costs. When testing against real services, use dedicated resources, cost caps, and cleanup mechanisms.

### 14.1. Metrics to Collect

- **Requests:** p50/p95/p99 latency, attempt counts, timeout counts, status/exceptions per operation, in-flight requests, pool saturation.
- **SDK/retries:** retry counts, backoff, throttling, total operation duration, circuit breaker open rates.
- **Messaging:** message age, backlog, delivery counts, lock/visibility expirations, DLQ depth, suppressed duplicates, consumer lag.
- **Database:** pool usage, lock waits, transaction duration, commit failures, read-replica lag, conflict rates.
- **Business:** actual orders created, payment attempts, pending outbox events, reconciliation counts, data loss/recovery duration.

Logs should record trace IDs, request IDs, event IDs, safely sanitized idempotency keys, resource IDs, Region, and attempt numbers; **never log tokens, passwords, raw secrets, payment data, or sensitive payloads**. Tracing shows how far the client got, yet when a response is lost it **does not prove the server failed to commit**.

## 15. Provider-Specific Application Scenarios

### 15.1. AWS: S3 + SQS + RDS

Spring Boot creates an order in RDS and writes an outbox row in the same transaction. The outbox worker publishes the event over SQS. On send timeouts, the worker may resend; the consumer deduplicates using event ID. When reading objects from S3, remember object operations have their own consistency guarantees; if reading through a CDN, cache, or cross-Region replication, account for those sync mechanisms. With RDS read replicas, order-confirmation read-your-writes flows should query primary or manage replica lag.

SQS Standard consumers must tolerate duplicates. Even when using FIFO to preserve ordering per order ID/message group, still validate event sequences and protect DB side effects.

### 15.2. Azure: Blob + Service Bus + Azure SQL

The application writes invoices to Blob Storage and emits events via Service Bus. If the consumer writes to Azure SQL yet fails to Complete the message due to network loss or lock expiration, the message can reappear; the `processed_message` table skips duplicate side effects. When reading from geo-secondary replicas of storage or SQL, freshness can trail primary. Tune retries and lock renewal within SDK and service limits.

Azure Managed Identity avoids storing long-lived credentials, yet missing RBAC data roles or misconfigured private endpoint DNS still fail calls. Do not handle every 403 by retrying; check the principal, role scope, and networking.

### 15.3. Google Cloud: Cloud Storage + Pub/Sub + Cloud SQL

The application saves objects in Cloud Storage, publishes events to Pub/Sub, and updates Cloud SQL. Cloud Storage's strong guarantees on object operations do not create atomic transactions between objects and the DB. If the producer publishes successfully yet loses the response, duplicate events can appear; consumers need business-generated event IDs.

Pub/Sub ordering keys or conditional exactly-once delivery do not eliminate the need for idempotency in Cloud SQL. Cloud SQL read replicas can still exhibit replica lag. Service accounts require exact permissions on buckets/topics/secrets; a 403 is not a consistency issue.

## 16. Misconceptions That Frequently Cause Production Incidents

| Misconception | Reality |
|---|---|
| "Timeout means the server didn't process it" | The server may have committed; the client simply didn't receive the result |
| "Retrying every exception is good" | Retries can multiply side effects, overload services, and blow past deadlines |
| "The SDK already retries so idempotency isn't needed" | Retry policies do not automatically enforce business correctness |
| "Object storage strong consistency means multi-object transactions" | Guarantees are generally per operation/object; cross-system transactions do not exist automatically |
| "Same project/Region means all replicas are equally fresh" | Location and replica type determine synchronization lag |
| "FIFO queues guarantee every consumer runs exactly once" | Ordering/dedup have scopes; DB commits and ACKs can still diverge |
| "@Transactional covers SQS/Pub/Sub/Service Bus sends" | A DB transaction manager is not automatically atomic with external brokers |
| "Raising visibility timeout prevents duplicates forever" | Crashes/ACK losses still cause redeliveries; processing must be idempotent |
| "Reading from cache/replica fits every screen" | Business decisions may require fresh reads from primary |
| "Circuit breakers fix the root cause of errors" | They limit blast radius; downstream issues still need diagnosis and fixes |
| "Secret manager handles rotation so apps switch instantly" | Credential caching, connection pools, and version transitions still require design |

## 17. Checklist Before Taking Cloud Integrations to Production

- **Consistency contract:** document freshness guarantees per service and operation; define primary, replica, cache, and index read paths.
- **Latency budget:** set overall deadlines and per-layer timeouts based on p95/p99 and SLOs; monitor pool saturation.
- **Retries:** define retryable criteria, backoff/jitter, and attempt caps; check SDK default retries to prevent nesting.
- **Idempotency:** assign stable event/request IDs per business intent, unique constraints, payload-mismatch checks, and concurrency handling.
- **Messaging:** ACK after commit, handle redeliveries/duplicates/out-of-order events, configure DLQs, and design safe replay.
- **Transactions:** use outbox/inbox or Sagas for cross-system side effects; never rely on `@Transactional` for broker atomicity.
- **Security:** grant roles/managed identities/service accounts only required permissions, verify endpoints/Regions, keep secrets out of logs.
- **Reliability controls:** configure circuit breakers, bulkheads, concurrency caps, and business-valid fallbacks.
- **Testing:** test lost responses after commit, timeouts, retry storms, replica lag, duplicates, 403/429s, and recovery in staging.
- **Observability:** track latency, retries, duplicates, DLQs, replica lag, backlog, reconciliations, and traces linked by event ID.

## 18. Summary

When Spring Boot calls remote managed services, **consistency** governs which data is visible, **latency** governs whether requests finish within time budgets, and **partial failure** creates situations where one step succeeds while the next fails or responses vanish in transit. No single timeout or retry setting solves all three concerns.

Safe integrations with AWS, Azure, and Google Cloud require explicitly designing **consistency contract → deadline → bounded retries → idempotency → transactions/outbox → ACK → observability and recovery**. By understanding each layer and testing indeterminate outcomes, development teams can harness Spring Cloud and managed services while preserving data accuracy, predictable behavior, and operational resilience when cloud components fail.
