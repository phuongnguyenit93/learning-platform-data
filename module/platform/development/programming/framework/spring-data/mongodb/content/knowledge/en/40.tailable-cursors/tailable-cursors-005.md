# Invalid Cursors, Empty Results, and Reconnection Strategies

> **Chapter:** Tailable cursor  
> **Module:** `SPRING_DATA_MONGODB`

An operational event-tracking system stores records in a **MongoDB capped collection** and needs to receive new records in near real time. The application uses a **tailable cursor**: after reaching the end, the cursor can stay open waiting for newly appended documents instead of closing like a regular query cursor. When events stop arriving for several minutes, the application must distinguish: **are there genuinely no new events, is the cursor still waiting, or has the cursor died and needs to reconnect?**

In Spring Data MongoDB, you can use `ReactiveMongoTemplate.tail(...)`, a reactive repository with `@Tailable`, or `MessageListenerContainer` with `TailableCursorRequest` on the imperative side. Yet simply reopening a `Flux`/cursor upon error is not enough. A capped collection can **overwrite old data**, a cursor can become invalid, an initial query with no match can close the stream, and **a tailable cursor provides no change-stream resume token**. Reconnecting only from "now" risks losing data; replaying from an earlier point without deduplication risks duplicate processing.

This lesson belongs to the `SPRING_DATA_MONGODB` module: using Spring Data MongoDB to connect, map documents, and work with MongoDB via `MongoTemplate` or repositories; designing queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics. Its direct focus is **classifying invalid cursors, empty results, and reconnect/recovery strategies**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why tailable cursors work only with **capped collections** and natural order (`$natural`).
2. Distinguish `onNext`, **no `onNext` while the cursor remains alive**, `onComplete`, `onError`, and `cancel`.
3. Recognize cursor invalidation caused by collection drop/recreate, capped rollover/position lost, elections, network issues, or unsuitable query configuration.
4. Understand the **initial query without matching records** case, how to monitor subscriptions/cursors, and why `Flux.empty()` does not mean "waiting."
5. Use `ReactiveMongoTemplate.tail(Query, Class<T>)` or `@Tailable` to read continuously without calling `subscribe()` per HTTP request.
6. Separate **retry on error** from **repeat/reopen on cursor completion**, using backoff, retry budgets, and hot-loop prevention.
7. Design application-level checkpointing when **no resume token exists**, with idempotency and gap detection for capped rollover.
8. Compare tailable cursors against change streams and decide when another solution is needed.
9. Test against real capped collections, quiet live cursors, cancelled connections, initial no-match, and reconnect cycles.
10. Design metrics, alerts, resource limits, and an incident-response runbook.

## 2. How Does a Tailable Cursor Work?

MongoDB distinguishes two concepts:

- **Regular cursor:** iterates over results at query time; once exhausted, the cursor normally closes.
- **Tailable cursor:** for capped collections, after reaching the end of existing data, the cursor can stay open to observe newly appended documents.

```text
CAPPED COLLECTION (append order)

[E01][E02][E03][E04]       <- current end
                  ^
                  | Tailable cursor read up to here
                  v
             Wait for next document

After inserting E05:

[E01][E02][E03][E04][E05]
                       ^
                       |
                    onNext(E05)
                       |
                       v
                  Keep waiting
```

A cursor **does not turn into a message queue on its own**. It is a cursor attached to a MongoDB collection, subject to collection lifecycle, batch/`getMore` mechanics, query predicates, network, sessions, and overwritten data.

### 2.1. Why Must You Use a Capped Collection?

A capped collection has a **configured maximum size**; MongoDB retains data in a ring-like manner: when capacity reaches its limit, older documents can be evicted to make room for new ones. This is an essential prerequisite for tailable cursors, and also the reason **a cursor cannot be treated as permanent event storage**.

Suppose a capped collection only holds E100–E200. If a consumer goes offline at E050, upon reconnecting **E051–E099 may already have been overwritten**. Even if reconnection succeeds, that cursor cannot retrieve documents no longer present in the collection.

### 2.2. Natural Order—Do Not Re-Sort

A tailable cursor reads in the **natural order (`$natural`)** of the capped collection. Do not attach `Sort.by("createdAt")` or `sort({_id:1})` expecting proper tail semantics. If your use case requires reading in exact business-key order, design appropriate data/replay mechanisms rather than altering cursor sorting.

### 2.3. Tailable Cursors Do Not Emit Updates Like Change Streams

Tailable cursors are used to receive **newly appended documents** in a capped collection. They do not emit an event envelope carrying `operationType`, `updateDescription`, and `resumeToken` for arbitrary mutations across other collections. If the use case is "every update/delete on `orders` must produce an event," a **change stream** or transactional outbox is usually better suited.

## 3. Five States You Must Distinguish

| State | Reactive API Signal | Meaning | Action |
| --- | --- | --- | --- |
| **New document available** | `onNext(document)` | Cursor is returning data | Process; checkpoint only after successful processing |
| **Open but silent** | No `onNext/onError/onComplete` yet | Likely just no new documents | Keep cursor open, monitor health; do not treat as an error |
| **Cursor completed** | `onComplete` | Publisher stopped emitting | Classify cause and reopen with delay if policy permits |
| **Cursor errored/invalid** | `onError` | Server, network, query, or cursor position error | Classify error; retry/reopen or fail-fast/reconcile |
| **Caller actively cancelled** | `cancel` / `Disposable.dispose()` | Not a database error | Clean up; **do not auto-reconnect** after intentional shutdown |

### 3.1. No Events Is Not the Same as Flux.empty()

`Flux.empty()` emits `onComplete` immediately. A tailable `Flux` waiting for inserts typically **has not emitted any terminal signal yet**. If code simply does:

```java
source.switchIfEmpty(fallback());
```

`fallback()` runs only when upstream **completes empty**, not simply because the cursor has seen no records for 30 seconds. Furthermore, when a tailable cursor closes early due to no initial match, `switchIfEmpty` signals completion, **not proof that the server is still watching**.

### 3.2. blockFirst() Can Wait Indefinitely

```java
EventDocument first = reactiveTemplate
    .tail(query, EventDocument.class)
    .blockFirst();
```

This is an **anti-pattern** in WebFlux applications: without an event, the blocking call can stall until data arrives or the cursor closes/errors. It ties up a thread, complicates cancellation, and does not help recover cursors. In reactive pipelines, keep the `Flux` and manage subscription via lifecycle.

### 3.3. timeout() Easily Confuses Silence with Errors

```java
// Illustrative policy only; NOT a safe default.
Flux<EventDocument> impatient = source
    .timeout(java.time.Duration.ofSeconds(10));
```

`timeout` **cancels upstream** if no item arrives within 10 seconds and emits `TimeoutException`. If a legitimate workload can stay quiet for 10 minutes, the code above repeatedly kills and reconnects a perfectly healthy cursor.

Use timeout as a **liveness policy** only when the source guarantees a clear heartbeat/event cadence. For irregular business event tails, rely on cursor metrics, driver/server monitoring, or dedicated heartbeat documents with an explicit contract.

### 3.4. onComplete Does Not Mean "Work Is Done"

A stream responsible for continuous monitoring has no concept of "finished permanently" while the database remains active. `onComplete` can indicate **the cursor became invalid** or the query no longer has a valid tail condition; if the system must keep receiving events, a supervisor must decide when to reopen and check for potential data loss.

### 3.5. onError Does Not Mean Every Error Is Retryable

Transient network faults may recover after reconnecting; however, querying a regular (non-capped) collection, bad authorization, unsupported sorting, or schema mapping bugs will **repeat the exact same failure** unless configuration is fixed. Unbounded `retryWhen` turns configuration mistakes into an infinite reconnect loop.

## 4. Initial Condition: A Non-Matching Query Can Kill the Cursor

Spring Data MongoDB states that tailable cursors can become **dead/invalid**, with a query **finding no initial matching documents** being a major pitfall. Do not assume "no results at open time" always means the cursor registered a listener waiting for future matching documents.

For example:

```java
Query query = Query.query(
    Criteria.where("tenantId").is("TENANT-A")
        .and("level").is("CRITICAL"));

Flux<EventDocument> stream =
    reactiveTemplate.tail(query, EventDocument.class);
```

If the capped collection currently contains only `INFO` and `WARN` events, the `CRITICAL` query may fail to find a valid starting point. Depending on server/driver/query, the cursor may complete early rather than waiting indefinitely. Test against your exact target version and **observe terminal signals**.

### 4.1. Why Do Narrow Filters Increase Risk?

- If a query matches an existing document, the cursor has a starting position to tail from.
- If the query matches nothing initially, the cursor may close before a future event arrives.
- With many user-driven filters, opening/closing a cursor per filter wastes resources and complicates no-match detection.
- If a consumer must **stay running regardless of event type**, consider tailing unfiltered within an authorized scope, then **filtering in the processing layer** with proper bounds and authorization.

That last point does not permit loading and sending arbitrary tenant data to clients; the backend must still enforce read permissions and safe stream routing.

### 4.2. Two Kinds of "No Results"

```text
CASE A — cursor found an initial position:
  Open -> read existing match(es) -> await more documents
                                   -> no onNext for a while
  => Likely still alive.

CASE B — initial query found no match:
  Open -> no initial match -> cursor may close/dead
  => Must observe onComplete/onError and reopen policy.
```

Tests must distinguish both cases; `expectNoEvent(Duration)` alone cannot prove a cursor remains open without cursor readiness or subscription lifecycle signals.

## 5. Creating the Capped Collection and Sample Data

Event model for a device monitoring system:

```javascript
// Run ONLY in an authorized TEST MongoDB instance.
db.createCollection("device_event_log", {
  capped: true,
  size: 16 * 1024 * 1024,
  max: 20000
});

db.device_event_log.insertMany([
  {
    _id: "EVT-0001",
    sequence: NumberLong(1),
    tenantId: "TENANT-A",
    deviceId: "DEV-01",
    level: "INFO",
    message: "started",
    recordedAt: ISODate("2026-11-20T02:00:00Z")
  },
  {
    _id: "EVT-0002",
    sequence: NumberLong(2),
    tenantId: "TENANT-A",
    deviceId: "DEV-01",
    level: "WARN",
    message: "temperature-high",
    recordedAt: ISODate("2026-11-20T02:00:01Z")
  }
]);
```

This collection has a configured **maximum size and document count**. Once full, MongoDB can evict the oldest documents to add new ones. These `size`/`max` values are illustrative; in production, measure **write rate, average event size, and desired retention duration**.

### 5.1. Verifying It Is Truly a Capped Collection

```javascript
db.device_event_log.isCapped()
// Expected: true.

db.getCollectionInfos({ name: "device_event_log" })
// Inspect options: capped, size, max.
```

Do not infer a collection is capped merely because its name contains "log." A regular MongoDB collection does not properly support tailable cursors just because `recordedAt` is indexed.

### 5.2. A Capped Collection Is Not an ACK Queue

Tailable cursors do not delete documents after processing and offer no broker-managed consumer-group offset commits or ACKs. Multiple consumers tailing the same collection can receive **the same documents**. Consumers must manage on their own:

- Idempotency keys and duplicate handling.
- Dedicated checkpoint definitions.
- Consumer ownership if business rules permit only one worker to apply effects.
- Replay/backfill policies when data has been overwritten.
- Tenant access control and retention.

### 5.3. Do Not Use a Capped Collection When Infinite Retention Is Required

A 16 MiB capped collection might hold hours of data under low load yet only a few seconds under heavy burst traffic. Never treat it as the **sole source of truth** for financial records, long-term auditing, or workflows where losing an event is unacceptable.

If requirements state "events must remain replayable for 30 days," use durable storage with matching retention; a tailable cursor can serve only as a **fast delivery path**, not a replacement for an archive, outbox, or durable queue.

## 6. Entity and ReactiveMongoTemplate.tail(...)

File `DeviceEvent.java`:

```java
package com.example.monitoring;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "device_event_log")
public record DeviceEvent(
    @Id String id,
    long sequence,
    String tenantId,
    String deviceId,
    String level,
    String message,
    Instant recordedAt
) {}
```

File `DeviceEventTailSource.java`:

```java
package com.example.monitoring;

import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
public final class DeviceEventTailSource {

    private final ReactiveMongoTemplate template;

    public DeviceEventTailSource(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<DeviceEvent> tailAll() {
        return template.tail(
            new Query(), DeviceEvent.class);
    }
}
```

`tail(Query, Class<T>)` is the reactive Spring Data MongoDB API returning `Flux<T>`. An empty `Query` does not mean empty results: it means **no filter applied**, and the cursor may read existing documents before waiting for subsequent ones.

### 6.1. Calling the Method Does Not Open the Cursor Yet

```java
Flux<DeviceEvent> events = source.tailAll();
// Creates a Publisher; does not prove a subscription exists.
```

Once a caller subscribes, the driver begins interacting with MongoDB. In real applications, maintain a **subscription-managing component** holding the `Disposable`, supporting controlled shutdown and error reporting; never open hidden cursors inside request handlers.

### 6.2. Tail with a Filtered Query

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Flux<DeviceEvent> tailForTenant(
        String authorizedTenantId) {

    if (authorizedTenantId == null
            || authorizedTenantId.isBlank()) {
        return Flux.error(new IllegalArgumentException(
            "Missing authenticated tenant"));
    }

    Query query = Query.query(
        Criteria.where("tenantId").is(authorizedTenantId));

    return template.tail(query, DeviceEvent.class);
}
```

This is an **illustrative method** placed inside a service with an injected `template`. `authorizedTenantId` must come from the security context; never accept an arbitrary tenant from the client and assume the query enforces authorization.

Filtering can prevent the cursor from finding an initial document and close it early as discussed in Section 4. If the requirement is "watch tenant A without missing events," design an open/reopen and checkpoint strategy rather than returning a bare `Flux` and forgetting it.

### 6.3. Do Not Sort or Paginate a Tail Like a Regular Query

```java
// ANTI-PATTERN: sorting by recordedAt breaks natural-order assumptions.
Query query = new Query()
    .with(org.springframework.data.domain.Sort.by("recordedAt"));
return template.tail(query, DeviceEvent.class);
```

Altering sort order can be rejected by MongoDB or prevent the cursor from remaining tailable. To read the "5 newest records" for historical display, use a separate **regular query** with indexing and sorting. To stream appends, use a tailable cursor in natural order with an appropriate policy.

### 6.4. Do Not Use take(1) Alone to Prove Stream Health

```java
Flux<DeviceEvent> first = source.tailAll().take(1);
```

`take(1)` cancels upstream after the first event; this test proves **at least one document was read**, not that the cursor holds a subscription over minutes, recovers from rollover, or handles reconnects. Liveness and recovery tests must exercise sustained lifecycles and inserts occurring after the watcher is ready.

## 7. @Tailable on ReactiveMongoRepository

Spring Data MongoDB supports declarative repository queries:

File `DeviceEventRepository.java`:

```java
package com.example.monitoring;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.mongodb.repository.Tailable;
import reactor.core.publisher.Flux;

public interface DeviceEventRepository
        extends ReactiveMongoRepository<DeviceEvent, String> {

    @Tailable
    Flux<DeviceEvent> findByTenantId(String tenantId);
}
```

Application code can call:

```java
Flux<DeviceEvent> tenantEvents =
    repository.findByTenantId(authorizedTenantId);
```

`repository` is a Spring-injected bean, and `authorizedTenantId` must be authorized. `@Tailable` changes how the MongoDB query cursor operates; it does not turn the repository into a durable broker, supply a resume token, or handle collection rollover automatically.

### 7.1. @Tailable vs. ReactiveMongoRepository.findAll()

| API | Meaning |
| --- | --- |
| `repository.findAll()` | Reactive stream of documents from a regular query; completes at the end |
| `@Tailable Flux<T> ...` | Attempts to keep a cursor open on a capped collection to receive subsequent appends |
| `template.tail(Query, T.class)` | Controls the tailable query directly via template |
| `ChangeStreamEvent<T>` | Change stream envelope; **not** the return type of `@Tailable` |

Calling `findAll()` followed by `repeat()` merely **re-runs a regular query**, without tailable cursor semantics. That creates a polling loop, reloads duplicate data, and increases load.

### 7.2. Query Filter with No Match at Subscription Time

Even when the method returns `Flux<T>`, startup behavior of the tailable cursor still needs observation. For long-lived consumers, never assume `findByTenantId("TENANT-NOT-SEEN-YET")` will wait forever for the first document. In tests, verify both a tenant with existing data and one without, observing actual driver `onComplete`/`onError` signals.

## 8. Imperative: MessageListenerContainer and TailableCursorRequest

For applications using imperative `MongoTemplate`, Spring Data MongoDB provides a messaging abstraction to manage tailable cursors via a listener container. Key APIs include:

- `DefaultMessageListenerContainer`.
- `TailableCursorRequest` and its builder.
- `MessageListener` receiving messages.
- `Subscription`/container lifecycle for cancelling and stopping.

Conceptual example:

```java
import org.springframework.data.mongodb.core.messaging.DefaultMessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.MessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.TailableCursorRequest;
import org.springframework.data.mongodb.core.query.Query;

MessageListenerContainer container =
    new DefaultMessageListenerContainer(mongoTemplate);

TailableCursorRequest request = TailableCursorRequest.builder()
    .collection("device_event_log")
    .filter(new Query())
    .publishTo(message -> {
        DeviceEvent event = (DeviceEvent) message.getBody();
        // Process safely; do not ignore errors or checkpoints.
    })
    .build();

container.start();
container.register(request, DeviceEvent.class);

// Stop only during application shutdown lifecycle:
// container.stop();
```

This snippet illustrates integration points rather than a complete Spring bean; signatures/generic types may require adjustment for your specific Spring Data version. Never call `container.stop()` immediately after `register(...)` in production. When a listener fails, observe container error handlers/tasks and invoke dedicated recovery.

### 8.1. Do Not Open Blocking Cursors on Request Threads

`MongoCursor` in the synchronous driver exposes blocking reads. Running a `while(true)` loop waiting for tailable events on an HTTP request thread ties up the thread indefinitely and complicates shutdown.

With imperative Spring Data, prefer `MessageListenerContainer` with an appropriate executor and lifecycle. With reactive, keep the `Flux`/subscription inside a component with explicit ownership and stop policies.

### 8.2. Imperative Listeners Must Also Distinguish Silence from Death

A `MessageListener` callback **not firing** for a minute can be completely normal if no inserts occur. To verify the cursor is alive, inspect subscription/container task state, errors, driver monitoring, and heartbeats; never treat "listener isn't running" as proof MongoDB has failed.

## 9. Causes of Cursor Invalidation

There is no single cause for "tailable cursor stopped." Classify by layer:

| Category | Examples | Characteristics | Initial Policy |
| --- | --- | --- | --- |
| **Data and cursor position** | Capped collection overwrites the cursor's position; capped position lost | Cursor can become invalid even while networking is healthy | Reopen **with data-gap assessment** |
| **Query and collection** | Initial query has no match, collection is non-capped, unsupported sort | May complete early or error depending on case | Fix query/config; reopen only when conditions make sense |
| **Collection lifecycle** | Drop, recreate, rename/structural change | Old cursor is no longer attached to the right collection | Stop, verify schema and scope; re-bootstrap |
| **MongoDB topology** | Primary stepdown, election, node unavailable | Transient network/server errors may recover | Retry with backoff, monitor state, check for gaps |
| **Network / client** | Socket reset, server selection timeout, pool pressure | Driver/reactive publisher emits error | Bounded retry; do not apply blindly to all exceptions |
| **Security** | Expired credentials, revoked role, authentication failure | Retrying identically will not fix it | Fail-fast and alert operations |
| **Application lifecycle** | JVM shutdown, `dispose()`, upstream `take(1)`, HTTP disconnect | Cursor closed **intentionally** | Clean up; do not auto-restart |
| **Downstream business** | Handler throws exception, checkpoint store fails | Can terminate the whole stream even though source cursor is healthy | Handle business errors; do not blindly loop source |

### 9.1. CappedPositionLost: Not Just Another Retryable Error

A tailable cursor following a capped collection must preserve its read position. When writes are fast and the consumer processes slowly or stops, the document at the next read position can be **overwritten**. MongoDB can report an error such as **capped position lost**. Reopening lets you read currently retained documents, but **cannot recover evicted ones**.

```text
Cursor last saw E005

Producer fast:
  E006 ... E500 inserted

Capped collection now retains only:
  E300 ... E500

Cursor position E006 no longer available
       |
       +--> cursor error / invalid
       |
       +--> reopen from existing data
                 |
                 +--> E006..E299 cannot be read here
```

If SLAs require "zero lost events," you need an archive/outbox/durable queue or rebuild procedure, not merely more reconnect attempts.

### 9.2. Collection Drop/Recreate

When a collection is dropped and recreated with the same name, **an old cursor does not automatically become a valid cursor on the new collection**. The system must:

1. Recognize that collection lifecycle may have changed.
2. Verify the new collection is capped with expected schema/options.
3. Evaluate whether the old collection's checkpoint still has meaning.
4. Decide whether a snapshot/rebuild is required.
5. Reopen only after preconditions are verified.

Never treat "same name `device_event_log`" as proof of a continuous data stream.

### 9.3. Permission or Query Errors Are Persistent Failures

If an account lacks read privileges on a collection, or MongoDB rejects `tailable` on a regular collection, retrying every 100 ms only generates noise and load. Separate **configuration errors** from transient network errors via exception classes/error codes and fail clearly so operators can fix them.

Avoid parsing English error strings as your sole rule: driver and server versions can change wording. Prefer exception types, verified server error codes/names, and a tested error policy.

## 10. Retry on Error Differs from Repeat on Complete

In Reactor:

- `retryWhen(...)` resubscribes **when upstream emits `onError`** according to policy.
- `repeatWhen(...)` resubscribes **when upstream emits `onComplete`** according to policy.
- When a subscriber **cancels**, no new subscription should be triggered automatically.

Because a tailable stream can terminate via both **errors** and **normal completion**, attaching only `retryWhen` is **insufficient** to cover all cases. Conversely, attaching only `repeat()` will not recover from errors and risks creating a hot loop.

### 10.1. Wrong Way: Infinite Retry on Every Error

```java
// ANTI-PATTERN.
return template.tail(new Query(), DeviceEvent.class)
    .retry();
```

Drawbacks:

- Retries configuration errors forever.
- No backoff, potentially spamming MongoDB.
- Fails to separate source errors from downstream errors.
- Does not handle cursor completion.
- No checkpointing, risking duplicates or missed events.
- Gives operators no failure state to act upon.

### 10.2. Wrong Way: Immediate Repeat

```java
// ANTI-PATTERN when a cursor can close immediately due to no initial match.
return template.tail(query, DeviceEvent.class)
    .repeat();
```

When a query matches nothing at open time and completes immediately, `repeat()` creates a **tight reopen loop**, burning CPU, issuing continuous queries, and overloading MongoDB.

### 10.3. Use defer to Create a Fresh Cursor per Retry

```java
Flux<DeviceEvent> newCursorEverySubscribe =
    Flux.defer(() ->
        reactiveTemplate.tail(
            new Query(), DeviceEvent.class));
```

`Flux.defer` ensures each subscribe/retry constructs **a fresh tail Publisher** and re-evaluates decisions inside the supplier. When using checkpoints, load the checkpoint **inside `defer`** instead of capturing a stale value once.

### 10.4. Reconnect Policy with Backoff and Bounds

File `TailableReconnectSource.java`:

```java
package com.example.monitoring;

import java.time.Duration;
import com.mongodb.MongoSocketException;
import com.mongodb.MongoTimeoutException;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

public final class TailableReconnectSource {

    private final ReactiveMongoTemplate template;

    public TailableReconnectSource(
            ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<DeviceEvent> watchWithReconnect() {
        Flux<DeviceEvent> eachCursor = Flux.defer(
            () -> template.tail(
                new Query(), DeviceEvent.class));

        return eachCursor
            // Retry only classified transient errors.
            .retryWhen(Retry.backoff(
                    5, Duration.ofMillis(300))
                .maxBackoff(Duration.ofSeconds(10))
                .jitter(0.5)
                .filter(TailableReconnectSource::isNetworkProblem))
            // Cursor completed: reopen slowly, do not spin.
            .repeatWhen(completions ->
                completions.delayElements(
                    Duration.ofSeconds(3)));
    }

    private static boolean isNetworkProblem(Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof MongoSocketException
                    || current instanceof MongoTimeoutException) {
                return true;
            }
        }
        return false;
    }
}
```

This is a **baseline reconnect pattern**, not yet a consumer with delivery guarantees. If the driver emits other errors such as election-related failures or overwritten position, this classifier may **stop** rather than auto-restart. That is intentional: decide explicitly when reopening is safe versus when reconciliation is required.

### 10.5. Reading the Operator Chain Carefully

```text
DEFER(create tailable cursor)
          |
          +--> onNext: forward event
          |
          +--> onError:
          |     if transient + retry budget -> backoff -> new subscribe
          |     else -> propagate error to supervisor
          |
          +--> onComplete:
                repeatWhen -> wait 3s -> new subscribe

Cancel/shutdown -> close subscription, no automatic re-open.
```

In this example, `retryWhen` retries only errors matched by `isNetworkProblem`. All other errors must surface to the supervisor/alerting layer instead of being hidden inside `onErrorResume(ex -> Flux.empty())`—masking errors turns exceptions into completions and triggers unclassified repeat loops.

### 10.6. Retry Budget Is Not a Downtime Budget

`Retry.backoff(5, ...)` caps **attempts within a single error streak**, but does not tell you whether RTO was exceeded or how long the cursor has been silent. Add alerts, overall deadlines, or a service-level lifecycle supervisor.

Once retries are exhausted, **emit the error**, mark the consumer degraded/failed, and let operations tooling decide on restarts. Never loop endlessly on every error merely to keep the process looking "up" on a dashboard.

### 10.7. Distinguish Restart from Data Recovery

`watchWithReconnect()` addresses **connection liveness** only, without checkpointing. If a cursor completes and reopens from the start of retained data, the consumer may re-read already processed records; if it starts at the current tail, it can miss records written during downtime.

Therefore **"reconnect success" ≠ "recovered without data loss."** When business effects must apply once, design application checkpointing, replay, and deduplication from the beginning.

## 11. Why Do Tailable Cursors Lack Resume Tokens?

Change streams return a **resume token** inside the event envelope and support `resumeAfter(...)`/`startAfter(...)` within oplog limits. Tailable cursors return **documents from the capped collection**, not change-stream tokens.

```text
Change stream:
  ChangeStreamEvent<T>
     +-- event._id = opaque resume token
     +-- operationType / documentKey / fullDocument

Tailable cursor:
  DeviceEvent
     +-- DeviceEvent.id
     +-- DeviceEvent.sequence (if application-generated)
     +-- payload fields
     +-- NO change-stream resume token
```

Never pass `DeviceEvent.id` into `ChangeStreamOptions.resumeAfter(...)`. They belong to completely different protocols. Likewise, do not treat a MongoDB `ObjectId` as a globally monotonically increasing append offset in all situations.

### 11.1. If Replay Is Needed, Define a Meaningful Offset

One approach is adding `sequence` or `eventId` to **each appended document**. However:

- `eventId` supports deduplication only if unique and stable.
- A `sequence` used as an offset **must reflect a reliable write order**. A counter allocated prior to insert is insufficient if multiple producers can commit inserts out of sequence order.
- `recordedAt` or `ObjectId` does not guarantee exact append order across hosts, producers, and clocks.
- Once data has rolled over, even a strict sequence **cannot recreate** lost documents.

Do not default to "resume via `_id > lastId`." If `_id` is a random UUID, numeric/lexicographic comparisons have nothing to do with append order.

### 11.2. Conditions for Meaningful Sequence Checkpoints

A simple strategy works when the system guarantees:

1. Every event carries a `sequence` that increases monotonically **in exact append order within a single stream**.
2. No lower-sequence record is ever appended after a higher-sequence record in the same stream.
3. No sequence number is reserved and left unwritten such that it looks like data loss.
4. The consumer checkpoints only after a durable effect.
5. A unique `eventId` exists for idempotency during replay.

These are **producer architecture invariants**, not guarantees provided automatically by MongoDB or Spring Data.

## 12. Re-Reading from an Application Checkpoint

Suppose a producer assigns `sequence` in strict append order within the collection. A checkpoint store persists `lastAppliedSequence` per **stream/consumer identity**, for example:

```javascript
{
  _id: "device-event-consumer-A",
  lastAppliedSequence: NumberLong(1250),
  updatedAt: ISODate("2026-11-20T02:30:00Z"),
  streamVersion: 1
}
```

On reconnect, the consumer can query for documents with `sequence > 1250`. Still, if no matching document exists when opened, **the tailable cursor may close early**. Delayed reopen logic is still required; do not treat the filtered query as a guaranteed infinite subscription.

### 12.1. Reactive Checkpoint Reader

File `DeviceEventCheckpointStore.java`:

```java
package com.example.monitoring;

import reactor.core.publisher.Mono;

public interface DeviceEventCheckpointStore {

    // Empty means this stream has never completed an event.
    Mono<Long> loadLastAppliedSequence();

    // Must durably persist a monotonic checkpoint,
    // not blindly overwrite a newer checkpoint.
    Mono<Void> saveLastAppliedSequence(long sequence);
}
```

This is an interface, not a complete repository implementation. In production, include `streamId`, `consumerOwner`, `streamVersion`, and monotonic update/fencing checks when multiple instances may run.

### 12.2. Load the Checkpoint Inside Flux.defer, Never Cache Stale Offsets

File `CheckpointAwareTailableSource.java`:

```java
package com.example.monitoring;

import java.time.Duration;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

public final class CheckpointAwareTailableSource {

    private final ReactiveMongoTemplate template;
    private final DeviceEventCheckpointStore checkpoints;
    private final CursorErrorPolicy errorPolicy;

    public CheckpointAwareTailableSource(
            ReactiveMongoTemplate template,
            DeviceEventCheckpointStore checkpoints,
            CursorErrorPolicy errorPolicy) {
        this.template = template;
        this.checkpoints = checkpoints;
        this.errorPolicy = errorPolicy;
    }

    public Flux<DeviceEvent> open() {
        return Flux.defer(() ->
                checkpoints.loadLastAppliedSequence()
                    .defaultIfEmpty(0L)
                    .flatMapMany(lastApplied -> {
                        Query query = Query.query(
                            Criteria.where("sequence")
                                .gt(lastApplied));
                        return template.tail(
                            query, DeviceEvent.class);
                    }))
            .retryWhen(Retry.backoff(
                    5, Duration.ofMillis(300))
                .maxBackoff(Duration.ofSeconds(8))
                .filter(errorPolicy::isTemporary))
            .repeatWhen(completions ->
                completions.delayElements(
                    Duration.ofSeconds(2)));
    }

    public interface CursorErrorPolicy {
        boolean isTemporary(Throwable error);
    }
}
```

**Prerequisite:** this code is sound only when `sequence` strictly follows append order as in Section 11.2. `defaultIfEmpty(0L)` starts at sequence 1. Adjust if your stream starts at another number or uses a snapshot offset.

**Separate error handling:** `CursorErrorPolicy` identifies only temporary cursor open/read failures. Unaccepted errors must propagate to trigger supervisor alerts; never silently treat invalid-index/collection errors or capped position lost as harmless transient network retries.

### 12.3. A Subtle Bug: Sequence Allocation Order Differing from Insert Order

```text
Producer A obtains sequence=100
Producer B obtains sequence=101
Producer B inserts E101 first
Consumer processes 101, checkpoints 101
Producer A inserts E100 later
Consumer resumes with sequence > 101
E100 is now permanently skipped
```

Consequently, with concurrent writers, **a monotonically incremented sequence at ID allocation time is not enough**. Enforce actual append order, use a single writer/partition with an ordering contract, or design replay with event IDs plus bounded overlap/deduplication/watermarks. Otherwise, never claim `sequence > checkpoint` provides "exactly once."

### 12.4. Never Use Timestamps as Absolute Checkpoints

`recordedAt > lastSeenTimestamp` can drop events sharing identical timestamps or arriving late. `recordedAt >= lastSeenTimestamp` can cause duplicates, though duplicates are usually easier to handle than missed events when `eventId` deduplication exists.

If timestamps must be used, account for bounded allowed lateness (watermark), bounded overlap scanning, deduplication, and retention checks. Never assume clocks across multiple producers are perfectly synchronized.

## 13. Sequential Processing, Durable Effect, Then Checkpoint

Given a `DeviceEventHandler`:

```java
package com.example.monitoring;

import reactor.core.publisher.Mono;

public interface DeviceEventHandler {
    // Must be idempotent by stable event.id().
    Mono<Void> applyOnce(DeviceEvent event);
}
```

File `DeviceEventConsumer.java`:

```java
package com.example.monitoring;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class DeviceEventConsumer {

    private final CheckpointAwareTailableSource source;
    private final DeviceEventHandler handler;
    private final DeviceEventCheckpointStore checkpoints;

    public DeviceEventConsumer(
            CheckpointAwareTailableSource source,
            DeviceEventHandler handler,
            DeviceEventCheckpointStore checkpoints) {
        this.source = source;
        this.handler = handler;
        this.checkpoints = checkpoints;
    }

    public Flux<DeviceEvent> consume() {
        return source.open()
            .concatMap(event ->
                handler.applyOnce(event)
                    .then(checkpoints.saveLastAppliedSequence(
                        event.sequence()))
                    .thenReturn(event));
    }
}
```

`concatMap` ensures **each event finishes processing before starting the next** on the consumer branch, preserving checkpoint order. Events may replay after consumer crashes or reconnects, so `handler.applyOnce` must be idempotent and persist its effect durably before completing `Mono<Void>`.

### 13.1. Never Checkpoint Before the Business Effect

```java
// ANTI-PATTERN: loses the event if the process crashes after checkpointing.
source.open().concatMap(event ->
    checkpoints.saveLastAppliedSequence(event.sequence())
        .then(handler.applyOnce(event)));
```

If `saveLastAppliedSequence` succeeds and `handler.applyOnce` fails, restarting with `sequence > lastApplied` skips an event whose business effect never occurred.

### 13.2. Never Swallow Errors and Still Checkpoint

```java
// ANTI-PATTERN: marks processed even when the handler fails.
handler.applyOnce(event)
    .onErrorResume(error -> Mono.empty())
    .then(checkpoints.saveLastAppliedSequence(
        event.sequence()));
```

To skip an event intentionally, implement an **explicit policy, metrics, audit trail, and/or dead-letter record**. Never apply `onErrorResume` broadly and treat the event as processed.

### 13.3. Handler Failures Differ from Cursor Failures

In Section 13's code, `source.open()` handles cursor-error retries independently, while `handler.applyOnce` executes **after** the source operator. If the handler throws an error, it exits the consumer to the supervisor instead of being misclassified as a MongoDB cursor failure.

Benefits:

- Avoids reopening cursors merely because a downstream API rejected a call.
- Allows separate classification of business, validation, timeout, and poison-event errors.
- Avoids accidentally skipping over unprocessed events.
- On consumer restart, the checkpoint still points to the last completed event.

### 13.4. Writing Effect and Checkpoint in One Transaction Where Suitable

When both target read model and checkpoint reside in the **same transaction-capable MongoDB deployment**, consider a short transaction that writes the **idempotent applied-event marker/effect** and updates the checkpoint together. Do not expect `@Transactional` to wrap external systems: HTTP calls, Kafka, and external databases do not roll back with MongoDB.

For external side effects, rely on stable event IDs, consumer inbox/outbox patterns, ACKs, and reconciliation. Never claim "exactly once" solely from `concatMap` and a `lastAppliedSequence` field.

### 13.5. What Should Checkpointing Do on Capped Position Lost?

Suppose the checkpoint reads `100`, while the capped collection currently retains events starting at `300`:

1. The old cursor may have lost its position, unable to read events `101..299`.
2. Reopening with `sequence > 100` starts reading at `300`.
3. Unless gaps are normal producer behavior, this is a **data loss gap**.
4. Do not checkpoint `300` and silently claim `101..299` completed.
5. Trigger alerts, mark degraded, and run snapshot/reconciliation from a durable source.

**Caveat:** if sequences are generated from a counter with legitimate gaps (rollbacks, skipped numbers), checking `next == previous + 1` alone cannot prove data loss. Gap detection must follow the **producer's sequence contract**, not generic assumptions about MongoDB.

## 14. Three Recovery Strategies and Their Limits

No single reconnect recipe fits every system. Choose among:

### 14.1. Strategy A — Live Only, Event Loss Acceptable

On each reconnect, open a tailable cursor on the relevant dataset without attempting exact document-by-document replay. Use only when:

- The consumer only refreshes transient UI/caches.
- Another snapshot/current-state API exists to resync.
- No financial, reward-point, or mandatory audit side effects occur.
- Product owners accept missing updates during downtime.

Pros: minimal state, easy to implement. Cons: **no delivery guarantees**; state this explicitly in SLAs.

### 14.2. Strategy B — Application Checkpoint + Replay Within Retention

Persist a valid event ID or sequence; on reconnect, re-read retained events in the capped collection and deduplicate.

Conditions:

1. The producer supplies a valid replay key and guarantees append ordering by contract.
2. The consumer is idempotent.
3. Gap detection and fallback exist if the checkpoint falls behind retained data.
4. Consumer throughput can catch up to producers, not just reconnect.

Pros: recovers from brief network hiccups. Cons: **bound by retention and producer ordering**; queries alone do not provide exactly-once.

### 14.3. Strategy C — Durable Event Source + Tailable Cursor for Low Latency

Events are written to a **durable source** (outbox/queue/event store) with a meaningful offset/event ID. The tailable cursor acts solely as a fast notification channel; on disconnects or rollover, the consumer compares offsets and replays from the durable source.

Pros: provides genuine gap recovery; simplifies downstream consistency verification. Cons: adds components, cost, and consistency workflow complexity.

### 14.4. Strategy Selection Table

| Requirement | Live only | Checkpoint on capped | Durable source + reconcile |
| --- | --- | --- | --- |
| Dashboard tolerates occasional missed events | Possible | Possible | Usually unnecessary |
| Needs a few minutes of replay after offline period | Not guaranteed | Conditional | Yes |
| Outage longer than capped retention window | No | **No** | Yes, if durable source still holds data |
| Increment reward points exactly once | Unsuitable | Only with idempotency and gap handling | Generally better fit |
| Mandatory multi-month audit trail | Unsuitable | Unsuitable | Requires durable storage per policy |
| Minimal component footprint | High | Medium | Lower |

## 15. Reconnection Requires a State Machine, Not Just One Operator

For a production consumer, lifecycle states can be modeled as:

```text
STARTING
   |
   v
VALIDATING_COLLECTION
   |
   +-- non-capped / no permission --> FAILED_CONFIG
   |
   v
OPENING_CURSOR
   |
   +-- temporary error --> BACKOFF --> OPENING_CURSOR
   +-- non-retryable  --> FAILED_CONFIG / MANUAL_REPAIR
   |
   v
ACTIVE (receiving, or validly waiting)
   |
   +-- onNext --> PROCESSING --> CHECKPOINT --> ACTIVE
   |
   +-- onComplete --> CLOSED --> BACKOFF --> OPENING_CURSOR
   |
   +-- network error --> BACKOFF --> OPENING_CURSOR
   |
   +-- capped position lost --> RECONCILIATION_REQUIRED
   |
   +-- cancellation / shutdown --> STOPPED
```

**ACTIVE** does not mean "always receiving an event within 5 seconds." It is a liveness state verified via subscription lifecycle, server health, and heartbeats when applicable.

### 15.1. Never Reconnect After Intentional Stop

Example:

```java
import reactor.core.Disposable;

Disposable subscription =
    consumer.consume().subscribe(
        event -> metrics.onProcessed(event),
        error -> metrics.onConsumerFailed(error));

// Inside the owning component's shutdown callback:
subscription.dispose();
```

`consumer` is an injected/initialized instance, and `metrics` is a monitoring service. This shows `Disposable` ownership only; production code needs integration with Spring lifecycle (`SmartLifecycle` or equivalent), supervision, readiness, and cleanup—never call `subscribe()` ad hoc and lose the reference.

When `dispose()` executes, downstream cancellation ends the upstream tail; never wrap an external "reopen whenever stopped" loop around the subscription that hangs JVM shutdown or spawns cursors continuously.

### 15.2. Never Hide Errors in doOnError

```java
source.open()
    .doOnError(error -> metrics.onCursorError(error))
    .onErrorResume(error -> Flux.empty());
```

This is a **dangerous pattern**: `onErrorResume` turns every error into a normal completion, triggering an outer `repeatWhen` layer and masking the root cause. Logging and metrics **do not replace** error classification and fail-fast/reconcile decisions.

### 15.3. Bounded Retries and Circuit Breakers

When the server is down, hundreds of attempts per instance can worsen the outage. Apply:

- Exponential backoff with jitter.
- Reasonable attempt limits/deadlines before reporting degraded status.
- Bounds on consumer instances and cursors.
- Routing misconfiguration/credential errors to manual intervention.
- Reconnect concurrency limits and circuit breakers during cluster-wide outages.

Never "self-heal" a consumer by wiping checkpoints and jumping to current time; doing so destroys evidence of data gaps that must be reconciled.

## 16. Heartbeats and Health: Detecting Whether a Cursor Is Alive

For sporadic business event streams, **time since last `onNext`** is an activity metric, **not proof the connection is alive**.

### 16.1. Three Separate Metrics

| Metric | Question Answered |
| --- | --- |
| `time_since_last_event` | How long since an event was received? |
| `cursor_subscription_active` | Is the subscription/client task still running? |
| `time_since_last_successful_checkpoint` | How long since an event was durably applied? |

On low-traffic sources, the first two might read "1 hour with no events" and "cursor still active"—which is normal. On a source emitting heartbeats every 5 seconds, one minute without a heartbeat is suspicious.

### 16.2. Heartbeat Documents Require Their Own Contract

A producer can periodically append a heartbeat to the capped collection:

```javascript
{
  _id: "HB-20261120-020000",
  type: "HEARTBEAT",
  tenantId: "SYSTEM",
  recordedAt: ISODate("2026-11-20T02:00:00Z")
}
```

If using heartbeats, define:

- Who is responsible for appending them, and what happens if that producer dies?
- Do heartbeats degrade retention/rollover for real business data?
- Does filtering out heartbeats **on the server** put initial cursor matches at risk?
- Should heartbeats advance checkpoints, or act purely as health signals?
- How are emission schedule, alert thresholds, and clock skew handled?

Never append heartbeats with a fake user tenant ID, and never emit them so frequently that they evict business events prematurely.

### 16.3. Server maxAwaitTime Is Not Total Stream Timeout

In MongoDB drivers, tailable-await cursors can use `maxAwaitTimeMS`/`maxAwaitTime` to control how long a single `getMore` waits for data before returning. **The wait period of one `getMore`** does not mean **the cursor must complete or error afterward**, nor can Reactor's `Flux.timeout` be swapped directly for `maxAwaitTime`.

Check the exact MongoDB Java Driver and Spring Data APIs in use when tuning await/batch behavior. Never set `maxAwaitTimeMS=1000` and treat it as an SLA that "events must arrive within 1 second."

### 16.4. Do Not Confuse MongoDB Health with Consumer Health

A passing MongoDB ping **does not prove** the stream is subscribed or checkpoints are advancing. Conversely, a quiet period with no events does not prove MongoDB is down. Readiness/health checks should combine:

- Driver connection and server selection health.
- Subscription/container state.
- Error and reconnect counters.
- Checkpoint lag when the source is known to be active.
- Producer heartbeats or synthetic end-to-end events **only in controlled environments**.

## 17. Backpressure and Capped Collection Write Rate

A tailable cursor can deliver faster than a downstream processor. If producers insert E001–E010000 in one minute while the consumer processes only 100 events/minute, **the capped collection will overwrite positions before the consumer reads them** if the retention window is small.

### 17.1. Increasing Buffers Does Not Solve Long-Term Data Loss

```java
// ANTI-PATTERN if using an unbounded buffer to mask a slow consumer.
source.open()
    .onBackpressureBuffer();
```

This merely moves the bottleneck from the MongoDB cursor into application RAM; unbounded buffers risk OOM and do not keep historical data available on the source. Instead:

- Reduce handler latency and downstream I/O overhead.
- Control concurrency while preserving ordering/offset invariants.
- Increase capped size/retention where reasonable.
- Use a durable queue/outbox if event loss is unacceptable.
- Monitor consumption and producer/consumer rates.

### 17.2. Key Rates and Windows to Measure

| Variable | Meaning |
| --- | --- |
| `write_rate_events_per_second` | Documents appended per second |
| `bytes_per_second` | Rate at which capped storage fills |
| `effective_retention_window` | Age of the oldest document still retained |
| `process_rate_events_per_second` | Rate at which consumer applies effects |
| `consumer_lag_events` | Sequence delta (when an ordering contract exists) |
| `time_to_catch_up` | Whether the consumer can catch up before rollover |

A **capacity estimate**, not a guarantee:

```text
retention_seconds ~= capped_size_bytes / observed_write_bytes_per_second
```

For example, 16 MiB at a 1 MiB/s write rate may retain only about 16 seconds of data, before accounting for overhead and `max` limits. Measure under realistic workloads, especially when document sizes vary.

### 17.3. Checkpoint Ordering with Parallelism

`source.flatMap(event -> handler.applyOnce(event))` can complete out of order. With a single linear checkpoint, offset E105 can be saved before E104 finishes. To scale throughput, shard the stream by a stable partition key with **per-partition checkpoints/watermarks**, rather than simply swapping `concatMap` for `flatMap(concurrency=32)`.

## 18. Testing Tailable Cursors Requires a Real Capped Collection

A unit test mocking `ReactiveMongoTemplate.tail(...)` with `Flux.just(E1, E2)` proves only that the service consumes a `Flux`. It **does not** prove:

- The real MongoDB collection has `capped: true`.
- The cursor stays open at the end of the data.
- Initial no-match queries can complete or become invalid.
- The cursor errors when capped positions are overwritten.
- Reconnecting reads retained documents without recovering evicted ones.
- Repository `@Tailable` executes properly under Spring Data.

These behaviors require **integration tests against a real MongoDB server**. A replica set is not required solely to test a basic tailable cursor on a capped collection, though the environment must support capped collections. If also testing transactions or change streams, those features carry their own topology requirements.

### 18.1. Test Matrix

| Test | Condition | Expectation |
| --- | --- | --- |
| Valid collection | `capped: true` | Tail receives existing and subsequently appended documents |
| Non-capped collection | Regular collection | Server/driver rejects tailable behavior or raises appropriate error |
| Silent cursor | Inserts pause after initial match | No spurious `onNext`; terminal state monitored separately |
| Initial no-match | Filter matches no retained record | Observe complete/error/idle per server version; supervisor does not spin |
| Cursor completes | Fake `Flux.empty()` source | `repeatWhen` reopens after delay |
| Transient error | Fake source emits retryable error | `retryWhen` honors budget |
| Non-retryable error | Fake source emits validation/config error | Does not retry; propagates error |
| Cancel | Dispose subscription | Does not open new cursor |
| Rollover | Small collection size, fast producer | Observe position loss/gap; do not claim full replay |
| Checkpoint | Handler succeeds before save | Event checkpointed only after durable effect |
| Crash/replay | Failure between effect and checkpoint | Idempotent handler prevents double-apply |
| Producer reorder | Sequences out of append order | Test exposes skipped-event risk |

### 18.2. Integration Test Receiving New Documents After Subscribing

Spring Boot 3.x, JUnit 5, Reactor Test, Spring Data MongoDB Reactive example. **Run only against an authorized TEST MongoDB with an isolated database**. Use random collection names to avoid colliding with other data.

File `TailableCursorIntegrationTest.java`:

```java
package com.example.monitoring;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class TailableCursorIntegrationTest {

    @Autowired
    ReactiveMongoTemplate template;

    private static DeviceEvent event(
            String id, long sequence, String level) {
        return new DeviceEvent(
            id, sequence, "TENANT-TEST",
            "DEV-TEST", level, "test",
            Instant.parse("2026-11-20T02:00:00Z"));
    }

    @Test
    void receivesAnAppendAfterInitialDocument() {
        String name = "tail_test_"
            + UUID.randomUUID().toString()
                .replace("-", "");

        String suffix = UUID.randomUUID().toString();
        DeviceEvent first =
            event("E1-" + suffix, 1L, "INFO");
        DeviceEvent second =
            event("E2-" + suffix, 2L, "WARN");

        try {
            StepVerifier.create(
                template.createCollection(
                    name,
                    CollectionOptions.empty()
                        .capped()
                        .size(2 * 1024 * 1024)
                        .maxDocuments(1000)))
                .expectNextCount(1)
                .verifyComplete();

            StepVerifier.create(template.insert(first, name))
                .expectNextCount(1)
                .verifyComplete();

            Flux<DeviceEvent> tail = template.tail(
                new Query(), DeviceEvent.class, name)
                .take(2);

            StepVerifier.create(tail)
                .assertNext(actual -> {
                    assertThat(actual.id()).isEqualTo(first.id());
                    assertThat(actual.sequence()).isEqualTo(1L);
                })
                // First event received: cursor has an active subscription,
                // avoiding sleeping and guessing watcher readiness.
                .then(() -> StepVerifier.create(
                        template.insert(second, name))
                    .expectNextCount(1)
                    .verifyComplete())
                .assertNext(actual -> {
                    assertThat(actual.id())
                        .isEqualTo(second.id());
                    assertThat(actual.sequence())
                        .isEqualTo(2L);
                })
                .expectComplete()
                .verify(Duration.ofSeconds(20));
        } finally {
            // Drop only the isolated collection owned by this test run.
            StepVerifier.create(template.dropCollection(name))
                .verifyComplete();
        }
    }
}
```

Because `first` is seeded **before subscribing** and `StepVerifier` waits for `first` before inserting `second`, the test avoids the common race condition: "inserting before the cursor opens." `take(2)` actively cancels upstream after two records; that is **test behavior**, not the cursor completing on its own.

### 18.3. Never Run drop on a Real Database

Although the example uses a random collection name, it still runs `dropCollection(name)` in `finally`. Always configure test profiles/URIs to point to an **isolated database**, never shared with dev or prod. Never place this code inside a production startup service.

Before running tests, verify:

1. The MongoDB test connection has permission to create/drop collections.
2. The database is dedicated solely to testing or containers.
3. The collection has `capped=true` and a reasonable size.
4. The test runner has Reactor Test and Spring Data MongoDB reactive dependencies.
5. MongoDB and driver versions align with the APIs used.

These tests are **illustrative snippets** in documentation and carry no claim of having been compiled or executed during Markdown authoring.

### 18.4. Testing Initial No-Match Without Assuming Identical Behavior Across Versions

In another test, seed only `level=INFO` documents, then tail with `level=CRITICAL`. Observe all three signals:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

AtomicBoolean sourceCompleted = new AtomicBoolean(false);
AtomicReference<Throwable> sourceError =
    new AtomicReference<>();

Query criticalOnly = Query.query(
    Criteria.where("level").is("CRITICAL"));

Flux<DeviceEvent> tail = template
    .tail(criticalOnly, DeviceEvent.class, testCollectionName)
    .doOnComplete(() -> sourceCompleted.set(true))
    .doOnError(sourceError::set);

// Bound observation window on the test side.
StepVerifier.create(
        tail.take(Duration.ofSeconds(2)))
    .verifyComplete();

System.out.println("Source completed = "
    + sourceCompleted.get());
System.out.println("Source error = "
    + sourceError.get());
```

This is a **test method snippet** assuming `template`, `testCollectionName`, `StepVerifier`, and imports are present. The goal is not to assert that every MongoDB version completes within a fixed delay, but to observe **source completion/errors separately from test-timeout upstream cancellation**. If the source emits an error, assert the error against the fixture rather than hiding it and passing unconditionally.

### 18.5. Unit Testing repeatWhen Without MongoDB

To test the **reopen policy**, mock a source that completes immediately:

```java
package com.example.monitoring;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class TailableReconnectPolicyTest {

    @Test
    void reopensAfterTwoEmptyCompletions() {
        AtomicInteger opens = new AtomicInteger();
        DeviceEvent expected = new DeviceEvent(
            "TEST-" + UUID.randomUUID(),
            1L, "TEST", "DEV", "INFO",
            "arrived", java.time.Instant.now());

        Flux<DeviceEvent> syntheticSource =
            Flux.defer(() -> {
                int attempt = opens.incrementAndGet();
                if (attempt <= 2) {
                    return Flux.<DeviceEvent>empty();
                }
                return Flux.just(expected);
            });

        Flux<DeviceEvent> reopen =
            syntheticSource
                .repeatWhen(completions ->
                    completions.delayElements(
                        Duration.ofMillis(20)))
                .take(1);

        StepVerifier.create(reopen)
            .expectNext(expected)
            .verifyComplete();

        assertThat(opens.get()).isEqualTo(3);
    }
}
```

This test proves only **Reactor resubscription after completion** without spinning immediately. It does not prove MongoDB cursors complete on no-match in all versions, nor does it test capped position loss.

### 18.6. Unit Testing Retry Budget and Fail-Fast

Another test should inject error sources:

- Error A is transient → policy retries several times then recovers.
- Error B is permission/config → policy does not retry and emits `onError`.
- After retry budget exhaustion → stream emits error to supervisor.
- After cancel from `take(1)` or `Disposable.dispose()` → no unintended resubscription occurs.

You do not need a disconnected real cluster to test **pure Reactor policy**; unit tests with `Flux.defer`/`Flux.error` suffice. Testing real driver close semantics still requires integration tests.

## 19. Reproducing Rollover Errors in a Test Environment

Rollover depends on write rate, collection size, and cursor scheduling. A test can:

1. Create a very small capped collection on an **isolated test MongoDB**.
2. Seed event E001 and open tail.
3. Intentionally delay the consumer (in test) and append many relatively large documents to force rollover.
4. Observe overwritten events and potential position-lost errors.
5. Stop and inspect the collection to find the lowest retained sequence.
6. Compare against the checkpoint to identify the unreplayable gap.
7. Assert **RECONCILIATION_REQUIRED** status per business policy instead of marking success.

Do not write a test asserting `CappedPositionLost` always occurs after exactly 100 inserts: behavior depends on storage, batching, scheduling, MongoDB version, and `getMore` timing. What matters is verifying that **when a gap or position loss occurs, the consumer does not silently skip past it**.

### 19.1. A Retained-Range Indicator

If the producer assigns sequences in append order and the capped collection retains E300–E500, running:

```javascript
db.device_event_log.find().sort({ $natural: 1 }).limit(1);
```

reveals the **oldest surviving document**. Note this is a **regular** query, not a tail. From that first document, the consumer can compare against its checkpoint under its sequence contract. Do not conclude "there is no gap" merely because the first document has an ascending `_id`—that does not prove all prior events were processed.

## 20. Metrics and Logging for Reconnects

A system can reconnect endlessly without alerting if metrics only check "service process is up." Separate liveness, correctness, and data retention.

### 20.1. Metrics to Track

| Metric | Meaning |
| --- | --- |
| `tailable_cursor_open_attempts_total` | Total cursor open attempts |
| `tailable_cursor_active` | Active subscriptions/cursors per stream |
| `tailable_cursor_completed_total` | Source `onComplete` signals, separate from cancel |
| `tailable_cursor_errors_total` | Errors by category: transient, config, position lost |
| `tailable_cursor_reconnect_total` | Reopens triggered by error or complete |
| `tailable_cursor_reconnect_delay_seconds` | Wait time before next attempt |
| `tailable_cursor_retry_exhausted_total` | Retry budget exhausted count |
| `tailable_events_received_total` | Documents emitted by source |
| `tailable_events_processed_total` | Business effects durably applied |
| `tailable_checkpoint_write_failure_total` | Checkpoint persistence failures |
| `tailable_checkpoint_sequence` | Last applied offset per stream (only when sequence is valid) |
| `tailable_duplicate_event_total` | Duplicate events deduplicated |
| `tailable_gap_detected_total` | Unreplayable or ordering gaps detected |
| `tailable_oldest_retained_age_seconds` | Age of oldest document remaining in buffer |
| `tailable_handler_duration_seconds` | Downstream processing duration |

Never attach high-cardinality event IDs, user IDs, or tenants as metric labels. Use low-cardinality stream names, worker roles, error categories, and environments. In logs, use safe correlation IDs and avoid printing full PII payloads.

### 20.2. Structured Log Classification

```json
{
  "event": "tailable_cursor_reconnect",
  "stream": "device-event-log",
  "cause": "CURSOR_COMPLETED",
  "action": "REOPEN_AFTER_BACKOFF",
  "attempt": 3,
  "delayMs": 2000,
  "checkpointMode": "APPLICATION_SEQUENCE",
  "dataGapStatus": "NOT_YET_CHECKED"
}
```

Keep `dataGapStatus` as **not yet checked** until backed by producer/retained-range evidence. Never log `"recovered": true` simply because MongoDB accepted a new cursor.

### 20.3. Alert on Impact, Not Raw Error Counts Alone

For example:

- **Reconnect rate rising**, no gaps yet: inspect network, elections, connection pool, and server selection.
- **Checkpoint age rising** while producers emit steadily: inspect slow/blocked downstream or processing exceptions.
- **Capped retention window drops below target RTO**: increase capacity, throttle write rate, or add a durable source.
- **Position lost**: prioritize data reconciliation, not merely restarting processes.
- **Active=0** while supervisor is expected running: inspect shutdown/cancellation and error paths.
- **Received rising while processed stays flat**: business handler failure, not a disconnected cursor.

## 21. Runbook: Troubleshooting "No New Events Received"

Follow the evidence step by step:

### Step 1 — Check the Producer

- Are new events actually being appended to the right collection and database?
- Do appended events have the expected shape and tenant?
- Is the producer blocked by validation, permissions, or quotas?
- Do new documents appear when running a **regular query** (authorized read check)?

If no inserts occur, a quiet tail is normal behavior.

### Step 2 — Verify the Collection

```javascript
db.device_event_log.isCapped();
db.getCollectionInfos({ name: "device_event_log" });
```

Check:

- `capped=true`?
- Was the collection dropped/recreated?
- Right database and collection name?
- Is data still within the retention window?

Never resize or drop/recreate a production collection without an approved migration plan and proper authorization.

### Step 3 — Check Subscription and Driver

- Was the `Flux` actually subscribed to?
- Do logs/traces show `onComplete`, `onError`, or `cancel`?
- Is an imperative listener container running, or did its task fail?
- Did application shutdown or request disconnect dispose the cursor?
- Are there MongoDB server-selection errors or primary elections?

Never rely on "last `onNext` was 5 minutes ago" as the sole diagnosis.

### Step 4 — Check the Initial Query

- Is an overly narrow filter causing **initial no-match**?
- Was an unsupported sort used on the tailable cursor?
- Does the query lack an initial match while code simply waits without monitoring completion?
- Is it filtering on a tenant that has never had a document in the capped collection?

If a query can close early on no-match, adjust the delayed reopen policy or redesign scope; never create a sub-100 ms reconnect loop.

### Step 5 — Inspect and Classify Errors

| Observed Error | Action |
| --- | --- |
| Socket timeout / transient server selection | Retry with backoff/budget; check network/cluster |
| Cursor completed | Repeat/reopen with delay if consumer should remain active |
| Non-capped collection | Fail config; do not retry infinitely |
| Capped position lost | Reconcile / detect gaps before claiming recovery |
| Authentication/authorization failure | Fail-fast; fix credentials/roles |
| Invalid query / unsupported sort | Fix code/query and run tests |
| Handler/checkpoint failure | Fix downstream; do not checkpoint failed events |
| Intentional dispose | Do not auto-reconnect |

### Step 6 — Assess Potential Data Loss

1. Read the last durably stored checkpoint.
2. Identify the oldest document remaining in the capped collection (in natural order).
3. If valid sequences exist, compare under the **actual append-order contract**.
4. If a gap exists, record the potentially lost range and which durable source can backfill it.
5. Never advance the checkpoint to current just to silence alerts.
6. After reconciliation, restore the consumer and watch the checkpoint catch up to the source.

### Step 7 — Postmortem

Document root cause: configuration, network, rollover, consumer lag, retention sizing, unauthorized query, or lifecycle bug. Update monitoring, capacity sizing, and integration tests to prevent recurrence.

## 22. Comparing Tailable Cursors, Change Streams, and Polling

| Criterion | Tailable cursor | Change stream | Checkpointed polling |
| --- | --- | --- | --- |
| Source data | **Capped collection** | Supported replica set/sharded MongoDB | Suitable collection/query |
| Purpose | Read newly appended documents | Follow insert/update/delete/... **changes** | Periodically read records matching criteria |
| MongoDB event envelope | No `operationType`/resume token like change streams | Has `ChangeStreamEvent<T>`/resume token | None unless self-designed |
| Resume | Self-defined checkpoint/replay | Resume token within oplog/history range | Self-designed keyset/checkpoint |
| Retention | Capped capacity, rollover | Oplog/change-stream history | Per collection/history policy |
| Source updates/deletes | Not emitted for regular collection updates/deletes | Emits corresponding events | Depends on query/delta design |
| No events | Cursor can await; handle initial no-match | Long-lived cursor waiting for changes | Empty poll returns normally |
| Reconnect | Open new cursor, evaluate gaps | Driver resumes with token as conditions allow | Re-poll from checkpoint |
| Required infrastructure | Capped collection | Replica set/sharded cluster | Need not be capped |
| Durable auditing | Insufficient if capped-only | Insufficient if history ages out | Needs durable source |

### 22.1. When to Choose Tailable Cursors

Suitable when:

- Data is inherently a **short-lived append-only log** stored in a capped collection.
- Producer/consumer run near real time with brief outages and sufficient retention windows.
- The application defines clear liveness/recovery policies.
- Event envelopes for updates/deletes on other collections are unnecessary.

### 22.2. When to Choose Change Streams

Better suited when:

- You must react to **changes** on regular collections.
- You need `operationType`, `documentKey`, update deltas, and resume tokens.
- You need to watch multiple collections across a database/deployment.
- You already run a replica set or sharded cluster.

Change streams still face oplog retention limits, duplicates/retries, and checkpointing needs. Do not mistake "has a resume token" for a guarantee of infinite replay.

### 22.3. When Polling Can Be Simpler

If the application only needs to refresh summary tables once per minute, an indexed/checkpointed query on a scheduler **can be simpler** than a long-lived stream. Polling gives clear per-request lifecycles, though you must avoid full scans and design keysets/idempotency if events cannot be dropped.

Choose the model based on SLA, write rate, retention, and delivery requirements—not merely because an API sounds "reactive" or "real-time."

## 23. Misconceptions to Eliminate

1. **"Tailable works on any collection."** False: requires a capped collection.
2. **"No events for 10 seconds means the cursor is dead."** False: it may simply be waiting.
3. **"Flux.empty() means the cursor is waiting."** False: that is immediate completion.
4. **"No initial match will always wait for future documents."** Not guaranteed; the cursor may die/close.
5. **"retryWhen alone handles every termination."** False: completion is not an error.
6. **"repeat alone is enough."** False: does not handle errors and can create a hot loop.
7. **"Timeout is a heartbeat."** No: `timeout` can cancel valid cursors.
8. **"Reconnecting means zero data loss."** False: capped rollover can overwrite history.
9. **"Document ID is a change-stream resume token."** False: two different cursor protocols.
10. **"ObjectId is always an insert-order offset."** No global guarantee exists.
11. **"An incrementing sequence counter guarantees order."** Insufficient if writer inserts arrive out of order.
12. **"Checkpointing before running the handler is faster."** Wrong: loses events on crash.
13. **"Parallel flatMap can still write a single sequential checkpoint."** Not without watermarks or partitioning.
14. **"On no-match, reopen immediately with zero delay."** Wrong: creates a hot loop.
15. **"Changing sort to recordedAt is more accurate."** Incompatible with tailable natural-order semantics.
16. **"dispose() should also auto-reconnect."** Wrong: intentional cancellation requires cleanup and stop.
17. **"If MongoDB responds to ping, the stream must be active."** False: separate subscription/lifecycle state.
18. **"A capped collection is itself a durable queue."** False: lacks ACKs, consumer groups, and infinite retention.
19. **"@Tailable handles reconnect and dedupe automatically."** No; the application must design them.
20. **"Mocking Flux.just() proves cursor behavior."** No: requires integration tests on a real capped collection.

## 24. Pre-Deployment Code Review Checklist

### 24.1. Data Contract and Collection

1. **Real capped collection:** verified `isCapped()`/collection options, not just annotations.
2. **Retention sizing:** `size`/`max` handle write rate and target offline window.
3. **Stable schema:** Java entity maps fields, version, and collection accurately.
4. **Event ID:** stable key exists for deduplication when needed.
5. **Sequence (if used):** has an **append-ordering contract** and producer concurrency tests.
6. **No infinite replay expectations:** archive/rebuild policy covers exceeding retention.
7. **No routine drops/deletes:** avoids invalidating cursors and unplanned data loss.

### 24.2. Cursor/Query Lifecycle

8. **Right API:** `ReactiveMongoTemplate.tail`/`@Tailable` or `MessageListenerContainer`.
9. **Natural order:** no arbitrary field sorting on tailable queries.
10. **Initial no-match:** tested with a delayed reopen policy.
11. **Idle differs from complete:** silence without `onNext` is not treated as a dead cursor.
12. **Complete differs from error:** separate `repeatWhen` and `retryWhen` policies.
13. **Fail-fast on misconfiguration:** permission, non-capped, and invalid-query errors do not retry forever.
14. **Capped position lost:** detected and routed to reconciliation/alerts.
15. **Backoff/jitter:** prevents reconnect storms.
16. **Retry budget:** exhausting the budget emits failed/degraded status.
17. **Cancel/shutdown:** no new cursor opened after stop.
18. **Single ownership:** no unbounded cursors opened per HTTP request.

### 24.3. Processing and Checkpointing

19. **Explicit replay mode:** live-only, capped checkpoint, or durable source.
20. **Checkpoint after durable effect:** never inverted.
21. **Idempotency:** replay or multiple replicas do not duplicate business effects.
22. **No swallowed errors:** failed handlers never advance checkpoints.
23. **Ordered processing:** `concatMap` or partition-aware watermarks; never checkpoint past unfinished events.
24. **Gap detection:** policy handles rollover/consumer lag; never silently jumps checkpoints over gaps.
25. **No ID confusion:** `ObjectId`, timestamps, or `ChangeStreamOptions` tokens are not treated as tailable offsets.
26. **Failover support:** network errors classified and recovery planned when collection lifecycle changes.

### 24.4. Validation and Operations

27. **Unit tests:** retry budget, complete-repeat, cancel, fail-fast.
28. **Integration tests:** real capped collection, initial match, post-subscribe append, initial no-match.
29. **Fault scenarios:** rollover, network/driver disconnect, process restart with checkpoint.
30. **Right environment:** test isolation; never drop shared data.
31. **Metrics:** active, errors, reconnects, checkpoints, lag, capped retention, and gaps.
32. **Runbook:** alerts distinguish config vs. transient vs. data-loss paths.
33. **Security:** tenant-scoped; never expose raw events/PII to arbitrary clients.
34. **Accurate SLAs:** distinguish "near-real-time streaming" from "zero event loss."

## 25. Hands-On Exercises

The application has a capped collection `sensor_events` with events:

```javascript
{
  _id: "EVT-500",
  sequence: NumberLong(500),
  sensorId: "S-01",
  tenantId: "TENANT-A",
  kind: "MEASUREMENT",
  value: 37.8,
  recordedAt: ISODate("2026-11-20T02:00:00Z")
}
```

### Exercise 1 — Classify Terminal Signals

Given five scenarios:

1. No inserts for 15 minutes; cursor has not emitted `onComplete`/`onError`.
2. Cursor emits `onComplete` immediately when query `kind="ALERT"` matches no documents.
3. Driver emits a network timeout.
4. MongoDB reports capped position lost.
5. Operator shuts down the app and disposes the subscription.

For each scenario, fill in:

| Scenario | Reconnect? | Check for Data Loss? |
| --- | --- | --- |
| 1 | Not solely due to silence | Only if lag/retention evidence exists |
| 2 | Can reopen after delay if stream must continue | Depends on replay/offset policy |
| 3 | Bounded retry if transient error | Yes, if downtime may exceed retention |
| 4 | Reopen only after assessment/reconciliation | **Yes, top priority** |
| 5 | **No** | Per shutdown/restart contract |

Explain why `timeout(Duration.ofSeconds(10))` is not a default solution for (1).

### Exercise 2 — Capped Collection and Query

Create a test collection:

```javascript
db.createCollection("sensor_events_test", {
  capped: true,
  size: 1024 * 1024,
  max: 1000
});
```

Tasks:

1. Verify `isCapped()` returns `true`.
2. Seed a `MEASUREMENT` event.
3. Open a tailable cursor with an empty query.
4. Append an `ALERT` event **after verifying the cursor received the seed**.
5. Observe the new event and terminal signals.
6. Try initial query `kind="NEVER-SEEN"` and observe the difference.

Execute only on an isolated test MongoDB. Never touch production data or capped collections.

### Exercise 3 — Retry or Repeat?

Evaluate:

```java
Flux<DeviceEvent> events =
    template.tail(new Query(), DeviceEvent.class)
        .retryWhen(Retry.backoff(
            3, Duration.ofMillis(100)));
```

Why does this code **fail to handle normal completion**? Add `repeatWhen` with an appropriate delay, distinguish retryable from non-retryable errors, and explain why repeating should not occur after `cancel`.

### Exercise 4 — A Hot Loop

An API uses:

```java
return template.tail(
        Query.query(Criteria.where("tenantId")
            .is("TENANT-NOT-YET-SEEN")),
        DeviceEvent.class)
    .repeat();
```

Assume MongoDB completes the cursor immediately on no-match. Explain why the query reopens continuously, how `repeatWhen(...delayElements(...))` fixes liveness without **guaranteeing delivery**, and how to design initial matches/filters to avoid the problem.

### Exercise 5 — Choosing a Checkpoint

A team plans to store `lastSeenObjectId` and query:

```java
Criteria.where("_id").gt(lastSeenObjectId)
```

Critique this design:

- Is `ObjectId` guaranteed to increase in append order across multiple JVM writers?
- Could documents use random UUIDs as `_id`?
- What happens when the capped collection rolls over?
- Is `_id` alone enough to detect missed events?
- Can you combine `eventId` for deduplication with a sequence/offset backed by a producer contract?

### Exercise 6 — Producer Reordering

Timeline:

```text
t0 A reserves sequence 100
t1 B reserves sequence 101
t2 B inserts E101
t3 consumer checkpoints 101
t4 A inserts E100
t5 consumer reconnects with sequence > 101
```

Demonstrate how event E100 is skipped under a naive checkpoint strategy. Propose mechanisms to enforce append ordering, or overlap/dedupe/watermarks capable of handling late arrivals.

### Exercise 7 — Checkpoint After Processing

Buggy code:

```java
source.flatMap(event ->
    checkpoint.saveLastAppliedSequence(
        event.sequence())
        .then(service.apply(event)));
```

Point out:

1. Checkpointing happens before the effect.
2. `flatMap` can finish sequences out of order.
3. Crashing after checkpointing loses the unprocessed event.

Rewrite using `concatMap`, an idempotent `applyOnce`, and checkpointing after durable effects. Explain why crashing after the effect but before checkpointing causes replay without double-applying.

### Exercise 8 — Rollover and Data Gaps

The consumer checkpoint is 100, while the collection retains 300 onward. Pick one of the three strategies:

- Live-only: ignore the gap under an approved SLA; rebuild UI snapshots if needed.
- Checkpoint + capped: report `RECONCILIATION_REQUIRED`; do not claim full processing.
- Durable source: fetch E101..299 from archive/outbox/queue before catching up to realtime.

Why does increasing a capped collection's `size` **after events are overwritten** fail to recover old history?

### Exercise 9 — Health Design

The system receives no new events for 20 minutes while MongoDB ping succeeds. Design an observability panel:

```text
source_has_new_data?
subscription_active?
source_completed_or_error?
producer_heartbeat_due?
checkpoint_age?
capped_retention_window?
```

Explain each scenario:

- Producer is genuinely quiet.
- Cursor completed, yet supervisor failed to reopen.
- Handler errored, preventing checkpoint updates.
- Cursor remains active, yet producer stopped.

### Exercise 10 — Testing Reconnect Without MongoDB

Build `Flux.defer`:

- Attempt 1: `Flux.empty()`.
- Attempt 2: `Flux.empty()`.
- Attempt 3: `Flux.just(E1)`.

Use `repeatWhen` with a short delay and `take(1)`, asserting three opens. Then add an error branch with a `retryWhen` budget of 2, a non-retryable error, and a cancel test. Do not use `Thread.sleep` to guess ordering.

### Exercise 11 — When to Switch to Change Streams?

A system initially used capped `device_event_log`, but now must track **updates/deletes** on a regular `devices` collection with MongoDB resume tokens. Answer:

1. Why can't `@Tailable` on `devices` satisfy this requirement?
2. What topology do change streams require?
3. What metadata do change streams provide beyond tailable cursors?
4. Can resume tokens expire when oplog history is gone?
5. When is a transactional outbox still needed to emit reliable business events?

### Exercise 12 — Production Incident

Observed metrics:

```text
tailable_cursor_reconnect_total       rising rapidly
tailable_cursor_completed_total       rising proportionally
tailable_cursor_errors_total          barely increasing
tailable_events_received_total        = 0
tailable_checkpoint_age_seconds       rising
```

Primary hypothesis: **initial no-match is causing the cursor to complete immediately**, and an unthrottled `repeat()` is causing a hot loop. Inspect query/filters, collection, subscriptions, and server-version behavior; add backoff, cursor-open rate limits, and alerts. Note that if producers have not yet written any events to the collection, rising checkpoint age **does not prove data loss**.

## 26. Quick Review Questions

| Question | Short Answer |
| --- | --- |
| Which collection type does a tailable cursor require? | Capped collection |
| Does no `onNext` mean an error occurred? | No |
| Is `onComplete` handled by `retryWhen`? | No; use a repeat/reopen policy |
| Is `onError` handled by `repeatWhen`? | Not directly |
| What can an initial no-match query cause? | Cursor may die/complete |
| What does capped rollover do? | Can lose cursor position and old history |
| Is there a MongoDB resume token? | No, unlike change streams |
| Is `ObjectId` a reliable offset? | Not by default |
| When should you checkpoint? | After durable business processing |
| Why idempotency? | Reconnect/replay can re-process events |
| Is `Flux.timeout` a heartbeat? | No |
| Should `dispose()` trigger reconnect? | No, on intentional shutdown |
| Which repository is `@Tailable` used on? | `ReactiveMongoRepository` in these examples |
| Which template API performs reactive tailing? | `ReactiveMongoTemplate.tail(Query, Class<T>)` |
| Why shouldn't you add a timestamp sort? | Tailable cursors require natural order |
| When is snapshot/reconciliation needed? | When checkpoint falls outside retained data/gaps occur |
| Why might increasing capped size still be insufficient? | Load/retention can grow and already-lost data is gone |
| When are change streams a better fit? | Tracking updates/deletes and needing event envelopes/resume tokens |

## 27. References

- Spring Data MongoDB — [Tailable Cursors](https://docs.spring.io/spring-data/mongodb/reference/mongodb/tailable-cursors.html): capped collections, imperative container, reactive template, and `@Tailable` repositories.
- Spring Data MongoDB API — [ReactiveMongoTemplate](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): `tail(Query, Class<T>)` and overloads.
- Spring Data MongoDB API — [Tailable](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/Tailable.html): tailable repository annotation.
- Spring Data MongoDB API — [TailableCursorRequest](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/messaging/TailableCursorRequest.html): imperative request and listener container.
- Spring Data MongoDB API — [DefaultMessageListenerContainer](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/messaging/DefaultMessageListenerContainer.html): managing subscriptions/tasks and lifecycle.
- MongoDB Manual — [Tailable Cursors](https://www.mongodb.com/docs/manual/core/tailable-cursors/): capped cursor semantics, restrictions, and liveness notes.
- MongoDB Manual — [Capped Collections](https://www.mongodb.com/docs/manual/core/capped-collections/): fixed size, natural order, and rollover.
- MongoDB Manual — [getMore Command](https://www.mongodb.com/docs/manual/reference/command/getMore/): `maxTimeMS` and await semantics of tailable cursors.
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changestreams/): comparing event envelopes and resume tokens.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): subscribe, complete/error/cancel, `retryWhen`, `repeatWhen`, `concatMap`, and backpressure.

## Key Takeaways

**No new documents does not mean the cursor is dead; cursor completion, cursor errors, and cancellation are three distinct situations requiring separate policies.** Tailable cursors work properly only with capped collections and natural order; queries without initial matches can invalidate cursors, and capped rollover can lose read positions. In Reactor, `retryWhen` handles transient errors and `repeatWhen` handles completion—both need backoff/bounds and must respect intentional shutdown. **Reconnecting does not equal lossless recovery**: tailable cursors have no resume token, so checkpointing, idempotency, and gap detection must be designed by the application with a durable replay source if SLAs prohibit event loss. Test against real capped collections, distinguish idle/complete/error states, monitor retention and checkpoints, and choose change streams or an outbox when requirements exceed tailable cursor limits.
