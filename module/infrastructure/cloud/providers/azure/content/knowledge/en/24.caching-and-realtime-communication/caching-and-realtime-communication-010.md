# Designing Live Notifications with Messaging and Caching

An e-commerce app needs to alert buyers the instant an order is paid, an online learning platform must push progress updates in real time, and an operations dashboard needs to alert the on-call shift about incidents. The requirement sounds simple: "when an event happens, push a notification to the browser." Yet what happens when the user is offline, a tab drops its WebSocket, the backend restarts, a worker processes a duplicate message, or the cache gets wiped?

A sound design separates four responsibilities:

1. **Message broker** transports events between services, absorbs load spikes, and supports retries per configured delivery mechanics.
2. **Durable notification store** persists notification state and history so clients can query missed items when they return.
3. **Cache** accelerates transient or hot reads: unread counts, presence, snapshots, and rate-limit state.
4. **Realtime gateway** pushes hints to currently online connections over WebSockets or supported application protocols.

This lesson belongs to the **Caching and Real-time Communication** chapter of the **CLOUD_PROVIDERS_AZURE** module. Along the Azure learning path from subscriptions, resource groups, and Microsoft Entra ID to networking, compute, storage, and data, this lesson brings application architecture together: service deployment, identity protection, monitoring, fault handling, and cost control.

Examples center on **Azure Service Bus**, **Azure Web PubSub** or **Azure SignalR Service**, **Azure Managed Redis** (alongside existing legacy Redis deployments), **Azure Cosmos DB for NoSQL** or **Azure SQL Database**, and **Java** applications. These services serve as reference building blocks rather than mandatory components for every single problem.

> **Core principle:** Pushing a WebSocket frame **never proves a user read it**, and writing to Redis **does not automatically provide durable storage**. Business events, persisted notification records, real-time push attempts, and read state are **independent states** that require explicit, consistent contracts.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **event**, **command**, **message**, **notification**, **real-time push**, **ACK**, and **read receipt**.
2. Define responsibility boundaries across Service Bus, Event Grid, Redis, Web PubSub/SignalR, and databases.
3. Design the workflow **transactional outbox → broker → notification worker → persistent inbox → push**.
4. Distinguish delivery guarantees: accepted by broker, persisted, accepted by real-time service, received by client, displayed, and read.
5. Model notification IDs, event IDs, tenant/user IDs, read status, timestamps, versions, and cursors.
6. Apply **cache-aside**, TTLs, and versioned invalidation to accelerate unread counts without treating the cache as truth.
7. Manage presence, multi-device connections, WebSocket reconnects, authentication, and notification authorization.
8. Design client reconnects, history sync, deduplication, and out-of-order event handling.
9. Handle retries, DLQs, duplicate deliveries, cache failures, gateway failures, quotas, and hot users/groups.
10. Write an idempotent Java worker and a cursor-syncing JavaScript client.
11. Estimate throughput, connection counts, fan-out, memory, networking, and operational costs.
12. Define metrics, SLOs, alerts, runbooks, and production chaos drills.

## 2. End-to-end scenario: order notifications

Consider a retail platform with three notification types:

- **OrderPaid:** when payment succeeds, notify the order owner.
- **ShipmentUpdated:** when shipping status changes, notify the order owner.
- **OperationalAlert:** when a payment gateway fails, notify the on-call operations team.

Requirements:

- Users viewing the website receive near-real-time alerts.
- One user signed in on mobile and two browser tabs receives alerts across all active connections.
- If offline for 30 minutes, notifications remain queryable after signing back in.
- Alerts carry stable IDs; clients never show duplicate cards just because WebSockets reconnected.
- Notification read APIs enforce tenant and user ownership.
- Authoritative notifications and read state are stored durably.
- Cache loss must never wipe notification history.
- The system absorbs traffic spikes and emits telemetry to diagnose faults.

Illustrative event:

~~~json
{
  "eventId": "evt-order-481-paid-1",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "tenantId": "tenant-hcm",
  "orderId": "order-481",
  "recipientUserId": "user-91",
  "occurredAtUtc": "2026-11-20T03:10:00Z",
  "correlationId": "corr-481"
}
~~~

This is synthetic test data. Never place payment card numbers, access tokens, passwords, or unnecessary personal data into brokers, caches, or logs.

## 3. Reference architecture

~~~mermaid
flowchart LR
    ORD["Orders API"] --> DBTX["Orders database<br/>transaction + outbox"]
    DBTX --> OUT["Outbox relay"]
    OUT --> BUS["Azure Service Bus<br/>topic / subscription"]
    BUS --> WORK["Notification worker<br/>Java / Functions / Container Apps"]
    WORK --> STORE["Durable notification inbox<br/>Cosmos DB / Azure SQL"]
    WORK --> DISPATCH["Notification delivery outbox"]
    DISPATCH --> PUSH["Azure Web PubSub<br/>or Azure SignalR Service"]
    PUSH --> WEB["Web / mobile clients<br/>online connections"]
    WEB --> API["Notifications API<br/>GET feed / PATCH read"]
    API --> CACHE["Azure Managed Redis<br/>unread, presence, throttling"]
    API --> STORE
    WORK -. "invalidate/update" .-> CACHE
    ID["Microsoft Entra ID<br/>identity / RBAC"] -. "auth" .-> ORD
    ID -. "auth" .-> API
    OBS["Azure Monitor / App Insights"] -. "traces / metrics" .-> WORK
    OBS -. "telemetry" .-> PUSH
~~~

A separate **delivery outbox** may be unnecessary for tiny prototypes; however, when reliable retries are needed after persisting a notification while the gateway is temporarily down, durable dispatch state prevents losing pushes to process restarts.

### 3.1. Component responsibilities

| Component | What it should guarantee | What never to expect from it |
|---|---|---|
| Orders DB + outbox | Persist business state and publish intent in one database transaction | Pushing WebSockets directly to browsers |
| Service Bus | Buffer/deliver messages to workers per retention, TTL, settlement, retry, and DLQ config | Proving end users read notifications |
| Notification store | Persist notifications, recipient ownership, read state, and cursors | Pushing real-time alerts automatically |
| Redis cache | Accelerate hot reads/presence/TTLs while tolerating cache misses | Holding the sole copy of non-losable notifications |
| Web PubSub / SignalR | Manage real-time connections and push frames to sockets/groups | Maintaining an offline inbox history like a database |
| Notifications API | Serve feeds, mark-read, enforce authorization and consistency | Trusting a browser-supplied `userId` |
| Client | Render, deduplicate, reconnect, call sync APIs | Deciding whether another user may view data |

### 3.2. Hot real-time path vs durable sync path

- **Real-time path:** pushes a lightweight "something changed" hint so active UIs react fast.
- **Reliable path:** clients call **GET notifications** to fetch persisted records and catch up after disconnects.
- **State path:** **PATCH mark-read** commits to the database first, then invalidates or version-updates the cache.

Where latency, throughput, and security allow, pushes may carry minimal display payloads. Even then, clients must still **resync from the durable store** upon reconnecting, spotting gaps, or suspecting delayed messages.

## 4. Concepts that must never be conflated

| Concept | Core meaning | Owner |
|---|---|---|
| **Domain event** | A business fact that occurred: `OrderPaid` | Domain producer |
| **Message** | Envelope carrying events/commands through a broker | Producer and broker |
| **Notification** | User/group-facing record with content and state | Notification service |
| **Push** | Sending a hint/payload over an online connection | Real-time gateway |
| **Presence** | Approximate estimate that a user has an active socket | Gateway / ephemeral cache |
| **Delivery attempt** | One attempt to push to the gateway/client | Dispatcher |
| **Gateway accepted** | Real-time service accepted the publish request | Gateway |
| **Client received** | Client app received and ran its callback | Client (if ACKed) |
| **Displayed** | UI rendered the notification | Client telemetry if instrumented |
| **Read** | User marked the item read per app contract | Durable store |
| **Unread count** | Projection/count derived from database state | Store is truth; Redis is cache |
| **Cursor** | Sync checkpoint for a user's feed | Notifications API / store |

State progression example:

~~~text
OrderPaid event → message accepted → notification persisted
→ realtime publish accepted → browser callback fired
→ UI rendered → user clicks "Mark as read"
~~~

Every arrow can fail or repeat. Never collapse all of these states into a single **`delivered=true`** flag.

## 5. Choosing an Azure messaging service

### 5.1. Azure Service Bus

**Azure Service Bus queues/topics/subscriptions** fit best when:

- Workers process messages asynchronously.
- You need **PeekLock**, Complete/Abandon, retries, `MaxDeliveryCount`, and DLQs.
- Multiple independent consumer types subscribe to one producer.
- You need topic filtering, session ordering, or duplicate detection per tier/config.
- **Resilient business processing** matters more than raw telemetry ingestion.

Example: **`OrderPaid`** publishes to a topic; Notification Worker's subscription reads it to write inbox rows, while another subscription feeds reporting/auditing.

### 5.2. Event Grid

**Azure Event Grid** fits when:

- Routing discrete event notifications like `BlobCreated`, Azure resource events, or domain events.
- Using push/pull delivery with retries/TTL/DLQ per supported topic/subscription type.
- One event fans out to multiple reactive handlers.

Event Grid carries distinct semantics. **Never replace core workflows needing PeekLock queues, sessions, or broker transactions with Event Grid** when those capabilities are central.

### 5.3. Storage Queue

**Azure Queue Storage** is a simpler choice for basic background jobs not needing advanced Service Bus features. Account for message size limits, visibility timeouts, poison message handling, and lack of native multi-consumer topic fan-out.

### 5.4. Azure Event Hubs

**Azure Event Hubs** targets high-throughput event streams, retention, and consumer groups—great for telemetry and clickstreams, without per-message PeekLock settlement or DLQs like Service Bus queues. Never choose Event Hubs just because your domain model uses the word "event".

### 5.5. Quick selection guide

| Need | Preferred choice |
|---|---|
| Order events needing reliable workers and DLQs | Service Bus |
| `BlobUpdated` triggering Functions | Event Grid |
| Simple background jobs with minimal routing | Storage Queue |
| Millions of telemetry events/hour with replay | Event Hubs |
| Push only to currently connected browsers | Real-time gateway (still add a store if offline access is needed) |
| Multiple distinct notification consumers | Service Bus topics/subscriptions or Event Grid per semantics |
| Ephemeral, loss-tolerant alerts in tiny systems | Minimal brokerless design acceptable only with explicit risk sign-off |

## 6. Redis is a cache, not durable notifications

On Azure, evaluate **Azure Managed Redis** for new architectures. For systems still running **Azure Cache for Redis**, verify product lifecycles, support timelines, compatibility, and migration plans rather than assuming identical SKUs or features.

Redis helps by:

- Caching recent **notification previews** with short TTLs.
- Caching **unread counts** derived from the durable store.
- Holding **presence heartbeats** and ephemeral connection hints per policy.
- Enforcing notification rate limits and throttling counters.
- Absorbing repeated database reads during traffic spikes.

Redis **must never** be the sole store for critical notifications when offline retrieval, auditing, user read state, or long-term recovery is required.

### 6.1. Redis Pub/Sub vs durable message brokers

Redis **Pub/Sub** delivers only to currently listening subscribers. Pub/Sub frames do not form a replayable durable queue. If a client or worker disconnects at publish time, never assume it can retrieve missed messages afterward.

Redis **Streams** offer an append-only log and consumer groups unlike Pub/Sub. They can fit separately evaluated workloads, yet if your architecture already uses Service Bus for reliable events, adding Redis Streams as a second broker introduces unnecessary operational state.

**Rule:** Service Bus transports business messages; Redis accelerates hot reads and short-lived state; Web PubSub/SignalR pushes updates over WebSockets.

### 6.2. Cache entries can disappear anytime

Common causes:

- Key TTL expires.
- Redis fails over or restarts.
- Memory pressure/eviction policy drops keys.
- Cache invalidation lags.
- A deployment flushes keys by mistake.
- Network connectivity to Redis blips.

**A cache miss is normal**, never an excuse to lose unread counts or notification history. APIs must fall back to the durable store (or surface errors per SLO) rather than falsely reporting "you have zero notifications".

## 7. Choosing Web PubSub, SignalR, or polling

### 7.1. Azure Web PubSub

**Azure Web PubSub** is a managed service for WebSocket connectivity and routing across hubs, groups, and users with service-supported event handlers.

Fits when:

- Web/mobile clients speak WebSockets directly.
- Java, .NET, JavaScript, or polyglot backends push to users/groups.
- You want to offload WebSocket fleets, connection scaling, and fan-out.
- Clients need clean reconnects and structured payloads.

### 7.2. Azure SignalR Service

**Azure SignalR Service** fits apps built on **ASP.NET Core SignalR** or supported SignalR client/server ecosystems, offering managed connections and SignalR scale-out.

**SignalR and raw WebSockets do not share the same protocol contract.** Never stand up a SignalR Hub and point plain browser WebSocket code at it as if it were Web PubSub without the SignalR protocol/SDK.

### 7.3. Server-Sent Events and polling

- **SSE (Server-Sent Events):** server → browser HTTP stream; suitable for one-way feeds. Plan reconnects, proxy buffering, scaling, and token handling.
- **Long polling:** client holds an open HTTP request until data or timeout; easy to integrate, yet increases request volume and latency.
- **Periodic polling:** client calls `GET /notifications` every N seconds; simple and often sufficient for small user bases without sub-second urgency.

Do not force WebSockets onto every screen simply because "real-time sounds modern".

### 7.4. Decision table

| Scenario | Recommended choice | Trade-off |
|---|---|---|
| Low-traffic dashboard updating every 30s | Polling / SSE | Simple, few persistent socket states |
| 100,000 clients needing near-real-time push | Web PubSub / managed real-time | Reconnects, auth, connection limits/cost |
| Existing ASP.NET Core SignalR hubs | Azure SignalR Service | Coupled to SignalR protocol/SDKs |
| Java backend pushing to browsers without SignalR | Azure Web PubSub | Requires explicit auth/negotiate and payload contract |
| Mobile OS background/offline alerts | APNs/FCM/platform push + durable inbox | WebSockets rarely survive background app suspension |
| Workflows needing legal email/SMS records | Dedicated notification provider / Logic Apps + audit | WebSockets never replace out-of-band channels |

## 8. Defining the notification contract

Never push raw domain events to clients and force browsers to guess business semantics.

### 8.1. Durable notification object

~~~json
{
  "id": "notif-tenant-hcm-user-91-order-481-paid-v1",
  "tenantId": "tenant-hcm",
  "recipientUserId": "user-91",
  "sourceEventId": "evt-order-481-paid-1",
  "type": "ORDER_PAID",
  "schemaVersion": 1,
  "title": "Order paid",
  "body": "Your order payment has been confirmed.",
  "link": "/orders/order-481",
  "createdAtUtc": "2026-11-20T03:10:03Z",
  "readAtUtc": null,
  "expiresAtUtc": null
}
~~~

**`id`** should be deterministic or written once with a deduplication mapping for the same business notification. Avoid embedding sensitive personal information inside IDs.

### 8.2. Separating business events from notifications

One **`OrderPaid`** event can generate:

- A customer notification.
- An assigned merchant/staff notification.
- A financial reporting event.
- An email receipt if business rules require it.

**One domain event does not equal one notification.** Deciding recipients, channels, templates, and priority belongs to the Notification Service.

### 8.3. Keys that enable idempotency

| Key | Role |
|---|---|
| **`eventId`** | Deduplicates producer-emitted domain events |
| **`notificationId`** | Uniquely identifies one notification for one recipient |
| **`tenantId`** | Business tenant isolation boundary |
| **`recipientUserId`** | Identifies the target inbox owner |
| **`dispatchAttemptId`** | Audits an individual real-time push attempt |
| **`correlationId / traceId`** | End-to-end distributed tracing |
| **`cursor`** | Feed sync checkpoint |
| **`schemaVersion`** | Governs payload contract evolution |

One `eventId` can fan out into many `notificationId`s; never put a table-wide unique constraint on `eventId` alone when an event targets multiple recipients.

### 8.4. Delivery state vs read state

Illustrative state model:

~~~text
Notification:
    CREATED → AVAILABLE → READ/ARCHIVED

Delivery attempt:
    PENDING → PUBLISH_ATTEMPTED → GATEWAY_ACCEPTED/FAILED

Client state:
    CONNECTED → RECEIVED → DISPLAYED (optional telemetry)

Business acknowledgement:
    UNREAD → READ
~~~

Never collapse **`GATEWAY_ACCEPTED`** into **`READ`**. Pushing a frame to a socket does not mean a human saw the screen.

## 9. Persistent inbox: Azure SQL vs Cosmos DB

### 9.1. Azure SQL

Illustrative schema:

~~~sql
-- Directional DDL pseudocode; design real constraints and indexes for your workload.
CREATE TABLE Notifications (
    NotificationId VARCHAR(160) PRIMARY KEY,
    TenantId VARCHAR(80) NOT NULL,
    RecipientUserId VARCHAR(80) NOT NULL,
    NotificationType VARCHAR(80) NOT NULL,
    SourceEventId VARCHAR(160) NOT NULL,
    CreatedAtUtc DATETIME2 NOT NULL,
    ReadAtUtc DATETIME2 NULL,
    PayloadJson NVARCHAR(MAX) NOT NULL
);

CREATE INDEX IX_Notifications_Recipient_Time
ON Notifications (TenantId, RecipientUserId, CreatedAtUtc DESC);
~~~

Add a unique constraint on **tenant + recipient + event + notification type**, and plan retention/partitioning for scale. SQL transactions allow committing the notification alongside a **delivery-outbox record** in the same database atomically.

### 9.2. Azure Cosmos DB for NoSQL

Each JSON item represents a notification. For the access pattern "fetch feed for one user in a tenant", choose a partition key supporting distribution and queries—such as **`/inboxKey`** (`tenantId + userId`) or a supported hierarchical partition key.

~~~json
{
  "id": "notif-481-paid",
  "inboxKey": "tenant-hcm:user-91",
  "tenantId": "tenant-hcm",
  "recipientUserId": "user-91",
  "type": "ORDER_PAID",
  "sourceEventId": "evt-order-481-paid-1",
  "createdAtUtc": "2026-11-20T03:10:03Z",
  "readAtUtc": null
}
~~~

**Watch for hot users:** a shared organization account receiving millions of alerts can overheat one logical partition. For massive tenant/group broadcasts, avoid writing millions of redundant per-user items unnecessarily—and never pick a low-cardinality partition key like **`/read`**.

### 9.3. Read patterns

| API | Known inputs | Storage design |
|---|---|---|
| `GET /notifications` | `tenantId`, `userId`, `limit`, `cursor` | Indexed query inside inbox partition |
| `GET /notifications/unread-count` | `tenantId`, `userId` | Store query/projection with cache-aside |
| `PATCH /notifications/{id}/read` | `tenantId`, `userId`, `id` | Conditional update enforcing ownership |
| `GET /notifications?since=cursor` | Tenant/user/cursor | Keyset pagination or server cursor |
| `GET /notifications/{id}` | Tenant/user/id | Point read / scoped key query |
| Admin audit | Filter by event/source/tenant | Dedicated index or materialized audit view |

### 9.4. Pagination and cursors

Never rely solely on **`OFFSET 100000`** for a live-updating feed. In SQL, use keyset pagination on **`(CreatedAtUtc, NotificationId)`** with a matching index; in Cosmos DB, use SDK continuation tokens or query-compatible cursors.

Never use browser **`Date.now()`** as the sole sync marker: client clocks drift, multiple items share timestamps, and reconnects skew arrival order.

Reliable client sync requires a **server-managed durable cursor** with consistent tie-breaking—often an opaque versioned token updated whenever schemas or queries change.

## 10. Transactional outbox: preventing lost domain events

Suppose the Orders API does:

~~~text
INSERT/UPDATE Orders in Azure SQL
then SEND OrderPaid to Service Bus
~~~

If the app crashes after DB commit and before broker send, the order is PAID with no notification. If the broker accepted the message while the HTTP response dropped, a producer retry sends a duplicate.

### 10.1. Saving business mutations and outbox records in one transaction

~~~mermaid
flowchart TD
    API["Orders API"] --> TX["SQL transaction"]
    TX --> ORD["Orders: status=PAID"]
    TX --> OUT["Outbox: OrderPaid event"]
    OUT --> RELAY["Outbox relay/publisher"]
    RELAY --> SB["Service Bus topic"]
    SB --> NWORK["Notification consumer"]
~~~

Workflow:

1. Write the Order state change and Outbox row in the **same DB transaction**.
2. Commit.
3. Outbox publisher polls/reads unpublished rows.
4. Sends a Service Bus message with a stable **`MessageId`**.
5. Once the broker acknowledges, mark the outbox row published.
6. On a crash between steps 4 and 5, the publisher resends; consumers handle duplicates idempotently.

**A transactional outbox does not turn HTTP calls, Service Bus, and the DB into one distributed ACID transaction.** It durably persists publish intent and delivers **at-least-once publication** paired with deduplication.

### 10.2. Persisting notifications and the delivery outbox

After receiving the Service Bus message, the notification worker can:

1. Resolve authorized recipients from trusted data.
2. In **one notification database transaction**, insert the notification if absent and insert a **delivery-outbox** record.
3. Commit the DB transaction.
4. Complete the Service Bus message.
5. A separate dispatcher claims delivery-outbox jobs, pushes via Web PubSub/SignalR, and updates attempt state.

If the worker crashes after DB commit before **Complete**, Service Bus redelivers the message, and unique constraints / conditional upserts prevent duplicate inbox rows. If the dispatcher crashes after pushing before marking dispatched, clients may receive a duplicate frame; **clients deduplicate by `notificationId`**.

Never hold a long SQL transaction open across a WebSocket gateway HTTP call chasing "exactly-once push": the gateway is outside that transaction.

## 11. Service Bus topics, subscriptions, retries, and DLQs

Illustrative layout:

~~~text
Topic: commerce-events

Subscription: notifications
    Filter: OrderPaid, ShipmentUpdated

Subscription: analytics
    Filter: matching domain events

Notification consumer:
    PeekLock → durable inbox + delivery outbox → Complete

On transient error:
    Retry / Abandon / backoff per policy

On malformed / unprocessable event:
    Dead-letter with reason + correlation
~~~

### 11.1. Why use `PeekLock`?

With **`PeekLock`**, the consumer locks and reads a message without deleting it from the subscription. It calls **`Complete`** only after durable persistence succeeds, or settles via retry/DLQ on errors.

With **`ReceiveAndDelete`**, the broker deletes the message upon delivery per service semantics—losing the event forever if the worker crashes before DB commit.

### 11.2. Retries and idempotency

- Bound retries and separate transient from permanent errors.
- Set a deterministic **`MessageId`**; if enabling duplicate detection, understand its dedup time window.
- Enforce idempotency inside the notification DB too, rather than trusting broker deduplication alone.
- Configure **`MaxDeliveryCount`** so poison messages move cleanly to the DLQ.
- Never let one broken message spin endlessly and starve the consumer.
- During a full database outage, throttle or pause consumers instead of dead-lettering millions of valid messages.

### 11.3. Are Service Bus Sessions required?

Service Bus **Sessions** serialize processing per **`SessionId`** (such as `orderId`) when entities/tiers enable sessions.

Keep in mind:

- Sessions cap concurrency/throughput per hot session.
- They do not enforce global ordering across distinct users or orders.
- Real-time gateways and the Internet can still reorder frames reaching clients.
- Even with sessions, clients still need IDs, versions, and resyncs.

Enable sessions only when strict sequential per-entity processing is truly needed.

### 11.4. Recipient fan-out

When one event targets 100,000 recipients:

- Never run 100,000 DB writes and real-time pushes inside one long broker lock.
- Split work into **fan-out batches** with checkpoints, idempotency, and bounded concurrency.
- For general announcements not needing per-user inbox records, store one shared **announcement** paired with membership and per-user read cursors.
- For mandatory per-user alerts, persist per-recipient state while managing backlogs, TTLs, quotas, and costs.

## 12. Cache-aside for unread counts and feed previews

### 12.1. Namespaced cache keys

Examples:

~~~text
notif:unread:v1:tenant-hcm:user-91
notif:preview:v1:tenant-hcm:user-91
presence:v1:tenant-hcm:user-91
ratelimit:v1:tenant-hcm:user-91:minute
~~~

Avoid putting emails, phone numbers, or raw tokens in Redis keys since key names surface in telemetry, backups, and operations tools. If user IDs are sensitive, use opaque surrogate IDs or managed HMAC hashes.

### 12.2. Unread count cache-aside

~~~mermaid
flowchart TD
    API["GET /notifications/unread-count"] --> C{"Redis key exists?"}
    C -->|Yes| HIT["Return cached count<br/>per freshness contract"]
    C -->|No| DB["Query/projection from durable store"]
    DB --> SET["Cache SET with TTL"]
    SET --> RESP["Return count"]
~~~

Steps:

1. API authenticates the caller and verifies tenant/user ownership.
2. Checks Redis for the key.
3. On hit, returns cached value per freshness SLO.
4. On miss, computes count from the database/projection.
5. Writes cache with a TTL and returns the result.
6. On new notifications or mark-read, invalidates or conditionally updates the key.

**Redis counts are never the source of truth.** Keys can vanish, drift, or go stale; APIs must fall back cleanly and define staleness tolerance.

### 12.3. Why never `INCR`/`DECR` blindly?

Suppose Service Bus delivers one event twice:

~~~text
Notification N1 is persisted exactly once
Worker attempt 1 → Redis INCR unread
Worker crashes before Complete
Worker attempt 2 → Redis INCR unread a second time
~~~

The database holds 1 unread notification, yet Redis returns 2.

Fixes:

- Update cache counters only when a **brand-new insert** occurs or state transitions `UNREAD → READ`.
- Enforce idempotency in both DB and cache update logic.
- Simpler and safer: **invalidate** the key after DB commit so the next read recomputes from the store.
- At very high scale, maintain a durable versioned projection/counter and cache snapshots.
- Periodically reconcile cached counts against the database.

### 12.4. Race between cache refill and invalidation

A classic race:

~~~text
T1 API reads count=5 from DB (before N6 inserts)
T2 Worker inserts N6 and deletes cache key
T3 API writes count=5 into Redis after the delete
Result: Redis serves stale count=5 until TTL expires
~~~

This is a real production race. Mitigations by strictness:

- Keep TTL short and accept eventual consistency for badges.
- Use a **versioned cache** tied to a DB projection version.
- Use atomic compare-and-set via Redis Lua/transactions where appropriate.
- Maintain read-through projections ordered by sequence/version.
- Never overwrite Redis with an older version.
- If badges require immediate exact accuracy, read directly from the DB or a strongly consistent durable projection.

Never rely on best-effort cache invalidation callbacks to guarantee accuracy for financial figures.

## 13. Presence and multiple connections per user

One user can have:

~~~text
user-91:
    Browser tab A
    Browser tab B
    Mobile foreground session C
~~~

Treat presence strictly as an **online estimate**, never absolute truth.

### 13.1. Heartbeat with TTL

Illustrative design:

- Clients send a heartbeat every **15 seconds** while connected.
- Backend/gateway sets a presence TTL of **45 seconds** (illustrative numbers).
- Without heartbeats, the key expires automatically.
- Reconnects create new connections; disconnect events can lag.
- Never skip persisting a notification based on presence status.

**Heartbeat and TTL intervals are design assumptions** that must be tested across mobile networks, browser tab throttling, and real gateway disconnect delays.

### 13.2. Connection IDs are not durable identities

- Connection IDs change on every reconnect.
- One user holds multiple connection IDs.
- Connection tokens carry finite lifetimes and scopes.
- Never store a `connectionId` as a foreign key on notification history.
- Grouping real-time sockets by **tenant + recipient** or managed user identity simplifies publishing under server-side authorization.
- Lock down group membership—never let clients join `admin-alerts` on their own.

### 13.3. When the gateway already tracks connections

Azure Web PubSub and SignalR track connections and groups internally per product design. Do not mirror the entire connection registry into Redis if you only need to push alerts and the gateway already supports send-to-user/group. Store Redis presence only when the app has a clear feature need (such as "who's online"), accepting stale edge cases.

### 13.4. Never confuse "online" with "received"

Even if the gateway shows an active socket for a user:

- The client may have just dropped connectivity.
- A background tab hasn't rendered the UI.
- A mobile OS suspended the app.
- The user isn't viewing the notifications drawer.
- A frame may arrive duplicated or out of order.

Therefore **presence must never serve as a condition to delete inbox records**.

## 14. Connection negotiation and real-time security

With Web PubSub or SignalR, clients typically obtain connection URLs/tokens from a trusted backend per SDK/service design.

Illustrative protocol flow:

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant A as Notifications API
    participant I as Entra ID / Auth
    participant G as Realtime gateway
    U->>A: POST /realtime/negotiate + access token
    A->>I: Validate identity/claims
    I-->>A: tenantId + userId
    A->>G: Create limited-time client access URL/token
    G-->>A: Scoped connection URL
    A-->>U: Connection URL with short expiry
    U->>G: Connect WebSocket over TLS
    G-->>U: Connected
    U->>A: GET /notifications?cursor=...
    A-->>U: Durable feed snapshot
~~~

This is a **conceptual flow**; exact endpoints and SDK calls depend on the chosen product and SDK.

### 14.1. Never grant arbitrary send permissions

Clients only need to **receive their own notifications**. Tokens/roles minted for browsers must not allow publishing to arbitrary groups, reading other tenants' groups, or joining unverified admin groups.

### 14.2. Backend derives identity from verified tokens

Never do:

~~~text
POST /realtime/negotiate
{"userId":"ceo"}
→ mints token for user=ceo
~~~

Do this instead:

~~~text
Validated access token → trusted tenantId/userId
→ server resolves authorized group/user mapping
→ mints least-privilege token with short TTL
~~~

### 14.3. Sensitive data in connection URLs

Access URLs/tokens can leak into logs, browser history, diagnostics, or proxies if handled carelessly. Enforce:

- TLS/WSS everywhere.
- Short-lived tokens; never expose server access keys.
- Suppress logging of token-bearing query strings.
- CORS/origin restrictions per product and gateway settings.
- Tight TTLs and scopes with safe refresh/reconnect.
- Avoid storing access tokens in Redis or `localStorage` if forbidden by security policy.

### 14.4. Tenant isolation

A bare name like **`user-91`** can collide across tenants. Include **tenant scope** in user/group mappings alongside backend authorization:

~~~text
group = "tenant-hcm:user-91"
group = "tenant-hn:user-91"
~~~

Group names are **routing aids**, never a replacement for authorization checks in the Notifications API.

## 15. Client protocol: push + resync

### 15.1. API design

~~~text
POST  /realtime/negotiate
GET   /notifications?limit=50&cursor=<opaque-cursor>
GET   /notifications/unread-count
PATCH /notifications/{notificationId}/read
POST  /notifications/read-all
~~~

Sample response:

~~~json
{
  "items": [
    {
      "id": "notif-481-paid",
      "type": "ORDER_PAID",
      "title": "Order paid",
      "createdAtUtc": "2026-11-20T03:10:03Z",
      "readAtUtc": null,
      "link": "/orders/order-481"
    }
  ],
  "nextCursor": "opaque-cursor-issued-by-server",
  "hasMore": false,
  "unreadCount": 1,
  "snapshotVersion": "v-9381"
}
~~~

Never ship a homemade cursor lacking versions or tie-breakers to production assuming it preserves total order across regions.

### 15.2. Lean server pushes, client fetches authoritative data

Minimal real-time frame:

~~~json
{
  "type": "NOTIFICATION_AVAILABLE",
  "notificationId": "notif-481-paid",
  "recipientVersion": "v-9381",
  "emittedAtUtc": "2026-11-20T03:10:04Z"
}
~~~

The client can:

1. Receive the push.
2. Deduplicate `notificationId`.
3. Call `GET` feed or fetch by ID with an authorized token.
4. Update the badge and notification list.
5. Advance its cursor only after merging items into local state.
6. Always resync on reconnect rather than merely waiting for new pushes.

If a push includes full display fields, the UI can render immediately to shave latency while keeping the **backend store as the synchronization authority**.

### 15.3. Two orderings can diverge

- Notification A commits before B in the database.
- The gateway might deliver B before A due to retries, reconnects, or multiple dispatch workers.
- Clients must sort by server-issued stable ordering and compare versions.
- **READ** state must never be overwritten back to **UNREAD** by an older delayed push.
- Systems should not promise global cross-user ordering unless genuinely required.

## 16. Syncing when clients go offline or reconnect

WebSockets deliver hints only to **currently live connections**. When users lose connectivity, close tabs, or suspend mobile apps, the architecture needs a **durable inbox resync path**.

### 16.1. Reconnect workflow

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Notifications API
    participant G as Web PubSub
    participant D as Durable inbox
    C->>A: Authenticate + POST /realtime/negotiate
    A-->>C: Short-lived, scoped WebSocket URL
    C->>G: WebSocket connect
    G-->>C: Connected
    C->>A: GET /notifications?cursor=...
    A->>D: Query authorized user inbox
    D-->>A: Page + cursor + version
    A-->>C: Durable notification items
    C->>C: Merge / dedup by notificationId
    G-->>C: NOTIFICATION_AVAILABLE hint
    C->>A: Fetch new items
~~~

**Connecting and immediately running a GET sync** is safer than waiting passively for pushes. If a push arrives mid-GET, the client might see an item twice—merge cleanly by **`notificationId`**. If a push arrives while a sync is already running, set **`syncPending`** and run another pass rather than dropping the hint.

### 16.2. Cursors and time sources

- Never use browser **`Date.now()`** as the sole sync cursor.
- Use **backend-issued order markers** with tie-breakers for same-timestamp rows.
- SQL supports **keyset pagination** on stable sort keys; Cosmos DB supports query/partition continuation tokens.
- In multi-region setups, check consistency and sequence generation rather than treating one machine's clock as a global sequence.
- Scope cursors by **user, tenant, query, and schema version** so callers cannot reuse another user's cursor to leak data.
- For multi-page syncs, persist cursor progress only after pages merge cleanly—never mark sync complete while **`hasMore=true`**.

### 16.3. Multiple tabs and devices

Three active sockets for one user receive the same alert. `READ`/`UNREAD` state typically lives **shared in the backend** unless product rules require per-device state. Marking read on Tab B should propagate to Tab A; pushes speed this up, while APIs/reconnects keep state authoritative.

### 16.4. Mobile push differs from WebSockets

Background or powered-off mobile apps drop WebSockets. For out-of-app alerts, integrate **APNs/FCM** or platform push providers, managing device tokens, opt-ins, privacy, and retries—while keeping the durable inbox as the authority when users open the app.

## 17. Java: idempotent Service Bus message processing

Processing pattern:

~~~text
Service Bus: OrderPaid (PeekLock)
→ validate schema + business recipient
→ transaction in Notification DB:
      INSERT notification IF ABSENT
      INSERT delivery-outbox IF NEW
  COMMIT
→ Complete Service Bus message
→ Separate dispatcher processes delivery-outbox
~~~

### 17.1. Domain types and repository

~~~java
package example.notifications;

public record OrderPaidEvent(
        String eventId,
        String tenantId,
        String orderId,
        String recipientUserId) {}

public record Notification(
        String notificationId,
        String tenantId,
        String recipientUserId,
        String sourceEventId,
        String orderId,
        String type) {}

public interface NotificationRepository {
    /**
     * Single database transaction:
     * - Insert notification by unique notificationId if absent.
     * - Only when newly inserted, insert a delivery-outbox record.
     * - Commit both or roll back both.
     *
     * Returns true if newly created; false if the event was already processed.
     */
    boolean insertNotificationAndDispatchIntentIfAbsent(
            Notification notification);
}
~~~

These three Java types belong in their respective project files alongside a JDBC/Cosmos implementation. **Database unique constraints**, not an in-RAM **`Set`**, enforce deduplication across scaled-out workers.

### 17.2. Handler decoupled from transport

~~~java
package example.notifications;

public final class OrderPaidHandler {
    private final NotificationRepository repository;

    public OrderPaidHandler(NotificationRepository repository) {
        this.repository = repository;
    }

    public boolean handle(OrderPaidEvent event) {
        if (event == null || blank(event.eventId())
                || blank(event.tenantId())
                || blank(event.orderId())
                || blank(event.recipientUserId())) {
            throw new IllegalArgumentException("Invalid event");
        }

        String notificationId =
            "order-paid:" + event.tenantId() + ":"
            + event.recipientUserId() + ":" + event.eventId();

        Notification item = new Notification(
            notificationId,
            event.tenantId(),
            event.recipientUserId(),
            event.eventId(),
            event.orderId(),
            "ORDER_PAID");

        return repository
            .insertNotificationAndDispatchIntentIfAbsent(item);
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

Concatenating fields into an ID is illustrative. Production systems can hash a canonical business key to avoid leaking details, cap length, and enforce uniqueness in the DB.

### 17.3. Service Bus processor skeleton

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusProcessorClient;

import java.util.concurrent.CountDownLatch;

// Initialize via dependency injection.
OrderPaidHandler handler = /* repository-backed handler */ null;

ServiceBusProcessorClient processor =
    new ServiceBusClientBuilder()
        .credential(
            System.getenv("SERVICEBUS_FQDN"),
            new DefaultAzureCredentialBuilder().build())
        .processor()
        .topicName("commerce-events")
        .subscriptionName("notifications")
        .disableAutoComplete()
        .processMessage(context -> {
            try {
                // parseValidatedEvent must be implemented by your app.
                OrderPaidEvent event =
                    parseValidatedEvent(context.getMessage());

                handler.handle(event);
                // Complete only after durable DB commit succeeds.
                context.complete();
            } catch (IllegalArgumentException badPayload) {
                // Dead-letter with reason via matching SDK API
                // and record correlation/diagnostics.
                settlePermanentFailure(context, badPayload);
            } catch (Exception transientFailure) {
                // Retries/backoff must be bounded.
                context.abandon();
            }
        })
        .processError(error ->
            System.err.println(error.getThrowable()))
        .buildProcessorClient();

Runtime.getRuntime().addShutdownHook(
    new Thread(processor::close));
processor.start();
new CountDownLatch(1).await();
~~~

**This is skeleton code, not directly runnable**: add domain imports, **`parseValidatedEvent`**, **`settlePermanentFailure`**, repository adapters, and an injected handler. Pin SDK packages/APIs to your exact version. During prolonged outages, avoid tight `abandon()` hot loops—pause consumers, use circuit breakers, or schedule bounded retries.

### 17.4. Crash window matrix

| Crash point | Outcome | Recovery |
|---|---|---|
| Before DB commit | Broker has not Completed message | Worker redelivers and processes |
| Inside DB transaction | DB rolls back or outcome verified | Retry + idempotency |
| After DB commit, before Complete | Inbox/outbox saved; broker redelivers | Unique key prevents duplicate insert |
| After Complete, before push | Delivery outbox stays pending | Dispatcher picks up and pushes |
| After push, before mark-dispatched | Dispatcher may push again | Client deduplicates on `notificationId` |

Never promise "exactly-once WebSocket delivery". Aim for **durable at-least-once processing**, idempotent notification identity, and client convergence.

## 18. Dispatcher: pushing is its own retryable task

### 18.1. Decoupling the gateway interface from domain logic

~~~java
package example.notifications;

public interface RealtimePublisher {
    /**
     * Minimal push to the backend-authorized user/group.
     * Success = gateway accepted the request per adapter,
     * NOT that the client read it.
     */
    void publishToUser(
            String tenantId,
            String userId,
            String notificationId,
            String payloadJson);
}

public record DeliveryJob(
        String deliveryId,
        String tenantId,
        String userId,
        String notificationId,
        String payloadJson,
        int attempts) {}

public interface DeliveryOutboxRepository {
    DeliveryJob claimNextReady(String workerId);
    void markGatewayAccepted(String deliveryId);
    void scheduleRetry(String deliveryId, long nextAttemptEpochMs);
    void markNeedsReview(String deliveryId, String reason);
}
~~~

The **`RealtimePublisher`** adapter can wrap the Azure Web PubSub server SDK/REST API or Azure SignalR SDK per environment, authenticating via managed identity or service credentials—**never exposing service keys to frontends**.

### 18.2. Retry pseudocode

~~~text
loop:
    job = outbox.claimNextReady(workerId) # atomic claim/lease
    if job is null: wait with jitter

    try:
        gateway.publishToUser(job.tenantId, job.userId,
                              job.notificationId, job.payloadJson)
        outbox.markGatewayAccepted(job.deliveryId)
    catch transient error / throttling:
        outbox.scheduleRetry(job.deliveryId,
                             exponentialBackoffWithJitter())
    catch permanent invalid payload / authorization:
        outbox.markNeedsReview(job.deliveryId, reason)
~~~

Key design concerns:

- Claiming jobs must be concurrency-safe across multiple dispatchers.
- Never keep DB transactions open during HTTP calls to the gateway.
- Enforce retry caps, lease/visibility timeouts, and idempotency.
- If the gateway accepted a push yet the HTTP response dropped, a retry emits a duplicate frame.
- Marking dispatched means only **`gateway accepted`**.
- Keep pushed payloads lean; sensitive details load via the authenticated Notifications API.
- Rate-limit dispatch per user/group to prevent push floods.

## 19. Java cache-aside unread counts

### 19.1. Interfaces

~~~java
package example.notifications;

import java.time.Duration;
import java.util.OptionalLong;

public interface UnreadStore {
    long countUnread(String tenantId, String userId);
    boolean markReadIfUnread(
            String tenantId, String userId, String notificationId);
}

public interface NotificationCache {
    OptionalLong getCount(String key);
    void putCount(String key, long count, Duration ttl);
    void invalidate(String key);
}
~~~

**`markReadIfUnread`** must enforce recipient ownership in the database query—never update unconditionally by `notificationId` alone.

### 19.2. Cache-aside service

~~~java
package example.notifications;

import java.time.Duration;
import java.util.OptionalLong;

public final class UnreadCountService {
    private final UnreadStore store;
    private final NotificationCache cache;

    public UnreadCountService(
            UnreadStore store, NotificationCache cache) {
        this.store = store;
        this.cache = cache;
    }

    public long count(String tenantId, String userId) {
        String key = cacheKey(tenantId, userId);

        try {
            OptionalLong hit = cache.getCount(key);
            if (hit.isPresent()) return hit.getAsLong();
        } catch (RuntimeException ignored) {
            // Emit controlled metric/log.
        }

        long value = store.countUnread(tenantId, userId);
        try {
            cache.putCount(key, value, Duration.ofSeconds(30));
        } catch (RuntimeException ignored) {
            // Still serve from DB when cache is down.
        }
        return value;
    }

    public boolean markRead(
            String tenantId, String userId, String notificationId) {
        boolean changed = store.markReadIfUnread(
                tenantId, userId, notificationId);

        if (changed) {
            try {
                cache.invalidate(cacheKey(tenantId, userId));
            } catch (RuntimeException ignored) {
                // TTL bounds stale entries; if strict freshness
                // is required, use a versioned projection.
            }
        }
        return changed;
    }

    private static String cacheKey(String tenantId, String userId) {
        return "notif:unread:v1:" + tenantId + ":" + userId;
    }
}
~~~

This pattern provides **eventual consistency**; refill/invalidation races can still occur. Products needing strictly exact unread counts right after mark-read must use DB-first reads or conditional versioned caches—never claim a 30s TTL delivers strong consistency.

### 19.3. Redis implementation considerations

- Connection pooling, TLS, DNS/private networking, and service/SDK auth.
- Short timeouts and circuit breakers so cache faults never sink the API.
- TTL jitter when stampede prevention is needed.
- Never run full-keyspace scans in production just to locate one user.
- Redis evictions/restarts lose keys; rebuild cleanly from the DB.
- Never run blind Redis `INCR`/`DECR` inside retry loops.
- Align cache payloads with data classification; keep PII out of Redis keys and logs.

## 20. Browser JavaScript: reconnect, deduplication, and resync

A Web PubSub client can use native WebSockets when the server returns a compatible URL/token and the hub supports the protocol. This example assumes illustrative backend APIs and omits UI rendering and auth token refresh.

~~~javascript
class NotificationClient {
  constructor() {
    this.socket = null;
    this.stopped = false;
    this.reconnectAttempt = 0;
    this.cursor = null;
    this.items = new Map();
    this.syncing = false;
    this.syncPending = false;
  }

  async start() {
    this.stopped = false;
    await this.connect();
  }

  async connect() {
    if (this.stopped) return;
    try {
      // Backend authenticates via session or access token.
      const response = await fetch("/realtime/negotiate", {
        method: "POST",
        credentials: "include"
      });
      if (!response.ok) throw new Error("Negotiate failed");

      const { url } = await response.json();
      const socket = new WebSocket(url);
      this.socket = socket;

      socket.onopen = () => {
        this.reconnectAttempt = 0;
        this.requestSync();
      };
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "NOTIFICATION_AVAILABLE"
              || msg.type === "NOTIFICATION_READ") {
            this.requestSync();
          }
        } catch (_) {
          console.error("Invalid realtime payload");
        }
      };
      socket.onclose = () => this.scheduleReconnect();
      socket.onerror = () => {
        try { socket.close(); } catch (_) {}
      };
    } catch (_) {
      this.scheduleReconnect();
    }
  }

  requestSync() {
    this.syncPending = true;
    if (!this.syncing) this.syncFromStore();
  }

  async syncFromStore() {
    this.syncing = true;
    try {
      while (this.syncPending) {
        this.syncPending = false;
        let cursor = this.cursor;
        let hasMore = true;

        // Lab caps at 20 pages; production must continue
        // accurately via continuation/state while hasMore is true.
        for (let pageNo = 0; pageNo < 20 && hasMore; pageNo++) {
          const query = new URLSearchParams({ limit: "50" });
          if (cursor) query.set("cursor", cursor);

          const response = await fetch(
            "/notifications?" + query.toString(),
            { credentials: "include" }
          );
          if (!response.ok) throw new Error("Feed sync failed");

          const page = await response.json();
          for (const item of page.items) {
            const old = this.items.get(item.id);
            if (!old || (item.revision ?? 0) >=
                         (old.revision ?? 0)) {
              this.items.set(item.id, item);
            }
          }
          cursor = page.nextCursor;
          hasMore = page.hasMore;
        }

        // Pages fetched above merged cleanly, so advance checkpoint.
        // While hasMore remains true, the next pass MUST advance from the new cursor
        // instead of re-reading the first 20 pages endlessly.
        this.cursor = cursor;
        if (hasMore) {
          this.syncPending = true;
          // Yield event loop; production needs a bounded paging budget.
          await new Promise(resolve => setTimeout(resolve, 50));
        }

        this.render();
      }
    } catch (error) {
      console.error("Cannot sync notifications", error);
    } finally {
      this.syncing = false;
    }
  }

  scheduleReconnect() {
    if (this.stopped) return;
    const delayBase = Math.min(
      30000, 1000 * 2 ** Math.min(this.reconnectAttempt++, 5)
    );
    const delay = delayBase * (0.5 + Math.random());
    setTimeout(() => this.connect(), delay);
  }

  render() {
    // Escape title/body and validate links. Never render raw HTML.
    console.info("Notifications", this.items.size);
  }

  stop() {
    this.stopped = true;
    if (this.socket) this.socket.close();
  }
}
~~~

**Limitations of this snippet:** omits auth refresh, CSRF/CORS handling, GET error retries, persistent client cursors, UI rendering, and snapshot semantics. The API must supply a **stable cursor**—never rely on local timestamps. When hitting the 20-page cap while `hasMore` stays true, production needs a bounded paging budget rather than spinning indefinitely. Also add abort/shutdown hooks and close stale sockets on reconnect so duplicate sockets never accumulate.

If the backend uses **Azure SignalR Service**, clients must use the SignalR Hub Protocol/SDK rather than swapping in a raw WebSocket in this class.

## 21. Mark-read and read-all

### 21.1. Mark-read is a durable business operation

Sample request:

~~~http
PATCH /notifications/notif-481-paid/read
Authorization: Bearer <access-token>
Content-Type: application/json

{"read":true}
~~~

Server handling:

1. Validate access token/session.
2. Extract `tenantId` and `userId` from trusted claims/context.
3. Verify the notification belongs to that user.
4. Transition **`UNREAD → READ`** only if not already marked read.
5. Persist **`readAtUtc`** server-side and commit.
6. Invalidate/update cache per policy.
7. Optionally push **`NOTIFICATION_READ`** to other active tabs.
8. Repeated requests must never decrement the unread count a second time.

### 21.2. Read-all must never run unbounded blind updates

For a user with 500,000 notifications, marking all read can burn huge writes/RU. Consider:

- Batched updates with continuation checkpoints and bounded concurrency.
- A **`LastReadCursor` / watermark** when business semantics allow.
- Exceptions for notifications needing individual state tracking.
- A server snapshot boundary so newly arriving alerts right as the user clicks aren't accidentally marked read.
- Per-item audit records if compliance demands exact `readAtUtc` per item.

### 21.3. Read watermarks have trade-offs

A single marker saying "all notifications before cursor X are read" cuts writes, yet cannot replace per-item auditing. If an older item is backfilled before X, define its read semantics explicitly. Never use read watermarks when compliance requires per-item read receipts.

## 22. Fan-out to users, groups, and broadcasts

### 22.1. Personal notifications

~~~text
OrderPaid → one notification record → one delivery intent
→ publish to user group → all matching active connections
~~~

One user receives it across browser tabs A/B and mobile; clients deduplicate by ID.

### 22.2. Team alerts

An `OperationalAlert` sent to 200 staff members:

- Pull membership from an authoritative source.
- Decide whether the audience is a **publish-time snapshot** or **live membership**.
- Store one shared announcement or per-recipient rows depending on offline/audit needs.
- Group broadcasts push only to online members—never proving everyone read them.
- When staff leave the team, revoke membership and access cleanly.

### 22.3. Large broadcasts

If 100,000 users average 2 active connections each:

~~~text
Active connections ≈ 100,000 × 2 = 200,000

One eligible system-wide announcement
can fan out across up to 200,000 connections.
~~~

This is a capacity estimate, not an exact billable message count: tiers, protocols, payload sizes, and quotas all affect metering. Load-test group fan-out, publish rates, connection churn, and DB read spikes when browsers refresh feeds simultaneously.

### 22.4. When do you avoid 100,000 inbox rows?

A general maintenance banner can be stored once with audience rules and per-user read cursors. Conversely, a legal notice requiring proof of receipt per recipient may require per-recipient records.

Never optimize database writes by erasing required business audit trails.

## 23. Backpressure, prioritization, and load shedding

### 23.1. When ingress outpaces workers

Let:

- **λ**: incoming domain events/second into Service Bus.
- **μ**: events/second fully processed and persisted to the inbox.
- **B(t)**: message backlog.

Without caps:

~~~text
Backlog growth ≈ (λ - μ) × t when λ > μ

Example:
λ = 8,000 events/s
μ = 5,000 events/s
t = 120 seconds

Backlog grows ≈ 3,000 × 120 = 360,000 events

Once recovered, μ = 10,000 events/s
while λ remains 8,000 events/s:

Drain rate ≈ 2,000 events/s
Ideal catch-up time ≈ 360,000 / 2,000 = 180 seconds
~~~

This idealized model excludes DB throttling, retries, partition skew, payload sizes, and traffic spikes.

### 23.2. Never increase concurrency blindly

If the notification DB sustains 3,000 writes/s, scaling workers from 10 to 100 only triggers more 429s and timeouts.

Design with:

- Bounded executors/thread pools.
- Separate concurrency caps for DB writes and gateway publishes.
- Exponential backoff + jitter.
- Retry limits, error classification, and circuit breakers.
- Bulkheads per tenant/priority.
- DLQ/quarantine for poison events.
- Alerts on **oldest pending outbox age**, not just total pending count.

### 23.3. Priority levels

| Priority | Examples | Recommendation |
|---|---|---|
| Critical | Security incidents, critical transaction failures | Persist + push + fallback channel; strict SLO |
| High | Payment action required | Durable + push + retries |
| Normal | Order delivered | Durable + rate-limited push |
| Low | Product recommendations | Batch, coalesce, or digest if business permits |

Never **silently drop** mandatory financial, safety, permission, or compliance notifications. Load shedding applies only to event classes with explicit policy approval.

### 23.4. Coalescing

If a user triggers 100 "document edited" alerts in 3 seconds, coalesce them into "12 documents updated" over a business window. Redis can hold temporary counters while the durable store records a summary if auditing is needed.

Never merge notifications with different access scopes into one summary that could leak restricted details.

## 24. Retry semantics and guarantee levels

| Milestone | What is confirmed | What cannot be inferred |
|---|---|---|
| Broker accepted | Service Bus accepted message per semantics | Worker finished processing |
| Inbox persisted | Notification saved in DB | Browser received it |
| Gateway accepted publish | Real-time service accepted publish call | Client is actually online |
| Client callback | Client code received payload | Human looked at screen |
| Client display telemetry | Client UI rendered per client code | User read or understood it |
| DB `readAtUtc` committed | User/session marked read via API | Human truly read every word |

### 24.1. Duplicate delivery is normal

A dispatcher can experience:

~~~text
Publish → gateway accepts
Network response drops
Dispatcher retries the same job
→ Client receives two frames with the same notificationId
~~~

Clients must deduplicate/upsert rather than rendering two cards. If UX forbids showing the same toast twice on a device, keep a local seen-set with a sensible TTL while keeping authoritative read state on the backend.

### 24.2. Minimal pushes

When payloads carry sensitive data or fast-changing schemas, push only:

~~~json
{
  "type": "REFRESH_INBOX",
  "recipientVersion": "v-9381"
}
~~~

Clients then `GET` the authenticated/authorized feed. The trade-off is extra DB reads per push—mitigate with debouncing, caching, and jitter to dampen thundering herds.

## 25. Security, privacy, and tenant isolation

### 25.1. Least-privilege table

| Call path | Identity and permissions |
|---|---|
| Orders API → Service Bus | Managed identity, **Azure Service Bus Data Sender** |
| Notification worker → Service Bus | **Data Receiver** on target subscription/namespace scope |
| Worker/API → Notification DB | Cosmos native data-plane role or scoped SQL DB permissions |
| API/Worker → Redis | TLS + auth/Entra per service/client model |
| Backend → Web PubSub / SignalR | Server credential/managed identity and supported role |
| Browser → real-time service | Short-lived client token/URL scoped to receive messages |
| Browser → Notifications API | Entra/OIDC session + tenant/user authorization |
| Operator → Azure Monitor | Scoped Azure RBAC with sensitive fields masked in logs |

**Azure Contributor** on a resource group does not grant Cosmos DB document data access, and a Private Endpoint never replaces application authorization.

### 25.2. Never trust `recipientUserId` from external clients

If an external webhook could dictate **`recipientUserId`**, attackers could redirect alerts to other accounts. Workers must authenticate producers and resolve recipients from trusted business ownership/membership records.

### 25.3. Never use group names as authorization

Group **`tenant-hcm:user-91`** is a routing hint. Users must never choose groups freely during negotiation. Servers must:

- Validate tokens.
- Verify tenant membership.
- Construct properly namespaced user/group identities.
- Issue least-privilege tokens.
- Revoke/expire tokens or close sockets on permission changes per service capabilities.

### 25.4. Preventing XSS, phishing, and payload leaks

- Escape notification titles and bodies when rendering HTML.
- Allow only relative URLs or allowlisted domains in `link` fields.
- Never push password-reset tokens, session tokens, or sensitive PII in notifications.
- Consider mobile lock-screen notification previews.
- Never log token-bearing Web PubSub client access URLs.
- Enforce CORS/origin policies and CSRF protection for cookie sessions.
- Define retention and legal deletion workflows across inboxes, outboxes, and telemetry.

### 25.5. Private networking

Service Bus, Redis, databases, Web PubSub/SignalR, and app runtimes offer different networking features by tier and region. Verify VNet integration, Private Endpoints, DNS, TLS, routing, firewalls, and NAT. Never assume every service shares identical private networking rules—check each SKU before deploying.

## 26. Monitoring and correlation

### 26.1. Metrics matrix

| Component | Key signals | Purpose |
|---|---|---|
| Service Bus | Active/DLQ message counts, throttles, incoming/outgoing | Broker backlogs and failures |
| Worker | Processing success, idempotent duplicates, DB commit latency | Accurate message handling |
| Notification DB | Write/query p95, RU/429s or CPU/DTU, storage | Durability and DB saturation |
| Delivery outbox | Pending jobs, oldest age, retries, permanent failures | Post-persistence push lag |
| Real-time gateway | Active connections, message counts, errors, throttling | Socket and fan-out capacity |
| Redis | Hit/miss, latency, memory, evictions, errors | Cache effectiveness |
| Notifications API | Feed GET p95, mark-read failures, auth failures | End-user experience |
| Client | Reconnect rate, resync latency, duplicate push rate | Last-mile quality |
| Business | Time from `OrderPaid` to inbox available, unknown recipients | End-to-end SLOs |
| FinOps | Cost per persisted notification; gateway/DB/cache spend | Cost optimization |

Not every metric is emitted out of the box by Azure Monitor under these exact names. Instrument business KPIs and client events using Application Insights / OpenTelemetry per policy.

### 26.2. Correlation

Example log:

~~~json
{
  "stage": "NOTIFICATION_PERSISTED",
  "sourceEventId": "evt-order-481-paid-1",
  "notificationId": "notif-481-paid",
  "correlationId": "corr-481",
  "tenantId": "tenant-hcm",
  "recipientUserHash": "hash-example",
  "durationMs": 42,
  "timestampUtc": "2026-11-20T03:10:03Z"
}
~~~

Never put raw recipient PII, access tokens, or sensitive payloads in logs. Trace milestones end-to-end:

~~~text
Domain commit → outbox publish → broker accepted
→ notification DB committed → gateway accepted
→ client callback → UI render → read-state DB commit
~~~

### 26.3. Illustrative SLOs

- 99% of `OrderPaid` events create an inbox row within **5 seconds**.
- 95% of connected users' alerts are accepted for push by the gateway within **2 seconds** of persistence.
- 99% of reconnecting sessions sync retained feed items within **10 seconds**.
- Zero dispatch jobs stay stuck past 15 minutes without alerting.
- DLQs are triaged on an operational cadence.
- Cache failures never lose inbox rows or leak cross-tenant data.

These are **illustrative business SLOs**, not Azure SLAs or guarantees that every online client receives frames.

## 27. Capacity planning and calculations

### 27.1. Connections

Assumptions:

~~~text
30,000 online users
2 connections per user on average

Active connections ≈ 30,000 × 2 = 60,000

Each user receives 1 notification/minute:

Notifications created/s ≈ 30,000 / 60 = 500

If pushed to both connections:
Frame deliveries ≈ 500 × 2 = 1,000/s
~~~

These are averages; traffic peaks, broadcasts, and reconnect storms multiply operations dramatically. **One publish call does not equal one billable message**—check your real-time service's tier meters and message-size rules.

### 27.2. Fan-out broadcasts

Sending 1 `OperationalAlert` to 20,000 users averaging 2 sockets each yields roughly 40,000 socket deliveries. Group publishing cuts server-to-gateway API calls while still consuming client fan-out bandwidth and quotas.

Add debouncing and jitter if all clients immediately call `GET /notifications` on receiving a broadcast.

### 27.3. Cache estimation

Suppose we cache unread counts for 100,000 users at an assumed **150 bytes** per key/value + metadata:

~~~text
100,000 × 150 bytes = 15,000,000 bytes ≈ 15 MB
~~~

This is **not a recommendation to pick a 15 MB Redis SKU**: add Redis internal overhead, fragmentation, replicas, connection buffers, other keys, peaks, and headroom. Measure actual memory via benchmarks.

### 27.4. Hot users and hot tenants

If an admin account receives 10,000 alerts/s, its per-user inbox partition, cache key, or group can overheat. Use digests, synthetic/sharded partition keys, priority queues, and per-user/tenant rate limits. Never upsize Redis RAM to cure a hot DB partition.

## 28. Cost and right-sizing architecture complexity

| Component | Cost drivers to consider |
|---|---|
| Service Bus | Tier, messaging operations, throughput, message size |
| Durable inbox | SQL vCore/DTU/storage or Cosmos RU/storage/replication |
| Delivery outbox | Database writes, storage, cleanup, and worker compute |
| Azure Managed Redis | Instance/tier/capacity/HA/networking per billing model |
| Web PubSub / SignalR | Connection units, messages, bandwidth, and tier |
| Java worker / Functions / Container Apps | CPU/RAM, executions/instances, scaling |
| Azure Monitor | Log ingestion, retention, and alerts |
| Private networking | Private Endpoints, NAT/firewalls, cross-region transfer |
| Mobile push / email / SMS | Provider fees and quotas |

Never hardcode unit prices in designs since tiers, regions, and pricing change. Use the pricing calculator and Cost Management on real resources.

### 28.1. Minimalist architecture when caching isn't needed yet

~~~text
Orders outbox → Service Bus → Notification inbox
                              → Web PubSub hint

Browser → GET inbox / mark-read
~~~

If the unread-count API serves a few hundred users and DB p95 stays healthy, you may **not need Redis yet**. Caching is a data-driven optimization, not a prerequisite for real-time features.

### 28.2. Architecture with caching under heavy load

~~~text
Orders outbox → Service Bus → Inbox + delivery outbox
                                  ↓
                                Gateway dispatcher
                                  ↓
                              Web PubSub
                                  ↓
                                Browser

Browser → Notifications API → Redis cache-aside → Durable inbox
~~~

Adding layers increases cost, failure modes, and operational burden. Introduce complexity only when it measurably improves SLOs or total cost.

### 28.3. Sound FinOps KPI

~~~text
Cost per available notification
  = (broker + worker + database + cache
     + gateway + network + monitoring + operations)
    / number of successfully persisted notification records
~~~

Never divide by push attempts and call it cost per delivered user notification; one notification can fan out across multiple sockets without any read receipt.

## 29. Failures and graceful degradation

| Failure | Target behavior |
|---|---|
| Service Bus rejects messages | Domain outbox retains events; relay retries |
| DB inbox slow/down | Worker does not Complete before commit; applies backoff |
| Redis disconnects | Cache miss falls back to DB; zero history lost |
| Redis count stale | Bounded by TTL, versioned invalidation, and reconciliation |
| Real-time gateway down | Inbox keeps persisting; delivery outbox retries; clients resync |
| Client offline | Reloads inbox upon reconnecting |
| Client receives duplicate | Deduplicates via `notificationId` |
| Out-of-order alerts | Sorted by server order/revision; client merges cleanly |
| Poison event | Dead-lettered/quarantined with reason; no infinite retries |
| User access revoked | Token expiry/revocation + API authorization |
| Oversized broadcast | Fan-out budgets, rate limits, and debouncing |
| Regional outage | Failover/restore per tested architecture |

### 29.1. Overload priorities

1. Preserve accurate business state and never drop committed domain events.
2. Never deliver alerts to unauthorized users.
3. Persist notifications durably and idempotently.
4. Push quickly when connected, backed by retries and resyncs.
5. Allow Redis counts/presence brief staleness within SLO budgets.

### 29.2. Redis failover

If Redis restarts and loses keys, APIs query the DB to rebuild them. Cap cache retries so they never exhaust CPU/network; watch cache hit rates, DB fallback load, and evictions.

### 29.3. Reconnect storms

After a 5-minute gateway outage, 100,000 clients may reconnect and fetch inboxes simultaneously. Mitigate with exponential backoff + jitter, rate-limited negotiation, pagination, API rate limits, DB headroom, and user-friendly retries.

## 30. Azure lab with authorized resources

The steps below are **guidance only** and were not deployed to Azure.

### 30.1. Prerequisites

- Lab subscription/resource group and budget.
- Service Bus Standard namespace (for topics/subscriptions).
- Notification store on Azure SQL or Cosmos DB for NoSQL.
- Azure Web PubSub instance/hub for the lab.
- Optional Azure Managed Redis if testing cache-aside.
- Java worker, Notifications API, and browser test client.
- Microsoft Entra ID / managed identities and matching role assignments.
- Monitoring/telemetry and a resource cleanup plan.

Never use production queues, secrets, or real customer data.

### 30.2. Creating Service Bus with Azure CLI

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-realtime-notify-lab"
REGION="southeastasia"
NS="<globally-unique-servicebus-namespace>"

az group create \
  --name "$RG" \
  --location "$REGION"

az servicebus namespace create \
  --resource-group "$RG" \
  --name "$NS" \
  --location "$REGION" \
  --sku Standard

az servicebus topic create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "commerce-events"

az servicebus topic subscription create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --topic-name "commerce-events" \
  --name "notifications"
~~~

Verify:

~~~bash
az servicebus namespace show \
  --resource-group "$RG" \
  --name "$NS" \
  --output table

az servicebus topic subscription show \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --topic-name "commerce-events" \
  --name "notifications" \
  --output json
~~~

Commands require compatible Azure CLI/extension versions; never re-run create against resources owned by another team. Default subscription rules match all events; add filters if scoping strictly to `OrderPaid`.

### 30.3. Creating Web PubSub and the app

In the Azure Portal:

1. Create **Azure Web PubSub** in the lab region/tier.
2. Configure the hub and server-side publishing identity/secret management.
3. Expose a trusted **`POST /realtime/negotiate`**.
4. Backend authenticates users and mints short-lived, tightly scoped client access URLs/tokens.
5. Browser opens the WebSocket and listens for hints.
6. Backend sends a test push to an authenticated user/group.
7. Enable required metrics without logging connection tokens.

If the project uses ASP.NET Core SignalR, provision Azure SignalR Service with the SignalR SDK; raw WebSocket code from this lesson will not talk to a SignalR Hub.

### 30.4. Setting up the inbox and cache

- Create `Notifications` + `DeliveryOutbox` with unique notification identities.
- Index by tenant, user, and time with durable read state.
- On Cosmos DB, align the partition key with per-user feeds and transaction boundaries.
- Add Redis only after measuring demand; cache unread counts with suitable TTLs and DB fallback.
- Test post-commit invalidation, duplicate delivery, Redis outages, and cross-tenant read isolation.

### 30.5. End-to-end testing

1. Emit an `OrderPaid` event.
2. Confirm the broker receives the message.
3. Confirm the worker writes one notification and one dispatch intent.
4. Confirm the message Completes after DB commit.
5. Confirm the dispatcher pushes to the gateway.
6. Confirm the online browser receives the push hint and calls `GET` inbox.
7. Go offline and emit another event.
8. Reconnect and confirm full history resyncs cleanly.
9. Mark read in Tab A; confirm Tab B syncs the read state.
10. Inspect logs, metrics, and DLQs, then clean up dedicated lab resources.

## 31. Diagnostic runbook

| Symptom | Possible causes | Action |
|---|---|---|
| Order PAID yet no notification | Domain outbox relay, broker, worker, or DB commit failed | Trace `eventId` through every layer |
| Notification in DB yet missing in UI | Delivery outbox, gateway, or client reconnect failed | Check publish state, socket, and sync API |
| Browser shows duplicate cards | Push retry without deduplication | Enforce stable `notificationId` + merge |
| Cached count exceeds DB count | Duplicate `INCR` or stale refill race | Recompute/invalidate/version cache |
| Tab A marks read, Tab B stays unread | Missed read hint or offline tab | Resync read state from API |
| Service Bus DLQ grows | Bad payload schema or `MaxDeliveryCount` exceeded | Inspect DLQ reason; replay controllably |
| Queue backlog grows | Slow worker or DB | Measure λ vs μ, throttle, scale within limits |
| Gateway 401/403 | Expired token or wrong scope/role/identity | Inspect negotiate auth and server credentials |
| Gateway throttled | Connection/message quota exceeded | Check fan-out rate, payload size, tier |
| Redis evictions | Memory pressure | Inspect cache size, TTLs, and policy |
| Browser reconnect loops | Network flaps, expired tokens, or client bug | Add backoff/jitter and token refresh |
| User A sees User B's alert | Tenant/group authz bug | Security incident: revoke, contain, audit |
| Rising bills | Gateway connections, DB reads, Redis sizing, logs | Track FinOps metrics and cost per notification |

### 31.1. Tracing from `OrderPaid` to browser

1. Locate **`sourceEventId`** and **`correlationId`**.
2. Check Orders DB and its outbox row.
3. Verify Service Bus publish/acceptance.
4. Check subscription Active/DLQ counts.
5. Inspect worker validation and DB commit.
6. Verify the single `notificationId` in the inbox.
7. Check delivery-outbox state and retries.
8. Inspect gateway publish acceptance/errors.
9. Verify user/group mappings and auth.
10. Inspect browser socket, cursor, and sync calls.
11. Compare DB `readAtUtc` with the Redis badge count.
12. Add a regression test for the root cause.

### 31.2. When unread counts drift

Query the durable store for that exact user, then inspect cache key/TTL/version, duplicate events, conditional mark-read updates, and refill-invalidation races. Never just wipe Redis and call it fixed—measure again and eliminate the drift source.

### 31.3. Security incident: cross-tenant leak

Halt the affected publish/group path, revoke active tokens/sessions where possible, audit tenant memberships and server-side authz, preserve logs per policy, omit PII from tickets, and add negative tests ensuring users cannot negotiate or `GET` another tenant's data.

## 32. Pre-production chaos and test drills

| Scenario | Expected outcome |
|---|---|
| Worker crashes before DB commit | Message is redelivered and processed |
| Worker crashes after DB commit, before Complete | No duplicate notification inserted |
| Dispatcher crashes after gateway accepted | Client deduplicates if redelivered |
| Redis outage | Durable inbox and mark-read stay accurate |
| Gateway outage | Notifications still persist; browsers resync |
| Browser offline 30 minutes | Full retained history loads on return |
| 3 tabs for one user | Zero cross-user leaks; read state syncs |
| Expired token | Safe re-negotiation with valid scoped roles |
| Event fans out to 20,000 recipients | Bounded concurrency with backlog telemetry |
| Malformed message schema | Dead-lettered/quarantined without hot retry loops |
| Cache refill/invalidation race | Bounded staleness within SLO |
| Client receives B before A | Stable server ordering / revision merge |
| User A calls PATCH on User B's ID | Rejected without disclosing data |
| Reconnect storm | Backoff/jitter keeps API and DB stable |

Run drills on **staging resources**—never sever live production connections deliberately. Reconcile **unique `notificationId`** counts against valid events and recipient mappings.

## 33. Choosing right-sized complexity

### Level 1: polling

~~~text
Orders DB → Notifications store
Browser → periodic GET notifications
~~~

Fits small user bases with 30–60s freshness needs and no strong real-time urgency. Neither Redis nor a managed real-time gateway is needed yet.

### Level 2: reliable broker + real-time

~~~text
Orders outbox → Service Bus → Notification store + delivery intent
                                         ↓
                                    Web PubSub
Browser → real-time hint + GET on reconnect
~~~

Fits multi-service event producers needing durable offline history.

### Level 3: caching + resilient dispatch

~~~text
Orders outbox → Service Bus → Notification store + dispatch outbox
                                            ↓
                                       bounded dispatcher
                                            ↓
                                      real-time gateway

Browser → Notifications API → Redis cache-aside / durable DB
~~~

Fits high traffic, hot unread counts/presence, multi-tenancy, and strict SLO/DR/observability targets. Not every app needs Level 3.

## 34. Production checklist

- [ ] Clearly separated domain events, broker messages, notifications, gateway pushes, and read state.
- [ ] Selected Service Bus/Event Grid/Storage Queue/Event Hubs matching real semantics.
- [ ] Never used Redis Pub/Sub as the sole durable notification source.
- [ ] Durable inbox enforces stable `notificationId` and recipient/tenant ownership.
- [ ] Transactional outbox commits domain state and event intent in one DB transaction where needed.
- [ ] Notifications and delivery-outbox commit atomically or reconcile cleanly.
- [ ] Service Bus `Complete` runs only after durable persistence.
- [ ] Retries/backoff, `MaxDeliveryCount`, DLQs, and poison-message handling configured.
- [ ] Clients deduplicate, reconnect, and resync from the durable inbox.
- [ ] Server-managed cursors include tie-breakers and authorization.
- [ ] Read state uses conditional/idempotent updates—never decrementing unread counts twice.
- [ ] Unread-count cache has TTLs, invalidation/versioning, and DB fallback.
- [ ] Cache refill/invalidation races tested.
- [ ] Presence TTL treated strictly as an approximation.
- [ ] Multi-tab/device pushes never leak unauthorized data.
- [ ] Real-time negotiate uses verified identities, short token TTLs, and least-privilege roles.
- [ ] Backend controls group memberships with tenant isolation.
- [ ] Zero server access keys, client tokens, or PII in logs.
- [ ] Notification links validated, HTML escaped, and XSS prevented.
- [ ] Workers/dispatchers enforce bounded concurrency and fan-out budgets.
- [ ] Alerts watch backlogs, DLQs, dispatch-outbox age, cache evictions, and gateway errors.
- [ ] End-to-end SLOs instrumented with measurable telemetry.
- [ ] Tested gateway outages, Redis outages, retry duplicates, and reconnect storms.
- [ ] Retention, backup/restore, privacy lifecycle, and permission reviews established.
- [ ] Estimated costs across broker, DB, cache, gateway, compute, and monitoring.
- [ ] Avoided deploying Redis if SLOs already pass without it.

## 35. Hands-on exercises

### Exercise 1: Choosing components

Pick the right components for:

1. Users offline for 1 hour still see missed notifications.
2. 100,000 WebSocket clients receive an announcement.
3. Unread counts read 1,000 times/second.
4. Worker crashes right after receiving `OrderPaid`.
5. Telemetry at 1 million events/minute.
6. Small website needing updates every 60 seconds.

Explain the roles of Service Bus, Web PubSub, Redis, databases, Event Hubs, and polling—do not merely list service names.

### Exercise 2: Transactional outbox

Design two outboxes: a **business event outbox** in Orders DB and a **delivery outbox** in Notifications DB. Diagram crash points before/after publish, before/after Complete, and after gateway acceptance, naming every idempotency key.

### Exercise 3: Unread counts

A user has 10 unread notifications. A worker processes the same `OrderPaid` twice, the user marks one notification read twice, a Redis key gets evicted, and a GET races with invalidation. Design how counts stay accurate or within published staleness bounds.

### Exercise 4: Multi-tab and reconnect

Two tabs go offline for 10 minutes while 15 notifications are created. On reconnect, an old push arrives twice and the user marks items read in Tab 2. Design cursors, deduplication, revisions, and resyncs so both tabs converge.

### Exercise 5: Security

Two tenants both have a local `userId=91`. Design group names, negotiate tokens, server-side tenant membership checks, token TTLs, and negative tests proving User A cannot receive or read User B's notifications.

### Exercise 6: Fan-out

50,000 users averaging 1.5 connections each. Compute ideal connection deliveries for one broadcast, design throttling, and decide between a shared announcement vs per-recipient inbox rows.

### Exercise 7: Gateway outage

The gateway drops for 5 minutes. What still persists? How does the delivery outbox behave? Upon recovery, how must rate budgets and client resyncs operate?

### Exercise 8: Java worker

Complete `OrderPaidHandler` with a JDBC/Cosmos adapter: unique `notificationId`, transactional notification + outbox insert, manual Service Bus `Complete`, and redelivery handling.

### Exercise 9: FinOps

A system generates 2 million notifications/day with 2 connections/user on average and a 90% unread-count cache hit rate. Build a cost breakdown across broker, DB, Redis, gateway, compute, networking, and logs, then propose cost cuts that preserve offline notifications.

### Exercise 10: Architecture review

A team wants to use "only Redis Pub/Sub + WebSockets, no database or broker" for payment reminders with a 90-day audit requirement. Analyze what fails when users go offline, Redis restarts, workers crash, pushes duplicate, or read state must be audited, and propose a minimal compliant architecture.

## 36. Self-check questions

1. How do domain events and notifications differ?
2. Why is a WebSocket push not proof a user read a notification?
3. Can Service Bus replace a database for notification history?
4. Does Redis Pub/Sub automatically replay messages when a subscriber reconnects?
5. How do Redis Streams and Pub/Sub differ in persistence and consumption models?
6. Why is a durable inbox needed whenever users can go offline?
7. Which data should Redis cache in this architecture?
8. Should a Redis failover ever lose business read state?
9. Does a presence TTL prove a user is definitely online?
10. Why can one user have multiple `connectionId`s?
11. Do Azure SignalR and raw WebSockets share the same protocol?
12. When is polling a better choice than WebSockets?
13. What should backgrounded mobile apps use besides in-app WebSockets?
14. Which crash window does a transactional outbox close?
15. Why can an outbox still emit the same event twice?
16. Where does a unique `notificationId` prevent duplicates?
17. Why must a worker never `Complete` a broker message before DB commit?
18. Which failure does the delivery outbox guard against?
19. How does `GatewayAccepted` differ from `ClientReceived` and `Read`?
20. Why not run Redis `INCR` every time a worker receives a message?
21. How does a refill/invalidation race produce a stale unread count?
22. When is TTL alone insufficient for unread-count correctness?
23. What must a browser do with the durable feed after reconnecting?
24. How do server-ordered cursors differ from client clocks?
25. Why can pushes arrive out of order?
26. Why is a group name never authorization?
27. Which real-time permissions should browsers receive?
28. Can backends trust a `recipientUserId` supplied by a browser?
29. Does one publish to 10,000 sockets equal one user reading the message?
30. How should HTTP 429s at the gateway or database be handled?
31. Should Service Bus Sessions be enabled for every user blindly?
32. How does a DLQ differ from a durable notification inbox?
33. During a gateway outage, do the broker and DB keep working?
34. Which SLOs are server-measurable vs dependent on client telemetry?
35. When is skipping Redis altogether the better architectural choice?
36. During an incident, should you prioritize durability or push latency?

## 37. References

- [Azure Service Bus messaging overview — Microsoft Learn](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview)
- [Message settlement and locks in Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Service Bus dead-letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Service Bus duplicate detection](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection)
- [Azure Web PubSub overview](https://learn.microsoft.com/azure/azure-web-pubsub/overview)
- [Azure Web PubSub key concepts](https://learn.microsoft.com/azure/azure-web-pubsub/key-concepts)
- [Web PubSub client access URLs](https://learn.microsoft.com/azure/azure-web-pubsub/howto-generate-client-access-url)
- [Java server SDK for Azure Web PubSub](https://learn.microsoft.com/java/api/overview/azure/messaging-webpubsub-readme)
- [Azure SignalR Service overview](https://learn.microsoft.com/azure/azure-signalr/signalr-overview)
- [Azure Managed Redis overview](https://learn.microsoft.com/azure/redis/overview)
- [Azure Cache for Redis documentation and migration guidance](https://learn.microsoft.com/azure/azure-cache-for-redis/)
- [Cache-aside design pattern](https://learn.microsoft.com/azure/architecture/patterns/cache-aside)
- [Azure Cosmos DB for NoSQL overview](https://learn.microsoft.com/azure/cosmos-db/nosql/overview)
- [Service Bus trigger for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-bindings-service-bus-trigger)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Azure Service Bus pricing](https://azure.microsoft.com/pricing/details/service-bus/)
- [Azure Web PubSub pricing](https://azure.microsoft.com/pricing/details/web-pubsub/)
- [Azure SignalR Service pricing](https://azure.microsoft.com/pricing/details/signalr-service/)
- [Azure Managed Redis pricing](https://azure.microsoft.com/pricing/details/redis/)
