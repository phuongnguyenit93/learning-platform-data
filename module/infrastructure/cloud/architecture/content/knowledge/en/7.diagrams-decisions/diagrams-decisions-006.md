# Specifying API Contracts, Events, and Component Ownership

> **Chapter:** Diagrams and Decisions  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment models. This lesson focuses on explicitly specifying interfaces and responsibilities between components so reliability, security, scalability, cost, and operations can be evaluated with Well-Architected thinking.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **API contracts**, **event contracts**, and **ownership contracts**, and explain why architecture diagrams must link to all three.
2. Specify an API thoroughly enough for client and server to develop independently: endpoints, authentication, data, business semantics, errors, idempotency, compatibility, and operational requirements.
3. Specify integration events: emission timing, source of truth, payload, schema versioning, ordering, redelivery, error handling, and replay mechanisms.
4. Assign owners for data, services, contracts, infrastructure, and on-call duties to prevent gaps during changes or incidents.
5. Draw container/interaction flow diagrams showing sync–async boundaries, data boundaries, trust boundaries, and accountability points.
6. Use ADRs, contract tests, and Well-Architected evaluation tables to justify and verify design decisions.

## 1. Why Must Contracts Be Documented Alongside Diagrams?

A diagram with three boxes **Frontend → Booking API → Database** only shows that components communicate. It does not yet answer:

- What data does the frontend send; what does the API return on a successful write, on slot contention, or on timeout?
- Can the API be retried safely after a network error? How do we avoid creating two bookings?
- After saving a booking, who publishes the event to the notification system? Can the event be delivered twice?
- Who is the sole authority deciding booking state; can other teams modify the data directly?
- Which team updates contracts, handles production errors, reconciles data, and communicates breaking changes?

A **contract** is the set of observable commitments at the boundary between components. It specifies **inputs, outputs, semantics, failure behavior, compatibility rules, and maintenance responsibilities**. A good contract lets a component evolve internally while other components continue operating within agreed bounds.

Three interrelated contract categories:

| Category | Exchanged between | What must be defined | Example |
|---|---|---|---|
| **API contract** | Client and target service, usually synchronous | Path/method, schema, auth, response codes, timeouts, idempotency, rate limits | Client calls create booking; API returns booking ID or clear error |
| **Event contract** | Producer and consumers, usually asynchronous | Event name, emission timing, payload, schema, delivery/retry/ordering, retention, versioning | Booking Service emits BookingConfirmed for Notification Service to process |
| **Ownership contract** | Dev teams, data owners, platform, and operations | Who owns components, data, and contracts; who approves changes; who is on call | Booking team owns booking state; Notification team owns message-sending logic |

A contract **does not have to be a single file**. OpenAPI or AsyncAPI describes the machine-readable part; ADRs record rationale and trade-offs; a catalog/team registry records owners; dashboards and runbooks express operational requirements. What matters is that these sources are linked, verifiable, and kept up to date by designated owners.

### 1.1. From Business Requirements to Interface Boundaries

Suppose we are designing a service booking system:

- Users must know for sure when a booking **has been confirmed**.
- No two bookings may occupy the same exclusive resource and time slot.
- Email/SMS notifications may arrive a few minutes late; notification provider failures must not corrupt the booking transaction.
- Analytics services may receive data with delay, yet analytics data must never serve as the source of truth for checking slot availability.

From this follows: **writing a booking** requires a synchronous API contract with safe retry behavior; **notifications** fit an event emitted after transaction commit; **Booking Service** owns transaction state; and **Notification Service** owns only notification delivery state.

### 1.2. A "Contract" Is Broader Than a Schema

Two components can share the exact same JSON schema yet still be semantically incompatible:

- A status field shifts from meaning "confirmed" to "pending" without changing its name.
- An API previously returned an error when sold out, and now silently creates a waitlist booking.
- A producer shifts event emission from **post-commit** to **pre-commit**, causing consumers to observe data that does not exist yet.
- A timestamp keeps the same field name, but its meaning changes from when the business event occurred to when the message was sent.

Therefore you must document **semantic invariants**, preconditions/postconditions, error behavior, and guarantee limits—not just field names and data types.

## 2. Positioning Contracts on Architecture Diagrams

### 2.1. Choosing the Right View

Diagrams serve different questions:

| View | Helps understand | Should explicitly show |
|---|---|---|
| **System context** | Actors and external systems, product boundaries | Users, third parties, interfaces, and system-level responsibilities |
| **Container/component** | Services, datastores, queues, gateways, and dependencies | Deployment/data boundaries, sync APIs, async events, owners |
| **Sequence** | Interaction order of a business flow and failures | Transactions, requests/responses, events, states, and failure paths |
| **Deployment** | Which region, zone, network, and compute host components | Trust boundaries, public/private zones, HA, secrets, connectivity paths |
| **Data lineage/event flow** | Who creates, transforms, and consumes data | Source of truth, event names, topics, retention, consumers, and latency |

Do not try to cram every detail into one diagram. A readable overview uses component names and arrows, then **references** detailed contracts on each arrow.

### 2.2. Container View Example

~~~mermaid
flowchart LR
    C[Web / Mobile] -->|HTTPS POST /v1/bookings| G[API Gateway]
    G -->|HTTPS + user identity| B[Booking Service]
    B -->|SQL transaction| DB[(Booking Database)]
    B -->|Write in same transaction| O[(Outbox)]
    O -->|Dispatcher: publish| Q[(Event Broker)]
    Q -->|booking.confirmed.v1| N[Notification Service]
    Q -->|booking.confirmed.v1| A[Analytics Consumer]
    N -->|HTTPS API| P[Email / SMS Provider]

    subgraph BookingDomain[Ownership domain: Booking Team]
        B
        DB
        O
    end
    subgraph NotificationDomain[Ownership domain: Notification Team]
        N
    end
    subgraph AnalyticsDomain[Ownership domain: Data Team]
        A
    end
~~~

Each arrow has its own contract form:

- **Client → Gateway/Booking:** synchronous API contract; must specify auth, responses, and errors.
- **Booking → Database/Outbox:** Booking's internal data constraints and transactions; do not grant other consumers permission to update the booking table.
- **Outbox → Broker → Consumer:** event contract, allowing message redelivery.
- **Notification → Provider:** external API; needs timeouts, retries, and a policy for handling uncertain outcome states.

The logical diagram above **does not yet show networks, zones, or regions**. When moving to a deployment view, add public/private boundaries, workload identities, secret management, encryption, quotas, and appropriate redundancy components. The label "Booking Team" indicates business ownership; the infrastructure owner of the broker or cloud account may be Platform.

### 2.3. Annotation Template for Arrows

Instead of vague arrow labels like "calls" or "uses", record:

| Annotation field | Example |
|---|---|
| Communication style | Synchronous HTTPS / asynchronous event / internal SQL |
| Contract name | CreateBooking API v1 / booking.confirmed.v1 |
| Call or publish direction | Web → Booking / Booking → Broker |
| Identity and permissions | User JWT; service identity; topic subscribe permission |
| Key guarantees | API returns 201 only after commit; event may be redelivered |
| Owner and doc links | Booking team; links to OpenAPI/AsyncAPI/catalog/ADR |

When using Mermaid, label arrows with short contract names; keep field details and semantics in tables or docs beside the diagram. Diagrams do not need full payloads.

## 3. API Contracts: Describing Behavior Callers Can Rely On

### 3.1. Minimum Sections

A quality API contract must specify:

1. **Purpose:** which business action, who may call it, and success conditions.
2. **Address and method:** base path, HTTP method, resource addressing, version.
3. **Authentication and authorization:** credential type, scopes/roles, owner/tenant checks, denied actions.
4. **Request:** path/query/header/body, required fields, types and formats, size limits, validation, time/unit definitions.
5. **Response:** status codes, success schema, Location or processing status, key headers.
6. **Errors:** status codes, machine-readable error codes, response structure, whether retryable.
7. **Correctness:** invariants, transaction boundaries, idempotency, concurrency handling.
8. **Operations:** timeouts, rate limits, quotas, SLOs, trace/correlation IDs, observability, compatibility, and sunset policies.

OpenAPI can serve as the **machine-readable contract source**, yet behaviors hard to capture purely in schema—such as "confirm only after commit"—still must be stated clearly in descriptions, behavioral docs, or contract tests.

### 3.2. Booking Creation Request Example

Suppose the client calls **POST /v1/bookings** over HTTPS, using a bearer access token and an **Idempotency-Key** header. The client sends only the resource ID and slot ID. The API derives user/tenant from the verified identity; never trust a client-supplied customerId for authorization.

Example request:

~~~http
POST /v1/bookings HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 01JY-BOOKING-REQUEST-001
X-Request-Id: req-7a21

{
  "resourceId": "doctor-42",
  "slotId": "slot-2026-11-20T09:00:00+07:00"
}
~~~

Example response after **successful commit**:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/bookings/bkg-817
X-Request-Id: req-7a21

{
  "id": "bkg-817",
  "resourceId": "doctor-42",
  "slotId": "slot-2026-11-20T09:00:00+07:00",
  "status": "CONFIRMED",
  "createdAt": "2026-11-18T05:00:00Z"
}
~~~

**Invariant:** if the slot type permits only one booking, the transaction at the authoritative data store must guarantee at most one confirmed booking per resource/slot pair. Checking "is slot free?" and then writing without an appropriate transaction/constraint can cause double booking under concurrent requests.

If the same Idempotency-Key and intent are resent after a client misses the response, the server must return the stored outcome (or in-progress status if unfinished) rather than creating a new booking. Keys must be scoped to caller identity and operation with a published retention window; reusing the same key with a different payload must be rejected. Key creation and concurrent-request protection must execute durably without race conditions.

### 3.3. Response and Error Policy Table

| Scenario | Typical HTTP status | Illustrative business error code | What the caller should do |
|---|---|---|---|
| Booking committed | **201 Created** | — | Save booking ID and Location |
| Syntactically invalid JSON/request | **400 Bad Request** | INVALID_REQUEST | Fix request; do not retry verbatim |
| Unauthenticated / expired session | **401 Unauthorized** | UNAUTHENTICATED | Re-authenticate via valid flow |
| Authenticated but unauthorized | **403 Forbidden** | ACCESS_DENIED | Do not retry with same credentials; review authorization |
| Slot already claimed by someone else | **409 Conflict** | SLOT_UNAVAILABLE | Prompt user to pick another slot |
| Same idempotency key, different intent | **409 Conflict** | IDEMPOTENCY_CONFLICT | Generate a new key for new intent; do not overwrite old key |
| Syntactically valid data violating input rules | **422 Unprocessable Content** if adopted | VALIDATION_FAILED | Fix fields per error details |
| Quota/rate limit exceeded | **429 Too Many Requests** | RATE_LIMITED | Retry per Retry-After/backoff where appropriate |
| Critical dependency temporarily down | **503 Service Unavailable** | TEMPORARILY_UNAVAILABLE | Bounded retry with same key within deadline |

Not every 409 or 5xx should be retried. For instance, a taken slot is a business conflict requiring the user to choose again; an HTTP timeout may have occurred **after the booking committed**. Clients should query by booking ID or retry with the same idempotency key to avoid duplicates.

Example stable structured error:

~~~json
{
  "code": "SLOT_UNAVAILABLE",
  "message": "The time slot is already booked.",
  "requestId": "req-7a21",
  "details": {
    "slotId": "slot-2026-11-20T09:00:00+07:00"
  }
}
~~~

Machine-readable error codes must stay stable across compatible versions. User-facing messages may change or be localized; clients must never branch business logic on message text. Never expose stack traces, connection strings, secrets, or sensitive data in error bodies or logs.

### 3.4. Abbreviated OpenAPI Example

This is an **OpenAPI 3.0.3** document illustrating one endpoint; server name, permissions, and limits are lesson assumptions. Operational policies and invariants still must be explained in accompanying docs.

~~~yaml
openapi: 3.0.3
info:
  title: Booking API
  version: 1.0.0
servers:
  - url: https://api.example.test
paths:
  /v1/bookings:
    post:
      operationId: createBooking
      summary: Create a confirmed booking if the slot is available
      description: >
        Returns 201 only after the booking transaction has committed.
        The same Idempotency-Key with the same request will not create a second booking.
        The caller is identified from the bearer token.
      security:
        - bearerAuth: []
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          description: Unique key for a single booking-creation intent.
          schema:
            type: string
            minLength: 1
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateBookingRequest'
      responses:
        '201':
          description: Booking created and committed
          headers:
            Location:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Booking'
        '400':
          description: Invalid request
        '401':
          description: Unauthenticated
        '403':
          description: Forbidden
        '409':
          description: Slot or idempotency key conflict
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
        '429':
          description: Rate limit exceeded
        '503':
          description: Temporarily unavailable
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    CreateBookingRequest:
      type: object
      required: [resourceId, slotId]
      additionalProperties: false
      properties:
        resourceId:
          type: string
          minLength: 1
        slotId:
          type: string
          minLength: 1
    Booking:
      type: object
      required: [id, resourceId, slotId, status, createdAt]
      properties:
        id:
          type: string
        resourceId:
          type: string
        slotId:
          type: string
        status:
          type: string
          enum: [CONFIRMED]
        createdAt:
          type: string
          format: date-time
    ApiError:
      type: object
      required: [code, message, requestId]
      properties:
        code:
          type: string
        message:
          type: string
        requestId:
          type: string
~~~

To turn this into a production contract, add error examples and schemas for all responses, per-resource/tenant authorization, PII protection requirements, versioning, timeout and quota rules, expired-key policy, lookup endpoints, and time-validity rules. OpenAPI describes only the **interface surface**; it does not implement transactions, IAM, or double-booking prevention.

### 3.5. Synchronous or Asynchronous at the API Layer?

When the API responds only after commit, **201 Created** means the outcome is durable within committed guarantees. If the system accepts requests for background processing before confirming the booking, use a pattern like **202 Accepted** with an operation ID and a status-check endpoint; never return CONFIRMED without proof of completion.

Example:

| Design | When the client learns the outcome | When appropriate | Risks |
|---|---|---|---|
| Synchronous booking creation | After transaction, returns 201 or error/conflict | Short transactions where immediate slot confirmation is needed | Long-running work increases latency and held resources |
| Asynchronous intake | Returns 202 and operation ID, then poll/callback | Long-running work or multi-step independent workflows | Must design states, TTL, callbacks, retries, and terminal failures |

Do not pick 202 merely to lower perceived latency if users genuinely need to know the transaction succeeded. Payment or booking operations must accurately expose terminal states and how uncertain states are resolved.

### 3.6. Non-Functional API Contract

Beyond schemas, publish **measurable** boundaries:

| Attribute | Example commitments to align on |
|---|---|
| SLO | Request success rate and p95/p99 at defined load, measurement window, and measurement point |
| Timeouts | End-to-end deadlines, connection limits, and request cancellation |
| Quotas | Request limits per caller/tenant, 429 behavior, Retry-After header if supported |
| Size | Body limits, item counts, pagination, and supported sorting/filtering |
| Security | TLS, bearer identity, tenant isolation, auditing, and PII redaction in logs |
| Observability | Correlation/request IDs, trace spans, error metrics by stable error code |
| Resilience | Retry policy, duplicate-request handling, and dependency failures |
| Lifecycle | Supported versions, deprecation policy, consumer notification channels |

Targets are examples for design and verification, not a promise that using an API Gateway or managed compute automatically satisfies SLOs.

## 4. Event Contracts: Describing What Happened and How Others Observe It

### 4.1. Distinguishing Events, Commands, and Queries

In asynchronous architectures, not all messages carry the same meaning:

| Type | Meaning | Example | Key traits to note |
|---|---|---|---|
| **Event** | Something that already happened; describes a past fact | BookingConfirmed | Published by producer; multiple consumers may subscribe |
| **Command** | Requests a component to perform an action | SendBookingNotification | Has a specific target/handler; may succeed or fail |
| **Query** | Requests information without intending to mutate state | GetBooking | Requires clarifying data freshness/consistency |

Events should be named in past tense or reflect a state that already occurred. **BookingConfirmed** must only be emitted after booking state commits. A message saying "please confirm booking" is actually a command; calling it an event blurs who owns deciding the outcome.

Distinguish further:

- **Domain event:** reflects an occurrence inside a business boundary and may include internal details; not automatically a contract for external services.
- **Integration event:** a version intentionally published for consumers outside the boundary; minimal payload, stable, and governed by a change process.

Do not automatically push every domain event onto a public broker. Doing so exposes internal structure, increases coupling, and risks leaking sensitive data.

### 4.2. Contents of an Event Contract

An event contract must document at least:

1. **Name, meaning, and emission condition:** which exact state does the event reflect, and is it emitted only post-commit?
2. **Producer and source of truth:** which service determines truth; who is authorized to publish?
3. **Channel/topic and consumers:** where it is published, subscribers, and access rules.
4. **Envelope metadata:** event ID, event type, version, timestamp, aggregate ID, correlation ID, and tenant scope where needed.
5. **Payload:** fields, types, semantics, optional/required, time rules, and sensitive data.
6. **Delivery guarantees:** at-most-once, at-least-once, or effective per-hop guarantees; can duplicates or reordering occur?
7. **Ordering and partition key:** does order matter per booking, per customer, or globally?
8. **Retries, DLQ, retention, and replay:** what happens when a consumer crashes, falls behind, or needs to rebuild a projection?
9. **Compatibility:** schema version, field addition/removal rules, parallel support window, and approving owner.
10. **Operational requirements:** commit-to-publish/consume latency, backlog metrics, alerts, and incident recovery procedures.

These criteria must be **recorded in a discoverable contract**, not merely assumed from a consumer's current behavior.

### 4.3. Example `booking.confirmed` Event Version 1

Suppose Booking Service committed a booking successfully and produced a post-commit integration event:

~~~json
{
  "eventId": "evt-80231",
  "eventType": "booking.confirmed",
  "schemaVersion": 1,
  "producer": "booking-service",
  "aggregateType": "booking",
  "aggregateId": "bkg-817",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-18T05:00:00Z",
  "correlationId": "req-7a21",
  "data": {
    "bookingId": "bkg-817",
    "resourceId": "doctor-42",
    "slotId": "slot-2026-11-20T09:00:00+07:00",
    "status": "CONFIRMED"
  }
}
~~~

Explanation of key fields:

| Field | Meaning | Rules to finalize |
|---|---|---|
| **eventId** | Identifier for one logical event occurrence | Stable if the broker redelivers the same event; used for deduplication |
| **eventType** | Business event type | Never silently change meaning under the same name |
| **schemaVersion** | Payload structure version | Support/lifecycle rules and how consumers distinguish versions |
| **producer** | Service publishing the event | Publish permissions and contract owner |
| **aggregateId** | Business entity identifier | Used for correlation and partitioning/ordering where applicable |
| **aggregateVersion** | Entity state version after transition | Helps detect stale, duplicate, or out-of-order events |
| **occurredAt** | Time the business event occurred | Defined in UTC; distinct from publish and consume times |
| **correlationId** | Links a transaction from HTTP through workers | Helps tracing/auditing; not a deduplication key |
| **data** | Business info needed by consumers | Minimized, documented fields, and PII protection |

**eventId, aggregateVersion, and correlationId serve different purposes.** One correlation ID may span many events and requests; never use it instead of eventId for deduplication. In multi-tenant systems, specify how tenant identity is determined and enforced; never trust a tenant ID inside the payload alone if consumers could receive messages from untrusted sources.

Payload scope must be decided alongside data and access rules. This example **contains no email, phone number, or patient name**. Notification Service can use the booking ID reference and an appropriately authorized service identity to fetch needed details, or receive an explicitly approved minimal payload depending on latency and coupling trade-offs. Either choice must consider PII, access control, data retained in DLQs, logs, and retention.

### 4.4. Event Contract Catalog

An internal YAML catalog can record commitments that do not fit neatly into JSON Schema alone. This is an **illustrative custom template**, not a claim to be standard AsyncAPI or CloudEvents schema:

~~~yaml
name: booking.confirmed
schemaVersion: 1
meaning: "Booking committed with status CONFIRMED."
producer:
  service: booking-service
  owningTeam: booking
channel:
  logicalName: booking.events
  partitionKey: aggregateId
consumers:
  - notification-service
  - analytics-consumer
delivery:
  assumption: at-least-once
  duplicatesPossible: true
  globalOrderGuaranteed: false
  consumerMustBeIdempotent: true
  orderingScope: "per booking when supported by broker/configuration"
failure:
  retry: "bounded backoff"
  deadLetter: true
  replay: "only via controlled procedure"
schema:
  required: [eventId, eventType, schemaVersion, aggregateId, occurredAt, data]
security:
  containsPersonalData: false
  publisherScope: booking-service-only
  subscriberPolicy: approved-consumers-only
operations:
  alertOwner: booking
  publishLagSlo: "per agreed service level"
~~~

AsyncAPI can describe channels, messages, payloads, operations, and schemas for event-driven APIs. JSON Schema or a schema registry supports validation/compatibility; an ownership catalog and runbooks still need to supply policies and operational behavior. Event contracts should follow versioning and CI/CD pipelines just like API contracts.

### 4.5. Delivery Does Not Equal Exactly-Once Successful Processing

A broker or client may redeliver the same message after timeouts, crashes, or lost acknowledgements. Distinguish:

| Guarantee | Implication | What must be designed |
|---|---|---|
| **At-most-once delivery** | Messages may be lost, unlikely to duplicate on that delivery hop | Use only when message loss is acceptable |
| **At-least-once delivery** | Messages may be received multiple times | Consumers process idempotently and record progress |
| **Exactly-once processing** within one platform | May apply to certain internal operations under specific conditions | Never extrapolate to end-to-end exactly-once across external APIs and systems |

For a notification worker, typical steps are: receive message, verify schema/permissions, check whether eventId was already processed, perform work, persist status, and acknowledge. Yet calling an email provider can succeed right before the worker crashes prior to saving status; on redelivery, duplicate sending can occur. Use a provider-supported idempotency token, or maintain explicit duplicate-handling policies.

**Never treat a consumer receiving an event as proof that the booking was just created.** A booking is confirmed in Booking Service's transaction; the event is the notification mechanism for that fact. Queue delays can delay Notification Service without altering booking state.

### 4.6. Transactional Outbox Solves the Dual-Write Problem

If Booking Service executes two independent commands:

1. Write to database successfully.
2. Publish event to broker.

then a crash between the two leaves the booking existing with no event published. Reversing the order does not fully solve it either: the event can be published while the database transaction rolls back.

A **transactional outbox** stores the booking and event record in the same database transaction. Post-commit, a dispatcher reads the outbox to publish. Consequently, unconfirmed events can be retried, though the dispatcher may publish duplicates if it crashes after publishing but before marking the row processed.

~~~mermaid
sequenceDiagram
    actor Client as Web / Mobile
    participant API as Booking API
    participant DB as Booking DB + Outbox
    participant Dispatcher as Outbox Dispatcher
    participant Broker as Event Broker
    participant Consumer as Notification Worker
    Client->>API: POST /v1/bookings + Idempotency-Key
    API->>DB: Transaction: check slot, insert booking, insert outbox
    alt Commit succeeds
        DB-->>API: booking ID
        API-->>Client: 201 Created
        Dispatcher->>DB: Read committed outbox
        DB-->>Dispatcher: booking.confirmed event
        Dispatcher->>Broker: Publish event
        Broker-->>Dispatcher: Ack publish
        Dispatcher->>DB: Mark as published
        Broker->>Consumer: Deliver event (may repeat)
        Consumer->>Consumer: Deduplicate + process
        Consumer-->>Broker: Ack after processing per policy
    else No slot available
        DB-->>API: Conflict / rollback
        API-->>Client: 409 Slot unavailable
    end
~~~

Commitments that must be recorded in the contract:

- Events represent committed bookings only, never pre-commit intent.
- Publishers may re-emit the same event ID; consumers must handle duplicates safely.
- Time from commit to event publish **is not zero**; monitor publish lag and backlog.
- If the dispatcher or broker goes down, the outbox persists events for later publishing within designed storage/retention and recovery limits.
- Requires outbox cleanup, replay, retry, and alerting mechanisms to prevent unbounded accumulation.

### 4.7. Ordering, Replay, and Late Events

Never blindly assume all broker events have **global ordering**. If consumers must process each booking's states sequentially, agree on:

- **Ordering key:** e.g., aggregateId as booking ID; do the broker/partitions preserve per-key order under real config and retries?
- **Aggregate version:** how does a consumer handle receiving version 3 before version 2?
- **Late events:** if `booking.cancelled` arrives before `booking.confirmed`, what should the projection do?
- **Replay/backfill:** when rebuilding a read model, can historical events be replayed without resending emails or triggering external side effects?
- **Retention:** how long does the broker retain messages, how long does the DLQ retain them, and can deleted personal data still be replayed?

For example, Analytics Consumer can store the latest version per booking and ignore events whose aggregateVersion is not higher than the processed version. However, if logic depends on **every intermediate transition**, dropping older versions is insufficient; you need waiting, gap detection, or reconciliation mechanisms.

**Replay for analytics and replay for notifications mean different things.** Analytics can rebuild projections; notifications must avoid sending last month's confirmation emails when replaying historical events. Contracts must document replay policies per consumer type.

### 4.8. Versioning and Changing Event Contracts

Adding an optional field with clear defaults/semantics is usually less risky than renaming or changing the meaning of an existing field. A sound process:

1. Identify the producer owner and list of active consumers.
2. Add the new schema and verify compatibility with supported consumers.
3. For breaking changes, introduce a **new event version or transition channel** with a parallel support period.
4. Deploy consumers capable of reading the new version before the producer retires the old version.
5. Measure consumer adoption, error messages, DLQs, and replays before ending old-version support.
6. Document deprecation dates, rollback plans, and projection recovery steps.

An event **must not change meaning while keeping the same name/version**. For example, if BookingConfirmed previously fired only after holding the slot and now fires as soon as payment starts pending, that is a semantic breaking change even if the JSON schema is unchanged.

## 5. Ownership: Who Has Authority to Decide, Change, and Recover?

### 5.1. Do Not Conflate Types of Ownership

| Asset | What does "owning" mean? | Example |
|---|---|---|
| **Business capability** | Accountable for business rules and outcomes | Booking team defines what counts as a confirmed booking |
| **Service/component** | Maintains service code, deployments, SLOs, and runbooks | Booking team is on call for Booking Service |
| **Data / source of truth** | Governs authoritative data, schemas, retention, and write controls | Booking team owns booking data |
| **API/event contract** | Preserves semantics, versions, change notices, and compatibility | Booking team maintains CreateBooking and BookingConfirmed |
| **Consumer projection** | Maintains separate tables built from events, handles replays and consumer errors | Analytics team owns the analytics read model |
| **Cloud infrastructure** | Platform policies, accounts, networking, broker operations, and quotas | Platform team may own the broker and landing zone |
| **Security/governance** | Defines IAM policies, sensitive-data rules, and exceptions | Security team approves elevated access exceptions |
| **Cost/budget** | Accepts costs and optimizes against business value | Product/service owner manages workload budget |

A broker operated by Platform **does not mean Platform owns the semantics of every event**. Likewise, a database run on a managed cloud service does not mean the provider is responsible for access permissions, business logic, or customer data quality. Responsibility boundaries must follow the chosen service's shared responsibility model.

### 5.2. Setting Data and Write-Access Boundaries

Guiding principles:

- Every business dataset must have a **designated source of truth** with controlled write permissions.
- Other services access data via APIs/events or an explicitly contracted shared interface; avoid writing directly to another service's tables, which creates tight coupling to internal schemas.
- Consumers may keep their own **read model/cache**; sync latency, replay behavior, and stale-data behavior must be published.
- If multiple teams update one data source, define coordination rules, write scopes, and conflict resolution rather than leaving data effectively "unowned".

Example: Booking Service confirms slots; Notification Service never directly flips a booking from PENDING to CONFIRMED. Notification Service may store DELIVERY_PENDING/DELIVERED in its own datastore; if the business needs to display notification delivery status, define an API/event or an explicit projection.

**You do not have to split a physical database per module.** In a modular monolith or transitional phase, one physical database can still define per-module schemas/tables, internal APIs, and write permissions. Data ownership boundaries matter more than database instance counts.

### 5.3. Example Service Catalog and Contract Registry

| Component/contract | Owning team | Interface responsibilities | Data source / dependencies | Incident responder |
|---|---|---|---|---|
| Booking API | Booking | CreateBooking, GetBooking; versions and error codes | Booking DB | Booking on-call |
| Booking DB | Booking (data), Platform (platform) | Booking transactions and schema | Managed relational DB | Booking + Platform by incident layer |
| booking.confirmed.v1 | Booking | Event semantics, schema, publish lag | Outbox and broker | Booking on-call |
| Event broker | Platform | Broker throughput, retention, access policy, and availability | Messaging infrastructure | Platform on-call |
| Notification Consumer | Notification | Subscribe, dedup, retries, DLQ, message delivery | Broker + email/SMS provider | Notification on-call |
| Analytics Read Model | Data/Analytics | Projections, reconciliation, replays | Approved integration events | Analytics on-call |
| API gateway | Platform and Booking per policy | Platform routing/TLS/quotas; API auth/semantics defined by Booking | Edge/network | Platform + Booking by symptom |

A real catalog should add service ID, repository, environment, support channel, backup owner, dashboard/runbook links, OpenAPI/AsyncAPI links, version support windows, sensitive data tags, SLOs, and dependency lists. **An owner is a maintainable role/team**, not just an individual's personal address.

### 5.4. RACI for Contract Changes

RACI: **R**esponsible (executes), **A**ccountable (final owner), **C**onsulted, **I**nformed. The table below is illustrative only; each organization adapts it to its own governance.

| Activity | Booking | Notification | Analytics | Platform | Security |
|---|---|---|---|---|---|
| Define CreateBooking API semantics | **A/R** | C | I | C | C |
| Release new booking.confirmed schema | **A/R** | C | C | I | C |
| Update notification consumer | C | **A/R** | I | I | C |
| Govern broker/quotas/ACLs | C | C | C | **A/R** | C |
| Approve sensitive-data exceptions | C | C | C | I | **A/R** |
| Run producer–consumer contract tests | **A** | R | R | I | I |
| Resolve outbox publish failures | **A/R** | I | I | C | I |
| Handle failed messages in Notification DLQ | C | **A/R** | I | C | I |

When an incident spans multiple components, define **incident triage and escalation paths**; neither "Platform runs the broker so Platform owns all event bugs" nor "producer published so consumer is on its own" works. Each owner takes accountability within its boundary while supporting cross-service tracing.

### 5.5. Ownership Contracts Need a Maintenance Cadence

Fields to include in a record:

~~~yaml
componentId: booking-service
businessCapability: bookings
owningTeam: booking
onCall: booking-oncall
dataOwner: booking
apiContracts:
  - create-booking-v1
eventContracts:
  - booking.confirmed.v1
dependencies:
  - booking-database
  - event-broker
runtime:
  environment: production
  regionPolicy: approved-regions
assurance:
  runbook: "link-to-controlled-runbook"
  dashboard: "link-to-controlled-dashboard"
  securityContact: security-review
review:
  cadence: "per organizational policy"
  lastVerified: "2026-11-18"
~~~

This is an **internal catalog template**, not a mandatory standard schema. On-call addresses and links must point to access-controlled management systems without embedding passwords or keys.

When a service changes ownership, transfer access rights, dashboards, runbooks, published contracts, consumer lists, and incident duties. A product may run smoothly today yet become hard to change if catalogs and owners are not updated as staffing and team structures evolve.

## 6. Representing Failure Flows and Trust Boundaries

### 6.1. Sequence Diagrams with Success and Failure Paths

Container diagrams show static relationships; sequence diagrams explain order and outcomes when components collaborate. When drawing a critical flow, include at least **success, business errors, dependency failures, and duplicate-request handling**.

~~~mermaid
sequenceDiagram
    actor User as User
    participant API as Booking API
    participant DB as Booking DB
    participant D as Outbox Dispatcher
    participant MQ as Event Broker
    participant W as Notification Worker
    User->>API: POST booking (token, idempotency key)
    API->>API: Authenticate + authorize + validate
    API->>DB: Begin transaction, check slot and idempotency
    alt Slot valid, no existing booking
        API->>DB: Insert booking and outbox, commit
        DB-->>API: Commit OK
        API-->>User: 201 Created, booking ID
        D->>DB: Poll committed outbox
        DB-->>D: Event data
        D->>MQ: Publish booking.confirmed.v1
        MQ->>W: Deliver event
        W->>W: Deduplicate, process
    else Slot contested
        DB-->>API: Constraint conflict
        API-->>User: 409 SLOT_UNAVAILABLE
    else Request with existing key and same payload
        DB-->>API: Saved booking result
        API-->>User: Stored result, no new booking created
    end
    Note over User,W: HTTP success and notification delivery are two distinct states
~~~

On timeouts, the client may not know whether the server committed. The client must use the **same idempotency key** when retrying or call a status-lookup API per contract. For an API returning 202, add operation states, polling/callbacks, and terminal failure states to the diagram.

### 6.2. Security and Data Boundaries on Diagrams

Points that must be inspected when running in the cloud:

| Boundary | Questions | How to note on diagrams/contracts |
|---|---|---|
| Internet → Edge | HTTPS/TLS, WAF, DDoS protection, rate limits, and routing? | Mark public ingress, protection controls, and owner |
| Edge → Booking | How are tokens/identities passed and verified? | Auth method, token audience, workload identity, and permissions |
| Booking → DB | Does DB have private access, least privilege, encryption, and timeouts? | Private channel, data owner, transaction boundary |
| Producer → Broker | Who can publish to which topic; do events contain PII? | Publish ACL, schema/data classification, retention |
| Broker → Consumer | Who can subscribe; are tenants isolated and replays bounded? | Subscribe ACL, identity, audit, and DLQ access |
| Consumer → Provider | Where are secrets stored; how are errors/responses handled? | Secret manager, timeouts/retries, and provider contract |

Boundaries must be marked on deployment/network views. Having a WAF or TLS **does not replace** object/tenant authorization inside Booking Service; an authenticated user still must be denied access to someone else's booking.

### 6.3. Relationship Between Contracts and Physical Architecture

API/event contracts primarily define **logical behavior**, yet meeting them depends on deployment:

- API SLOs depend on load, instance count, load balancers, databases, connection pools, and deployment zones.
- Event publish lag depends on outbox, dispatcher, broker, partitions, quotas, storage, and backlogs.
- Infrastructure ownership must be explicit across accounts/projects, networking, identity, KMS, databases, and brokers.
- Zone/region fault tolerance must examine **every** component on the path, not be inferred solely from Booking API replica count.
- Costs include network egress, broker throughput/retention, traces/logs, databases, queues, standby capacity, and test environments.

A promise like "events reach consumers within 2 seconds" is meaningful only when you know how it is measured from **commit** to **consumer receipt/processing**, under what load, and at which percentiles/exceptions. Diagrams should link to metrics and dashboards verifying that commitment.

## 7. Managing Changes and Contract Testing

### 7.1. Distinguishing Compatible vs. Breaking Changes

A change is **compatible** when every consumer within the supported scope continues operating correctly under the contract. This is judged by **behavior and how consumers use the contract**, not just by diffing two schema files.

| Change | Potentially compatible? | Conditions to check |
|---|---|---|
| Add an **optional** field in API response | Usually yes | Clients ignore unknown fields and do not rely on field order |
| Add a **required** field to request | Usually breaking | Older clients cannot send it; need optional/default or new version |
| Remove/rename response field | Usually breaking | Consumers may depend on the old field |
| Change enum/status meaning or emit event earlier | Potentially breaking despite identical schema | What business assumptions does each consumer hold? |
| Add optional field to event | Potentially compatible | Consumers handle unknown and missing fields across versions |
| Change field type from string to number | Usually breaking | Parsers/validation, previously stored data, and replays |
| Change event delivery ordering | Potentially breaking | Do consumers rely on state ordering? |
| Change idempotency or retention policy | Potentially breaking | How long do clients retry, and from how far back do consumers replay? |
| Lower quotas or shorten timeouts | Potentially operationally breaking | Do SLOs and load profiles rely on prior limits? |

**Versioning does not fix silent semantic changes.** Major versions may live in URLs, headers, or message identifiers per organizational convention, yet you must still publish support windows, migration steps, and ways to detect legacy consumers before retiring a contract.

### 7.2. Contract Change Process with Owners

A release lifecycle can be modeled as:

~~~mermaid
flowchart TD
    A[Propose API / event change] --> B[Owning team analyzes invariants and compatibility]
    B --> C[Check consumers / owners / data policies]
    C --> D{Breaking contract?}
    D -- No --> E[Update schema + docs + tests]
    D -- Yes --> F[Design new version / migration / parallel support]
    F --> E
    E --> G[CI: lint + schema + contract + security tests]
    G --> H{Passed and reviewed?}
    H -- Not yet --> B
    H -- Yes --> I[Deploy and observe canary / staging]
    I --> J[Consumers confirm compatibility]
    J --> K[Roll out, monitor SLIs + errors + DLQ]
    K --> L[Deprecate old version only when criteria met]
~~~

For asynchronous contracts, **consumers generally need to read the new version first** before the producer stops emitting the old version. For APIs, the producer can support two versions concurrently until clients upgrade. No single deployment order fits every system; examine actual data paths and backward/forward compatibility.

### 7.3. Recommended Testing Layers

| Test type | What issues does it catch? | Applied example |
|---|---|---|
| **Schema lint/validation** | Missing fields, wrong types, naming/version violations | Validate OpenAPI, JSON Schema, or AsyncAPI in CI |
| **Provider contract test** | Actual producer/API deviates from spec | POST booking returns 201 with promised schema and headers |
| **Consumer-driven contract test** | Producer change breaks consumer expectations | Notification requires specific fields on booking.confirmed.v1 |
| **Backward compatibility check** | Deleting/changing fields or breaking enums | Compare new schema against published contract |
| **Integration test** | Routing/auth/transactions/broker differ in reality | Test API → DB/outbox → broker → consumer |
| **Concurrency/idempotency test** | Duplicates, race conditions, lost responses | Send same key multiple times, concurrent slot contention |
| **Failure/replay test** | Broken retries/DLQ/ordering | Kill consumer after processing before ack; replay old events |
| **Security test** | Missing auth, tenant isolation bugs, PII leaks | Call another tenant's booking; subscribe to unauthorized topic |
| **Performance test** | Contract SLO missed at target load | API p95, publish lag, oldest message age, backlog |

**Contract tests do not replace integration tests or failure testing.** A valid schema does not prove database transactions are correct; a passing mocked provider test does not tell how production handles timeouts and message redelivery.

Example behavioral test suite for the booking creation API:

~~~text
Given: slot A is free, caller is authorized, key K is unused
When: POST /v1/bookings with resource/slot A and K
Then: 201, returns booking ID and Location, DB has exactly one confirmed booking.

Given: outcome for key K already committed
When: resend identical request and K
Then: returns the same business outcome, creates no extra booking/logical event.

Given: key K is already bound to slot A
When: reuse K for slot B
Then: returns conflict, writes no new booking.

Given: slot A was booked by another transaction
When: another caller books the same slot
Then: returns conflict error, DB still has only one confirmed booking.

Given: email provider is down
When: booking commits
Then: booking status is unaffected; event awaits processing/retry per policy.
~~~

Example consumer tests:

~~~text
Given: event E already processed successfully
When: broker redelivers the same eventId E
Then: creates no duplicate business side effects outside policy.

Given: consumer receives an unsupported schemaVersion
When: validating event
Then: handles per error/parking/DLQ policy, alerts, and never silently drops event.

Given: booking.cancelled arrives before booking.confirmed
When: projection must preserve latest state
Then: resolves using aggregateVersion and committed reconciliation rules.
~~~

### 7.4. Stability Gates in CI/CD

A practical pipeline includes checks at these points:

1. **Before merge:** spec linting, schema compatibility, auth/security review, provider/consumer tests, and docs/owner checks.
2. **Before deploy:** consumer inventory, version/schema plan, API/broker permissions, rollout and rollback strategy.
3. **During canary:** monitor error rates by error code, p95, booking success rate, publish lag, consumer lag, and DLQ.
4. **After deploy:** verify active served version, track adoption, watch retries/backlogs, update catalog and ADRs.
5. **Before deprecation:** proof no supported consumer depends on the old version, notices sent, and plan for historical stored data.

In particular, **rolling back a producer does not necessarily roll back schemas, data, or already-published events**. Events already read by consumers or migrated data may not revert cleanly; plans must define compensating/reconciliation measures where needed.

## 8. Recording Architectural Decisions with ADRs

An **Architecture Decision Record (ADR)** preserves a long-impact decision, its rationale, alternatives, and verification methods. ADRs suit decisions hard to read from diagrams alone: why booking returns 201 instead of 202, why transactional outbox is used, why Booking Service owns the data, and why Notification cannot write directly to that database.

### 8.1. Sample ADR for Post-Commit Event Emission

~~~text
ADR-006 — Use transactional outbox for booking.confirmed

Status: Accepted
Owner: Booking team
Date recorded: 2026-11-18

Context:
- Committed bookings must have a reliable path to notify consumers.
- A database transaction cannot commit atomically with a broker
  when the two systems lack a proven shared transaction mechanism.
- Queues and workers can fail and reprocess duplicates.

Decision:
- Booking transaction writes booking + outbox in the same DB.
- Dispatcher publishes events post-commit.
- Events carry eventId, schemaVersion, aggregateId, and correlationId.
- Consumers process idempotently; owner monitors publish lag and DLQ.

Options considered:
A. Call Notification API directly before returning response.
B. Write DB then publish event via two independent commands.
C. Transactional outbox + broker + idempotent consumers.

Rationale for C:
- Isolates Notification failures from booking transaction outcome.
- Keeps durable event records for re-publishing after failures.
- Scales to multiple consumers without forcing Booking to call each one.

Trade-offs and residual risks:
- Requires dispatcher, duplicate-publish handling, outbox cleanup, monitoring.
- Events arrive asynchronously; no global ordering or end-to-end exactly-once guarantee.
- Higher broker, logging, retry, retention, and operational cost.

Verification evidence:
- Crash before/after publish; no logical events lost and consumers deduplicate.
- Measure publish lag and oldest message age at target load.
- Verify ACLs: only Booking may publish this event.
- Test schema compatibility and controlled replay path.

Revisit when:
- SLOs, cost, volume, or transaction model change significantly.
~~~

An ADR does not need to be long. It needs enough detail for future readers to understand **which need the decision addresses**, **which trade-offs are accepted**, **who is accountable**, and **what evidence proves it sufficient**. When architecture evolves, create a new superseding ADR or update status rather than erasing past rationale.

### 8.2. Linking ADRs to Contracts and Diagrams

Each major decision should trace as follows:

~~~text
Business requirement / SLO / constraints
    ↓
ADR (decision + trade-offs + owner)
    ↓
Container / sequence / deployment diagrams
    ↓
OpenAPI / event schema / ownership catalog
    ↓
Tests + dashboards + runbooks
    ↓
Production observation → revisit ADR or contracts
~~~

For example, if the requirement shifts from "notify within a few minutes" to "notify within 5 seconds at p99", review the outbox ADR, dispatcher/queue/worker capacity, event publish/processing lag contracts, cost, and SLOs together. Editing one line in a doc without verifying the system leaves the architectural change incomplete.

## 9. Reviewing Contracts and Ownership Against Well-Architected

Well-Architected helps inspect a design from multiple angles. The table below uses the six pillars of **AWS Well-Architected** as a reference checklist; applying it does not require using AWS.

| Pillar | Questions on API/event contracts and ownership | Evidence needed |
|---|---|---|
| **Operational Excellence** | Are there owner catalogs, dashboards, runbooks, and contract-change procedures? | Contract registry, on-call, CI/CD checks, incident drills |
| **Security** | Do APIs enforce auth/authorization, brokers enforce ACLs, and payloads restrict sensitive data? | Cross-tenant tests, IAM policies, encryption, audits |
| **Reliability** | Are timeouts, retries, idempotency, DLQs, outbox, and recovery clearly specified? | Duplicate/replay tests, fault injection, restores, and SLOs |
| **Performance Efficiency** | Are API limits, event rates, partition keys, consumer lag, and capacity plans defined? | Load tests, p95/p99, backlog, DB pools, throughput |
| **Cost Optimization** | Are request, egress, broker retention, log, DLQ, and standby costs measured? | Per-service cost allocation, budgets, retention tuning |
| **Sustainability** | Are duplicate work, bloated event payloads, and unnecessary storage/replays avoided? | Resource utilization evidence, data lifecycle, scale-in |

### 9.1. Practical Trade-Offs

| Decision | Benefits | New costs/risks |
|---|---|---|
| Synchronous API returns after commit | Caller immediately knows booking is confirmed | Higher latency/request concurrency when DB slows |
| Post-commit notification events | Reduces coupling and allows independent background work | Eventual consistency, outbox/queue, replay, DLQ |
| Rich event payloads | Consumers rarely need to call back to producer | Higher PII exposure, coupling, egress, retention |
| Reference-only payloads | Minimal data, less exposure | Consumers must fetch data; higher access dependency/risk during replays |
| Shared broker | Easier to operate, better utilization | Shared quotas and blast radius; requires ACLs and tenant isolation |
| Domain-isolated brokers/topics | Reduces cross-domain impact and clarifies permissions | More resources, operational work, and cost |
| Explicitly owned APIs/events | Faster, consistent changes and incident response | Requires maintaining catalogs and coordinating consumers |

No choice is universally optimal. A small team may start with a modular monolith using internal APIs and a simple outbox/queue. As consumers, load, and independent release needs grow, services can be split while preserving **defined contracts and ownership** as the boundaries.

### 9.2. Failure Evaluation Scenario

Suppose Notification Consumer is down for 20 minutes while Booking API continues operating.

1. **Reliability:** bookings must still commit properly; queues have sufficient retention, retry/backoff, and DLQ configured; events are not lost when dispatchers/brokers restart.
2. **Operations:** Booking on-call monitors publish lag, Notification on-call monitors consumer lag; escalation procedures handle incidents whose root cause is initially unclear.
3. **Security:** never widen ACLs or disable auth to "clear" a backlog quickly; verify what data events carry.
4. **Performance:** when the consumer recovers, rate-limit processing and connections so downstream providers or sibling workloads are not overwhelmed.
5. **Cost:** measure queue storage, retries, logs, and resend costs; prevent infinite retries.
6. **Sustainability:** prioritize backlog recovery and avoid unconditionally replaying notifications that have lost business relevance.

A claim that "the architecture tolerates consumer outages" holds value only after **shutting down the consumer in a test**, measuring backlog, checking duplicate effects, and confirming recovery against agreed targets.

## 10. Common Design Mistakes

| Symptom | Consequence | Remediation |
|---|---|---|
| Drawing only "Service A calls B" arrows | Method, auth, timeouts, and errors remain unknown | Label arrows with contract names and spec links |
| OpenAPI has schemas without business semantics | Clients misinterpret confirmation timing | Document invariants, pre/postconditions, and contract tests |
| Returning 200/201 when merely enqueued | Clients assume the transaction is already certain | Use appropriate status/202 and progress-check contracts |
| Retrying POST without idempotency | Creates duplicate bookings/transactions | Idempotency keys + transactions/constraints |
| Emitting events before DB commit | Consumers act on events that never committed | Commit before publishing; use outbox where appropriate |
| Two separate DB write and broker publish commands with no recovery | Events lost on crash between steps | Transactional outbox or proven recovery mechanism |
| Consumers assume every message arrives once | Duplicate messages sent or duplicate writes | Idempotent processing, deduplication, retries/DLQ |
| All services edit each other's tables | Lost ownership and internal schema coupling | Contracted access interfaces and bounded write permissions |
| Code owner exists but no production owner | Nobody knows who is on call; unclear SLA ownership | On-call catalog, runbooks, incident routing |
| New version silently changes field meaning | Breaks consumers even though schemas still parse | Semantic versioning / contract review governance |
| Packing full customer records into events for convenience | PII spreads to logs, DLQs, and many consumers | Payload minimization, data classification, and ACLs |
| Deleting old topics/events immediately on producer deploy | Existing consumers or replays break | Migration/dual-read, track adoption, announced deprecation |

## 11. Practice Exercise: Contracts and Diagrams for a Booking Platform

**Scenario:** A product includes Web/Mobile, Booking Service, and Booking Database. After booking, customers receive an email; Analytics needs booking-volume data. The team plans to use a cloud managed event broker. Under growing traffic, the system must prevent double booking, keep the email provider from slowing down the API, and allow independent consumer updates. Booking, Notification, Analytics, and Platform teams have separate operational scopes.

**Initial assumptions for discussion:** the booking-creation API targets a p95 response threshold agreed with product; emails may lag by a few minutes; each exclusive slot confirms at most one booking; events may redeliver; Platform operates the broker. Load figures, costs, and RTO/RPO are unknown and must be marked as needing measurement rather than turned into commitments.

Prepare a design package containing:

1. **Container diagram:** show clients, gateway, Booking Service/DB/outbox, broker, Notification, Analytics, provider, and sync/async arrow labels. Mark owners and public/private boundaries.
2. **API contract:** define POST create booking; request/response, bearer auth and tenant ownership, 201/409/429/503, idempotency, error codes, and lookup mechanism on request timeout.
3. **Event contract:** define `booking.confirmed.v1`; envelope fields, payload, emission timing, partition key, duplicate/ordering semantics, retries, DLQ, retention, and replay.
4. **Sequence diagram:** include success, slot conflict, duplicate request, and interrupted consumer/provider branches.
5. **Ownership matrix:** specify owners for booking data, API schema, event schema, broker ACLs, Notification DLQ, Analytics projections, dashboards, and on-call.
6. **ADR:** compare sending email synchronously during the HTTP request, dual DB+broker commands, and transactional outbox. Pick an option with risk rationale and test evidence.
7. **Change plan:** add a field to the event and then evolve state representation while old consumers still run; detail rollout steps, tests, and deprecation criteria.
8. **Well-Architected table:** state at least one risk per pillar, its owner, and a test or evidence reducing that risk.

To self-check, fill out this table:

| Question | Answer required in documentation | Evidence |
|---|---|---|
| When is a booking confirmed? | After transaction commit in Booking Service | Contract tests, concurrency tests |
| Do timeouts create duplicate bookings? | Same idempotency key plus data constraints | Replay/concurrency tests |
| Who publishes events and when? | Booking Service, post-commit via outbox | Crash/recovery tests |
| Who is allowed to subscribe? | Approved consumer list enforced by ACLs | IAM/authorization tests |
| What if messages redeliver? | Consumers enforce idempotency policy | Duplicate-delivery tests |
| What if Analytics receives events late? | Eventual consistency and documented reconciliation | Ordering/replay tests |
| What if a consumer is down for 20 minutes? | Bookings are unaffected; backlog is monitored | Fault tests, queue age, DLQ |
| Who handles each incident type? | On-call and runbooks per service/broker | Catalog, incident drills |
| What if a schema changes incompatibly? | Versioning, notices, and transition roadmap | Compatibility tests, consumer adoption |

**Completion criteria:** Another team reading the design package should be able to answer **who calls whom, what is called, which outcomes are trustworthy, where data lives, what truth an event represents, how errors are handled, and who is accountable**. Any claims about latency, availability, or delivery must carry measurement methods and verification checks—not just labels on a diagram.

## 12. Key Takeaways

1. An **API contract** defines requests, responses, errors, authentication, idempotency, and operational limits callers can rely on.
2. An **event contract** defines a business fact that already occurred, its payload, and the delivery/ordering/replay guarantees consumers may assume.
3. An **ownership contract** determines who owns data semantics, services, interfaces, operations, and changes; running infrastructure does not make Platform the owner of all business data.
4. **Diagrams** are useful only when communication paths and boundaries carry clear labels linked to specs, ADRs, catalogs, and tests.
5. **Trade-offs** across sync/async, rich/minimal payloads, shared/isolated brokers, and change speed vs. safety must be documented and verified.

In cloud architecture, networking, compute, data, deployment, reliability, security, scaling, cost, and operations are tightly interconnected. API/event contracts and ownership are the layer binding **design diagrams** to **actual behavior**: they state what each component promises, where those guarantees end, and who is accountable for keeping them.
