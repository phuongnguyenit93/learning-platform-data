# Managing State and Choosing Stateless Components

When designing cloud applications, a foundational decision is **where system state (*state*) is stored, who owns it, and how long it lives**. This decision affects how services scale, handle incidents, protect data, manage cost, and operate reliably. Choosing **stateless components** makes many application layers easier to deploy and scale flexibly, but it does not eliminate the need for data management or consistency.

Within the scope of cloud architecture, this lesson connects business requirements with compute, networking, datastore, and deployment model choices. The goal is to understand **when to keep compute stateless, when stateful components are needed, and how to coordinate both** to satisfy reliability, security, performance, cost, and operations under Well-Architected thinking.

## 1. What Is State? Distinguishing Stateless from Stateful

**State** is information that current or future processing results depend on: order data, login sessions, account balances, in-flight job status, counters, processing progress, or temporarily cached data.

A **stateful** component retains or relies on state from prior interactions. A **stateless** component does not require session or task state from a previous request to reside in the memory or local disk of that specific instance in order to handle the next request. Any equivalent instance can handle the same valid request.

Examples:

- An order confirmation API only receives a request, authenticates it, and reads/writes a shared database: **the API instances can be stateless**, while **the overall system remains stateful**.
- An API keeps shopping carts only in server A's RAM: instance A is **stateful with respect to the session**; if the next call hits server B, the cart may not exist.
- Databases storing orders, queues holding pending messages, and object storage storing files: these are components **responsible for maintaining state**.

> **Core rule:** Stateless design does not mean "storing no data." It means **moving state that must persist out of replaceable processing instances** into a storage component or coordination mechanism designed for that requirement.

### Two Meanings of "Stateless" Often Confused

1. **Stateless at the compute layer:** Web/API instances do not depend on their own local state between requests. Another instance can handle the next request if it has access to the same managed source of state.
2. **Stateless at the protocol or interaction style:** Each request carries all necessary context for the server to understand and process it, rather than relying on conversational session state held by the server. Under REST's *stateless* constraint, client session state is sent with each request; merely moving a server-side session from RAM into a shared store **does not automatically make the protocol stateless in the REST sense**.

In cloud practice, the phrase "stateless service" usually describes **the replaceability and horizontal scalability of compute instances**. Always clarify which meaning is intended to avoid misjudging the architecture.

## 2. Identify and Classify State Before Choosing Technology

Different types of state have different lifecycles, criticality, and consistency requirements. Do not push every kind of data into the same store just because it has fast access speed.

| State Type | Examples | Characteristics to Clarify | Typically Suitable Location |
|---|---|---|---|
| **Durable business state** | Orders, payments, inventory, asset ownership | Must never be arbitrarily lost; requires consistency and auditing rules | Transactional database or appropriate durable datastore |
| **User sessions** | Session ID, unplaced cart, temporary login info | Time-to-live, revocation, authorization, multi-device handling | Client-side tokens, shared session store, or database per requirements |
| **Job/workflow state** | Running jobs, import progress, tasks awaiting retry | Must it resume if a worker dies? Can it be processed repeatedly? | Durable queue, job state database, workflow engine |
| **Temporary acceleration state** | Search result caches, recomputable derived data | Can it be lost? How much staleness is tolerable? | In-memory cache or shared cache with TTL and invalidation policy |
| **Short-lived local state** | Per-request local variables, buffers, intermediate data | Does not need to survive past the request; loss on instance death is acceptable | Processing instance RAM |
| **Files and objects** | Images, PDF invoices, exported reports | Durability, permissions, lifecycle, downloads | Object storage or appropriate file storage system |
| **Configuration and secrets** | Feature flags, API keys, database passwords | Sensitive; requires secure distribution, updates, and revocation | Configuration/secret management service; injected at runtime |

For each type, answer: **What is the *source of truth*? Who is permitted to write? Is immediate consistency required? Can the data be lost or recomputed? What are the retention and recovery requirements?**

Example: a cache displaying search results may tolerate data stale by a few seconds; the "seat already booked" state requires strict concurrency rules to prevent two transactions from reserving the same seat. If a cache becomes the sole place holding booking outcomes, cache loss causes business data loss.

## 3. Why Stateless Compute Instances Fit the Cloud Well

Cloud platforms commonly provide load balancing, multiple application replicas, rolling updates, autoscaling, and automatic instance replacement. These mechanisms work effectively when instances **can be created, deleted, or replaced without losing critical state**.

~~~mermaid
flowchart TB
    CLIENT["Users"] --> LB["Load balancer"]
    LB --> API1["API instance A: stateless"]
    LB --> API2["API instance B: stateless"]
    LB --> API3["API instance C: stateless"]
    API1 --> DB[("Database: source of truth")]
    API2 --> DB
    API3 --> DB
    API1 -. "if shared session needed" .-> SESSION[("Shared session store")]
    API2 -.-> SESSION
    API3 -.-> SESSION
~~~

In this design, the first and second requests from the same user can arrive at **two different instances**. All instances share the durable source of data and, if the application uses server-side sessions, access the appropriate shared session store.

Key benefits:

- **Horizontal scaling:** Add replicas when load increases and remove them when load drops without migrating per-host sessions.
- **Recovery:** A failed instance can be replaced by another; in-flight requests may fail, but new requests do not depend on the lost instance's memory.
- **Deployment:** Application versions can roll out gradually via rolling deployment, canary, or blue/green, provided API and data compatibility are preserved.
- **Traffic distribution:** Load balancers can route to any healthy instance rather than pinning users to a fixed host.
- **Operations:** Infrastructure as Code and autoscaling are simpler when disks or per-instance state do not need to be attached or migrated.

However, stateless compute **does not automatically solve database bottlenecks, lost in-flight requests, or logic bugs**. If 20 instances simultaneously open too many database connections, the application can run slower than with 5 instances. You must govern connection pools, traffic rates, timeouts, and the capacity of stateful dependencies.

### What Can Still Reside Locally on an Instance

Request-scoped local variables, short-lived buffers, and fully recomputable caches can remain in RAM. The condition is that **business correctness never depends on a specific value still existing on an old instance**. Local caches can reduce latency but need appropriate TTLs and invalidation; stale data becomes a risk if used to authorize critical actions.

## 4. Managing Session and Identity State

Login sessions are where state most easily ends up in the wrong place. Multiple implementation options exist, each with different trade-offs:

| Option | How It Works | Pros | Limits and Risks |
|---|---|---|---|
| **Session in instance RAM** | Server stores per-user sessions locally | Simple for a single instance | Hard to scale horizontally; sessions lost on restart; requires pinning users to specific hosts |
| **Sticky sessions at load balancer** | Routes a given user to the same instance | Minimizes changes for legacy apps | Skewed load balancing; instance loss still drops sessions; no substitute for durable storage |
| **Shared session store** | Instances read/write sessions in a shared store, client holds session ID | API instances stay replaceable; easy centralized revocation | Adds network/session-store dependency; needs HA, TTL, encryption, access control, and session ID protection |
| **Signed self-contained tokens** | Client sends signed token verified by server | Can authenticate many requests without central session reads | Harder to revoke early; needs short expiry, token protection, claims/audience/issuer checks, and key management |
| **Short-lived tokens + centralized session/refresh state** | Short-lived access tokens; refresh/revocation managed centrally | Balances performance with session control | More components; requires rotation policies and abuse detection |

**Signed tokens are not encrypted tokens.** JWS-formatted JWTs normally have readable payloads; avoid putting unnecessary sensitive data in claims. Servers must verify the signature using trusted algorithms/keys, expiration, issuer, audience, and relevant constraints; never trust a token merely because its payload looks valid.

Using a shared session store keeps **compute instances** decoupled from session affinity, yet the shared store itself is a **stateful component** and must be designed for security, availability, and recovery. Losing the session store may log users out or fail API calls; include this in SLO reviews and dependency maps.

## 5. Having No Local State Does Not Mean Consistency Is Optional

The hardest bugs often appear when multiple instances concurrently modify the same resource. Example: two users book the same open seat at the same time. Both requests may hit different API instances and read "available." If the application simply checks first and writes afterward, both can falsely succeed.

For critical business data, **correctness must be enforced at an authoritative write-control mechanism**, such as transactions, unique constraints, conditional updates, proper locking, or database concurrency control.

Suppose each seat is sold in fixed time slots. A unique constraint on `(seat_id, slot_start)` can protect confirmed bookings if the data model fits:

~~~sql
-- Illustrates a model where each seat allows only one booking per time slot.
CREATE TABLE reservations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    seat_id BIGINT NOT NULL,
    slot_start TIMESTAMP NOT NULL,
    user_id BIGINT NOT NULL,
    UNIQUE (seat_id, slot_start)
);

-- Two instances simultaneously INSERT the same seat and slot:
-- the database allows only one transaction to succeed.
INSERT INTO reservations (seat_id, slot_start, user_id)
VALUES (101, TIMESTAMP '2026-12-01 09:00:00', 17);
~~~

This example assumes discrete slots of fixed duration. If the system allows booking **overlapping time ranges** or has cancellation/hold states, constraints and transactions must match actual business semantics; a simple UNIQUE constraint may be insufficient.

### Idempotency for Operations with Side Effects

A booking request may **succeed in the database while the client receives no response** due to a timeout. Client retries risk creating a second booking unless the API detects duplicate requests.

You can require clients to send a unique `Idempotency-Key` for each creation operation:

~~~http
POST /reservations HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: 57ea43ca-bc46-49a6-8384-2d4903cce997
Content-Type: application/json

{"seatId": 101, "slotStart": "2026-12-01T09:00:00Z"}
~~~

The application stores the key, caller identity, request payload or fingerprint, processing state, and outcome in a **shared store with atomic write guarantees** (typically the database). Valid retries with the same key receive the stored outcome per defined policy; the same key with a different payload must be rejected. Define key scope, retention window, concurrent handling, and in-progress states. Keeping a Map in one API instance's RAM is insufficient because retries may route to another instance.

**Stateless compute** and **idempotent operations** are distinct properties: statelessness governs where state lives between requests; idempotency governs the effect of repeating the same operation. Both usually need to be designed together in distributed applications.

## 6. State in Background Jobs, Queues, and Events

A request may trigger work taking longer than an HTTP timeout: sending notifications, processing images, exporting reports, or syncing data. Never hold the sole copy of progress in an API instance's RAM and hope the instance stays alive until completion.

A common approach is persisting work in a durably backed queue/workflow, letting stateless workers pull jobs and write results to a job-state store.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Stateless API
    participant D as Database
    participant Q as Durable queue
    participant W as Stateless worker

    U->>A: Create order / processing request
    A->>D: Write order and business state
    D-->>A: Transaction succeeded
    A->>Q: Enqueue background work
    A-->>U: Return result or job ID
    Q->>W: Deliver message
    W->>D: Read/write job state
    W-->>Q: Acknowledge after processing
~~~

The diagram illustrates the conceptual flow. **Succeeding on the database write and failing on the queue publish** is a gap that must be handled. If the business requires guaranteeing an event is eventually emitted for every committed transaction, use a **transactional outbox**: write the business record and an outbox record in the same transaction, then have a relay process publish outbox records to the queue and mark them sent. The relay may retry, so consumers must still handle duplicate messages.

Key requirements for workers:

1. **Acknowledge at the right time:** Only ack a message after required outputs are persisted; if a worker dies before acking, the message can be redelivered.
2. **Idempotent consumers:** Use event IDs or business keys to avoid repeating side effects.
3. **Bounded retries:** Use backoff, jitter, and dead-letter queues where appropriate so permanent errors do not clog the system.
4. **Prevent overload:** Bound concurrency, enforce backpressure, and monitor queue depth and message age.
5. **Intentional progress persistence:** Long tasks that cannot restart from scratch must checkpoint externally; each checkpoint needs consistency rules.

Managed queues reduce broker operations, but the application team must still decide processing order, retention, delivery semantics (e.g., *at-least-once*), deduplication, and recovery when integrations fail. Never assume every queue delivers exactly once in all scenarios.

## 7. Choosing the Right Stateful Component for Each Data Type

Moving state out of compute does not mean dumping all data into a single Redis instance or database. Choose based on **durability, consistency, access patterns, latency, and cost**:

| Need | Common Options | What to Verify |
|---|---|---|
| Booking/payment transactions | Relational database with transactions and constraints | Isolation, concurrent writes, HA, backup/restore, RTO/RPO |
| Login sessions with TTL | Shared session store or appropriate token/auth system | Revocation, token security, session store dependency |
| Query caching | Managed cache or local cache with TTL | Cache misses, stale data, invalidation, memory pressure |
| Long-running job state | Durable queue + job-tracking DB, or workflow engine | Retries, checkpointing, durability, idempotency, observability |
| Images, large files, generated docs | Object storage | Access permissions, lifecycle, versioning, retention, encryption |
| Replayable event data | Event log/stream or appropriate event store | Ordering within supported partitions, retention, offsets, replayability |
| Per-instance state genuinely needing durability | Persistent volumes and stateful workload orchestrator | Identity, volume attachment, backup schedule, failover, upgrade management |

### Managed Services and Responsibility Boundaries

Using managed databases, managed caches, or managed queues reduces infrastructure management, patching, and node replacement work. However, the provider does not automatically guarantee schema correctness, application transactions, TTLs, retry policies, authorization, or RPO matching business expectations. For example, a managed cache with replication can still lose recent writes under certain failover modes; therefore, **never treat a cache as the source of truth** if the service's durability contract does not fit.

When deploying stateful workloads on Kubernetes, distinguish:

- **Deployment** generally suits **replaceable** application replicas; restarting a pod must not lose critical data.
- **StatefulSet** provides **stable identities** and coordinates stable storage for stateful pods; on its own, it **does not create database replication, backups, or consistency**.
- **PersistentVolume** lets data outlive a single pod within storage capabilities, but does not replace backup, multi-zone, or disaster recovery policies.

A stateful application does not necessarily have to run inside Kubernetes. If a managed database meets requirements, you can avoid operating a self-managed database cluster, depending on technical and cost constraints.

## 8. Sample Application: Booking Platform with Stateless Compute

Suppose a booking system must satisfy these requirements:

- Users can sign in and book from multiple devices.
- Each time slot can have at most one confirmed booking for the same resource.
- Peak-hour traffic surges multiple times higher than baseline.
- An API instance or an availability zone may fail while confirmed booking data remains protected within the designed RPO.
- Confirmation emails can be sent afterward; email failures must not corrupt booking writes.

Illustrative design:

~~~mermaid
flowchart TB
    U["Web / Mobile"] --> EDGE["DNS, CDN, edge protection"]
    EDGE --> LB["Load balancer"]
    subgraph NET["Private network on cloud platform"]
        LB --> API1["Booking API 1 - stateless"]
        LB --> API2["Booking API 2 - stateless"]
        API1 --> DB[("Transactional database - stateful")]
        API2 --> DB
        API1 -. "depending on session model" .-> S[("Shared session store - stateful")]
        API2 -.-> S
        API1 -. "cacheable queries" .-> C[("Cache - recomputable data")]
        API2 -.-> C
        DB --> OUT["Outbox publisher"]
        OUT --> Q[("Durable queue - stateful")]
        Q --> W1["Notification worker A - stateless"]
        Q --> W2["Notification worker B - stateless"]
    end
~~~

**State partitioning by role:**

1. **Stateless APIs:** Never hold sole copies of carts or confirmed orders in RAM. Authenticate and authorize every request; write data via transactions against the source of truth.
2. **Stateful database:** Serves as the booking source of truth; enforces concurrency controls properly, with backup and recovery policies.
3. **Session store if needed:** Holds only session metadata appropriate for TTLs; never replaces the business database.
4. **Cache:** Speeds up read queries that tolerate stale data; never uses cache state to enforce exclusive resource ownership.
5. **Queue and workers:** Decouples notification processing; supports retries, duplicate prevention, and backlog visibility.

**Booking request path:** Client sends a request with an operation identifier → load balancer picks any healthy API instance → API authenticates and executes a transaction enforcing double-booking protection → writes outbox in the same transaction if guaranteed event emission is required → returns response → publisher relays the event to the queue → worker sends notification. If the API instance dies after transaction commit but before returning the response, retrying with the same idempotency key lets the client retrieve the prior outcome without creating duplicate side effects.

Note: **Scaling the API from 2 to 20 instances does not mean database write throughput increases 10x.** You must measure transactions/sec, p95 latency, connections, lock contention, and service limits. If the database is the bottleneck, optimize queries/indexes, connection pooling, controlled read-write splitting, or data modeling when genuinely needed, instead of merely adding API replicas.

## 9. Key Trade-Offs: Reliability, Security, Scalability, Cost, Operations

| Dimension | Benefit of Stateless Compute | Risks / Costs to Plan For | How to Verify |
|---|---|---|---|
| **Reliability** | Failed instances are easily replaced; load spreads across instances/AZs | Shared database/session store/queue becomes a critical dependency | Kill an instance, fail over state stores, test backup/restore |
| **Security** | Instances hold little persistent data; access permissions can be standardized | Stolen tokens, exposed session stores, overly broad DB permissions | Threat modeling, least-privilege IAM, encryption, audit logs, test session revocation |
| **Scalability** | Fast, flexible horizontal scaling of APIs/workers | Database connections, lock contention, cache stampedes, quotas | Load test across concurrency levels, p95/p99, error rates, saturation |
| **Performance** | Easy to place compute near load and balance traffic | Every state access may incur a network hop | Profile DB/cache call times; measure cache hit ratios and real latency |
| **Cost** | Can scale to demand and trim idle compute | Managed services, network traffic, caches, storage, backups, and logs incur fees | Estimate at low/average/peak loads; measure cost/request |
| **Operations** | Smooth compute rollouts and self-healing | Operating distributed systems, multi-hop tracing, data migrations | Cross-service traces, SLO dashboards, runbooks, and incident drills |

The **stateless API + stateful storage** pattern does not automatically deliver high availability. If the database is a single point of failure, that foundational component can bring down the entire feature set even with many API replicas. Define availability targets, **RTO** (maximum recovery time), and **RPO** (maximum acceptable data loss) for business functions, then configure and test HA/DR accordingly. Backups do not replace HA, and replication does not replace backups against accidental deletion or data corruption.

### Essential Operational Engineering Practices

- **Graceful shutdown/draining:** When scaling in or deploying, stop accepting new requests and allow in-flight requests to finish within a bounded timeout; workers must handle ack/retry rules cleanly on shutdown.
- **Readiness and health checks:** Route traffic only to ready instances; avoid misconfigured health checks that mark every instance unhealthy simultaneously when a temporary external dependency blips.
- **Connection pools and timeouts:** Bound database connections; apply timeouts, conditional retries, exponential backoff, and jitter to prevent amplifying incidents.
- **Observability:** Track request IDs/trace IDs, p95 latency, error rates, DB connections, lock waits, cache hit ratios, queue depth, and duplicate-processing rates.
- **Configuration and secrets:** Inject configuration via environment-appropriate mechanisms, store secrets securely, restrict access, and enforce rotation procedures.
- **Data and schemas:** Use compatible migrations while multiple API versions run concurrently; rolling back code does not guarantee rolling back data.

## 10. Principles for Choosing Stateless vs. Stateful per Component

Not every component should be forced into statelessness. A selection workflow can walk through six questions:

1. **Is the state critical business data?** If yes, design the source of truth, transactions, auditing, and recovery plans first.
2. **Must the state outlive a single request or instance?** If yes, never keep the sole copy in compute RAM or ephemeral local disk.
3. **What are the consistency and concurrency requirements?** If multiple instances can write the same resource, synchronization is required at the data source level.
4. **Can the state be recomputed from another source?** If yes, caching with acceptable loss thresholds works; if no, ensure matching durability.
5. **Is a fixed instance identity or storage binding genuinely required?** If truly required (e.g., self-managed data system nodes), consider a stateful model with stable identities/volumes; budget for harder operations.
6. **Do managed service capabilities and total cost fit?** Compare service fees, operational effort, features, limits, security, and provider lock-in risks.

~~~mermaid
flowchart TD
    A["Does a component need to hold info?"] --> B{"Must info survive past request/instance?"}
    B -- "No" --> C["Process locally/temporarily; instance can be stateless"]
    B -- "Yes" --> D{"Can it be recomputed, temporary loss acceptable?"}
    D -- "Yes" --> E["Cache with appropriate TTL and invalidation"]
    D -- "No" --> F{"Requires transactions / strong consistency rules?"}
    F -- "Yes" --> G["Durable datastore with transactions/constraints"]
    F -- "No / business-dependent" --> H["Choose object store, queue, event log, session store, or suitable store"]
    E --> I["Compute accesses state via clear contracts"]
    G --> I
    H --> I
~~~

This is a **directional decision tree**, not an automated service-selection algorithm. Many problems use more than one store: a database as source of truth, a cache for fast reads, and a queue for background processing. The goal is clear data boundaries and responsibilities.

## 11. Common Design Mistakes

**Mistake 1 — Storing shopping carts only in RAM while enabling autoscaling.** When users route to another instance, their carts vanish. Fix by storing carts in an appropriate shared store or designing properly verified and synchronized client-side state; sticky sessions are only a temporary stopgap with clear limits.

**Mistake 2 — Using a cache as the primary database for critical transactions.** Caches can evict keys, expire via TTL, or lose data during failover. Fix with a durable source of truth and cache-aside/refresh/invalidation rules matching required consistency.

**Mistake 3 — Assuming a stateless API needs no concurrency control.** Two instances can still read the same data and write conflicting updates. Fix with transactions, constraints, and write controls at the component owning the state.

**Mistake 4 — Retrying every request without idempotency.** Timeouts can happen after business logic committed, causing retries to charge or book twice. Fix with appropriate business/idempotency keys, atomic processing state, and error-specific retry policies.

**Mistake 5 — Monitoring only API CPU.** CPU stays low while the database hits connection, lock, or IOPS limits. Fix with end-to-end measurement and monitoring of stateful dependencies.

**Mistake 6 — Using a StatefulSet and assuming the database is HA.** StatefulSet provides stable pod identities, whereas replication/consistency/backup/failover must be handled by the data system and operational design.

**Mistake 7 — Putting all data into JWTs to avoid database calls.** JWTs bloat in size, are hard to revoke, and may carry sensitive data or stale permissions. Limit claims, protect tokens, set appropriate expirations, and re-verify state/authorization for sensitive operations when required.

## 12. Evaluation Under Well-Architected Thinking

Treat state architecture as a chain of **evidence-backed decisions**, not just labels like "stateless" or "managed."

| Evaluation Pillar | Questions for State Design | Required Evidence |
|---|---|---|
| Operational Excellence | Can we tell what state a request/job is in and how to recover after failure? | Traces, logs, job states, runbooks, rollback and migration procedures |
| Security | Where does state reside, who reads/writes it, how are tokens/secrets stored and revoked? | IAM, encryption, data authorization, audits, session revocation tests |
| Reliability | What happens if an instance, cache, AZ, or primary database fails? | Fault injection, failover/restore drills, measured RTO/RPO and data loss |
| Performance Efficiency | Do stateless compute replicas still hit target p95 when the state store is under heavy load? | Load tests, connection counts, locks, cache hits, database metrics |
| Cost Optimization | How do session store/cache/backup and network costs grow with users? | Forecasts, cost allocation, usage metrics, configuration reviews |
| Sustainability | Are idle resources eliminated and is data purged past required retention? | Sensible autoscaling, TTLs, lifecycles, right-sizing |

For instance, a design target might be **API p95 under 400 ms at 1,000 requests/second** and **maximum RPO of 5 minutes** for a dataset. These are **practice assumptions only**; real targets must reflect business impact and budget. To verify, measure under high load and test recovery using the chosen methods. A diagram showing two APIs and a managed database proves none of those numbers on its own.

## 13. Hands-On Exercise: Refactoring a Locally Stateful Architecture

A ticketing system currently has three API servers behind a load balancer. Each server keeps sessions and carts in RAM; ticket availability is checked via cache before writing to the database; confirmation emails are sent synchronously within the request. When a fourth server is added, some users lose their carts. When the email provider slows down, ticket purchases frequently time out. When two customers select the same seat simultaneously, duplicate confirmations occasionally occur.

**Requirement:** Propose modifications so the system scales with traffic, protects business data, and supports fault testing.

One approach:

1. **Classify state:** Sessions and carts must survive across requests; sold tickets are durable business data; caches accelerate reads only; email is a background task.
2. **Make API instances stateless:** Move sessions/carts to a shared mechanism or design appropriate client-side tokens and state; ensure any request can land on any instance.
3. **Return consistency to the source of truth:** Use transactions and constraints to prevent double-selling seats; caches never adjudicate ticket confirmation.
4. **Decouple email:** Write events via an outbox or equivalent reliable mechanism into a queue; idempotent workers deliver notifications with controlled retries.
5. **Design HA and security:** Review the database, session store, queue, and access permissions; define RTO/RPO; drill losing an instance/session store/database.
6. **Measure before and after:** Test random routing across four instances, load increases, email outages, client retries, two concurrent requests competing for the same seat, and backup recovery.

**Self-check questions:**

- If one API instance is terminated, which data must absolutely not be lost? Which data can be recomputed?
- Why does a shared session store make API instances easier to replace while introducing a new stateful dependency?
- If a client times out after the database commits, how do you verify a retry does not create a second ticket?
- Which metrics should you inspect when adding API instances causes p95 latency to worsen?
- When does self-operating a stateful workload make more sense than a managed service, and what extra responsibilities must the ops team assume?

Good cloud design does not try to make **the entire system** stateless. It pinpoints **which state must persist, its ownership boundaries, and required durability guarantees**, while keeping replaceable processing components *stateless* where appropriate. Consequently, compute, database, cache, queue, and deployment choices serve actual business requirements with measurable trade-offs.
