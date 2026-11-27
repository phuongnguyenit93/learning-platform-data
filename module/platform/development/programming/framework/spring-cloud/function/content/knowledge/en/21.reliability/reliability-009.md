
# Managing Shared State Across Multiple Invocations

## 1. Lesson Objectives

A Spring Cloud Function can be invoked thousands of times across HTTP requests, messages, or serverless invocations. Each call may execute on the same JVM, a different instance, or a freshly started process. If business state lives only in a bean field or a `static` variable, subsequent calls have no guarantee of seeing the right data; two concurrent calls can even overwrite each other's results.

In the **SPRING_CLOUD_FUNCTION** module, business logic is structured using `Supplier`, `Function`, and `Consumer`, registered via `FunctionCatalog`, composed into pipelines, and deployed independently of HTTP, event, or serverless protocols. The functional model encourages transforming input to output; whenever the business needs to remember data across invocations, state must have a proper storage layer and explicit synchronization rules.

This lesson belongs to the **Reliability** chapter and focuses on **managing shared state across multiple invocations**. After this lesson, you will be able to:

- Distinguish per-invocation data from long-lived shared state.
- Understand why mutable fields, `static` variables, and local memory are not reliable shared data sources.
- Choose databases, distributed caches, event logs, or object storage according to state semantics.
- Design keys with tenant, aggregate, and version scopes to prevent collisions.
- Update state safely when multiple invocations run concurrently.
- Organize pure Functions, application services, and state stores.
- Manage caches, TTLs, event ordering, idempotency, and state migrations.
- Test multiple instances, restarts, race conditions, and multi-tenant isolation.

> **Guiding Principle:** An invocation is one execution; an instance is a replaceable process. If data must survive across invocations or be shared across instances, store it in a system with appropriate durability and concurrency semantics. Local memory is only a cache or optimization unless the business intentionally scopes it to a single process.

## 2. An Invocation Is Not an Instance

Spring Cloud Function allows the same function to be called from multiple adapters. Each call is an invocation; invocations may be handled by the same instance or different instances.

~~~text
                 ┌──────────────────────┐
HTTP request ───>│                      │
Message event ──>│  Function adapter   │
Serverless event>│                      │
                 └──────────┬───────────┘
                            |
                            v
                    Function invocation
                            |
                 ┌──────────┴──────────┐
                 v                     v
             Instance A            Instance B
                 |                     |
                 +---------+-----------+
                           |
                           v
                    Shared state store
~~~

Under horizontal scaling, multiple instances process requests concurrently. In serverless runtimes, the platform may reuse an instance across invocations or spin up fresh instances; never rely on an instance remaining alive.

### 2.1. What Is Never Guaranteed

- That the next invocation runs on the same JVM.
- That two messages for the same aggregate always execute sequentially.
- That a `static` variable is shared across containers or replicas.
- That an instance does not restart between calls.
- That instance memory survives scale-to-zero.
- That sticky sessions or routing always send the same user to the same instance.
- That a local write was replicated to other instances.

These properties depend on the adapter, platform, concurrency, and deployment. Business designs must remain correct even when two concurrent invocations run on two separate instances.

### 2.2. A Function Bean Usually Outlives One Invocation

Spring beans are typically singletons per application context. Hence a mutable field on a bean can be accessed concurrently by multiple threads:

~~~java
@Bean
public Function<Command, Result> process() {
    Map<String, Result> recentResults = new HashMap<>();

    return command -> {
        Result result = calculate(command);
        recentResults.put(command.id(), result);
        return result;
    };
}
~~~

This example has two flaws:

1. `HashMap` is not safe for concurrent reads and writes.
2. Data exists only in the current instance; restarts or requests routed to another instance will miss it.

Switching to `ConcurrentHashMap` solves only part of single-JVM concurrency. It adds no durability, no cross-replica sharing, and no database transactions.

## 3. Classify State Before Choosing Storage

Not all data belongs in a database. First identify the required lifecycle and consistency level.

| Data Kind | Example | Lifecycle | Suitable Storage |
|---|---|---|---|
| Immutable configuration | Default tax rate, endpoints | Per deployment | Configuration / properties |
| Invocation input | Command, headers, correlation ID | Single call | Parameters / `Message` |
| Transient pipeline data | Validation output, intermediate DTOs | Single call | Local variables / Function composition |
| Business state | Order status, payment state | Across invocations | Database / state store |
| Session / workflow | Wizard state, job progress | Multiple requests/events | DB or distributed state store |
| Cache | Frequently read product prices | With TTL, rebuildable | Local / distributed cache |
| Event history | `OrderCreated`, `PaymentCaptured` | Per retention/audit | Event log / event store |
| Large files | Reports, blob payloads | Long-term | Object storage, DB holds metadata |
| Metrics / traces | Latency, counts | Per telemetry retention | Monitoring backend |

### 3.1. Configuration Is Not Business State

Config values read at startup can live inside beans if immutable for the context lifecycle. If config changes dynamically, use an explicit refresh/versioning mechanism; never turn a field into a source of truth without knowing who updates it.

### 3.2. Intermediate Data Should Stay Inside the Invocation

Results of normalize/validate/calculate needed only within one pipeline belong in Function composition:

~~~text
OrderCommand
    |
    v
normalizeOrder
    |
    v
validateOrder
    |
    v
calculateQuote
    |
    v
Quote
~~~

There is no need to write every intermediate value into a global map. Keeping data local eases testing, reduces coupling, and avoids cleaning up temporary state.

### 3.3. Business State Must Have an Owner

Each kind of state needs a clear owner:
- Which service is allowed to create or update it?
- Which key identifies an aggregate?
- What are the valid state transition rules?
- Who may read and who may write?
- Are audit trails or history required?
- Which retention and deletion policies apply?

Never let multiple function beans modify the same table under conflicting rules without a single application service or state-transition owner.

## 4. Why Mutable State in Function Beans Is Dangerous

A simple counter example:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CounterFunctions {

    private long counter = 0;

    @Bean
    public Supplier<Long> nextCounter() {
        return () -> ++counter;
    }
}
~~~

With one instance and one thread, this looks fine. Under concurrent invocations, `++` is not atomic; two threads can read the same value and return the same number. With two instances, each maintains its own counter. On restart, the counter resets to 0.

### 4.1. AtomicLong Is Still Atomic Only Within One Process

~~~java
private final AtomicLong counter = new AtomicLong();
~~~

`AtomicLong` ensures atomic operations across threads sharing the same object in one JVM. It does not:
- Share values across two containers.
- Persist across restarts.
- Synchronize with a database.
- Prevent the same operation from running twice on redelivery.

Using `AtomicLong` for unimportant local metrics/sequences can be reasonable; using it as a system-wide business ID generator is not.

### 4.2. Static Is Not Distributed Storage

`static` fields belong to a classloader inside one process. Two pods have two separate static spaces. During rolling deployments, new pods do not inherit the old pods' state. When unique IDs are needed, use database sequences, UUID/ULID, or a dedicated ID service instead of incrementing a static counter.

### 4.3. Thread-Safe Does Not Mean Business-Safe

`ConcurrentHashMap` protects the map's internal structure, yet a read → compute → write sequence still races:

~~~java
Integer oldValue = map.get(key);
Integer newValue = oldValue + delta;
map.put(key, newValue);
~~~

Two threads both read 10, add 1, and write 11. The right result was 12. Using `compute` makes the update atomic inside one local map, yet still fails across instances and restarts.

## 5. Principles for Designing Stateless Functions

A stateless Function does not mean the system stores no state. It means an invocation's output is determined by its input, required context, and explicitly managed state stores rather than hidden bean fields.

### 5.1. Pure Functions

~~~java
@Bean
public Function<NormalizeCommand, NormalizedCommand> normalize() {
    return command -> new NormalizedCommand(
            command.tenantId(),
            command.orderId().trim().toUpperCase(),
            command.quantity());
}
~~~

Same input produces same output without mutating shared state. Pure Functions are easy to test and safe to rerun.

### 5.2. Functions Reading State

A function can inject a service to read current state:

~~~java
@Bean
public Function<OrderId, OrderView> getOrder(OrderQueryService queryService) {
    return queryService::findView;
}
~~~

The Function holds no state in fields. The service reads state from a store with defined ownership, access controls, and consistency guarantees.

### 5.3. Side-Effecting Consumers

~~~java
@Bean
public Consumer<OrderUpdated> updateOrder(OrderApplicationService service) {
    return service::apply;
}
~~~

A Consumer may update state, yet transactions, idempotency, validation, and concurrency belong inside the application service and repository. Never let each adapter invent its own update logic.

### 5.4. FunctionCatalog Only Registers and Looks Up Functions

`FunctionCatalog` looks up functions by name and type. It is not a state store, distributed cache, or transaction coordinator. A composition such as:

~~~text
normalizeOrder|validateOrder|calculateQuote|recordQuote
~~~

describes only the processing chain. When `recordQuote` writes to a database, the application service/repository is responsible for durable persistence and concurrent update protection.

## 6. Choosing Storage by State Semantics

| Storage | Best Fit | Things to Consider |
|---|---|---|
| Relational database | Business state, transactions, unique keys, queries | Locks, isolation, schema migrations, connection pools |
| Redis / distributed cache | Fast lookups, counters/leases/TTLs, ephemeral shared state | Persistence/replication config, eviction, failover, atomic scripts |
| Event log / event store | Change history, replays, audits | Ordering, projections, schema evolution, replay cost |
| Kafka compacted topic | Keyed state snapshots or changelogs | Eventual visibility, partition ordering, consumer offsets |
| Object storage | Large blobs/files, artifacts, snapshots | Unsuitable for high-concurrency small read-modify-write |
| Local cache | Lower latency for rebuildable data | Stale data, per-instance copies, invalidation |

### 6.1. Source of Truth and Caches

Pick one **source of truth** per aggregate. Caches speed up reads, yet must never be the sole store for critical state if caches can evict or restart.

Cache-aside pattern:

~~~text
Read state
   |
   v
Cache hit? ---- yes ----> Return cached view
   |
   no
   v
Read source of truth
   |
   v
Populate cache with TTL
   |
   v
Return
~~~

When updating state, define invalidation/update rules. If a DB write succeeds and cache invalidation fails, readers may see stale data. For critical state, consider outbox-driven invalidation events, version checks, or appropriately short TTLs.

### 6.2. Local Cache vs. Distributed Cache

Local caches offer low latency, yet each instance holds a separate copy. They fit reference data tolerant of brief staleness, not shared session/job state.

Distributed caches let multiple instances read the same cache system, yet still require understanding consistency, eviction, replication, persistence, and failover. "Distributed" does not automatically mean data cannot be lost.

### 6.3. Redis Counters and Atomic Operations

Redis offers atomic commands like `INCRBY`; incrementing server-side is safer than client-side read-modify-write. Still configure keys, TTLs, persistence, and failover properly. If a counter represents critical financial/audit data that must never be lost, consider DB transactions and durable logs instead of cache alone.

## 7. Key Design and Access Scoping

A state key must accurately identify both entity and tenant. Examples:

~~~text
tenant:{tenantId}:order:{orderId}
tenant:{tenantId}:session:{sessionId}
tenant:{tenantId}:job:{jobId}
~~~

Never use bare `orderId` if tenants can have overlapping IDs. Never use mutable usernames or emails as permanent unique keys if they can change or be recycled.

### 7.1. Keys Must Reflect Business Identity

Distinguish:
- **Tenant ID:** customer/organization boundary.
- **Aggregate ID:** order, account, workflow.
- **Operation ID:** a specific request or command.
- **Event ID:** a published event.
- **Version:** state revision or update sequence.

Event IDs detect duplicate deliveries; aggregate IDs identify state; operation IDs support safe retries; versions reject stale updates.

### 7.2. Authorization Is Independent of Keys

Knowing a state key does not grant permission to read or write it. Every invocation must authenticate the principal and verify tenant/permissions before accessing state. Never blindly trust a `tenantId` inside the payload; derive or verify it against the authenticated identity.

### 7.3. Bound Client-Supplied Keys

Client-supplied keys need length and character-set limits, normalization, and protections against unbounded namespace creation. When storing keys in Redis or a database, bound cardinality and quotas so one client cannot exhaust state storage.

## 8. Updating State Safely Under Concurrent Invocations

Shared storage alone does not prevent lost updates. Use atomic operations or explicit version/lock controls at the storage layer.

### 8.1. Lost Updates Under Read-Modify-Write

Suppose a counter is currently 10:

~~~text
Invocation A                 Invocation B
-------------                 -------------
READ value = 10
                              READ value = 10
value = 11
                              value = 11
WRITE 11
                              WRITE 11
~~~

Both invocations succeed, yet the counter increases by only one. This race condition happens even when the database is shared.

### 8.2. Atomic Updates in the Database

Instead of reading and writing in the client, increment in a single SQL statement:

~~~sql
INSERT INTO counter_state (
    tenant_id, counter_id, value, version
)
VALUES (
    :tenantId, :counterId, :delta, 1
)
ON CONFLICT (tenant_id, counter_id)
DO UPDATE SET
    value = counter_state.value + EXCLUDED.value,
    version = counter_state.version + 1
RETURNING value, version;
~~~

In PostgreSQL, `INSERT ... ON CONFLICT DO UPDATE` on a single row is coordinated atomically by the database. Concurrent invocations on the same key serialize on row lock/conflict; each increment applies once per successful execution. Check isolation levels, deadlock retries, and your database's exact semantics.

### 8.3. Illustrative Tables and Ports

~~~sql
CREATE TABLE counter_state (
    tenant_id   VARCHAR(80) NOT NULL,
    counter_id  VARCHAR(120) NOT NULL,
    value       BIGINT NOT NULL,
    version     BIGINT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, counter_id)
);

CREATE TABLE processed_operation (
    tenant_id       VARCHAR(80) NOT NULL,
    operation_id    VARCHAR(120) NOT NULL,
    counter_id      VARCHAR(120) NOT NULL,
    command_hash    CHAR(64) NOT NULL,
    result_value    BIGINT,
    result_version  BIGINT,
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Storage ports:

~~~java
package example.functions;

public interface CounterStore {
    CounterSnapshot incrementAndRead(
            String tenantId, String counterId, long delta);
}

public interface ProcessedOperationStore {
    boolean insertIfAbsent(
            String tenantId, String operationId,
            String commandHash, String counterId);

    String findCommandHash(String tenantId, String operationId);

    CounterSnapshot findResult(
            String tenantId, String operationId);

    void saveResult(
            String tenantId, String operationId,
            CounterSnapshot result);
}
~~~

`insertIfAbsent` and `saveResult` must share the same transaction manager as `CounterStore`. The PostgreSQL implementation of `incrementAndRead` executes the `RETURNING` query above and maps the result to a record.

### 8.4. Deduplicating Application Service

~~~java
package example.functions;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CounterService {

    private final CounterStore counters;
    private final ProcessedOperationStore operations;
    private final TenantAccess tenantAccess;
    private final CommandFingerprint fingerprint;

    public CounterService(
            CounterStore counters,
            ProcessedOperationStore operations,
            TenantAccess tenantAccess,
            CommandFingerprint fingerprint) {
        this.counters = counters;
        this.operations = operations;
        this.tenantAccess = tenantAccess;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public CounterSnapshot increment(IncrementCommand command) {
        String tenantId = tenantAccess.requireTenantId();
        String commandHash = fingerprint.hash(command);

        boolean claimed = operations.insertIfAbsent(
                tenantId, command.operationId(),
                commandHash, command.counterId());

        if (!claimed) {
            String oldHash = operations.findCommandHash(
                    tenantId, command.operationId());
            if (!commandHash.equals(oldHash)) {
                throw new OperationKeyConflictException(
                        "Operation ID reused with a different command");
            }
            CounterSnapshot previous = operations.findResult(
                    tenantId, command.operationId());
            if (previous == null) {
                throw new IllegalStateException(
                        "Committed operation has no stored result");
            }
            return previous;
        }

        CounterSnapshot result = counters.incrementAndRead(
                tenantId, command.counterId(), command.delta());

        operations.saveResult(
                tenantId, command.operationId(), result);

        return result;
    }
}
~~~

Supporting records and ports:

~~~java
package example.functions;

public record IncrementCommand(
        String operationId, String counterId, long delta) {}

public record CounterSnapshot(long value, long version) {}

public interface TenantAccess {
    String requireTenantId();
}

public interface CommandFingerprint {
    String hash(IncrementCommand command);
}
~~~

~~~java
package example.functions;

public class OperationKeyConflictException extends RuntimeException {
    public OperationKeyConflictException(String message) {
        super(message);
    }
}
~~~

`TenantAccess` derives the tenant from the authenticated principal/context; never trust an arbitrary client-provided tenant. `operationId` is a stable identifier for one request. `CommandFingerprint` computes the hash server-side from the validated/normalized command rather than accepting a client-supplied hash. If the same operation is resent with the same fingerprint, the service returns the stored snapshot without incrementing again.

This is a create-once example per operation. If the same `operationId` arrives with a different `counterId` or `delta`, the fingerprint mismatches and the service raises a conflict instead of returning an old result unchecked.

### 8.5. Keep the Function as a Thin Boundary

~~~java
@Configuration
public class CounterFunctions {

    @Bean
    public Function<IncrementCommand, CounterSnapshot> incrementCounter(
            CounterService service) {
        return service::increment;
    }
}
~~~

The Function bean holds no counter in fields. Every invocation delegates to the service, which manages tenant access, idempotency, and transactions. Whether bound over HTTP or messaging, state update rules live in the same application service.

### 8.6. Atomicity Does Not Mean Every Operation Is Addition

A single atomic SQL statement suits a counter, whereas updating an order may require checking current status, quotas, and multiple tables. Use transactions, versions/locks, and valid state transitions for those. Never force every business rule into a Redis `INCR` merely because it is atomic.

## 9. Optimistic Locking and Pessimistic Locking

When multiple invocations update the same aggregate, versions detect conflicts.

### 9.1. Optimistic Locking with Versions

A JPA entity can use `@Version`:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private String id;

    private String tenantId;

    private String status;

    @Version
    private long version;

    // getters/setters/constructor omitted
}
~~~

On update, JPA checks the current version in the write predicate. If another invocation committed a newer version, the update matches nothing and the provider throws an optimistic-lock failure. The application must re-read, re-check business rules, and retry the transaction if safe.

Optimistic locking fits infrequent contention. It does not by itself deduplicate duplicate commands; operation idempotency is still required.

### 9.2. Pessimistic Locking

You can lock rows inside a transaction when reading for update, e.g., `SELECT ... FOR UPDATE` or JPA lock modes. Other invocations wait for the lock or time out.

Use when updates on an aggregate must serialize and contention is acceptable. Ensure:
- Transactions stay short.
- Lock acquisition order is consistent to reduce deadlocks.
- Lock timeouts and deadlock handling exist.
- No remote calls occur while holding locks.

### 9.3. Choosing Mechanisms by Invariant Type

| Need | Typically Suitable Mechanism |
|---|---|
| Increment counter | Atomic SQL / Redis command |
| Prevent overwriting newer versions | Optimistic locking / CAS |
| Complex state transition on one row | Transaction + row lock or version |
| Execute an operation at most once | Unique operation key + transaction |
| Multi-row quota limit | Careful transaction/isolation or atomic counter |
| Distribute leases/claims | Storage with conditional update / lease semantics |

Never reach for distributed locks first if database unique constraints or atomic updates already protect the invariant.

## 10. Workflow State and State Transitions

Shared state is rarely just raw values to read and write. It often models a workflow with valid states.

Order example:

~~~text
NEW
 |
 v
VALIDATED
 |
 v
RESERVED
 |
 v
PAID
 |
 v
COMPLETED
~~~

A late stale event must never move an order backward from `COMPLETED` to `RESERVED`.

### 10.1. Define Valid Transitions

~~~java
public enum OrderStatus {
    NEW, VALIDATED, RESERVED, PAID, COMPLETED, CANCELLED
}

public OrderStatus transition(
        OrderStatus current, OrderEvent event) {

    return switch (current) {
        case NEW -> switch (event.type()) {
            case VALIDATED -> OrderStatus.VALIDATED;
            case CANCELLED -> OrderStatus.CANCELLED;
            default -> throw new InvalidTransitionException();
        };
        case VALIDATED -> switch (event.type()) {
            case RESERVED -> OrderStatus.RESERVED;
            case CANCELLED -> OrderStatus.CANCELLED;
            default -> throw new InvalidTransitionException();
        };
        case RESERVED -> switch (event.type()) {
            case PAID -> OrderStatus.PAID;
            case CANCELLED -> OrderStatus.CANCELLED;
            default -> throw new InvalidTransitionException();
        };
        case PAID -> {
            if (event.type() == EventType.COMPLETED) {
                yield OrderStatus.COMPLETED;
            }
            throw new InvalidTransitionException();
        }
        case COMPLETED, CANCELLED ->
                throw new InvalidTransitionException();
    };
}
~~~

This snippet assumes matching enums and exceptions in the application. The key point is that transitions verify current state and event type rather than blindly assigning whatever status string arrives in a message.

### 10.2. Event Versions and Ordering

Each aggregate can carry a monotonically increasing `version`. Events include aggregate ID and sequence/version. Consumers:
- Accept the next expected version.
- Recognize stale or already-applied versions.
- Detect gaps when events arrive out of order.
- Never apply stale events onto newer state.

In Kafka, partitioning by aggregate key preserves ordering within one partition, yet does not guarantee ordering across topics, producers, or external systems. Database version guards remain the safety net at the consumer.

### 10.3. Event Sourcing Is Not Required by Default

Event sourcing stores events as the primary source of truth and builds state via projections. It fits systems requiring complete history, audits, replays, or multiple projections—at the cost of schema evolution, ordering, snapshots, and replay overhead.

If you only need current state plus an audit log, relational tables plus an outbox are often simpler. Never adopt event sourcing just because your system uses messaging.

## 11. Pass Context Across Invocations, Not Hidden Mutable State

Requests typically carry metadata such as correlation IDs, tenant, locale, deadlines, or security principals. Metadata guides invocation handling; it does not replace durable business state.

### 11.1. Distinguish Payload, Metadata, and Durable State

| Component | Example | How Passed / Stored |
|---|---|---|
| Business payload | `OrderCommand`, `PaymentCommand` | Function input / `Message` payload |
| Invocation metadata | Correlation ID, trace ID, deadline | Message headers or execution context |
| Identity / authorization | Principal, scopes, verified tenant | Verified security context |
| Durable state | Order status, workflow progress | Database / state store |
| Cache key / version | Aggregate ID, version | Derived from identity and state |

Do not stuff entire business state objects into HTTP or message headers. Headers fit small metadata; business data requires validation, versioning, and authorization in the application service.

### 11.2. Spring Message Headers

Spring Cloud Function can accept and return `Message<T>` to work with headers:

~~~java
@Bean
public Function<Message<OrderCommand>, Message<OrderAccepted>> acceptOrder(
        OrderApplicationService service) {

    return message -> {
        OrderAccepted result = service.accept(message.getPayload());

        return MessageBuilder.withPayload(result)
                .setHeader(
                        "correlationId",
                        message.getHeaders().get("correlationId"))
                .build();
    };
}
~~~

This illustrates preserving correlation metadata with an application `correlationId` header. Import `Message` from Spring Messaging and `MessageBuilder` from Spring Messaging support. Never copy arbitrary headers blindly to outputs; propagate only allowed and necessary headers.

A tenant header sent by a producer or client is not automatically trustworthy. Adapters must authenticate identity and map the tenant from security context; application services still check permissions on state keys.

### 11.3. Correlation ID Is Not Operation ID

A correlation ID links logs/traces for one processing flow. An operation ID identifies a business action that may be retried. A retry request may carry a new correlation ID while keeping the same operation ID when intentionally retried.

Never use a trace ID as an idempotency key because trace IDs change across calls.

### 11.4. Reactor Context Differs from ThreadLocal

Reactive pipelines switch threads between operators. `ThreadLocal` does not follow a subscription/context across schedulers automatically. Reactor offers `Context` to pass metadata along with the subscriber:

~~~java
Mono<OrderView> view = Mono.deferContextual(context -> {
    String tenantId = context.get("tenantId");
    return orderService.findForTenant(tenantId, orderId);
}).contextWrite(context ->
        context.put("tenantId", authenticatedTenantId));
~~~

This illustrates reading/writing Reactor `Context`; verify how your stack bridges security/context propagation. Never populate tenant from an unverified payload.

If blocking code requires `ThreadLocal`, configure proper context propagation and cleanup so one request's data never leaks onto another task in the thread pool.

### 11.5. Function Composition Must Preserve Needed Context

When composing Functions, decide which metadata must travel onward and which stays at the boundary. Use a strongly typed envelope or `Message<T>`—never rely on `static` variables to "remember" correlation IDs or tenants across steps.

## 12. State Across HTTP, Messaging, and Serverless

The same application service may be called by different adapters, each with a different state lifecycle.

### 12.1. HTTP Requests and Sessions

HTTP requests are usually independent. If server-side sessions are needed, store them in a shared session store or session service—never keep sessions only in one web instance's memory when a load balancer can route requests elsewhere.

Stateless tokens like `JWT` carry signed claims, yet cannot reflect immediate revocation or permission changes on their own. If immediate logout, revocation, session versioning, or permission updates are required, add a lookup/revocation store or suitably short token lifetimes.

Sticky sessions reduce instance switching, yet offer no durability guarantee; instances still restart or scale down.

### 12.2. Message Consumers

Messages can be redelivered or handled by a different consumer instance. Workflow state belongs in a DB or shared store keyed by event/operation IDs. Never store processed-message history in Consumer instance fields.

When multiple events for the same aggregate can run concurrently, use partition keys, per-aggregate serialization, optimistic locking, or transactions. Partition ordering applies only within a broker/partition and never replaces version checks in the state store.

### 12.3. Serverless Invocations

Invocations can land on brand-new instances with no preserved memory. Job, session, and order state must live in external durable storage. Ephemeral local disk or execution-context storage should hold only disposable temporary data.

### 12.4. Do Not Serialize Entire State into Events

Events should describe meaningful facts or deltas, not necessarily duplicate full entity snapshots. Oversized payloads cause schema friction, higher costs, and wider stale-data propagation. Choose between fat events and ID/version-referenced events based on consistency and coupling trade-offs.

## 13. Cache Consistency and Invalidation

Caches lower load at the cost of holding a copy of state. Define how much staleness is tolerable and who owns invalidation.

### 13.1. Cache-Aside Can Serve Stale Data After Updates

~~~text
Writer A:
  DB updates value = 20
  cache invalidation fails

Reader B:
  cache hit value = 10
  returns stale data
~~~

If display data tolerates a few seconds of staleness, a short TTL may suffice. If state drives payments, quotas, or authorization, stale cache reads cause business errors; use stronger versioning or consistency strategies.

### 13.2. Invalidate Before or After DB Update?

- Invalidate before DB update: a concurrent reader can reload the old value into cache before the DB commits.
- Invalidate after DB update: the process can crash between commit and invalidation.
- Update cache directly: cache and DB diverge if either write fails.

No two separate commands across DB and cache are atomic together. Use outbox-published invalidation events after commit, versioned cache keys, or TTLs to bound the staleness window.

### 13.3. Versioned Cache Keys

When state carries a version, embed the version in the cache key or cached value. Readers verify the expected version to avoid stale entries. Note that you still need a source knowing the current version; reading the version itself from a stale cache leaves the same issue.

### 13.4. Cache Stampedes

When a popular key's TTL expires, many concurrent invocations miss and hit the database or remote service simultaneously. Use request coalescing, refresh-ahead, jittered TTLs, or leased locks where appropriate. Never hold locks indefinitely if a worker dies; every lease needs expiry and recovery.

## 14. TTL, Retention, and State Lifecycles

Not all state should live forever. Base TTLs and retention on business requirements and replay windows.

| State | Reference Policy |
|---|---|
| Catalog / price cache | Short TTL, rebuildable |
| Temporary sessions | Expire on inactivity and security policy |
| Running jobs | Never auto-delete while pending |
| Idempotency records | Retain at least through retry/replay windows and business rules |
| Order / payment state | Per business lifecycle and audit/legal needs |
| Event logs | Retention/archival per replay and audit requirements |
| Locks / leases | Expiry with fencing and recovery |
| Temporary uploads | Clean up after completion or expiration |

### 14.1. TTL Is Not a State-Transition Mechanism

A `PROCESSING` job should not vanish simply because a short TTL expired. Use terminal states, post-terminal retention, and explicit cleanup workflows. Expiry does not replace marking `COMPLETED`, `FAILED`, or `CANCELLED`.

### 14.2. Idempotency Retention and Replay Windows

Purging operation markers before clients or brokers stop retrying allows old operations to run again. Retention must cover:
- HTTP client retry windows.
- Broker retention, redelivery, and DLQ replay windows.
- Serverless retry horizons.
- Manual job replays.
- Audit and data-deletion rules.

Business uniqueness protects longer than delivery markers, yet must still distinguish creates from valid updates.

### 14.3. Data Deletion and Privacy

State stores can hold personal or sensitive data. Design retention, access controls, encryption, auditing, and deletion per data policy. Caches, backups, event logs, and dead-letter stores fall within retention scope too; deleting a primary row does not automatically purge every copy.

## 15. Schema Evolution and Multiple Running Function Versions

During rolling deployments, old and new instances run side by side against the same state store. Schemas and state rules must remain compatible across transitions.

### 15.1. Distinguish State Version from Schema Version

- **Aggregate version:** change sequence number on an order or account.
- **Schema version:** structure of serialized or stored data.
- **Function version:** revision of deployed business logic code.
- **Event version:** contract version of messages/events.

Never overload one `version` field for all four purposes. Aggregate version governs concurrency/ordering; schema version governs reading older records; event version governs producer/consumer compatibility.

### 15.2. Expand-Migrate-Contract

A safe migration typically proceeds in three phases:

~~~text
EXPAND
  Add new fields/tables/indexes so old code still works
       |
       v
MIGRATE
  Deploy code reading both old and new schemas
  Backfill data and observe
       |
       v
CONTRACT
  Drop old fields only after no old instances/consumers remain
~~~

Never deploy new code requiring a mandatory field before every old instance stops writing the old schema. During rolling deploys, ensure bidirectional read/write compatibility across the transition window.

### 15.3. Never Use Arbitrary Java Serialization as a Durable Format

Java object serialization tightly couples stored state to classes and creates compatibility and security risks. For durable state, prefer explicit schemas such as versioned JSON, Avro/Protobuf, or relational columns; validate inputs and manage migrations/upcasters.

### 15.4. Enums and New Fields Need Fallback Strategies

If a new Function version adds status `REFUND_PENDING`, older instances may fail to parse the unknown enum. Roll out compatibly, quarantine unknown events/states safely, or defer emitting new values until older consumers have upgraded.

Never map unknown states silently to `NEW` or a default value; doing so can corrupt workflow transitions.

### 15.5. Snapshots and Projections Must Be Versioned

When using event sourcing or materialized views, snapshots and projections need their own schema versions. When projection logic changes, rebuild or upcast intentionally—never mix old-version snapshots with new events without checking compatibility.

## 16. Local Caches, Warm Instances, and Reference Data

Local caches remain valuable when clearly separated from the source of truth.

### 16.1. When Local Caching Fits

- Slowly changing reference data that can be reloaded.
- Lookups tolerant of brief staleness.
- Bounded cache size and TTL.
- Cache misses fall back to the source of truth.
- Each instance warms up independently without breaking correctness.

Examples: country codes, public catalog metadata, version-immutable mapping tables.

### 16.2. Never Treat Warm Instances as Persistence

Serverless platforms may keep instances warm temporarily, yet can reclaim them at any moment. Warm caches only improve latency; a cold invocation on a new instance must yield identical business results.

### 16.3. Cache Versions and Refresh

Cache entries should carry a version or `updatedAt` timestamp so staleness is observable. Refresh via TTL, invalidation events, or version checks. If refresh fails, decide whether serving stale data is safe based on business rules—failing open on permissions or balances is usually unsafe.

### 16.4. Avoid Caching Shared Mutable Objects

If a cache returns the same mutable object to multiple threads, callers can mutate it and corrupt data seen by other invocations. Use immutable DTOs/value objects or copy on return.

## 17. Consistency, Availability, and State Store Outages

The state store is a critical dependency. When it slows down or disconnects, Functions need defined behavior instead of falling back to local mutable memory.

### 17.1. Never Fall Back to Local State "Just to Keep Going"

If the database is unreachable, buffering state temporarily in each instance's `HashMap` produces split-brain state branches that cannot be merged reliably. When the database recovers, conflicting records make it impossible to tell which state is authoritative.

Depending on business rules, you can:
- Fail fast and let the adapter retry or route to DLQ.
- Enqueue commands into a designed durable queue/outbox.
- Serve degraded read-only responses from TTL-bounded caches.
- Return a pending state and reconcile once the store recovers.

Never treat local memory as an equivalent substitute.

### 17.2. Read Replicas and Consistency Lag

Read replicas can lag behind the primary. Reading immediately from a replica after writing state can observe stale values. For read-your-writes consistency, read from the primary or use version/consistency tokens.

Never base critical state transitions on potentially stale replica reads.

### 17.3. Caches and Stores Under Failover

Distributed caches and databases can fail over with brief unavailability or partial write loss depending on durability configuration. Define:
- RPO and RTO.
- Persistence and replication policies.
- Write acknowledgement levels.
- Behavior during leader changes.
- Recovery and reconciliation procedures.
- Regular backup and restore drills.

"Shared" does not automatically mean "durable"; "replicated" does not automatically mean "zero data loss."

### 17.4. Fail Closed or Fail Open?

| What State Controls | Typical Behavior When Store Fails |
|---|---|
| Authorization / tenant access | Fail closed |
| Balances / quotas / payments | Never decide using stale cache |
| Display catalog | May serve stale cache within limits |
| Non-critical metric counters | May drop or aggregate later |
| Workflow progress | Keep pending, retry/reconcile |
| Idempotency records | Do not run side effects if checks cannot execute safely |

These are business and risk decisions, not built-in Spring Cloud Function defaults.

## 18. Testing Shared State Across Multiple Invocations

Unit testing one Function proves logic only within a single invocation. Proving shared state works requires tests against real storage and multiple execution paths.

### 18.1. Recommended Test Matrix

| Scenario | Setup | Expected Outcome |
|---|---|---|
| Two sequential invocations | Same state key, different operation IDs | Second reads state written by first |
| Resend same operation | Same tenant and operation ID | Returns prior result, no second update |
| Same operation ID, different command | Changed delta / counter ID | Conflict, state unchanged |
| Two concurrent operations | Two calls on same counter, distinct operation IDs | No lost updates |
| Two instances | Two application contexts sharing one DB | Both observe committed state |
| Instance restart | Write, then start a fresh process | Reads persisted state from storage |
| Tenants sharing aggregate ID | Two tenants with same counter ID | State remains isolated |
| Late stale event | Lower version than current state | Version never moves backward |
| Stale cache | Skip invalidation intentionally | Behavior follows stale policy |
| State store unavailable | Disconnect storage | Fails/degrades per policy, no ad-hoc local fallback |
| TTL / cleanup | Expire caches/sessions/jobs | Deletes only eligible state |
| Schema rollout | New code reads old-schema records | Migration/upcasting works |

### 18.2. Concurrency Tests Must Use Distinct Operation IDs

When testing counters, give each concurrent invocation its own operation ID to simulate distinct commands. The final value must equal the sum of committed deltas. Then run another pass reusing an operation ID to verify replays do not increment again.

A test calling the same operation ID repeatedly tests mostly idempotency, not lost updates across independent operations.

### 18.3. One JVM Does Not Prove Multi-Instance Behavior

Running multiple threads inside one Spring context tests thread safety and database atomicity. To test cross-instance state, start two separate application contexts/processes pointing to the same test database/cache; write via instance A, then read/update via instance B.

Tests must not share an in-memory singleton fake, which masks missing production storage wiring.

### 18.4. Testing Restarts and Cold Starts

Write state, stop instance A, launch a new instance B, and read state back. For serverless, simulate cold invocations in a fresh runtime or run adapter tests in a new process. If state disappears, it was stuck in local memory.

### 18.5. Testing Races and Invariants

Do not assert only the absence of exceptions. Verify invariants:
- Counter equals the sum of accepted deltas.
- Each operation ID produces a single outcome.
- One tenant cannot read another tenant's state.
- Aggregate versions only increase, never decrease.
- State transitions never skip required steps.
- Duplicate events produce no additional side effects.
- Stale caches are never used for decisions requiring strong consistency.

## 19. Testing FunctionCatalog and Adapters

Look up Functions by name in integration tests:

~~~java
@SpringBootTest
class CounterFunctionIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void functionUsesSharedStateStore() {
        Function<IncrementCommand, CounterSnapshot> increment =
                catalog.lookup("incrementCounter");

        assertNotNull(increment);

        IncrementCommand first =
                new IncrementCommand("op-100", "daily", 1);
        IncrementCommand replay =
                new IncrementCommand("op-100", "daily", 1);

        CounterSnapshot created = increment.apply(first);
        CounterSnapshot repeated = increment.apply(replay);

        assertEquals(created, repeated);
    }
}
~~~

This is a test skeleton; add JUnit / Spring Boot Test imports, `java.util.function.Function`, and `org.springframework.cloud.function.context.FunctionCatalog`. Test tenant identity, the `CommandFingerprint` bean, and database fixtures are provided by test configuration. If `FunctionCatalog` returns null, check bean registration, function names, and context setup before blaming storage.

### 19.1. Testing Over HTTP and Messaging

The same application service can be invoked through HTTP function adapters and Stream binders. Verify:
- Resending an HTTP request with the same operation ID returns the stored result.
- Message redeliveries do not apply state updates twice.
- Tenant context maps accurately from each adapter.
- Headers and correlation metadata follow contracts.
- Adapters do not swallow exceptions or ACK prematurely.

In-memory test binders do not replace real-broker integration tests when verifying partitions, redeliveries, visibility, or consumer concurrency.

### 19.2. Testing Two Coexisting Function Versions

For rolling deployments, run a writer on the old code version and a reader on the new version (and vice versa if needed). Verify new schemas, enums, and events do not crash old instances or write unreadable state.

## 20. Observability for Shared State

Measure both storage performance and invariant health. Suggested metrics:

| Metric | Meaning |
|---|---|
| `state_read_total` / `state_write_total` | Read/write throughput |
| `state_store_latency` | Storage latency |
| `state_store_error_total` | Store access errors |
| `state_conflict_total` | Version or operation-key conflicts |
| `optimistic_lock_retry_total` | Retries caused by version conflicts |
| `operation_duplicate_total` | Recognized operation replays |
| `cache_hit_ratio` / `cache_miss_total` | Cache effectiveness |
| `cache_stale_read_total` | Stale reads when observable |
| `state_version_gap_total` | Out-of-order events/versions |
| `state_migration_failure_total` | Migration/upcast failures |
| `state_key_count` | Aggregated cardinality per type/tenant |
| `state_expired_total` | Expired/cleaned-up state count |

Metric names are application suggestions, not built-in Spring Cloud Function defaults.

### 20.1. Log Context Without Leaking Sensitive State

Logs should record authorized tenant ID, aggregate ID, operation ID, state version, function name, adapter, outcome, and trace ID. Never log full payloads, tokens, balances, or personal data purely for debugging convenience.

### 20.2. Monitor Conflicts and Hot Keys

A heavily updated aggregate can create hot rows or lock contention. Watch optimistic conflicts, lock waits, Redis command latencies, and concurrent invocations on the same key. Consider partitioning, sharding, or redesigning aggregate boundaries if bottlenecks persist—never disable version checks for throughput.

### 20.3. Distinguish Normal Duplicates from State Corruption

Replaying an operation with a matching fingerprint can be normal. Same operation ID with a different command, decreasing versions, or invalid state transitions signal problems needing investigation. Metrics and logs must clearly separate these outcomes.

## 21. Common Design Mistakes

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Mutable field in a Function singleton | Thread race conditions | Keep only immutable config; put state in a store |
| `static` as source of truth | Other instances miss it; lost on restart | Database / distributed store |
| `AtomicLong` as system-wide ID | Atomic only in one JVM | DB sequences / UUID / ULID |
| `ConcurrentHashMap` for business state | No durability, no cross-instance sharing | Durable storage |
| Non-atomic read-modify-write | Lost updates | Atomic SQL, versions/CAS, or locks |
| Cache as sole source of truth | Eviction/failover loses state | Separate source of truth |
| Relying on sticky sessions | Restarts lose sessions | Shared session store |
| Trusting tenant from message payload | Cross-tenant access risk | Derive/verify tenant from principal |
| Using correlation ID as idempotency key | Retries with new trace IDs run as new ops | Stable operation ID |
| Deduplicating only by event ID | Producers emit fresh IDs for same action | Business keys / versions |
| Skipping event version checks | Stale events overwrite newer state | Version guards / state transitions |
| TTL deletes active running jobs | Workflows lose state | State-aware cleanup |
| Fire-and-forget cache invalidation | Prolonged stale reads | Outbox/events/versions/TTLs |
| Long-lived Java object serialization | Brittle migrations and compatibility | Explicit versioned schemas |
| Local fallback when DB fails | Divergent state branches cannot merge | Intentional fail/degrade policy |
| Distributed locks without leases/fencing | Expired lock lets stale worker write | Leases + fencing / conditional updates |

### 21.1. Anti-Pattern: Treating a Thread-Safe Cache as Distributed State

A local cache may be thread-safe yet still exists inside a single process. Once replicas scale out, each instance holds a different cache. Thread-safe does not imply cross-instance consistent.

### 21.2. Anti-Pattern: Updating State by Overwriting the Whole Object

If a client reads aggregate version 5 and sends back the entire object to overwrite while another invocation already committed version 6, the newer changes get clobbered. Use version checks or conditional updates, applying only valid commands against the latest state.

### 21.3. Anti-Pattern: Auto-Initializing Missing State Silently

Assuming missing state means `NEW` can hide wrong tenant/key errors, deleted records, or replica lag. Distinguish "never existed" from "unreadable" and "not yet replicated"; initialize state only when the business command explicitly allows creation.

## 22. Pre-Production Checklist

### 22.1. State Modeling

- [ ] Classified invocation data, intermediate data, caches, and durable state.
- [ ] Every aggregate/workflow has an explicit owner and transition rules.
- [ ] Source of truth is clearly chosen.
- [ ] No bean fields or `static` variables hold shared cross-instance state.
- [ ] Tenant, aggregate, operation, and version keys are well-designed.
- [ ] Identity and authorization are verified independently of keys.

### 22.2. Concurrency and Consistency

- [ ] Read-modify-write replaced with atomic updates, versions, or locks.
- [ ] Retried operations carry idempotency keys and fingerprints.
- [ ] Stale events, gaps, and version conflicts have explicit policies.
- [ ] Cache staleness windows are explicitly accepted.
- [ ] Cache invalidation uses retries/outbox or appropriate TTLs.
- [ ] Read-replica lag cannot corrupt critical decisions.

### 22.3. Lifecycle and Deployment

- [ ] State survives restarts and cold starts.
- [ ] TTLs never delete non-terminal workflows.
- [ ] Retention covers retries, replays, and audits.
- [ ] Schema/event versions support rolling deployments.
- [ ] Backup/restore and recovery drills exist.
- [ ] Outage behavior follows explicit fail/degrade policies rather than ad-hoc local fallbacks.

### 22.4. Testing and Operations

- [ ] Tested multiple concurrent threads on the same key.
- [ ] Tested two instances/processes sharing storage.
- [ ] Tested restarts and cold starts.
- [ ] Tested tenant isolation and duplicate operations.
- [ ] Tested stale caches, out-of-order events, and schema migrations.
- [ ] Metrics track latency, conflicts, duplicates, stale cache reads, and store errors.
- [ ] Logs include operation/aggregate/version without leaking sensitive payloads.

## 23. Practice Exercises

**Exercise 1 — Function Singleton.** A Function bean holds a `HashMap` in a field to remember user results. List three problems when scaling out and handling concurrent traffic.

**Exercise 2 — AtomicLong.** Why does `AtomicLong` prevent thread races yet fail to provide a durable sequence across multiple pods?

**Exercise 3 — Source of Truth.** A system uses PostgreSQL and a Redis cache. Which holds authoritative order status? What happens if Redis is flushed?

**Exercise 4 — Lost Updates.** Two invocations both read counter 10 and write 11. Propose atomic SQL or CAS so the result becomes 12.

**Exercise 5 — Idempotency.** An increment command resends after a timeout. Why can an atomic increment still add twice? What operation key and transaction are needed?

**Exercise 6 — Tenant Keys.** Two tenants share the same `orderId`. Design the key and explain why authorization must still be checked separately.

**Exercise 7 — Versions.** Event version 4 arrives after state is already at version 5. How should the consumer respond?

**Exercise 8 — State Transitions.** An order is already `COMPLETED` when an old `RESERVED` event arrives. Why must status never be blindly overwritten from payload?

**Exercise 9 — Cache Invalidation.** A DB update commits, then the process crashes before deleting the cache entry. Give two ways to shrink the stale window.

**Exercise 10 — Cache Stampedes.** 100 invocations simultaneously miss an expired TTL key. What happens, and how can load be mitigated?

**Exercise 11 — HTTP Sessions.** Why is in-memory session state on one web instance unsuitable when a load balancer routes requests across instances?

**Exercise 12 — JWTs.** Why can stateless JWTs not enforce immediate revocation on their own?

**Exercise 13 — Reactor Context.** Why can using `ThreadLocal` to carry tenant ID fail when a pipeline switches schedulers?

**Exercise 14 — Serverless.** The first invocation writes state to a `static` map; the next invocation runs on a cold instance. What happens? How should it be redesigned?

**Exercise 15 — TTLs.** A `PROCESSING` job has a 15-minute TTL yet can run for 40 minutes. What is the risk and the fix?

**Exercise 16 — Rolling Deployments.** New code adds an enum state that old code does not recognize. Propose a rollout/schema-compatibility sequence.

**Exercise 17 — Concurrency Tests.** Design a test where multiple distinct operation IDs increment one counter concurrently. Which assertion proves no updates were lost?

**Exercise 18 — Multi-Instance Tests.** Why do multiple threads inside a single Spring context not prove state is shared across two instances?

**Exercise 19 — Store Unavailable.** When the DB disconnects, why should you not buffer writes in a local map to sync later without a proper protocol?

**Exercise 20 — Observability.** List metrics/logs distinguishing valid duplicates, optimistic conflicts, stale cache reads, and state version gaps.

### Suggested Answers

- **Exercise 1:** `HashMap` is not thread-safe, state lives only on one instance, and restarts/scale-downs lose data.
- **Exercise 2:** `AtomicLong` synchronizes only one JVM object; other pods hold separate objects and restarts reset values.
- **Exercise 3:** PostgreSQL holds the source of truth; flushing Redis triggers cache misses that repopulate from the DB.
- **Exercise 4:** A single atomic SQL update/returning statement or optimistic versioning / CAS.
- **Exercise 5:** An atomic update still increments on every call; claim an operation key and increment inside the same transaction, saving the result and fingerprint.
- **Exercise 6:** Key combines tenant + order; authorization checks that the principal has access to that tenant/order.
- **Exercise 7:** Ignore if already processed/stale, or route per gap/quarantine policy; never roll versions backward.
- **Exercise 8:** State transitions must validate current state and event; payloads must never overwrite arbitrarily.
- **Exercise 9:** Outbox-published invalidation events after commit, or versioned keys / short TTLs.
- **Exercise 10:** Many requests hit the source of truth at once; use request coalescing, refresh-ahead, jittered TTLs, or leased locks.
- **Exercise 11:** Other instances lack local session memory; use a shared session store.
- **Exercise 12:** Tokens remain valid until expiry without a revocation lookup or version check.
- **Exercise 13:** `ThreadLocal` binds to threads and does not follow reactive subscribers across scheduler hops.
- **Exercise 14:** Static state is lost or unshared; persist durable state outside instances.
- **Exercise 15:** TTL can delete active jobs; apply TTL only after terminal states or use controlled heartbeats/lease extensions.
- **Exercise 16:** Expand schema first, deploy code compatible with old/new, migrate/backfill, and contract only once old instances are gone.
- **Exercise 17:** Run N distinct operation IDs concurrently and assert the counter equals the exact sum of deltas with matching version.
- **Exercise 18:** Threads test only one JVM; launch two separate processes/application contexts sharing one storage instance.
- **Exercise 19:** Two local maps diverge with no merge order; use durable queues/outboxes or explicit fail/degrade policies.
- **Exercise 20:** Track conflict/duplicate/cache-stale/version-gap metrics and log tenant/aggregate/operation/version/outcome.

## 24. Key Takeaways

- An invocation is a single execution; an instance is a reusable or replaceable process.
- Singleton beans, `static` fields, `AtomicLong`, and `ConcurrentHashMap` do not become cross-instance shared state stores.
- Separate transient inputs/context, immutable config, caches, and durable business state.
- Choose a source of truth matching durability and consistency needs; caches are copies with bounded staleness.
- Keys must capture tenant, aggregate, operation, and version; always enforce authorization separately.
- Use atomic updates, unique constraints, optimistic/pessimistic locking, and explicit state transitions for concurrency.
- Operation IDs and fingerprints protect retries; event versions prevent regressing state.
- `FunctionCatalog` and composition organize Functions; application services and repositories manage state.
- HTTP sessions, messaging workflows, and serverless state require storage aligned with each adapter's lifecycle.
- TTLs, schema evolution, cache invalidation, backups, and privacy are integral parts of state lifecycles.
- Test multiple threads, multiple processes, restarts, tenant isolation, and out-of-order events; monitor conflicts, stale cache reads, and state-store latency.





