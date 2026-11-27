# Data Ownership and Contracts Between Services

In a cloud architecture with multiple services, splitting an application into small APIs is not enough to create independent components. The harder question is: **which service has authority to decide business truth, which service is allowed to modify data, and which commitments may other services rely upon?**

For example, a booking platform has Booking, Room Availability, and Payment services. If all three modify booking status inside a shared table, one team's change can easily break another. If each service maintains its own copy of room data without specifying an authoritative source, the system might confirm two bookings for the same room. **Data ownership** resolves decision and update boundaries; **contracts between services** define how parties communicate, interpret data, and behave when changes or incidents occur.

This lesson belongs to the **Application Models** chapter of **CLOUD_ARCHITECTURE**. When designing cloud applications, service boundary decisions directly shape compute, networking, databases, deployment models, reliability, security, scalability, cost, and operations. The content below applies Well-Architected thinking to evaluate those trade-offs.

## 1. Learning objectives

After this lesson, learners can:

1. Distinguish **business data owner**, **authoritative data source**, **read replica/projection**, and **storage infrastructure operator**.
2. Partition service boundaries by business capability and specify who may create, update, cancel, publish, or consume each type of data.
3. Design REST/gRPC or asynchronous event contracts, including structure, semantics, errors, versioning, security, and operational commitments.
4. Explain **eventual consistency**, **idempotency**, **transactional outbox**, and **saga** mechanisms when business flows span multiple services.
5. Choose safe schema-change strategies, compatibility testing, and system observability.
6. Evaluate solutions with Well-Architected principles: reliability, security, operations, performance, cost, and sustainability.

## 2. Understanding data ownership properly

### 2.1. Who owns data in software architecture?

In this lesson, **architectural data ownership** is the assignment of authority to **define rules**, **decide valid states**, **execute mutations**, and **publish information** for a group of business data. It differs from legal ownership of data, data-subject privacy rights, or the legal data processor role.

For example, the Booking team has authority to manage a booking's lifecycle (create, confirm, cancel) according to business rules. That **does not mean** the team independently decides personal data retention periods, customer access rights, or statutory requirements. Privacy and compliance rules must still be enforced throughout.

A system typically involves multiple distinct roles:

| Role | Responsibility | Example |
|---|---|---|
| **Business owner / product team** | Defines data meaning and lifecycle; approves rule changes | Specifies when a booking counts as confirmed |
| **Authoritative service (system of record)** | Enforces validations and valid writes for data in its scope | Booking Service decides booking status |
| **Operations / platform team** | Operates databases, backups, monitoring, IAM, and infrastructure per assigned duties | Cloud team operates a DB cluster for multiple services |
| **Consuming service (consumer)** | Reads data via contracts; handles stale data and missing-data scenarios | Notification Service listens to BookingConfirmed events |
| **Data steward / legal & compliance** | Classification, retention, security, and compliance policies | Specifies retention duration for identity records |

**Key rule:** an important business truth needs **one place responsible for deciding the canonical state**, even when multiple copies exist for reading. This rule does not require every service to have its own dedicated database server; what matters is that write authority is clearly delineated and enforced.

### 2.2. Bounded contexts are a practical starting point

In *Domain-Driven Design (DDD)*, a **bounded context** is a boundary within which business concepts and rules have consistent meaning. These boundaries are usually a solid basis for shaping services, though a bounded context does not have to become an independent deployment process immediately.

Example for a booking system:

| Context | Authoritative Data Source | Data That May Be Replicated Elsewhere for Reads |
|---|---|---|
| **Listing / Catalog** | Property details, descriptions, publication status | Property name and thumbnail in booking history |
| **Availability** | Available time windows, hold rights, capacity limits | Search availability results at query time |
| **Booking** | Booking ID, booker, status, and cancellation rules | Booking list shown on the profile page |
| **Payment** | Payment transactions, authorization/refund states, reconciliation | High-level payment status on the booking screen |
| **Customer Profile** | Profile details and permitted stored preferences | Display name needed in transaction history |

Do not split services merely because nouns differ. Evaluate who changes the rules, how tightly data and transactions couple, independent scaling needs, team operational capacity, and network communication costs.

### 2.3. Separating write authority from read needs

For Booking Service to display a property name, it does not need write access to the listing table. You can:

- Query Catalog via API when the latest information is needed.
- Store a **snapshot** of selected attributes at booking time (such as property name and agreed price) if history must remain fixed to the transaction.
- Maintain a read copy (*read model/projection*) driven by events, complete with update timestamps and rebuild procedures.

Each option has trade-offs: direct API calls add latency/availability coupling; snapshots preserve history without reflecting current edits; projections reduce cross-service query load at the cost of sync lag and operational overhead.

**The canonical source for each attribute must be documented down to the attribute level.** For example, the accepted price in a booking agreement is Booking's truth, whereas the current list price is Catalog/Pricing's truth. Treating both values as identical and syncing unconditionally can corrupt historical transactions.

## 3. Organizing data along service boundaries

### 3.1. Database per service is an access boundary, not just a database name

The *database per service* principle requires each service to hold independent control over its schema or data area; other services use **published contracts** to access data rather than directly querying and writing internal tables.

Isolation levels to choose from:

| Deployment Approach | When It Can Fit | Risks to Manage |
|---|---|---|
| Shared DB server; each service has its own **schema and account** | Small systems, optimizing initial cost | Shared resources and admin privileges can affect neighbors; must restrict cross-schema permissions |
| Each service has its own **logical database** on the same cluster | Clearer schema isolation, connection configs, and permissions | Cluster remains a shared failure domain and performance ceiling |
| Each service has its own **dedicated database or cluster** | Needs independent scaling, backup, restore, and tuning | Higher infrastructure, monitoring, connectivity, and DR costs |

Every option must define who runs migrations, who manages roles/secrets, backup schedules, and recovery procedures. Splitting physical databases does not automatically guarantee independent services if APIs still call each other synchronously in a long chain.

### 3.2. Preventing direct access to another service's data

Anti-patterns to avoid:

~~~text
Booking Service ---SQL UPDATE---> payment.transactions
Booking Service ---SQL SELECT---> availability.holds
Payment Service ---SQL UPDATE---> booking.bookings
~~~

Problems:

1. One service can violate another service's business rules and invariants.
2. The table-owning team struggles to change schemas because it does not know all consumers.
3. A single transaction spanning multiple tables creates deployment coupling and overly broad database permissions.
4. Observability, authorization, auditing, and root-cause investigation become difficult.

A better approach is requiring consumers to call APIs or send commands that the **owner can reject** when business conditions fail, or subscribe to events published by the owner. Use a shared database intentionally within a single application/deployment unit only if module boundaries and change responsibilities are tightly controlled.

### 3.3. Who controls structural changes?

The service owner owns the schema and migrations for the data it manages. When adding columns, splitting tables, or changing storage layouts, internal changes can deploy independently **as long as external contracts remain compatible**. Conversely, sharing a database and querying across schemas turns changing one column into a cross-team change, risking lockstep deployments.

## 4. What is a contract between services?

A **service contract** is the set of commitments a service provider publishes to its consumers. A complete contract covers far more than endpoint paths or JSON schemas:

| Contract Element | What Must Be Clarified | Example |
|---|---|---|
| **Structure** | Endpoints/topics, request/response/event shapes, types, required fields, identifiers | `bookingId` is an immutable identifier string |
| **Semantics** | Field meanings, states, transition rules, invariants | `CONFIRMED` only when hold and payment conditions are met |
| **Failure behavior** | Error codes, timeouts, retries, limits, when an unknown outcome is returned | Timing out does not prove payment failed |
| **Consistency** | Which states are immediately readable vs. eventually synchronized | Search index may lag behind the source |
| **Security and data** | Authentication, authorization, sensitive fields, tenants, retention | Only the owning customer or authorized roles may read |
| **Versioning and change** | Compatibility rules, deprecation, support windows | Do not remove fields while old consumers still depend on them |
| **Operational commitments** | SLOs, load limits, throughput, event retention, alerting | API success rate and p95 latency under defined measurement conditions |
| **Owner and support** | Accountable team, docs, incident contact, change notification process | Booking team approves contract change requests |

A schema can be syntactically valid yet semantically broken. If a provider changes the meaning of an `amount` field from minor currency units to major currency units without changing its name or version, consumers still parse it cleanly yet miscalculate money severely.

## 5. Designing synchronous API contracts

### 5.1. When does synchronous communication fit?

REST/HTTP or gRPC usually fits when the caller needs an immediate result to proceed: checking permissions, fetching current product info, requesting a hold, or querying transaction status. In return, the caller depends on the callee's real-time latency and availability.

When designing, do not just write "Booking calls Availability." Specify:

- What answer does the caller need to make a decision?
- If the connection times out, how do we tell whether the operation executed?
- Is the action **idempotent** when requests repeat?
- What information is returned and who is permitted to see it?
- Is optimistic concurrency protection needed to prevent lost overwrites?

### 5.2. Example booking creation contract

One option is creating a booking asynchronously and letting the client poll status. Sample HTTP request:

~~~http
POST /v1/bookings HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 937e47cf-9886-44fd-9a39-26bdc8072c67

{
  "listingId": "listing_42",
  "checkIn": "2026-12-10",
  "checkOut": "2026-12-12",
  "guestCount": 2
}
~~~

A response when the request has been accepted for processing, but the transaction is not yet complete:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /v1/bookings/booking_913

{
  "bookingId": "booking_913",
  "status": "PENDING",
  "statusUrl": "/v1/bookings/booking_913"
}
~~~

In this example, the system must explicitly specify:

1. The token is authenticated and permission to create a booking is verified server-side; never blindly trust a client-supplied customer ID.
2. Check-out must be after check-in; `guestCount` must satisfy listing policy.
3. The same **Idempotency-Key** within the proper tenant/caller scope and key retention window, with the same payload, returns the same logical outcome instead of creating another booking. Reusing the key with a different payload must return a clearly defined conflict error.
4. `202 Accepted` means **accepted for processing**, not that the booking is confirmed. The client must poll status or receive a valid notification.
5. Identifiers, monetary amounts, time zones, guest limits, and cancellation rules must be defined by policy/schema—never inferred from raw data types alone.

Error codes must be defined consistently, for instance:

| Case | Selectable Contract Behavior |
|---|---|
| Missing or invalid token | HTTP 401; omit sensitive details from errors |
| Authenticated but lacks permission | HTTP 403; do not leak another user's booking details |
| Invalid input data | HTTP 400 or 422 by consistent convention, with business error code |
| Hold conflicts with another booking | HTTP 409 if detected synchronously, or `FAILED` status with reason code if processed asynchronously |
| Transient overload | HTTP 429 or 503, with `Retry-After`/backoff rules |
| Caller timeout | Outcome **unknown**; query by idempotency key or `bookingId` before retrying |

Never let consumers infer "transaction definitely failed" from an HTTP timeout. The request may have committed while the response was lost.

### 5.3. Concurrency contracts

For resources updatable by multiple parties, consider optimistic locking: records carry a `version` or `ETag`, and updates succeed only if the version matches what was read. For example, Availability Service checks and decrements remaining capacity inside its own transaction. This enforces the invariant where data is owned; an earlier availability check in the UI provides only temporary information.

## 6. Asynchronous event contracts

### 6.1. An event is a fact that happened; a command is a request

- **Command**: asks an owner to perform an action (e.g., `ReserveAvailability`). The owner may accept or reject after checking policy.
- **Domain/integration event**: announces a fact that already happened and was published (e.g., `BookingConfirmed`). Consumers may react without altering the outcome that occurred.
- **Query**: asks for information without requesting a state change.

Naming events as **completed facts** helps prevent misunderstandings. A `BookingConfirmationRequested` message must not be treated by consumers as `BookingConfirmed`.

### 6.2. Event envelopes need sufficient context

Example integration event after a booking is confirmed:

~~~json
{
  "eventId": "evt_01JXY99",
  "eventType": "BookingConfirmed",
  "eventVersion": 1,
  "occurredAt": "2026-12-01T09:16:22Z",
  "producer": "booking-service",
  "correlationId": "req_548",
  "tenantId": "tenant_7",
  "data": {
    "bookingId": "booking_913",
    "listingId": "listing_42",
    "checkIn": "2026-12-10",
    "checkOut": "2026-12-12"
  }
}
~~~

The event contract should clearly describe:

- **eventId**: identifies the event and deduplicates within a defined tracking window.
- **eventType + eventVersion**: helps consumers pick the right schema and compatibility rules.
- **occurredAt**: when the business event occurred, not when the consumer received it; use ISO 8601 with explicit timezone.
- **correlationId**: traces execution across multiple services; do not use as the default deduplication key.
- **tenantId**: identifies data scope; consumers must authenticate/authorize based on environment and trusted sources.
- **data**: contains only attributes consumers genuinely need; avoid carrying payment card details, ID documents, or unnecessary personal data.

The contract must also specify **ordering**, **delivery guarantees**, **retention**, **replay** capability, **DLQ** (*dead-letter queue*), schema registry rules, and the maximum expected time for consumers to receive updates. Many message brokers provide *at-least-once* delivery; consumers must tolerate duplicates.

### 6.3. Preventing hidden coupling in events

Events should carry enough context for consumers to complete their intended work without calling back into multiple APIs in a mandatory chain. However, do not turn events into dumps of entire internal tables; that creates coupling and raises data-leak risk. Design **integration events** separately from internal domain events when needed to protect change autonomy and keep contracts stable.

## 7. Consistency and transactions across services

### 7.1. A database transaction does not automatically span services

Within a single service, related writes can use an ACID transaction to guarantee consistency. Yet in an architecture separating Booking, Availability, and Payment into independent owners, updating all of them in a standard ACID transaction is no longer straightforward. Distributed transaction protocols exist in some platforms, but typically introduce coordination overhead, reduced availability risks, and operational coupling.

Instead, design **business workflows with multiple intermediate states**. That is where sagas, idempotency, events, and reconciliation jobs play critical roles.

### 7.2. Room-booking saga example

A viable workflow:

1. Booking creates a **PENDING** record, binding an idempotency key to the request.
2. Booking asks Availability to place a **time-bounded hold**. Availability validates and records the hold inside its own transaction.
3. If the hold succeeds, Booking asks Payment to **authorize payment** with a unique transaction reference.
4. If payment succeeds, Booking coordinates confirming the hold. Once required conditions are verified, Booking transitions to **CONFIRMED** and emits `BookingConfirmed`.
5. If payment failure is confirmed, Booking cancels the workflow and requests releasing the hold. If a step's outcome is unknown due to a timeout, the workflow moves to a state requiring **query/reconciliation**, avoiding prematurely assuming failure.
6. The system handles expired holds, reversals, or refunds based on actual state and business rules, with alerts for cases that cannot self-recover.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking
    participant A as Availability
    participant P as Payment
    participant E as Event Bus
    C->>B: Create booking (Idempotency-Key)
    B->>B: Write PENDING
    B->>A: Hold listing for date range
    A-->>B: holdId / declined
    alt Hold succeeded
        B->>P: Authorize payment (fixed reference)
        P-->>B: Authorized / Declined / Unknown
        alt Payment validly confirmed
            B->>A: Confirm hold
            A-->>B: Confirmed
            B->>B: Write CONFIRMED + Outbox
            B->>E: Publish BookingConfirmed
        else Declined or needs reconciliation
            B->>B: FAILED or RECONCILING
            B->>A: Release hold when safe
        end
    else Hold rejected
        B->>B: FAILED
    end
    C->>B: Check bookingId
    B-->>C: Current status
~~~

This is an illustrative logical diagram. In reality, Payment and Availability states can change between steps; you must define hold-expiration policies, transaction reconciliation, late-event handling, and compensation actions for cases where payment was captured but booking confirmation failed. Never assume compensating steps always succeed immediately.

### 7.3. What gap does a transactional outbox fill?

If Booking Service commits `CONFIRMED` to its database and crashes **before** publishing `BookingConfirmed` to the broker, the data changed while consumers remain unaware. Conversely, publishing the event before committing the database can notify consumers of a state that was never persisted.

A **transactional outbox** writes both the state change and the pending event record **within the same transaction of Booking's database**:

~~~text
BEGIN TRANSACTION
  UPDATE bookings
    SET status = 'CONFIRMED'
    WHERE id = 'booking_913' AND status = 'PENDING';
  INSERT INTO outbox(event_id, type, payload, created_at)
    VALUES ('evt_01JXY99', 'BookingConfirmed', '{...}', NOW());
COMMIT

Outbox publisher / CDC:
  read outbox -> send to broker -> mark published via appropriate mechanism
~~~

The publisher may resend after a crash. Thus, **an outbox alone does not guarantee end-to-end exactly-once processing**; consumers still need deduplication or idempotent handling. For example, Notification Service records processed `eventId` values before sending email or uses the email service's idempotency key; the exact choice depends on how writes and side effects can be coordinated.

### 7.4. Eventual consistency must be part of the contract

If a profile page reads an event-updated projection, immediately after successful payment the data may not yet reflect the new status. UX and consumers must understand the differences between **PENDING**, **CONFIRMED**, **FAILED**, and **RECONCILING**, have a path to read the authoritative source for sensitive actions, and never treat "record not found in read model" as "booking definitely does not exist."

Points to specify:

- Expected synchronization lag and how breaches are detected.
- How duplicate, out-of-order, or late events are handled.
- Rules to rebuild projections from authoritative sources when events are missed.
- Business impact when a consumer temporarily falls behind.

## 8. Evolving contracts without breaking consumers

### 8.1. Compatibility is more than "JSON still parses"

Changes that are **often** compatible:

- Adding an optional field with clear meaning; older consumers are designed to ignore unknown fields.
- Adding a new endpoint without altering existing endpoint behavior.
- Adding a new independent event type without altering old event semantics.

Changes that **typically break** contracts:

- Removing or renaming a field consumers use; changing types or currency units.
- Turning an optional field into required, or changing null/default semantics.
- Changing state meanings or adding enum values when consumers handle closed enum lists.
- Changing ordering/delivery guarantees, dropping retention, or tightening load limits beyond current assumptions.
- Switching an operation from synchronous success to asynchronous `202` without a migration protocol.

Even "adding a field" can break a consumer whose parser is configured to reject unknown properties. Compatibility depends on the **actual behavior of producers and consumers**, not a blanket rule.

### 8.2. Expand–migrate–contract

A safe procedure for migrating from `totalAmount` to `amountMinor` is:

1. **Expand:** provider publishes the new field, retains the old field, and documents exact units and rounding rules.
2. **Migrate:** consumers gradually move to the new field; run in parallel and verify outputs with tests.
3. **Observe:** measure usage of the old field, monitor errors, and verify relevant consumers have upgraded.
4. **Contract:** announce a deadline, retire the old field per the agreed deprecation policy, and only then remove it.

For events already sitting on a broker or in a replay archive, decide how many versions consumers must read and how long schemas remain retained. Sometimes a new event type/version is needed rather than keeping the same event with altered semantics.

### 8.3. Contract testing

Complementary testing layers:

| Test | What It Verifies | Responsibility |
|---|---|---|
| Schema / OpenAPI / AsyncAPI validation | Fields, types, formats, versions match the specification | Provider publishes and CI validates |
| **Consumer-driven contract test** | Provider still satisfies declared concrete consumer expectations | Consumers publish expectations; provider runs verification |
| Integration test with real or equivalent dependencies | Timeouts, auth, broker failures, status mapping | Integration, platform, and service owner teams |
| Business end-to-end | Booking creation/cancellation journey works across services | Product team owning the flow |
| Chaos / failover / replay test | System recovers from dropped messages, duplicates, network faults, replication lag | Operations team partnering with owners |

Contract tests catch interface mismatches, but **do not replace business-logic, reliability, and security testing**.

### 8.4. Contract lifecycle governance

Maintain a versioned registry or documentation repository, clear owners, review workflows, deprecation notice periods, and visibility into active consumers. For public APIs or APIs with many dependent teams, document compatibility policies and support windows explicitly to avoid forcing every team to deploy at the same hour.

## 9. Security, privacy, and cross-service data responsibility

### 9.1. Every communication hop is a trust boundary

Even when services run inside the same VPC/cluster, they must not implicitly trust every request. You need to:

- Authenticate calling service identities, such as workload identity, mTLS, or tokens with proper issuer, audience, and expiration.
- Enforce **authorization where business logic executes**, including resource-level and tenant-level checks.
- Apply least privilege to database roles, topic publish/subscribe permissions, secrets, and service accounts.
- Encrypt traffic in transit; never write tokens, card data, or sensitive personal data into logs.
- Restrict event subscription permissions by need-to-know and classify payloads before publishing to a broker.
- Audit critical data access, including administrative actions and data deletion requests.

For example, Booking Service may call Customer Profile for confirmation info, but should not receive the entire profile and identity documents just because it needs a display name. Events broadcast to many consumers require even stricter minimization of sensitive payload fields.

### 9.2. Data ownership does not replace data governance

In a multi-service architecture, data may exist in source DBs, projections, caches, backups, streams, logs, analytics warehouses, and partner systems. Data owners must align on lifecycle and deletion/anonymization policies; every service holding a copy must know its obligations.

If **data residency or data sovereignty** rules apply, audit replicas, event brokers, DLQs, logs, backups, support teams, and third-party services. Configuring the primary database region alone does not guarantee the entire pipeline complies. Legal requirements must be verified by data type, jurisdiction, and effective date.

## 10. Cloud architecture trade-offs and operational capacity

### 10.1. Smaller services are not automatically better

A **modular monolith** with modules holding clear data ownership can be the right starting point when the team is small, business workflows are tightly linked, and independent scaling/deployment is not yet needed. A single transaction in one process can be simpler, easier to observe, and have fewer network failure points.

Splitting into microservices pays off when bounded contexts need different development cadences, load scales, or operational ownership; in return, you must solve networking, distributed state, consistency, service-to-service security, tracing, and infrastructure cost.

### 10.2. Choosing communication by real need

| Communication Style | Advantage | Cost / Risk |
|---|---|---|
| Synchronous API | Immediate response; intuitive for queries/checks needing instant feedback | Coupling on latency and availability; cascading timeouts |
| Asynchronous event | Producer less coupled to immediate consumer availability; great for fan-out and background work | Eventual consistency, duplicates, ordering, DLQs, versioning |
| Event-updated read model | Fast queries, offloads owning service | Stale data, projection logic, and rebuild capability |
| Shared database with module boundaries | Simple in cohesive systems; local transactions | Harder to evolve separately; permission leakage and schema coupling if loosely enforced |

**Do not convert every API into an event** just to "reduce coupling." Choose synchronous calls when direct answers and explicit error handling are needed; choose asynchronous messaging when the business accepts multi-step workflows and needs temporal decoupling.

### 10.3. Well-Architected framework

| Pillar | Design Questions | Measures / Trade-offs |
|---|---|---|
| **Operational Excellence** | Who owns contracts, incidents, and migrations? | Service catalog, owners, tracing, logs, dashboards; more services raise monitoring toil |
| **Security** | Who can read/write data and receive events? | Per-workload IAM, tenant authz, encryption, payload minimization |
| **Reliability** | How does a service or broker failure affect business flows? | Timeouts, bounded retries, idempotency, outbox, DLQs, sagas, recovery |
| **Performance Efficiency** | Which flows need fast local reads vs. strong consistency? | Caches/projections boost speed but complicate sync; avoid synchronous fan-out |
| **Cost Optimization** | What does each DB, event, API call, and replica cost? | Split services when justified; manage retention, traffic, replicas, and compute |
| **Sustainability** | Are unnecessary data, transfers, and compute being generated? | Trim event payloads, redundant copies, and overly aggressive polling |

### 10.4. Failure points and cost curves

Each added service call on a synchronous path adds latency and another failure point. If Booking sequentially calls multiple dependencies before responding, tail latency rises and end-to-end availability becomes bounded by all dependencies. Mitigations include cross-chain deadlines, retries with backoff/jitter, retry caps, bulkheads, circuit breakers where appropriate, and graceful degradation.

On the cloud, costs go well beyond CPU: API gateways, load balancers, cross-zone/region traffic, managed databases, brokers, egress, logs, traces, and backups all require budget. Monitor load and replica counts before deciding on one cluster per service or long-term event retention.

## 11. Step-by-step process to design a service boundary from scratch

**Step 1 — Document business requirements.** List commands, queries, invariants, security levels, latency, RTO/RPO, load levels, and expected changes.

**Step 2 — Identify bounded contexts and owners.** For each data group, record who makes decisions, who has write rights, who only reads, and who owns compliance.

**Step 3 — Map data and transaction flows.** Mark source data, copies, events, logs, backups, and partner egress paths. Decide where local transactions are needed and where eventual consistency is acceptable.

**Step 4 — Design contracts.** Write request/response or event schemas, state semantics, error codes, idempotency keys, SLAs/SLOs, authn/authz, versioning, and deprecation policies.

**Step 5 — Select infrastructure.** Decide on separate databases/schemas, managed compute, API gateway, broker, private networking, secret manager, observability, backups, and DR based on requirements.

**Step 6 — Test under failure.** Rehearse post-commit timeouts, duplicate events, late events, stopped consumers, database failures, missing permissions, stale data, and new schemas before consumers upgrade.

**Step 7 — Operate the lifecycle.** Put dashboards and SLOs, alert owners, runbooks, replay/recovery steps, permission review schedules, API/event change processes, and old-version retirement plans in place.

### 11.1. Short Architecture Decision Record (ADR) template

~~~text
Decision: Booking owns booking state.
Authoritative data source: bookings and outbox owned by Booking Service.
Consumers: Notification, Search projection, Reporting.
Read path: GET /v1/bookings/{id} for authoritative state;
           projection used only for listings/search tolerating lag.
Write path: Booking Service only; other systems send commands via API.
Contract: BookingConfirmed v1; eventId, bookingId, occurredAt,
          tenantId, correlationId; excludes card details.
Consistency: outbox + at-least-once delivery + idempotent consumers.
Failures: timeout with unknown result -> query status or reconcile.
Versioning: expand-migrate-contract, with consumer contract tests.
Owner: Booking team; coordinated with Platform/Security.
Evidence: replay, failover, restore, and permission audit test results.
~~~

ADRs must reflect real requirements and be updated when topology or contracts change. Do not copy SLO targets, retention durations, or storage regions from examples without business owner approval.

## 12. Common mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Multiple services editing the same business table | Unclear source of truth; easy to break invariants | Assign an owner, restrict write permissions, access via contracts |
| Exposing entire internal schemas as APIs/events | Cannot refactor internals; leaks data | Design stable DTOs/integration events tailored to consumer needs |
| Using timestamps to guess "latest record" everywhere | Lost updates or business conflicts | Define versioning, conflict policies, and state-decision authority |
| Treating timeouts as failed transactions | Retries create duplicate bookings/payments | Idempotency keys, correlation, `UNKNOWN`/`RECONCILING` states |
| Publishing events after commit without an outbox | State changes without emitting events on crash | Outbox/CDC or equivalent reliable publishing mechanism |
| Assuming brokers never deliver duplicates or out of order | Duplicate notifications, wrong charges/commands | Idempotent consumers, per-entity version/order checks |
| Changing enums or field meanings unannounced | Consumers still parse yet misbehave | Versioning, compatibility tests, deprecation |
| Syncing all data across all services | Uncontrolled copies, higher egress, privacy exposure | Replicate only needed data with retention and owners |
| Routing every action through long API chains | Latency and cascading failures | Bound sync paths; leverage caches/projections/async |
| Splitting microservices before understanding the domain | Excessive network hops, vague data ownership | Start with clear module boundaries and split when justified |

## 13. Applied exercises

### Exercise A — Who is the authoritative source?

Catalog stores a room's current rate at 1,500,000 VND/night. A previously completed booking locked in 1,200,000 VND/night. The dev team wants to sync all bookings whenever Catalog changes prices.

**Question:** Should they sync?

**Hint:** Do not sync previously accepted transaction prices to current list prices. Pricing/Catalog owns the published rate table; Booking retains a snapshot of the confirmed price, currency, promotional policy, and billing basis so historical transactions are not erroneously altered.

### Exercise B — API timeout after payment succeeded

Booking calls Payment to authorize funds, and the request times out. The client immediately retries with a new transaction ID, resulting in two authorizations.

**Question:** How should handling be redesigned?

**Hint:** Use a stable transaction reference/idempotency key for the same intent, query or reconcile with Payment on timeout, cap retries, and avoid creating a new payment attempt while the first outcome is unknown. Payment owns payment status; Booking updates its state from verified outcomes.

### Exercise C — Duplicate and out-of-order events

A consumer receives `BookingCancelled` and then receives an old `BookingConfirmed` retry. If it blindly overwrites state with the latest received event, the read copy wrongly flips back to `CONFIRMED`.

**Question:** What conditions must the consumer add?

**Hint:** Use `eventId` for deduplication, per-booking version/sequence numbers, or verifiable state-transition checks against the source; design handling for out-of-order events, replay, and projection rebuilds. Never rely on message arrival time as a reliable business ordering guarantee.

### Exercise D — Contract evolution

A provider wants to remove `totalAmount`, return `amountMinor`, and introduce a `REFUND_PENDING` status. Old mobile consumers only accept the three existing enum values.

**Question:** Which parts risk being breaking changes?

**Hint:** Removing `totalAmount` is breaking; adding `REFUND_PENDING` can also break consumers parsing closed enums. Use expand–migrate–contract, keep new fields optional for legacy consumers, introduce a new version or backward-compatibility mapping, add contract tests, and plan a mobile upgrade rollout with clear support timelines.

## 14. Pre-finalization design checklist

- [ ] Every key entity and business rule has an identified owner and authoritative source.
- [ ] Only the owner directly mutates data within its scope; cross-service writes are controlled.
- [ ] Historical snapshots, caches, projections, and source data are distinguished; each copy has clear update and deletion rules.
- [ ] API/event contracts document schema, semantics, timeouts, errors, retries, idempotency, security, versions, and owners.
- [ ] Invariants and local transactions are specified; multi-service transactions have intermediate states, compensations, and reconciliation.
- [ ] Critical events use reliable publishing mechanisms; consumers tolerate duplicates, out-of-order delivery, and replay.
- [ ] Schema migration strategies, compatibility tests, deprecation policies, and rollback plans exist.
- [ ] Tokens, tenant permissions, IAM, secrets, networking, and event permissions follow least privilege.
- [ ] SLIs/SLOs, dashboards, tracing, auditing, DLQ/replay runbooks, and alert owners are in place.
- [ ] Backups, restores, RTO/RPO, data residency, logs, and replicas are evaluated against business and compliance requirements.
- [ ] Costs for DBs, brokers, replicated data, cross-service requests, and operations are calculated.
- [ ] Splitting into microservices has clear justification over a modular monolith.

**Key takeaway:** Data ownership answers **who holds authority to decide and mutate business truth**; service contracts answer **what parties exchange, which commitments can be trusted, and what happens when the system changes or fails**. Both must be designed together so services can evolve independently while preserving data correctness, security, and end-to-end experience.
