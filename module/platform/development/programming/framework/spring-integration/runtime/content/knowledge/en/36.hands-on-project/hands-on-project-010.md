# Complete Dossier: Topology, Lifecycle, State, Recovery, and Operations

A Spring Integration flow cannot be considered **production-ready** just because it handles one message on a local machine. In production, it must also answer: which channel currently holds a message, when is it considered accepted, where do worker errors go, which state must survive restarts, who is allowed to stop a flow, and how do you prove zero data loss or duplicate processing during an incident?

This is the culminating **Hands-On Project** lesson of the **SPRING_INTEGRATION_RUNTIME** module. We build **a complete design and acceptance dossier** for an order-event intake system that processes events with consumers/pollers, persists durable state, controls lifecycles, and handles retries, recovery, correlation, and operations. It connects channels, endpoints, executors, transactions, message stores, error handling, observability, performance, and testing. Code examples target **Java 17+, Spring Integration 6.5.x, Spring Framework 6.x, and PostgreSQL**; actual dependency versions must be locked consistently via your project's BOM.

> **Success standard:** A message can be *accepted*, *processed*, *committed*, *acknowledged*, and *published* at **different instants**. The dossier meets acceptance criteria only when it defines exactly which milestone represents success for each API and includes tests proving recovery when processes die or dependencies fail.

## 1. Project Problem and Scope

An **Order Intake Runtime** service receives `OrderEvent` events from an HTTP gateway or message broker. The service must record events reliably, update order state in PostgreSQL, and write an outbox record so downstream systems receive the outcome.

Business assumptions:

1. An `eventId` identifies a **logical event**; producers may resend the same event on timeouts or redeliveries.
2. Each event belongs to a `tenantId` and `orderId`; event ordering within an order may matter, yet must never be assumed automatically across all channels.
3. Return `202 Accepted` to HTTP clients **only after the event is durably persisted** at a clearly designed intake point. If persistence fails, callers must know to retry.
4. On successful processing, order state and the outbox record must commit inside the same database transaction.
5. Transient failures undergo bounded retries; permanently invalid payloads route to quarantine/DLQ rather than retrying forever.
6. Shutdowns or rolling deploys must never silently drop queues or lose already-accepted events.
7. The system must expose topology, lifecycle state, backlog, errors/retries, message correlation, and recovery steps.

**Out of guarantee scope:** End-to-end exactly-once between PostgreSQL and remote HTTP/brokers. We rely on **at-least-once delivery at appropriate boundaries + idempotent business transactions + outbox/reconciliation**. If a remote consumer lacks idempotency, no Spring annotation can promise exactly-once.

### Required Deliverables in the Dossier

| Artifact in Dossier | Question It Must Answer |
|---|---|
| Topology manifest + diagram | Which components and threads does a message traverse? |
| Input/output contracts | What do accepted, completed, and failed mean? |
| State inventory + DDL | Which state lives in heap, JDBC stores, business tables, and DLQs? |
| Lifecycle state machine | When does ingress open, and when do drain and stop happen? |
| Recovery matrix | Do crashes/rollbacks/retries cause replays or message loss? |
| Java DSL + idempotent services | How are endpoints, queues, pollers, and transactions wired? |
| Test evidence | Which tests prove sync/async and post-restart behavior? |
| Dashboards, alerts, runbooks | How does on-call isolate full queues, executor rejections, and error spikes? |
| ADRs + risk register | Why were current trade-offs chosen, and what limits remain? |

The entire dossier is presented directly in this lesson. Filenames and code blocks serve as a **design blueprint to apply to a project**, not a claim that extra files were created or builds executed in this workspace.

## 2. Invariants Preserved Across the Entire Flow

A dossier is easier to sign off when it starts with **invariants** rather than a technology checklist:

| Code | Invariant | Evidence |
|---|---|---|
| INV-01 | Each business event ID is applied to the business DB at most once | Unique constraint + duplicate/redelivery tests |
| INV-02 | HTTP returns accepted only after durable intake commits, never before | Commit/rollback tests and API status assertions |
| INV-03 | Transactional poller processes one logical event in one consistent transaction when sharing a `DataSource` | Rollback tests covering receive and business writes |
| INV-04 | Never ACK/mark completed before reaching a defined terminal outcome | Adapter tests + DB/outbox reconciliation |
| INV-05 | All retries are bounded; poison events have quarantine and an owner | Exhaustion tests, DLQ metadata, runbook |
| INV-06 | Ingress closes before stopping consumers; accepted work drains or has a recovery path | Lifecycle and race tests |
| INV-07 | Stopping one flow/tenant never destroys shared resources | Ownership map + multi-tenant tests |
| INV-08 | Crashes do not erase durably saved state; restarts never replay terminal events | Restart tests reusing the same database |
| INV-09 | Correlation and tracing are distinct identifiers; never put raw event IDs in metric tags | Header contracts + metric validation |
| INV-10 | Operators have dashboards/alerts distinguishing queue, worker, and downstream bottlenecks | Runbook drills and metrics |

`INV-03` **holds only** if polling, `JdbcChannelMessageStore`, and business writes actually share **the same** JDBC transaction manager/`DataSource`, exceptions are not swallowed by a recoverer prior to commit, and no async handoff cuts the transaction. This dossier highlights that boundary explicitly.

## 3. Overall Topology

~~~mermaid
flowchart LR
    subgraph ING["Ingress"]
      H["HTTP / Broker adapter"]
      G["Admission gate + validation"]
    end
    subgraph SI["Spring Integration runtime"]
      Q["orders.pending<br/>QueueChannel / JDBC store"]
      P["orders.worker<br/>PollingConsumer + TX advice"]
      V["OrderProcessor<br/>idempotency + business write"]
      E["errorChannel<br/>ErrorMessage"]
    end
    subgraph DB["PostgreSQL"]
      S["INT_CHANNEL_MESSAGE<br/>durable pending state"]
      I["processed_events<br/>unique eventId"]
      O["orders + outbox_events"]
      D["quarantine / replay ledger"]
    end
    R["Outbox relay"] --> X["External broker/API"]
    H --> G --> Q
    Q <--> S
    Q --> P --> V
    V --> I
    V --> O
    O --> R
    P -. "exception / ErrorMessage" .-> E
    E -. "diagnostic / recovery" .-> D
~~~

Dashed lines represent **observability and recovery paths**, not a guarantee that every failure is automatically pushed by Spring Integration onto the same `errorChannel`.

### Component Manifest: Bean Names Are Operational Contracts

| Suggested Bean/ID | Type | Thread | State | Lifecycle Owner | On Failure |
|---|---|---|---|---|---|
| `orders.admission` | Application-defined API/gate | HTTP/broker listener | Gate OPEN/CLOSED, non-durable | Application ingress | Rejects new intake; caller retries/NACKs |
| `orders.pending` | `QueueChannel` backed by `MessageGroupQueue` | Sender enqueues; poller dequeues | `JdbcChannelMessageStore` | Application context | JDBC fails or queue waits; never assume send succeeded if TX fails |
| `orders.worker` | `PollingConsumer` | Scheduler/poller thread | Running lifecycle + in-flight | Spring context | TX rollback/recovery policy |
| `orders.processor` | Service activator/handler | Same poller thread in primary design | Business/inbox/outbox tables | Spring bean | Runtime exceptions must trigger rollback or durable recovery |
| `orders.outbox.relay` | Dedicated worker/flow | Dedicated scheduler/worker | `outbox_events` | Outbox service | Retries publishing; at-least-once |
| `errorChannel` | Error publish/subscribe | Per publisher/error thread | `ErrorMessage` non-durable by default | Application context | Logging/metrics; not an automatic DLQ |
| `orders.dynamic.<tenant>` | Optional `IntegrationFlowRegistration` | Per endpoint | Registration, generation | Tenant runtime manager | Quiesce/drain/destroy per owner |

**Crucial:** dequeuing from `orders.pending` does not mean `orders.processor` committed. Completing `orders.outbox.relay` publish also does not guarantee the remote consumer applied it; the outbox must retain metadata for retries.

## 4. Channel Selection and Thread Boundaries

| Option | When Appropriate | Limits / Transaction Consequences |
|---|---|---|
| `DirectChannel` | Fast synchronous validation, routing, and handlers | Caller shares thread; errors propagate back; can extend ingress latency |
| `QueueChannel(128)` | Unit tests or bounded buffering inside one JVM | In-memory messages vanish on crash |
| `QueueChannel` + `MessageGroupQueue(JdbcChannelMessageStore)` | Demo project illustrating durable intake in PostgreSQL | JDBC I/O, serializer/schema, contention; **DB-as-queue has performance trade-offs** |
| `ExecutorChannel` | Decouple CPU/I/O from sender with bounded workers | Async handoff breaks thread-bound transactions and risks task rejection |
| `PublishSubscribeChannel` | Broadcast notifications or secondary audits | By default may succeed even with zero subscribers; not durable fan-out |
| Kafka/JMS/AMQP inbound | High throughput, broker durability, replay support | Requires dedicated ACK/offset, retry, and container lifecycle design |

The core design deliberately keeps **poller → processor synchronous**, avoiding placing an `ExecutorChannel` **inside** the dequeue transaction. If an executor sits there and the poller treats submission as completion, the dequeue transaction can commit and delete the message from the JDBC queue before the handler finishes.

For high-volume production systems, Spring Integration docs advise considering dedicated brokers rather than database-as-queue. We use a JDBC queue here to clearly demonstrate **shared `DataSource` and transaction scope**; you can swap in Kafka/AMQP/JMS later while rewriting ACK and recovery tests.

### Timeline of a Valid Message

~~~mermaid
sequenceDiagram
    participant C as Client / Broker
    participant G as Admission
    participant Q as JDBC Queue
    participant P as Poller + TX
    participant B as Business DB
    participant R as Outbox relay
    C->>G: OrderEvent(eventId=E42)
    G->>Q: send(event) inside intake transaction
    Q-->>G: accepted into store
    Note over G,Q: Confirmed accepted only after commit succeeds
    G-->>C: 202 Accepted / ACK per contract
    P->>Q: receive inside TX
    Q-->>P: OrderEvent E42
    P->>B: INSERT dedupe + UPDATE order + INSERT outbox
    B-->>P: commit in same TX as dequeue
    R->>B: fetch unpublished outbox rows
    R->>C: publish business event
    Note over R,C: If publish succeeds before marking sent, may resend
~~~

In the diagram, the relay arrow toward the client/broker represents an **independent outbound target**, not the initial `202` HTTP intake response. The system needs separate dashboards/lookup tables for `PROCESSING`, `APPLIED`, `PUBLISHED`, and `QUARANTINED` states.

## 5. State Inventory: What Data Must Survive Restarts?

| State | Storage Location | Durable? | Who Can Mutate/Delete? |
|---|---|---|---|
| Pending event | `INT_CHANNEL_MESSAGE` via `JdbcChannelMessageStore` | Yes, **after commit** | Poller with matching region/group + transaction |
| Applied event | `processed_events(event_id PK)` | Yes | Business transaction; controlled retention |
| Order projection | `orders` | Yes | Business transaction with version/ordering policy |
| Outbound event | `outbox_events` | Yes | Business TX inserts; relay updates publish state |
| Poison event | `quarantined_events` or broker DLQ | Yes if designed and committed | Recovery service, authorized operators |
| App queue depth | JMX/Micrometer/snapshots | Does not replace database | Observability |
| Endpoint running, active executor | Process memory | No | Lifecycle processors |
| Active admission gate | Memory + coordination state | Single-node RAM insufficient multi-node | Runtime coordinator |
| Tenant generation/flow config | Persistent config table | Yes | Provisioning/reconciler |
| `correlationId`, `traceId` | Message headers/tracing backend | Depends on serializer/header mapper | Producers, middleware, tracing |
| Retry attempt | Retry context / durable retry ledger | Depends on configuration | Retry/recovery policy |

Never confuse **existing state** with **committed state**. A row inserted inside an uncommitted transaction is not yet durable or visible. Never treat `"queue depth = 0"` as proof of zero in-flight work; the poller may have dequeued and still be processing.

### Application-Owned Business DDL

These tables are managed by your application; they **do not replace** the official Spring Integration JDBC schema:

~~~sql
-- PostgreSQL, illustrative business schema.
CREATE TABLE processed_events (
    event_id        VARCHAR(120) PRIMARY KEY,
    tenant_id       VARCHAR(120) NOT NULL,
    order_id        VARCHAR(120) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    tenant_id       VARCHAR(120) NOT NULL,
    order_id        VARCHAR(120) NOT NULL,
    amount_cents    BIGINT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE outbox_events (
    outbox_id       VARCHAR(120) PRIMARY KEY,
    event_id        VARCHAR(120) NOT NULL UNIQUE,
    payload_json    JSONB NOT NULL,
    state           VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outbox_pending
  ON outbox_events (state, next_attempt_at, created_at);
~~~

**Ordering note:** this example assumes events represent order values to upsert without complex update ordering. If an order has multiple versioned changes, add `eventVersion` and conditional updates (or partition/lock per order) so stale events never overwrite newer ones. Never treat multi-producer enqueue order as a global ordering guarantee.

**Duplicate note:** deduplicating by `event_id` works when identical IDs carry identical business data. Production should add a payload fingerprint/hash to catch an ID reused with different content—a **conflicting duplicate** requiring quarantine and investigation rather than silent success.

### Message Store Schema Must Match Your Exact Version

The `spring-integration-jdbc` module ships a sample `schema-postgresql.sql` for the `INT_...` tables. Before enabling the queue in a new environment:

1. Run migrations matching your exact **Spring Integration version**—never hand-write DDL from memory.
2. Verify query provider, indexes, `tablePrefix`/`region`, and payload/header serializers.
3. Test reading persisted messages with the **new version** prior to rolling upgrades.
4. Manage backups, retention, bloat/vacuum, and connection pools just like business data.
5. Since Spring Integration 6.2, JDBC stores validate tables at startup; schema errors can stop the application context from starting—fix the schema rather than disabling validation just to deploy.

## 6. Runtime Setup and Deployment Variants

Minimum stack: Spring Integration Core, Spring JDBC, Spring Transaction, PostgreSQL driver, and a test framework. With Spring Boot, use a compatible BOM to avoid mixing Spring versions:

~~~kotlin
// Snippet inside dependencies { ... } in Gradle Kotlin DSL.
implementation("org.springframework.boot:spring-boot-starter")
implementation("org.springframework.boot:spring-boot-starter-jdbc")
implementation("org.springframework.integration:spring-integration-core")
implementation("org.springframework.integration:spring-integration-jdbc")
implementation("com.fasterxml.jackson.core:jackson-databind")
runtimeOnly("org.postgresql:postgresql")

testImplementation("org.springframework.boot:spring-boot-starter-test")
testImplementation("org.springframework.integration:spring-integration-test")
testImplementation("org.testcontainers:postgresql")
~~~

This is an **illustrative dependency list**, omitting the Spring Boot plugin/BOM and repositories of a full build file. Never pin arbitrary version numbers on individual dependencies when using a BOM.

Two profiles express **two distinct durability contracts**:

| Profile | Queue Type | Purpose |
|---|---|---|
| `workshop` | In-memory `QueueChannel(128)` | Fast unit/flow tests without pretending to survive restarts |
| `durable` | `QueueChannel(new MessageGroupQueue(store, groupId))` | JDBC transaction and restart practice |

Activate **only one** profile per context so duplicate `orders.pending` beans never collide. To return `202` under **INV-02**, only the `durable` profile qualifies once the store write commits; never advertise `workshop` as equivalent to durable API acceptance.

### Serializable Domain Event

~~~java
import java.io.Serializable;

public record OrderEvent(
        String eventId,
        String tenantId,
        String orderId,
        long amountCents) implements Serializable {

    public OrderEvent {
        if (eventId == null || eventId.isBlank()
                || tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()
                || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid OrderEvent");
        }
    }
}
~~~

The payload is a record with serializable fields. Using Java serialization in a JDBC message store demands **strict serializer versioning, allowlisting, and security rules**; never deserialize arbitrary untrusted objects. In production, consider schema-stable JSON/Avro/Protobuf serializers with explicit migrations.

## 7. Configuring In-Memory and JDBC `QueueChannel`

~~~java
@Configuration
@Profile("workshop")
class WorkshopQueueConfig {

    @Bean(name = "orders.pending")
    QueueChannel pending() {
        return new QueueChannel(128);
    }
}
~~~

JDBC version sharing the **exact same PostgreSQL `DataSource`** as business tables:

~~~java
@Configuration
@Profile("durable")
class DurableQueueConfig {

    @Bean
    JdbcChannelMessageStore ordersChannelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
            new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
            new PostgresChannelMessageStoreQueryProvider());
        store.setRegion("orders-intake-v1");
        return store;
    }

    @Bean(name = "orders.pending")
    QueueChannel pending(JdbcChannelMessageStore store) {
        MessageGroupQueue persistentQueue =
            new MessageGroupQueue(store, "orders.pending.v1");
        return new QueueChannel(persistentQueue);
    }
}
~~~

Types and packages:

| Type | Package |
|---|---|
| `QueueChannel` | `org.springframework.integration.channel` |
| `JdbcChannelMessageStore` | `org.springframework.integration.jdbc.store` |
| `PostgresChannelMessageStoreQueryProvider` | `org.springframework.integration.jdbc.store.channel` |
| `MessageGroupQueue` | `org.springframework.integration.store` |
| `DataSource` | `javax.sql` |
| `@Profile`, `@Bean`, `@Configuration` | `org.springframework.context.annotation` |

**Two keys must remain constant:** `region` and `groupId`. Changing either across restarts makes new consumers see an apparently empty queue while old messages sit in the previous region/group. Multi-node deployments sharing a queue must agree on store schema, region, group, serializer, and polling transaction coordination.

The `durable` example above sets **no** in-memory capacity cap. Design admission/rate limits, depth alerts, quotas, and retention upfront. `MessageGroupQueue` has a capacity constructor overload, yet multi-node bounding behavior must be tested directly—never assume a constructor parameter enforces a hard global cap.

**Do not confuse** `JdbcChannelMessageStore` with `JdbcMessageStore`: the former is optimized for channel queues, while the latter suits aggregators/claim-checks. JDBC queues carry database cost and contention; for high throughput, the framework recommends considering dedicated brokers.

## 8. Java DSL: A `PollingConsumer` with Explicit Transaction Boundaries

Define the runtime flow in **one place** so operators can locate exact endpoint IDs. Only the poller triggers processing; never open HTTP/broker listeners before it is ready.

~~~java
@Configuration
@EnableIntegration
public class OrderProcessingFlow {

    @Bean
    IntegrationFlow ordersWorkerFlow(
            OrderProcessor processor,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from("orders.pending")
            .handle(processor, "apply", endpoint -> endpoint
                .id("orders.worker")
                .autoStartup(false)
                .poller(Pollers.fixedDelay(250)
                    .maxMessagesPerPoll(1)
                    .receiveTimeout(0)
                    .transactional(transactionManager)))
            .get();
    }
}
~~~

Key imports:

~~~java
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

**Why does this configuration matter?**

- `IntegrationFlow.from("orders.pending")` targets the **declared channel bean**; since it is a `QueueChannel`, the consuming endpoint needs a poller.
- `id("orders.worker")` gives a stable endpoint ID for start/stop control and log/graph diagnostics.
- `autoStartup(false)` lets the runtime coordinator wait until DB, store, and recovery paths are ready before starting.
- `fixedDelay(250)` sets the pause after each poll task finishes, not a guaranteed throughput rate.
- `maxMessagesPerPoll(1)` simplifies transaction testing and per-receive failure diagnosis. Before raising it for throughput, benchmark DB contention and ordering behavior.
- `transactional(transactionManager)` wraps the **poll task, covering receive and synchronous downstream work**. Under the `durable` profile, receive rollback recovers properly only when store and business writes share the same `DataSource` and transaction manager.

**Deliberately avoid placing `ExecutorChannel` between poller and processor.** An async handoff lets the poller commit the dequeue right after task submission while worker errors occur outside the original transaction.

### State Checkpoints on Each Thread

~~~mermaid
sequenceDiagram
    participant P as Scheduler / Poller thread
    participant Q as JDBC Queue
    participant H as OrderProcessor
    participant D as PostgreSQL TX
    P->>D: begin transaction
    P->>Q: receive
    Q-->>P: OrderEvent
    P->>H: apply(event) synchronously
    H->>D: INSERT dedupe + UPSERT order + INSERT outbox
    alt completes
      H-->>P: return void
      P->>D: commit (dequeue + business)
    else throws unrecovered exception
      H--xP: exception
      P->>D: rollback
      Note over P,Q: Redelivery behavior must be tested with store and policy
    end
~~~

A `MessagePublishingErrorHandler` may emit an `ErrorMessage` at the poller boundary; that **does not prove the transaction rolled back or the message will redeliver**. Recovery advice can swallow exceptions and alter the outcome. Test exact versions, advice ordering, and how error handlers terminate.

## 9. Idempotent Business Handler and Outbox in One Transaction

This class needs only a `JdbcTemplate` and Jackson `ObjectMapper`; the transaction **is already opened by the poller**, so JDBC statements join the same transaction through Spring JDBC/the transaction manager.

~~~java
@Component
public class OrderProcessor {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public OrderProcessor(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    public void apply(OrderEvent event) {
        int inserted = jdbc.update(
            """
            INSERT INTO processed_events (event_id, tenant_id, order_id)
            VALUES (?, ?, ?)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(), event.tenantId(), event.orderId());

        if (inserted == 0) {
            // Duplicate of a logical event already committed in a prior run.
            return;
        }

        jdbc.update(
            """
            INSERT INTO orders (tenant_id, order_id, amount_cents)
            VALUES (?, ?, ?)
            ON CONFLICT (tenant_id, order_id)
            DO UPDATE SET amount_cents = EXCLUDED.amount_cents,
                          updated_at = now()
            """,
            event.tenantId(), event.orderId(), event.amountCents());

        final String json;
        try {
            json = mapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize outbox", ex);
        }

        jdbc.update(
            """
            INSERT INTO outbox_events
                (outbox_id, event_id, payload_json, state)
            VALUES (?, ?, CAST(? AS jsonb), 'PENDING')
            """,
            "order-applied:" + event.eventId(),
            event.eventId(),
            json);
    }
}
~~~

Types: `JdbcTemplate` is in `org.springframework.jdbc.core`; `ObjectMapper` and `JsonProcessingException` are from Jackson; `@Component` is Spring's stereotype annotation. If Spring Boot does not auto-configure an `ObjectMapper`, register a Jackson bean explicitly. Since Java text blocks require Java 15+, the example requires Java 17+ as stated.

**Atomicity rules to understand clearly:**

1. First run of E42: inserts into `processed_events`, upserts `orders`, and inserts into `outbox_events`. If all three succeed and the poller commits, E42 is applied.
2. If the second or third SQL statement throws, the transaction rolls back the dedupe marker, business state, and JDBC dequeue together.
3. If a broker/client resends E42 after commit, `ON CONFLICT DO NOTHING` returns 0; the handler skips re-applying side effects or outbox rows.
4. If E42 arrives with **the same ID yet a different payload**, this example does not verify a payload fingerprint yet; add a digest and a conflict/quarantine branch for production.
5. With **multiple valid events on the same order**, the SQL upsert is last-writer-wins without version ordering; add ordering/version contracts if expanding the domain.

Never replace this logic with `if (!repository.existsById(id)) insert(...)` expecting multi-node deduplication. Read-then-write is non-atomic; the database **unique constraint** arbitrates concurrency.

### Limits of `@Transactional`

You can place `@Transactional` on business methods, yet if a handler runs on a different thread (executor/async) or self-invokes without crossing the Spring proxy, transaction scope diverges from expectations. In this design, **poller transaction advice** is the main boundary wrapping receive and handler; business JDBC shares the same transaction manager. Tests must query from an independent transaction after completion to confirm actual commits.

## 10. Ingress Gate: Return Accepted Only After Durable Commit

This internal API guards cutoff using `ReentrantReadWriteLock` and uses `TransactionTemplate` so responses return **only after the enqueue transaction finishes**. This is a **single-JVM** gate, not distributed admission control.

~~~java
@Component
public class OrderIngress {
    private final MessageChannel pending;
    private final TransactionTemplate transactions;
    private final ReadWriteLock lock = new ReentrantReadWriteLock(true);
    private boolean accepting = false;

    public OrderIngress(
            @Qualifier("orders.pending") MessageChannel pending,
            PlatformTransactionManager txManager) {
        this.pending = pending;
        this.transactions = new TransactionTemplate(txManager);
        // Intake commit must be independent of any outer transaction.
        this.transactions.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public boolean accept(OrderEvent event) {
        lock.readLock().lock();
        try {
            if (!accepting) {
                return false; // Not accepting; caller must retry per policy.
            }

            Boolean committed = transactions.execute(status -> {
                Message<OrderEvent> message = MessageBuilder
                    .withPayload(event)
                    .setHeader("businessEventId", event.eventId())
                    .setHeader("correlationId",
                        event.tenantId() + ":" + event.orderId())
                    .setHeader("tenantId", event.tenantId())
                    .build();
                if (!pending.send(message, 300)) {
                    throw new IllegalStateException("Intake queue unavailable");
                }
                return Boolean.TRUE;
            });
            return Boolean.TRUE.equals(committed);
        } finally {
            lock.readLock().unlock();
        }
    }

    public void open() {
        lock.writeLock().lock();
        try {
            accepting = true;
        } finally {
            lock.writeLock().unlock();
        }
    }

    public void close() {
        lock.writeLock().lock();
        try {
            accepting = false;
        } finally {
            lock.writeLock().unlock();
        }
    }
}
~~~

Types: `org.springframework.messaging.MessageChannel`, `org.springframework.integration.support.MessageBuilder`, `org.springframework.transaction.support.TransactionTemplate`, `org.springframework.transaction.TransactionDefinition`, `java.util.concurrent.locks.ReadWriteLock`/`ReentrantReadWriteLock`.

**Evidence for INV-02:** Under the `durable` profile, `pending.send(...)` writes to the JDBC store inside this transaction. `PROPAGATION_REQUIRES_NEW` starts an independent physical transaction even if an outer adapter transaction exists; `TransactionTemplate.execute(...)` returns normally only after the intake transaction commits. Hence `accept(...) == true` can map to HTTP 202 **provided** the store and manager share the same `DataSource` and nothing else acked prematurely. If commit fails, propagate failure to the caller. `REQUIRES_NEW` uses an extra JDBC connection when an outer transaction is open; size pools carefully to prevent starvation.

Under the **in-memory `workshop` profile**, the same method proves only RAM enqueuing—**not** durability. Real APIs must disable durability SLO claims or allow production intake strictly under the `durable` profile.

An optional HTTP gateway (add `spring-boot-starter-web` if needed) can map this as:

~~~java
@RestController
@Profile("durable")
@RequestMapping("/api/orders")
public class OrderIngressController {
    private final OrderIngress ingress;

    public OrderIngressController(OrderIngress ingress) {
        this.ingress = ingress;
    }

    @PostMapping("/events")
    public ResponseEntity<Void> accept(@RequestBody OrderEvent event) {
        if (!ingress.accept(event)) {
            return ResponseEntity.status(503)
                .header("Retry-After", "2")
                .build();
        }
        return ResponseEntity.accepted().build();
    }
}
~~~

In production, translate exceptions at the HTTP boundary into 400 (validation), 409 (conflicting event ID), and 503 (infrastructure intake failure)—never returning 202 when commit fails. If a client times out **after** commit before receiving the response, the client may resend E42; event-ID deduplication is mandatory.

### Race Between `accept()` and `close()`

`accept()` holds the read lock across the entire transaction commit. `close()` acquires the write lock only after active accepted calls return; calls arriving after `close()` finishes are rejected. Never hand a direct reference to `orders.pending` to another sender expecting this gate to guard it.

Holding locks across JDBC calls can delay shutdown if the DB hangs; configure bounded timeouts on `DataSource`/JDBC, transactions, and APIs. Multi-node deployments also need shared admission state, broker pauses, or owner fencing.

## 11. Lifecycle Dossier: `READY`, `QUIESCE`, `DRAIN`, `STOP`

A runtime needs an **explicit operational state machine**. <code>SmartLifecycle.isRunning()</code> reports only the lifecycle state of the queried bean—not whether all database transactions or outbox rows settled.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> STARTING: schema, dependencies, and flow ready
    STARTING --> READY: start worker and pass readiness
    READY --> QUIESCING: stop admitting new messages
    QUIESCING --> DRAINING: close gate + pause external sources
    DRAINING --> STOPPING: pending settled or durable replay intact
    STOPPING --> STOPPED: stop endpoints per ownership
    STOPPED --> CLEANING: destroy owned resources
    CLEANING --> TERMINATED: verify leaks and checkpoints
    STARTING --> FAILED: bean/store start error
    DRAINING --> FAILED: drain timeout
    STOPPING --> FAILED: lifecycle stop error
    FAILED --> QUIESCING: safe investigation/recovery
~~~

This is an **application-defined model**, not a Spring Integration enum. Persist durable state separately if a restarted instance must resume an unfinished cleanup operation.

### Start Sequence — Consumer First, Ingress Last

~~~text
1. PostgreSQL and schema migrations ready
2. JdbcChannelMessageStore starts / verifies tables, query provider, serializer
3. Idempotency / outbox / error-recovery sinks ready
4. Spring context registers orders.pending and orders.worker
5. Start orders.worker while still quiesced
6. Verify isRunning, store access, and dependency health
7. Open gate; advertise READY; start/resume broker listeners if any
~~~

With Spring Boot readiness probes, an open HTTP server port **does not automatically mean** <code>orders.worker</code> is running. Section 10's gate must reject intake until the coordinator finishes starting. Broker listeners are started/paused/acked via adapter APIs, never inferred from HTTP readiness.

### Stop Sequence — Block Intake Before Stopping Worker

~~~text
1. Close gate and pause inbound adapters
2. Wait for active ingress sends/transactions to commit or roll back
3. Keep poller running to drain backlog if draining is desired
4. Confirm pending + in-flight/retries settled into terminal states
5. Stop orders.worker, then stop outbox relay as appropriate
6. Shut down flow-owned executors/schedulers; keep shared resources intact
7. Confirm persistent state has a recovery owner
8. Record checkpoint and allow ApplicationContext shutdown
~~~

**Never stop the poller before step 3** if it is the sole consumer draining the queue. If the grace period expires with a durable queue and safe replay intact, you can stop after handing pending items to new instances; log explicitly what remains unfinished.

### `WorkDrainProbe` Contract

~~~java
public interface WorkDrainProbe {
    /**
     * True only when all accepted work for the current worker
     * has committed, is durably quarantined, or has durable replay.
     */
    boolean safeToStop();
    long pendingQueue();
    long inFlight();
}
~~~

This is an **application interface**, not built into Spring Integration. An implementation cannot just return <code>queue.getQueueSize() == 0</code>: the poller may have dequeued a message whose transaction has not committed, or an executor task may still be running. With a JDBC store, inspect active transactions, work-state ledgers, and replay readiness. With a broker, include offset/ACK state. Register outstanding counters **before** async work can finish, or track state in a ledger keyed by durable business event IDs.

### Minimal Coordinator Example

~~~java
public final class OrderRuntimeCoordinator {
    private final OrderIngress ingress;
    private final SmartLifecycle worker;
    private final WorkDrainProbe probe;

    public OrderRuntimeCoordinator(
            OrderIngress ingress,
            SmartLifecycle worker,
            WorkDrainProbe probe) {
        this.ingress = ingress;
        this.worker = worker;
        this.probe = probe;
    }

    public synchronized void startWhenReady() {
        // Caller must verify DB/store/recovery health before invoking.
        if (!worker.isRunning()) {
            worker.start();
        }
        if (!worker.isRunning()) {
            throw new IllegalStateException("Worker is not ready");
        }
        ingress.open();
    }

    public synchronized boolean quiesceDrainStop(Duration budget)
            throws InterruptedException {
        ingress.close();
        long deadline = System.nanoTime() + budget.toNanos();
        while (!probe.safeToStop()) {
            if (System.nanoTime() >= deadline) {
                return false; // Keep gate closed; never destroy before safe.
            }
            Thread.sleep(25); // Management thread only.
        }
        worker.stop();
        return !worker.isRunning();
    }
}
~~~

To wire the coordinator, look up the endpoint by its declared ID:

~~~java
@Bean
OrderRuntimeCoordinator orderRuntimeCoordinator(
        OrderIngress ingress,
        @Qualifier("orders.worker") SmartLifecycle worker,
        WorkDrainProbe probe) {
    return new OrderRuntimeCoordinator(ingress, worker, probe);
}
~~~

<code>SmartLifecycle</code> lives in <code>org.springframework.context</code>; <code>Duration</code> lives in <code>java.time</code>. In real applications, register a genuine <code>WorkDrainProbe</code> bean; the snippet above does not supply a durable counter automatically. Event/condition signals outperform polling with <code>Thread.sleep(25)</code> at scale; finite deadlines avoid infinite hangs.

**On timeout:** returning <code>false</code> **does not** mean messages were lost. The gate remains closed, the worker remains running, and operators must inspect queues, transactions, and recovery. If the platform kills the process after its grace period, PostgreSQL queue durability and idempotency provide recovery.

## 12. Threading, Phases, and Shutdown: Never Close Resources Out of Order

With <code>SmartLifecycle</code>, lower phases start earlier and stop later, while higher phases start later and stop earlier **within the same lifecycle processor**. That orders dependencies, consumers, and producers relatively, yet **never replaces** readiness gates, transaction settlement, or adapter-specific ACKs.

| Component | On Start | On Stop | Must Never Do |
|---|---|---|---|
| Database and message store | Before pollers and ingress | After zero DB work remains | Close `DataSource` while TXs are committing |
| Worker poller | Once schema/handler are ready | After drain or once durable recovery is verified | Stop the sole consumer before draining backlog |
| HTTP/broker ingress | After readiness | Before worker | Keep ACKing without durable acceptance |
| Flow-owned executor | After dependencies, before consumers needing it | After zero submissions/in-flight remain | Shut down before accepted tasks finish |
| Shared scheduler/connections | Managed by application owner | With the whole application | Destroy when removing one tenant |
| Error/recovery sink | Ready before processing starts | After publishers/workers have stopped | Close before the last `ErrorMessage` is handled |

If another outbound branch needs `ExecutorChannel`, place it **after the transaction/outbox boundary** on its own workers; never move business JDBC writes into an executor expecting the poller transaction to wrap them. Under saturation, `CallerRunsPolicy` can also shift thread, latency, and transaction behavior unpredictably.

### Readiness and Shutdown in Kubernetes

The application can coordinate these steps:

1. On `SIGTERM` or `preStop`: flip readiness so new traffic stops routing here.
2. Close the local gate and pause matching broker listeners.
3. Wait for active ingress transactions to finish; let the poller drain backlog within the grace period.
4. Once drained or durable replay is confirmed, stop the poller and close owned resources.
5. Exit the process and let surviving instances run reconciliation.

A `@PreDestroy` hook can perform brief cleanup, yet **is never guaranteed on `kill -9` or OOM**. Once the Spring context begins destroying dependencies, trying to drain inside `@PreDestroy` is also too late. Have an orchestrator quiesce **before context close** for clean behavior.

## 13. Recovery Dossier: Where Did It Crash, and How Do We Recover?

| Crash / Failure Point | Remaining State | On Restart / Caller Retry | What to Verify |
|---|---|---|---|
| Before enqueue TX commits | Nothing durably accepted | Caller retries; never returned 202 | Zero orphan business state |
| After enqueue commits, before HTTP response | Queue holds E42; client unsure | Client resends E42; processor is idempotent | Zero duplicate business/outbox rows |
| Poller received, processor uncommitted | JDBC dequeue and business TX non-terminal | Rolls back; event eligible again per store rules | Test with real DB and manager |
| After business TX commits, before outbox relay | Processed marker, order, pending outbox | E42 not re-applied; relay picks up outbox | Check row states after restart |
| Outbox publish succeeds, before mark `PUBLISHED` | Remote has event; outbox still pending/in-flight | Relay may resend | Remote deduplicates by stable outbox ID |
| HTTP/DB dependency timeout | Event queued or handled per recovery policy | Bounded retry/backoff; no storms | Attempt counts + circuit breakers |
| Permanently invalid payload/schema | Would retry forever without classification | Quarantine with reason, owner, replay policy | Never stalls the whole queue |
| Shutdown mid-flight | Task running or TX open | DB rollback/replay or commit reconciliation | Zero duplicate side effects |
| Dynamic tenant flow removed | Flow beans gone; DB store may remain | Reconciler rebuilds/replays/quarantines | Never resurrects `DELETED` tenants |

**Special note:** For a JDBC queue, "messages return after rollback" depends on proper transaction scoping, serializer/query providers, and not swallowing exceptions. Never promise that for in-memory `QueueChannel(128)`, `ExecutorChannel`, or broker sources that ACK before tasks complete.

### Retry Policy by Failure Category

| Failure Category | Retry? | Recovery |
|---|---|---|
| Timeout or transient downstream 503 | Yes, bounded + exponential backoff/jitter | Keep event durable; pause poller or use bounded delayed retry scheduler |
| Transient JDBC connection loss | Yes, avoiding tight spin loops | Wait for dependency health; reduce concurrency |
| Validation/unsupported schema | No, or strictly bounded | Quarantine/DLQ with safe metadata |
| Ordering/version violation | Per domain contract | Reorder buffer or reject stale events |
| No-subscriber during flow stop | Retry at producer/adapter once flow is ready | Block intake during stop; never add dummy handlers |
| Executor task rejected | Retry at submit boundary if unaccepted | Bounded backlog/broker; avoid `DiscardPolicy` |
| Unknown commit outcome | Never assume it failed | Reconcile event ID and outbox before replaying |

`RequestHandlerRetryAdvice` wraps only **handler invocations that actually started**. It does not retry failures before the handler (such as executor rejections or queue send failures). If retry advice exhausts N attempts and still throws, the JDBC poller can roll back and repoll on the next cycle—creating an **unbounded retry storm across poll cycles**. To enforce a system-wide retry budget, add a durable attempt ledger, delayed retry/retry topics, or poll filters.

### Safe Quarantine Does Not Mean Swallowing Exceptions

A sound recovery path runs inside a clear transaction/workflow:

~~~text
BEGIN TX
  receive E42 from persistent queue
  classify failure as terminal per attempt budget/exception class
  INSERT quarantined_events(eventId, reason, payloadRef, owner)
  record terminal marker or replay checkpoint
  commit dequeue and quarantine together if design allows
COMMIT
~~~

If persisting the quarantine record fails, never silently return "handled" and let the poller commit the dequeue. When messages and side effects span systems without a shared transaction, use outbox/saga patterns with reconciliation. Never log raw PII or store plaintext secrets in quarantine.

An optional quarantine table:

~~~sql
CREATE TABLE quarantined_events (
    event_id      VARCHAR(120) PRIMARY KEY,
    tenant_id     VARCHAR(120) NOT NULL,
    reason_code   VARCHAR(64) NOT NULL,
    payload_json  JSONB NOT NULL,
    attempts      INTEGER NOT NULL,
    state         VARCHAR(24) NOT NULL DEFAULT 'OPEN',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

This SQL is **application schema**. Attach low-cardinality error codes, owners, retention deadlines, and replay policies; never delete rows directly from `INT_CHANNEL_MESSAGE` just to clear red dashboards without confirmed quarantine commits.

## 14. Outbox Relay: Logically Once, Accepting Redeliveries

In this design, the business transaction **never** calls a remote HTTP endpoint or broker producer assuming both commit atomically. Instead:

1. Business write and outbox insert commit together in PostgreSQL.
2. An independent relay fetches due outbox records.
3. The relay publishes using a **stable idempotency key**, such as `outbox_id`.
4. Mark `PUBLISHED` only on reliable adapter confirmation; on uncertain outcomes, retry per deadline/lease.
5. Remote consumers deduplicate by event/outbox ID.

### Claiming a Batch by Lease Without Holding TX Across Network Calls

Extend the outbox table from Section 5:

~~~sql
ALTER TABLE outbox_events
  ADD COLUMN lease_owner VARCHAR(120),
  ADD COLUMN lease_until TIMESTAMPTZ;
~~~

A short **claim** transaction using PostgreSQL:

~~~sql
WITH picked AS (
    SELECT outbox_id
    FROM outbox_events
    WHERE
        (state IN ('PENDING', 'RETRY') AND next_attempt_at <= now())
        OR (state = 'IN_PROGRESS' AND lease_until < now())
    ORDER BY created_at, outbox_id
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE outbox_events AS o
SET state = 'IN_PROGRESS',
    lease_owner = :worker_id,
    lease_until = now() + interval '30 seconds',
    attempts = attempts + 1
FROM picked
WHERE o.outbox_id = picked.outbox_id
RETURNING o.outbox_id, o.event_id, o.payload_json, o.attempts;
~~~

This is **algorithm-illustrative SQL**; bind `:worker_id` (e.g., via `NamedParameterJdbcTemplate`) and verify indexes and transaction isolation. The claim transaction must **commit before** calling the broker; after publishing, open a fresh transaction verifying owner/lease before marking `PUBLISHED` or scheduling retries.

~~~mermaid
flowchart TD
    A["PENDING / RETRY"] --> B["Claim with SKIP LOCKED + lease"]
    B --> C["Publish externally with outbox_id"]
    C -->|Confirmed ACK| D["Mark PUBLISHED using owner token"]
    C -->|Timeout / unknown outcome| E["Lease expires → retry"]
    E --> B
    C -->|Permanent failure| F["QUARANTINED / human review"]
~~~

**Critical trade-off:** If publishing succeeds yet the process dies **before** marking `PUBLISHED`, the new relay resends. That is why an outbox architecture **does not** yield automatic exactly-once on remote receivers. Receivers must be idempotent, or else you need transaction/business-ID reconciliation.

Never mark a record `PUBLISHED` before receiving protocol-valid publish confirmation. Never set infinite leases: if a worker dies, records stay stuck. Conversely, overly short leases allow two relays to publish simultaneously; enforce fencing tokens, deadlines, and idempotency. Over HTTP without deterministic ACKs, timeouts cannot distinguish unreceived requests from completed ones.

### Must the Outbox Relay Be an `IntegrationFlow`?

You can implement the relay with a Spring Integration JDBC inbound adapter/poller plus outbound adapter, or a scheduled service. **Either approach must uphold the exact same contract**: claim, lease, publish, ACK, retry, and mark. A `SourcePollingChannelAdapter` firing periodically does not create distributed transactions across brokers and PostgreSQL. Never equate a 500 ms trigger with 2 events/second throughput; capacity depends on batch sizes and downstream latency.

## 15. Correlation and Message Groups: Conditional Extension

The core dossier handles events independently by `eventId`. If the product requires **aggregating multiple line items into one order**, add a splitter/aggregator with explicit group-state design:

~~~mermaid
flowchart LR
    A["Order batch"] --> S["Splitter"]
    S --> C["Correlation: tenantId + batchId"]
    C --> G["Aggregator / MessageGroupStore"]
    G --> R["ReleaseStrategy enough fragments"]
    R --> O["Persist business outcome"]
    G -. "timeout" .-> E["Expire / discard / quarantine"]
~~~

| Group Design Question | Decision to Document |
|---|---|
| Group key | `tenantId + ":" + batchId`, never `batchId` alone across multiple tenants |
| Release condition | Reached `sequenceSize`, terminal marker, or domain rule |
| Duplicate/out-of-order fragments | Deduplicate fragment IDs and define late-arrival rules |
| Store | `JdbcMessageStore` for message groups, **distinct from** channel `JdbcChannelMessageStore` |
| Concurrency | `LockRegistry` scoped appropriately; multi-node requires supported distributed locks and shared stores |
| Timeout | Where do expired groups go? Delete or preserve partial state? |
| Restart | Rehydrate pending groups matching `region` and serializer |
| Cleanup | Purge only terminal groups per retention; never delete on endpoint stop |

In Spring Integration, `correlationId` is a header for grouping/business context—**not a trace ID, message ID, or idempotency key**. In multi-tenant systems, combine tenant + order logically if order IDs can collide across tenants, without altering `eventId` deduplication.

**Warning:** A single-JVM `DefaultLockRegistry` provides no distributed locking. Multi-node aggregators typically require `JdbcLockRegistry`/Redis/ZooKeeper `LockRegistry` with shared stores, lease TTLs, `unlock` in `finally`, and lost-lock handling. Releasing a group in a transaction still does not prove outbound ACKs completed.

## 16. Dynamic Runtime: Multi-Tenancy and Resource Ownership

A common synthesis requirement is adding/removing per-tenant flows at runtime. `IntegrationFlowContext` lets you register flows by ID, start/stop/destroy them, and inspect registrations; this is **lifecycle topology**, not a durable configuration database.

~~~java
@Component
public class TenantDynamicFlowManager {
    private final IntegrationFlowContext flowContext;

    public TenantDynamicFlowManager(IntegrationFlowContext flowContext) {
        this.flowContext = flowContext;
    }

    public String install(String tenantId, long generation,
                          MessageHandler handler) {
        String flowId = "tenant.audit." + tenantId + "." + generation;
        if (flowContext.getRegistrationById(flowId) != null) {
            throw new IllegalStateException("Already registered: " + flowId);
        }

        IntegrationFlow flow = IntegrationFlow
            .from(new DirectChannel())
            .handle(handler)
            .get();

        flowContext.registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();
        return flowId;
    }

    public void stopAndRemoveAfterDrain(String flowId) {
        var registration = flowContext.getRegistrationById(flowId);
        if (registration != null) {
            registration.stop();
            registration.destroy();
        }
    }
}
~~~

Types: `IntegrationFlowContext` is in `org.springframework.integration.dsl.context`; `MessageHandler` in `org.springframework.messaging`; `DirectChannel` in `org.springframework.integration.channel`.

This example is a **secondary audit branch**—never bypass the main project's durable intake by sending HTTP requests straight into a newly created `DirectChannel`. It also lacks admission gates, durable checkpoints, and distributed ownership: in production, call `stopAndRemoveAfterDrain()` only after the coordinator blocks new intake and confirms pending items are settled or quarantined.

### Resource Ownership Matrix

| Resource | Flow/Tenant-Owned? | When Removing Tenant |
|---|---|---|
| Dynamic `IntegrationFlowRegistration` | Yes | Stop/destroy exact ID and generation |
| Per-tenant subscriptions, timers, scheduled tasks | Yes if created per tenant | Cancel by handle; verify no callbacks still run |
| Shared `TaskExecutor`/`TaskScheduler` | No | **Never shut down** for one tenant |
| Shared JDBC `DataSource`, broker connection factory | No | **Never close** while other tenants use it |
| Tenant credentials/caches | Possibly | Revoke after relevant in-flight/recovery work finishes |
| JDBC queue/aggregator state | Partitionable by tenant/group | Retain for replay or purge under audited policy |
| DLQ/outbox/audit records | Tenant data in shared storage | Retain per compliance; never auto-delete on flow destroy |

Dangerous race:

~~~text
T0: tenant A holds generation=7, flow ACTIVE
T1: cleanup for generation=7 starts
T2: tenant A recreates generation=8
T3: old cleanup deletes resources keyed only by tenantId
→ Accidentally destroys resources belonging to generation=8
~~~

Solve this with **generation fencing**, owner tokens, and version checks in DB/locks before every cleanup action. Checking `getRegistrationById(...) == null` then registering is non-atomic across threads/nodes; use a coordinator/CAS for provisioning authority. After crashes, runtime registries are empty and must rebuild from durable config state—never treat `IntegrationFlowContext` as a database.

## 17. Observability: Mapping Topology to Operational Evidence

You cannot debug incidents saying "Spring Integration isn't processing messages" without metrics at each boundary. Assign stable bean/endpoint IDs as in Section 3 and instrument **selectively**.

~~~java
@Configuration
@EnableIntegrationManagement(
    defaultLoggingEnabled = "false",
    observationPatterns = {
        "orders.pending",
        "orders.worker",
        "orders.*"
    })
public class OrderObservabilityConfig {
}
~~~

`@EnableIntegrationManagement` lives in `org.springframework.integration.config`. An `ObservationRegistry` and configured Micrometer/Tracing handlers/exporters are needed for observations to reach backends as metrics/spans. With Spring Boot Actuator, inspect auto-configuration before manually registering duplicate registries or handlers. Patterns must match **runtime component names**, not guessed labels.

If enabling history during investigations, scope it narrowly:

~~~java
@EnableMessageHistory({"orders.pending", "orders.worker"})
~~~

Place this annotation intentionally on a single managed configuration. `MessageHistory` is a header listing tracked hops; it is **not** a durable audit log or proof of transaction commit. History increases payload header size and serialization cost inside JDBC queues.

### Telemetry Contract

| Signal | Source | Question Answered |
|---|---|---|
| Accepted events/s and rejected-before-acceptance/s | Ingress gate | Can we accept new work? Did we return false 202s? |
| JDBC queue pending count + oldest age | JDBC store or measurable query/adapter | Is backlog building, and how old is the oldest item? |
| Poller running / poll count / errors | Endpoint + poller instrumentation | Did the worker start, and is it receiving? |
| Business apply successes/s | Transactionally applied events | True business throughput, not just dequeues |
| Duplicate events skipped/s | Unique constraint branch | Are redeliveries/timeouts spiking? |
| Outbox pending, in-progress, retrying, oldest age | `outbox_events` table | How many applied events await publishing? |
| Error rate by category | Error handlers / recovery ledger | Transient, poison, or downstream outage? |
| Executor active/queued/rejected | Executor binder or custom metrics | Is a relay or dynamic branch saturated? |
| Drain pending/in-flight/remaining | `WorkDrainProbe` | Is it safe to stop yet? |
| Transaction / DB pool latency | `DataSource`/DB metrics | Is the bottleneck SQL, locks, pool, or framework? |

Names like `accepted_events_total` and `outbox_oldest_age_seconds` are **application-suggested metrics**. Spring Integration emits its own meters/observations when configured, yet **does not** automatically track transactionally settled logical events for this domain model. Classic Micrometer and Observation APIs also emit different meter names; inspect live meters before authoring dashboard queries.

### Headers and Identifiers

| Identifier | Example | Purpose |
|---|---|---|
| Message ID | Framework-generated UUID | Identifies one message instance |
| Business event ID | `E42` | Deduplication/idempotency across redeliveries |
| Correlation ID | `tenantA:order123` | Links operations for the same order/batch |
| Trace/span ID | Tracing-system generated | Diagnoses latency across threads/processes |
| Outbox ID | `order-applied:E42` | Deduplicates outbound side effects |
| Flow generation | `tenantA:v8` | Fences stale lifecycle/cleanup actions |

Never use high-cardinality raw `eventId`, `orderId`, or tenant UUIDs as per-message **metric tags**. Keep them in masked, retention-governed, access-controlled traces and logs. Separating **business identity** from **telemetry identity** keeps collector costs bounded and search fast.

### Runtime Topology Graph

~~~java
IntegrationGraphServer graphServer =
    applicationContext.getBean(IntegrationGraphServer.class);

var snapshot = graphServer.rebuild();
log.info("Integration graph snapshot: {}", snapshot);
~~~

`IntegrationGraphServer` lives in `org.springframework.integration.graph`. This snippet assumes the server bean exists in the context. After dynamic register/remove calls, `rebuild()` refreshes the graph cache. The graph is **not a distributed trace** and does not prove a specific message crossed an edge right now.

## 18. Performance Budgets and Capacity Planning

The dossier must specify budgets for latency, throughput, queue age, database load, and recovery limits; the numbers below are **hypothetical exercise thresholds**, not default Spring SLAs.

| Example SLI/SLO | Hypothetical Target | When Breached |
|---|---|---|
| Intake durable commit p99 | < 300 ms | Inspect DB connection pool, disk, locks, serialization |
| Business apply completion p99 | < 2 seconds | Inspect poll lag, TX duration, queries |
| Oldest pending age | < 60 seconds steady-state | Throttle ingress or scale capacity after finding bottleneck |
| Outbox publish lag p99 | < 30 seconds | Inspect relay leases, remote ACKs, retries |
| Duplicate side effect count | 0 | Halt unsafe replays; investigate idempotency |
| Unowned quarantine records | 0 | Assign owner/replay deadline before closing incident |

Measure at **business boundaries**: a successful `QueueChannel.send()` is not completion, and a handler timer finishing may exclude DB commit or outbound ACK.

### Backlog Estimation Formula

Let `λ` be incoming events/second, `μ` be **terminal completions**/second, and `B` be backlog. Under steady rates:

\[
\Delta B/\Delta t \approx \lambda - \mu.
\]

When `μ > λ` without unusual bursts or retries:

\[
t_{\text{drain}} \approx \frac{B}{\mu-\lambda}.
\]

Hypothetical example: backlog of 4,000 events, ingress throttled to 250 events/s, completion rate 450 events/s; drain time is roughly 20 seconds. If downstream slows to 200 events/s, backlog **never drains** and keeps growing. This formula is a **capacity estimate**, not a recovery SLA; monitor p95/p99, oldest age, retry amplification, and transaction contention.

### Limits to Measure Before Scaling

1. Raising `maxMessagesPerPoll` lengthens poll cycles; if one transaction spans the batch, lock durations grow.
2. Increasing polling threads/concurrency can exhaust DB pools or increase JDBC message-store contention.
3. Inserting `ExecutorChannel` before business commit changes durability contracts, not just performance.
4. Enabling `MessageHistory`, `WireTap`, full payload logging, and per-hop tracing carries CPU, heap, and network costs.
5. With brokers, partitioning and consumer groups govern scalability; adding JVM workers does not speed up a single ordered partition.
6. Retry storms can multiply real work severalfold over logical ingress; measure **attempts/s** separately.

Simply enlarging queue sizes for slow consumers only delays OOM or bloats the JDBC store. Scale the measured bottleneck: DB, remote dependency, CPU, hot-key locks, pollers, or network.

## 19. Verification Dossier: Mandatory Tests Before Sign-Off

Calling `OrderProcessor.apply()` directly in a test verifies only JDBC logic inside the test transaction. It **does not prove** adapters/gateways, queue sends, polling receives, worker threads, or ACKs. Split tests into clear layers:

| Layer | Mechanism / Data | What It Proves |
|---|---|---|
| Unit | `QueueChannel(1)`, fake handler, latches | Channel capacity, send/receive, sync exceptions, races |
| Spring flow | `@SpringIntegrationTest`, endpoint IDs, mocks | Wiring, poller auto-start, header propagation, message handlers |
| PostgreSQL integration | Real JDBC store + business schema via Testcontainers | Dequeue commit/rollback, idempotency, outbox, restarts |
| Adapter contract | Real HTTP or broker container | 202/ACK/NACK/redelivery and timeouts |
| Failure injection | DB outage, worker kill, poison events, outbox crash | Recovery without lost or duplicated side effects |
| Game day | Load, rolling deploys, stop/drain, deadlocks | Runbooks and SLOs hold under realistic stress |

### 19.1. Unit Test: Bounded `QueueChannel` and Completion Boundary

~~~java
@Test
void queueAcceptsOneMessageAndRejectsWhenFull() {
    QueueChannel queue = new QueueChannel(1);
    Message<String> first = MessageBuilder.withPayload("one").build();
    Message<String> second = MessageBuilder.withPayload("two").build();

    assertTrue(queue.send(first, 0));
    assertEquals(1, queue.getQueueSize());
    assertFalse(queue.send(second, 0));

    assertEquals("one", queue.receive(0).getPayload());
    assertNull(queue.receive(0));
}
~~~

This verifies only **in-memory `QueueChannel`** behavior, not durability. `send(message, 0)` does not wait when full. Production must define how `false` is handled rather than ignoring it and returning 202.

### 19.2. End-to-End PostgreSQL Test Skeleton

Assemble the components above into a Spring Boot application:

~~~java
@SpringBootApplication
public class OrderRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderRuntimeApplication.class, args);
    }
}
~~~

Ensure all classes and configurations sit within the application's **component-scan scope**, enabling the `durable` profile for JDBC tests. For Testcontainers JUnit Jupiter and async assertions, add BOM-compatible test dependencies:

~~~kotlin
testImplementation("org.testcontainers:junit-jupiter")
testImplementation("org.awaitility:awaitility")
~~~

Illustrative skeleton:

~~~java
@SpringBootTest(classes = OrderRuntimeApplication.class)
@ActiveProfiles("durable")
@Testcontainers
class DurableOrderFlowIT {

    @Container
    static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void jdbcProperties(DynamicPropertyRegistry properties) {
        properties.add("spring.datasource.url", db::getJdbcUrl);
        properties.add("spring.datasource.username", db::getUsername);
        properties.add("spring.datasource.password", db::getPassword);
    }

    @Autowired OrderIngress ingress;
    @Autowired JdbcTemplate jdbc;

    @Autowired
    @Qualifier("orders.worker")
    SmartLifecycle worker;

    @BeforeEach
    void start() {
        worker.start();
        ingress.open();
    }

    @AfterEach
    void stop() {
        ingress.close();
        worker.stop();
    }

    @Test
    void duplicateIntakeAppliesOnlyOneBusinessEvent() {
        OrderEvent e = new OrderEvent(
            "E-IT-001", "tenant-A", "order-42", 12500);

        assertTrue(ingress.accept(e));
        assertTrue(ingress.accept(e)); // Two messages enqueued.

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
            Integer processed = jdbc.queryForObject(
                "SELECT count(*) FROM processed_events WHERE event_id=?",
                Integer.class, e.eventId());
            Integer outbox = jdbc.queryForObject(
                "SELECT count(*) FROM outbox_events WHERE event_id=?",
                Integer.class, e.eventId());
            assertEquals(1, processed);
            assertEquals(1, outbox);
        });
    }
}
~~~

Key annotations: `@SpringBootTest` from Spring Boot Test, `@Testcontainers`/`@Container` from Testcontainers Jupiter, `@DynamicPropertySource` from Spring Test, `@ActiveProfiles`, `@BeforeEach`/`@AfterEach` from JUnit 5. `await()` is statically imported from Awaitility.

**Absolute prerequisite:** the PostgreSQL test container must have **Spring Integration JDBC tables and business tables migrated** before `JdbcChannelMessageStore` starts. Configure Flyway/Liquibase or a version-matched SQL initializer; this snippet is a **test skeleton**, not a self-migrating suite. An unmigrated app fails at context startup—correctly signaling a fixture gap.

Never put `@Transactional` on the test method itself when verifying independent poller commits: an outer test transaction can mask results or roll back fixtures differently from production.

### 19.3. Two Sequential Application Contexts — Real Restart Test

A durable restart test must reuse **the exact existing database after the first context closes**, without recreating schemas or clearing queues in between:

~~~text
Context A:
  1. Boot under durable profile with orders.worker STOPPED.
  2. Open admission and accept E-RESTART-1.
  3. Confirm enqueue TX committed while business state is not yet applied.
  4. Close Context A WITHOUT wiping the database.

Context B:
  5. Boot with the same DataSource, schema, region, groupId, and serializer.
  6. Start worker; await E-RESTART-1 appearing in processed_events + outbox_events.
  7. Resend the same E-RESTART-1 simulating a client that missed 202.
  8. Assert exactly one processed row and one outbox event.
~~~

If a restart alters `region`, `groupId`, or serialized class compatibility without migration, tests may see zero pending messages even while rows sit in the DB. Document the persistence contract in both architecture and release checklists.

### 19.4. Failure-Injection Matrix

| Test Code | Fault Setup | Minimum Assertion |
|---|---|---|
| FT-01 | Break DB before enqueue commits | Never returns accepted; client can retry; zero half-committed events |
| FT-02 | Client times out after durable intake commit | Retrying same event ID creates zero duplicate business/outbox rows |
| FT-03 | Handler throws after dedupe insert before outbox | Transaction rolls back; message stays recoverable per JDBC policy |
| FT-04 | Stop context after receive before commit | Fresh context reprocesses without double side effects |
| FT-05 | Outbox publish ACKs, then kill before DB mark | Relay resends with same outbox ID; consumer is idempotent |
| FT-06 | Poison event always fails | No infinite retries; durable quarantine with owner |
| FT-07 | Poller `autoStartup=false` | Queue holds pending items while business does not run; readiness stays closed |
| FT-08 | Close gate while HTTP threads submit | Zero accepted items past cutoff; earlier requests commit or roll back cleanly |
| FT-09 | Multiple contexts polling same region/group | Never two business commits for one event; verify locks/concurrency |
| FT-10 | Executor rejects on outbox/dynamic branch | Never treat rejected task as published; retry/backlog preserved |
| FT-11 | Tenant generation 7 cleanup while generation 8 spawns | Generation 8 resources remain intact |
| FT-12 | Schema upgrade alters serializer | Older pending messages decode/recover or fail migration cleanly |

**Async testing rule:** Use `CountDownLatch`, completion futures, or Awaitility with **explicit deadlines**—never `Thread.sleep(5000)` assuming completion. Assert business transactions from an **independent connection/transaction** after completion; for brokers, verify real ACKs/offsets rather than handler logs alone.

### 19.5. Testing No-Subscriber Errors and `errorChannel`

If another branch replaces `orders.pending` with `DirectChannel`, stopping its consumer can raise `MessageDispatchingException` on send. With `QueueChannel`, however, stopping the polling consumer **does not** cause no-subscriber errors; the symptom is growing backlog.

If poller error handling sends an `ErrorMessage` to an error channel, verify **both** the root exception, dequeue rollback, and whether the error handler/recoverer returns normally. A logged error message never proves transaction rollback by itself.

## 20. On-Call Runbook: One Topology, Three Incident Playbooks

### Step T0 — Triage in the First Few Minutes

Gather incident ID, first-error timestamp, deployed version, affected tenants/partitions, readiness/gate status, and these signals:

~~~text
flowId / endpointId: orders.worker
inputChannel: orders.pending  (durable / workshop?)
queue_group: orders.pending.v1
queue_region: orders-intake-v1
gate: OPEN / CLOSED
poller_running: true / false
ingress_accepted_per_sec:
business_applied_per_sec:
queue_pending / oldest_age:
outbox_pending / in_progress / oldest_age:
error_attempts / unique_business_events:
db_pool_active / waiting / timeout:
retry_budget / quarantine_count:
deployment_version / owner:
~~~

Until you know whether events committed to the JDBC store, **never mass-restart or wipe queues**. With a broker, verify exact adapter ACK/offset/requeue behavior; under in-memory profiles, evaluate crash data-loss risk.

### A. Full Queue or Growing Backlog

| Symptom | Check | Conditional Action |
|---|---|---|
| In-memory queue full, send timeout | `QueueChannel.getQueueSize()`, capacity, consumer state | Throttle ingress, keep poller running, never block senders forever |
| JDBC queue pending climbing | DB I/O/locks, poller, completion throughput, oldest age | Throttle intake, find slow handler; never just add workers |
| Poller not running | `SmartLifecycle.isRunning()`, `autoStartup`, deploy state | Start once dependencies/tenant are valid; keep gate closed until ready |
| Queue nearly empty yet high latency | In-flight TXs, DB waits, outbox relay | Measure terminal completions; never trust queue depth alone |
| Single order/tenant stalled | Lock contention, ordering, hot correlation key | Adjust partitioning/concurrency per business key |

**Never** delete raw rows from `INT_CHANNEL_MESSAGE` or change `region` to make queues look "empty." Purging requires reconciliation, approval, and a recovery plan; deleting mid-flight risks lost or duplicate data.

### B. Executor Rejections

The main flow uses a synchronous poller; `TaskRejectedException` normally surfaces in the **outbox relay, adapters, dynamic branches, or custom executors** when worker pools exist.

1. Identify the executor bean, core/max pool sizes, queue capacity, active/queued/rejected counts, and `isShutdown`.
2. Distinguish shutdown/lifecycle rejections from saturation rejections.
3. Find workers blocked on DB pools, HTTP timeouts, locks, or futures waiting on tasks in the same pool.
4. Throttle submissions while preserving pending work in the outbox or durable source.
5. Never switch to `DiscardPolicy` just to silence exceptions; it drops work silently.
6. Consider `CallerRunsPolicy` only after verifying backpressure **and** thread/transaction shifts.
7. Re-open gradually once completion throughput stabilizes, executor queues drain, and downstream headroom returns.

**Never ACK outbound events merely because an executor accepted the task.** Publishing can still fail post-handoff. Record `PUBLISHED` in the relay only on contract-valid adapter confirmation/ACK.

### C. Error Spikes and Retry Storms

Inspect the **first root exception** along the timeline rather than counting raw log lines:

| Error Type | Signal | Action |
|---|---|---|
| Validation/schema | Same payload fails repeatedly | Quarantine; never retry infinitely |
| Downstream 503/timeout | Error attempts spike; high DB/API latency | Throttle, bounded retry/backoff, check circuit breakers |
| DB lock/transaction timeout | Lock waits, rollbacks, rising pending | Inspect DB wait graphs/TX durations; lower concurrency |
| No-subscriber | Endpoint stopped or dynamic flow removed | Check topology/lifecycle; gate admissions before stopping |
| Error flow failure | Secondary error publishing `ErrorMessage` | Preserve root cause; fix error sink and recovery |
| Outbox relay failure | `IN_PROGRESS` leases expiring; pending not dropping | Check lease owners, remote ACKs, retry states |

One business event can emit 3 retry attempts logged across multiple loggers. Count **unique event IDs** separately from attempt counts. Never put `eventId` into metric tags to avoid cardinality explosions; rely on traces/logs and ID-indexed recovery tables.

### D. Crash/Restart and Post-Deploy Verification

Before opening ingress on a new instance:

1. Confirm schema migrations, serializer version, and query provider.
2. Reuse the exact JDBC store `region` and `groupId`; never reset tables.
3. Start the poller and verify recovery sinks, outbox relay, and transaction managers.
4. Reconcile processed event IDs, pending outbox rows, and quarantine entries against durable state.
5. Rebuild dynamic tenant flows from config DB with generation fencing.
6. Open the gate only once workers, dependencies, and minimum telemetry are ready.
7. Monitor skipped duplicate events, backlog age, and remote publish lag post-restart.

### Minimal SQL Dashboard

Never guess `INT_` column names outside your deployed schema version. These queries use only **the lesson's application-owned tables**:

~~~sql
-- Outbox state and oldest record age per state.
SELECT state,
       count(*) AS records,
       min(created_at) AS oldest_created_at
FROM outbox_events
GROUP BY state
ORDER BY state;

-- Business commit throughput over 5 minutes.
SELECT count(*) AS applied_events
FROM processed_events
WHERE processed_at >= now() - interval '5 minutes';

-- Events awaiting manual handling.
SELECT reason_code, count(*) AS events
FROM quarantined_events
WHERE state = 'OPEN'
GROUP BY reason_code;
~~~

Never put raw event payloads, secrets, tokens, or full headers into incident tickets or log collectors. Log safe correlation and allowed IDs under appropriate access controls.

### Evidence Required Before Closing an Incident

- Error attempts and rejection rates returned within operational thresholds;
- Queue pending/oldest age and outbox lag trending down toward normal;
- Completed business throughput exceeds intake enough to drain remaining backlog;
- Zero unreconciled uncertain ACKs/commits;
- Every open quarantine/DLQ entry has an owner and replay plan;
- Readiness and dynamic flow states match durable configuration;
- Rollback steps documented in case traffic rises again.

## 21. On-Call Shift Handoff Template

~~~text
INCIDENT_ID:
PRIMARY_SYMPTOM: QUEUE_BACKLOG | EXECUTOR_REJECT | ERROR_SPIKE | RESTART
FIRST_SEEN_AT:
SERVICE_VERSION / INSTANCES:
FLOW_ID / CHANNEL / ENDPOINT:
TENANT_OR_PARTITION_SCOPE:
MESSAGE_DURABILITY: IN_MEMORY | JDBC | BROKER
INGRESS_RATE / COMMITTED_RATE / OUTBOX_PUBLISHED_RATE:
PENDING / OLDEST_AGE / IN_FLIGHT:
ERROR_CLASS_GROUP / UNIQUE_EVENTS / ATTEMPT_COUNT:
DB_POOL / BROKER / REMOTE_DEPENDENCY_STATUS:
ACK_TRANSACTION_REPLAY_VERIFIED:
MITIGATION / RISKS / ROLLBACK_PLAN:
RECONCILIATION_OWNER / NEXT_CHECK:
RECOVERY_CRITERIA / FINAL_OUTCOME:
~~~

This template intentionally separates **attempt counts** from **business event counts** and separates durable acceptance, business completion, and outbound publishing. A report stating "errors cleared after restart" is inadequate if an in-memory queue dropped messages or unowned outbox items remain pending.

## 22. Architecture Decision Records (ADR)

A "complete" dossier states not only what was chosen, but also **why alternatives were rejected** and when to revisit each decision.

| ADR | Current Decision | Rationale | When to Revisit |
|---|---|---|---|
| ADR-01 | Java DSL with stable bean/endpoint IDs | Easier graph/lifecycle/test debugging than generated IDs | When dynamic per-tenant topology or external config is required |
| ADR-02 | JDBC-backed `QueueChannel` for durable practice | Cleanly shows receive + business TX in PostgreSQL | When throughput, lock contention, or DB cost exceeds budget |
| ADR-03 | Polling consumer processing synchronously inside TX | Dequeue and business write roll back together | When long-running async work needs a different durable handoff |
| ADR-04 | Unique business event ID | Prevents re-applying on replay/redelivery | If ID reuse/conflicting payloads arise; add fingerprints/versions |
| ADR-05 | Transactional outbox | DB writes and outbound events commit together | When adopting CDC/outbox platforms or specialized TX brokers |
| ADR-06 | Admission gate defaults to `CLOSED` | Prevents premature intake before readiness or after shutdown | Multi-node needs distributed fencing and broker pauses |
| ADR-07 | Bounded retries and durable quarantine | Stops poison messages from triggering retry storms | Tune per error budget and external service contracts |
| ADR-08 | Selective Observation, low-cardinality metrics | Avoids overhead, cardinality explosions, and payload leaks | Enable temporary targeted debug tracing during incidents |
| ADR-09 | Per-tenant flows only for optional branches | Avoids multiplying thousands of endpoints unnecessarily | When isolation, security, or SLAs truly require per-tenant flows |

**ADR-02 requires realism about scale:** Spring Integration's JDBC channel supports persistence and rollback, yet docs do not recommend database-as-queue as the default for heavy loads. Before scaling to thousands of messages/second or many nodes, benchmark dedicated brokers (JMS/AMQP/Kafka) and evaluate MVCC, indexes, vacuum, and partitioning/ordering.

### Risk Register and Pre-Production Hardening Tasks

| Risk | Current Demo Status | Mandatory Hardening |
|---|---|---|
| Conflicting duplicate ID | Processor deduplicates solely by event ID | Store canonical payload fingerprint; quarantine same-ID payload conflicts |
| Out-of-order updates | Last-writer-wins upsert | Add version/conditional updates or per-order partitioning |
| Outbox relay lacks full runnable class | Claim SQL + state machine specified | Build relay, lease fencing, remote ACKs, retry/backoff, and kill-point tests |
| Poison message infinite loop | Quarantine schema and policy designed | Implement atomic durable attempts ledger/recovery; test zero storms |
| Drain probe is an interface only | Coordinator relies on probe | Implement using queue, in-flight TXs, adapter ACKs/recovery ledger; test races |
| Multi-node admission | Read/write lock is single-JVM only | Add distributed owner state, broker pauses, and fencing |
| Serialization across deploys | Illustrative Java record/serializer | Enforce version compatibility, safe deserialization, and migrations |
| Queue capacity in `durable` profile | No global hard cap configured | Throttle ingress, enforce storage quotas, oldest-age alerts, load tests |
| Sensitive data in logs/DLQ | Org policy not yet implemented | Add redaction, encryption, retention, and access controls |
| Migrations in integration tests | Test skeleton expects migrated schema | Run Flyway/Liquibase before store startup with checksums and rollback plans |
| Outbound exactly-once | Outbox delivers at-least-once | Enforce remote idempotency/reconciliation by outbox ID |

Items marked "must implement" are **real engineering deliverables**—never mark them PASS simply because the lesson provides examples. Keeping this honest distinguishes a reference design from production readiness verified in your target environment.

### Minimum Retention Policy

| Data | When Can It Be Deleted? |
|---|---|
| `processed_events` | Only past all supported redelivery/replay windows, including outbox and client retries |
| `outbox_events` | Only after terminal publish and past remote deduplication/reconciliation windows |
| `quarantined_events` | Only after resolution and per retention/compliance rules |
| `INT_CHANNEL_MESSAGE` | Via store APIs/mechanisms; never raw `DELETE` while pollers run |
| `MessageGroupStore` fragments | After release/expiry per policy, with clear late-fragment handling |
| Message history/traces/logs | Per investigation needs and security policies; never store payloads indefinitely |
| Tenant flow config/generation | Only after cleanup/reconcilers confirm zero resources or work remain |

Purging dedupe markers before client retry windows expire allows old events to re-apply. Deleting outbox rows before remote ACKs/reconciliation destroys replay capability. Retention is a **business contract**, not just a DB cleanup cron.

## 23. Five-Iteration Implementation Roadmap

### Iteration 1 — Runnable Topology

Build the domain event, in-memory `QueueChannel`, poller, and test handler. Document the bean ID manifest, draw sync/async boundaries, and test send/receive. Do not claim data durability yet.

**Iteration 1 passes when:** Valid events traverse the right endpoint, endpoints start/stop cleanly, full queues are handled explicitly, and exceptions are never treated as success.

### Iteration 2 — Durable State and Idempotency

Run PostgreSQL migrations, switch to `JdbcChannelMessageStore`, and add poller transaction advice plus `processed_events`, `orders`, and outbox tables. Reconcile by event ID.

**Iteration 2 passes when:** Real JDBC commit/rollback is verified and duplicate intake with the same event ID never creates two business side effects.

### Iteration 3 — Recovery and Lifecycle

Add admission gating, readiness, `WorkDrainProbe`, retry policies, quarantine, and restart reconciliation. Inject DB faults, kill processes mid-transaction, and test startup against an existing queue.

**Iteration 3 passes when:** Evidence proves no accepted response precedes durable commit, pending items recover cleanly, and stops never destroy unsettled data.

### Iteration 4 — Outbox and Correlation

Implement relay leasing/claiming, remote idempotency, and crash tests after publishing before DB marking. If batching is required, add an aggregator with a separate `MessageGroupStore` and group timeouts.

**Iteration 4 passes when:** Outbox rows persist alongside business commits, publishes retry safely, and remote consumers deduplicate by outbox/event ID.

### Iteration 5 — Observability and Operations

Add accepted/applied/outbox metrics, trace/header propagation, graph snapshots, lag alerts, runbooks, and game days. Benchmark baseline workloads before and after concurrency or logging changes.

**Iteration 5 passes when:** On-call can isolate queue backlogs, executor rejections, and error spikes, with timelines/snapshots to reconcile incidents afterward.

### Suggested Learner Submission Structure

~~~text
01-topology.md             diagrams + channel/endpoint/thread manifest
02-contracts.md            input/output, accepted/committed/published
03-state-and-schema.md     tables, region/group, retention, serializers
04-lifecycle.md            state machine, readiness/drain/shutdown
05-recovery-matrix.md      crash points, retries, DLQ, replays
06-tests.md                unit/integration/restart/game-day results
07-observability.md        metrics, logs, traces, dashboards
08-operations-runbook.md   queues, executors, errors, deployments
09-adr.md                  decisions, trade-offs, risk register
~~~

This list suggests **learner deliverable artifacts**, not files generated inside this module. This knowledge dossier remains a single Markdown document at its assigned path.

## 24. Final Acceptance Gate

### Acceptance Matrix

| ID | Criterion to PASS | Verification Method | Priority |
|---|---|---|---|
| AC-01 | Topology manifest documents channels, endpoints, owners, and threads | Diagram + Spring Integration graph review | Mandatory |
| AC-02 | Clients receive accepted only after durable intake commits | DB failure/timeout tests + client retries | Mandatory |
| AC-03 | Poller transaction wraps synchronous receive + business write | JDBC rollback integration tests | Mandatory |
| AC-04 | Duplicate events never increase business or outbox counts | Concurrent/restart idempotency tests | Mandatory |
| AC-05 | Transient retries are bounded; poison events go to durable quarantine | Exhaustion + poison-event tests | Mandatory |
| AC-06 | Outbox publishes replay cleanly; remote consumers deduplicate | Crash after-publish-before-mark test | Mandatory |
| AC-07 | Gate closes before stop; pending items keep a recovery path | Shutdown/race tests | Mandatory |
| AC-08 | Restart with identical region/group/serializer recovers queue | Two Spring contexts sharing PostgreSQL | Mandatory |
| AC-09 | Tenant flow cleanup never harms shared resources | Multi-tenant generation-fencing tests | When dynamic flows exist |
| AC-10 | Metrics/logs/traces pinpoint queues, workers, errors, and outbox | Dashboards + game-day evidence | Mandatory |
| AC-11 | Latency/throughput/DB load benchmarked at target workload | Load tests and capacity report | Mandatory before production |
| AC-12 | Retention, serializer upgrades, and rollbacks approved | Migration rehearsal + ADRs | Mandatory before production |

**Status recording:** Mark each row `NOT_RUN`, `PASS`, `FAIL`, or `BLOCKED` with evidence. This document contains **designs and examples**, not test execution logs. Never mark an item `PASS` before actually running the verification in its target environment.

### Comprehensive Checklist

- [ ] Distinguished `send()`, durable accepted, handler completed, transaction committed, and outbound ACK.
- [ ] Assigned stable channel/endpoint IDs and documented threads, error channels, and recovery.
- [ ] Selected the right stores for queues vs. aggregators; kept `region`/`groupId` constant across restarts.
- [ ] Ran database migrations before store startup; documented serializer version compatibility.
- [ ] Closed ingress by default, opening only after consumers, DB, and recovery are ready.
- [ ] Verified poller transactions share `DataSource`/manager without async handoffs cutting across them.
- [ ] Enforced unique event IDs; defined policies for conflicting duplicates and ordering.
- [ ] Committed outbox rows with business state; built relay leases, ACKs, and idempotent remote consumers.
- [ ] Bounded retries across all polls/restarts, not merely in-handler advice attempts.
- [ ] Quarantined poison messages durably; error flows never swallow failures before safe recovery.
- [ ] Verified draining checks in-flight work, transactions, and durable replay—not queue size alone.
- [ ] Prevented shutdown from closing shared schedulers/executors/`DataSource`s while other tenants run.
- [ ] Added generation/owner fencing and durable reconcilers for dynamic flows.
- [ ] Scoped metrics/traces/logs cleanly, avoiding high-cardinality tags and sensitive payload leaks.
- [ ] Tested crashes, duplicates, schema drift, rolling deploys, queue overloads, and outbox replays.
- [ ] Established on-call runbooks, DLQ/quarantine owners, and clear incident closure criteria.

**Conclusion:** A complete Spring Integration runtime dossier unites **named topology with explicit thread boundaries; readiness–quiesce–drain lifecycles; durable state with transactions and idempotency; recovery via retries, quarantine, and outboxes; actionable observability; and test-backed operational runbooks**. This project succeeds when you can prove where every message sits and how it will be handled **after any failure**, not merely when the flow runs smoothly in ideal conditions.

## Official References

- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration — Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html)
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration — Advice Chain and Retry](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html)
- [Spring Integration — Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
