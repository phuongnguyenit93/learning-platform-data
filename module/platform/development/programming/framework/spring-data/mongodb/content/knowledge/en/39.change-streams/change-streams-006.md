# ReactiveMongoTemplate.changeStream and Consuming with Flux

> **Module:** `SPRING_DATA_MONGODB` — Using Spring Data MongoDB to connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories. Practicing query design, aggregation, indexing, transactions, reactive access, testing, and data performance diagnostics.
>
> **Chapter:** Change stream.
>
> **Focus:** using `ReactiveMongoTemplate.changeStream(...)` to receive MongoDB change events as `Flux<ChangeStreamEvent<T>>`, processing them properly with Reactor, and maintaining resumability across service restarts.

## 1. Problem to Solve

Suppose an e-commerce system has an `orders` collection. When an order transitions to `PAID`, another component needs to update an admin dashboard, compute reports, or push data into a search index. A simple approach is to query repeatedly:

```text
SELECT orders WHERE updatedAt > lastCheckedAt
```

However, polling introduces problems: latency depends on the polling interval, repeated queries run when no new data exists, changes can easily be missed if timestamp fields are unreliable, and handling deleted records is complex.

**MongoDB Change Streams** allow tracking changes published by MongoDB on a supported collection, database, or deployment. With Spring Data MongoDB reactive, `ReactiveMongoTemplate` returns a **continuous `Flux`** rather than a finite list of results.

Example processing flow:

```text
Application writes order
        │
        ▼
MongoDB replica set / sharded cluster
        │  (recorded in change stream)
        ▼
ReactiveMongoTemplate.changeStream(...)
        │
        ▼
Flux<ChangeStreamEvent<Order>>
        │
        ├── filter event type
        ├── decode payload
        ├── process sequentially or with bounded concurrency
        └── persist resume token after successful processing
                        │
                        ▼
            projection / notifications / other services
```

Change streams are a useful source of change notifications; they do not by themselves provide a work queue with consumer groups, business checkpoints, or distributed transactions for operations outside MongoDB.

### Learning Objectives

After this lesson, readers will be able to:

1. Identify deployment prerequisites for Change Streams and required access privileges.
2. Open a `Flux<ChangeStreamEvent<T>>` via `ReactiveMongoTemplate.changeStream`.
3. Distinguish **declaring a pipeline** from actually **subscribing**, and understand stream lifecycle and cancellation.
4. Handle `INSERT`, `UPDATE`, `REPLACE`, and `DELETE`, including when `getBody()` is `null`.
5. Combine Reactor operators such as `filter`, `concatMap`, `flatMap`, `doOnError`, and `retryWhen` without losing data during asynchronous processing.
6. Design checkpointing based on **resume tokens**, and explain the limits of duplicate handling and recovery.
7. Build integration tests against a real MongoDB replica set and observe performance issues.

## 2. Prerequisites Before Using Change Streams

### 2.1. MongoDB Topology

Change Streams are supported on MongoDB **replica sets** and **sharded clusters** with compatible versions and configurations. A normal **standalone** MongoDB process cannot open a change stream like a replica set.

In local development, you can run a **single-node replica set** for experimentation. That is still a replica set topology; simply running a MongoDB container in standalone mode and calling `changeStream` will fail.

Verify the following:

- MongoDB is initialized as a replica set or sharded cluster, and the driver connects to a supported topology.
- The user has `changeStream` and `find` privileges on the watched resource; specific privilege scope depends on collection, database, or cluster level.
- The oplog has sufficient capacity and history retention to recover from a resume token when the application goes down.
- The application can connect to MongoDB with the proper TLS, credentials, and driver options for the environment.
- Reactive functionality uses compatible Spring Data MongoDB Reactive and MongoDB Reactive Streams Driver dependencies for the application version.

Example starter configuration for Spring Boot:

```yaml
spring:
  data:
    mongodb:
      uri: mongodb://app_user:secret@mongo1:27017,mongo2:27017,mongo3:27017/shop?replicaSet=rs0&authSource=admin
```

This is an illustrative structure only. Load the URI, password, and replica set name from configuration management or a secret manager; never hardcode credentials in source code, Docker images, or Git. In Atlas environments, use the cluster URI provided by Atlas.

### 2.2. Applications Using the Reactive Stack

Use `ReactiveMongoTemplate` when handling input/output with Reactor, especially with Spring WebFlux, reactive repositories, and other asynchronous APIs. Synchronous `MongoTemplate` uses a different listening mechanism; you do not get a `Flux` merely by changing a method name.

A typical dependency set in Spring Boot is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

MongoDB driver and Spring Data versions are typically managed by Spring Boot's BOM. Check the actual API when upgrading versions, especially `ChangeStream` overloads and builder options.

## 3. Understanding `Flux<ChangeStreamEvent<T>>`

In Project Reactor, `Flux` represents a stream of 0 to many `onNext` signals, which can terminate via `onComplete` or `onError`. Change Stream fluxes are typically **long-lived and do not complete after a fixed number of records**.

| Component | Meaning for a change stream |
| --- | --- |
| `Flux<ChangeStreamEvent<Order>>` | Publisher emitting order change events |
| `subscribe()` | Activates the subscription and requests data from the publisher |
| `onNext(event)` | Receives one change event; does not mean business work is finished |
| `onError(error)` | Pipeline failed and terminated the subscription unless a recovery mechanism handles it |
| `onComplete()` | May occur when bounded with `take(...)`, source closure, or other conditions; do not wait for it like a finite task |
| `cancel / Disposable.dispose()` | Cancels the subscription; releases resources on service shutdown |
| `request(n)` and backpressure | Consumer signals demand; event rate and resources must still be monitored |

In most cases, the publisher is **cold**: each subscription creates an independent watch process and may open an additional cursor on the server. Do not create multiple subscriptions just to "split work" without a coordination design.

### 3.1. Common Change Types

| `operationType` | Meaning | Payload characteristics |
| --- | --- | --- |
| `INSERT` | New document inserted | Usually includes `fullDocument` |
| `REPLACE` | Document replaced | Usually includes `fullDocument` |
| `UPDATE` | Partial document modification | By default includes update description; may lack `fullDocument` |
| `DELETE` | Document deleted | No full document; rely on `documentKey` |
| `INVALIDATE` | Stream no longer valid, e.g. on drop/rename within watched scope | Requires creating a new stream; `resumeAfter` has specific limits |
| Version-dependent expanded events | E.g., DDL operations or topology changes when enabled | Check MongoDB capabilities and version |

Common pitfall: `ChangeStreamEvent<T>.getBody()` **can return `null`**. Therefore, never assume every event carries an existing entity.

### 3.2. Resume Tokens and Metadata

Each event has a **resume token** (for supported events). A token is opaque data generated by MongoDB to identify a resumable position in the stream:

```java
event.getResumeToken();    // Token to resume the stream
event.getOperationType();  // INSERT, UPDATE, REPLACE, DELETE, ...
event.getBody();           // May be null, especially for DELETE / UPDATE
```

Do not interpret, modify, fabricate tokens from application timestamps, or assume tokens follow lexicographical order. Persist them in an appropriate BSON format, tagged with the **consumer identity and stream scope**.

## 4. Creating Sample Data and Opening a Simple Stream

Define the `Order` document:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class Order {

    @Id
    private String id;

    private String customerId;
    private String status;
    private BigDecimal total;
    private Instant updatedAt;

    // Constructors, getters, and setters (or use a record compatible with the mapper)
}
```

In the service layer, create a Change Streams publisher with `ReactiveMongoTemplate`:

```java
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Flux;

public class OrderChangeStreams {

    private final ReactiveMongoTemplate template;

    public OrderChangeStreams(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<ChangeStreamEvent<Order>> changes() {
        ChangeStreamOptions options =
                ChangeStreamOptions.builder().build();

        return template.changeStream(
                "orders",
                options,
                Order.class
        );
    }
}
```

**Analysis:**

- `"orders"` is the **actual MongoDB collection** name being watched.
- `ChangeStreamOptions` describes the options for the Change Streams source.
- `Order.class` instructs Spring Data to convert `fullDocument` into an `Order` entity when present.
- The method returns a publisher; it **does not begin processing** until subscribed to.
- Do not add `.collectList()` or `.blockLast()` on a stream intended to run continuously. Those operators wait for stream completion and may never return.

### 4.1. Using `Flux` to observe events in practice

```java
Flux<ChangeStreamEvent<Order>> changes = service.changes();

Disposable subscription = changes
        .doOnNext(event -> System.out.println(
                "type=" + event.getOperationType()
                + ", token=" + event.getResumeToken()))
        .doOnError(error -> System.err.println(error.getMessage()))
        .subscribe();

// At a managed shutdown point, cancel the subscription:
subscription.dispose();
```

You need to import `reactor.core.Disposable` for `subscription`. In production code, use a logger, identify the subscription owner, and manage its lifecycle alongside the application. The `dispose` call in the example shows an intentional stop action—do not place it immediately after `subscribe` or it will stop the stream before receiving events.

### 4.2. Generating events to observe

After the publisher is subscribed and the watch cursor has opened:

```javascript
use shop

db.orders.insertOne({
  _id: "O-1001",
  customerId: "C-01",
  status: "NEW",
  total: 1200000,
  updatedAt: new Date()
});

db.orders.updateOne(
  { _id: "O-1001" },
  {
    $set: {
      status: "PAID",
      updatedAt: new Date()
    }
  }
);

db.orders.deleteOne({ _id: "O-1001" });
```

The events will have types `INSERT`, `UPDATE`, and `DELETE` respectively. Event-receiving code must inspect the actual type and payload rather than assuming every event contains an `Order`.

**Note on when the cursor opens:** creating a `Flux` does not guarantee the watch cursor is already open. If you want to receive events that happened before the consumer became ready, start from a valid checkpoint/operation time, or ensure the stream is ready before writing in tests. Examples that "subscribe then immediately insert" can race under certain scheduling conditions.

## 5. Filtering Events on MongoDB with `ChangeStreamOptions`

Instead of receiving every operation type and filtering in Java, you can push some conditions down into the Change Streams pipeline. Spring Data provides `ChangeStreamOptions.builder().filter(...)` to pass an aggregation filter to the stream.

Example watching only `insert`, `update`, `replace`, and `delete`:

```java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.match;
import static org.springframework.data.mongodb.core.aggregation.Aggregation.newAggregation;

import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;

Aggregation filter = newAggregation(
        match(Criteria.where("operationType")
                .in("insert", "update", "replace", "delete"))
);

ChangeStreamOptions options = ChangeStreamOptions.builder()
        .filter(filter)
        .build();

Flux<ChangeStreamEvent<Order>> changes =
        template.changeStream("orders", options, Order.class);
```

Note that `operationType` values in aggregation are **lowercase strings** for MongoDB events, while the Java API may return enums such as `OperationType.INSERT`.

For long-running consumer streams, filters reduce the data sent to the application. However, filters have limitations: if you only watch for `PAID` via `fullDocument.status`, keep in mind that `UPDATE` events by default may not contain `fullDocument`. Filtering on `updateDescription.updatedFields.status` (when present) is another approach, though you must also account for `replace` and updates without that field.

### 5.1. Can `fullDocument` be used on updates?

By default, partial updates expose changed data in `updateDescription` and the document key. To ask MongoDB to look up the full document for update events, use the **`updateLookup`** policy; the corresponding builder method may vary across Spring Data versions.

With Spring Data MongoDB APIs supporting `returnFullDocumentOnUpdate()`:

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
        .returnFullDocumentOnUpdate()
        .build();

Flux<ChangeStreamEvent<Order>> changes =
        template.changeStream("orders", options, Order.class);
```

**Important limitation:** `updateLookup` queries the document state, and the result can be a **newer version than the UPDATE event itself** if multiple consecutive changes occur. It can also be `null` if the document was deleted. Therefore, do not use `getBody()` from update lookup as sole proof to reconstruct every intermediate value. When you need to know which fields changed, inspect `updateDescription` in the original event.

### 5.2. Preserving `_id` and resume token validity

In Change Streams output, the event's `_id` field holds the resume token. Do not use `$project`, `$replaceRoot`, or other stages to remove or modify this `_id` field in a change-stream pipeline. MongoDB needs the token to support resuming; altering the token breaks stream operation or causes rejection.

Do not confuse the **change event** `_id` with the **order document** `_id`. When you need the document key, read `documentKey._id` from the event metadata.

## 6. Processing with Reactor: Choosing Operators for the Goal

Because handlers often write data or call other services, event processing is **asynchronous**. Operator choice determines ordering, concurrency, and when work is considered "done".

### 6.1. `doOnNext` is only for synchronous side effects

Do not write:

```java
changes.doOnNext(event -> {
    projectionRepository.save(convert(event)).subscribe();
}).subscribe();
```

The bug here is creating an inner nested subscription: the outer stream does not wait for `save` to succeed, processing errors may go unhandled, and an outer checkpoint may be recorded prematurely.

Replace it with a composition operator that returns a publisher:

```java
Flux<Void> processing = changes.concatMap(event ->
        projectionService.apply(event)
);
```

Assume `projectionService.apply(event)` returns `Mono<Void>` and completes only once the desired side effect has genuinely completed.

### 6.2. When to use `concatMap`?

`concatMap` subscribes to each inner publisher one at a time, waiting for the previous one to complete before processing the next. It suits consumers that must preserve ordering and checkpoint progress:

```java
Flux<Void> processing = changes.concatMap(event ->
        projectionService.apply(event)
);
```

Advantage: simplifies processing order. Trade-off: throughput is bounded by single-event latency. One slow event can block subsequent events.

### 6.3. When to use `flatMap`?

`flatMap` allows tasks to run concurrently and may emit results **out of input order**:

```java
Flux<Void> processing = changes.flatMap(
        event -> notificationService.publish(event),
        8 // Limit to 8 concurrent tasks
);
```

Only suitable when events are **independent and idempotent**, and checkpointing does not assume every event prior to the latest token has finished. If you process concurrently but simply save the token of the most recently completed event, the application can lose earlier in-flight events upon restart.

You can partition by order key and process sequentially within each group, but that design requires a suitable global/partition checkpoint strategy; a MongoDB change stream does not provide per-group offsets by itself.

### 6.4. Other useful operators

| Operator | Usage | What to avoid |
| --- | --- | --- |
| `filter` | Discard irrelevant Java-side events | Dropping events before checkpointing without defining a resume policy |
| `handle` | Filter and transform in one pass, handling nullable bodies | Emitting `null` as an `onNext` signal |
| `map` | Synchronous data transformation | Calling blocking APIs inside the lambda |
| `concatMap` | Ordered async processing | Holding an inner publisher that never completes |
| `flatMap(mapper, concurrency)` | Bounded concurrency for independent work | Using unbounded concurrency and checkpointing out of order |
| `doOnNext` / `doOnError` | Logging, metrics, observation | Placing primary persistence inside callbacks without composing the publisher |
| `onErrorResume` | Controlled fallback handling | Swallowing errors and marking events successful when they failed |
| `retryWhen` | Backoff retry for transient errors | Retrying unrecoverable errors or expired tokens forever |
| `take(n)` | Finite tests | Mistaking a production stream as finished after n events |

## 7. Handling Event Types and `null` Payloads

Define a handler returning `Mono<Void>` to ensure processing finishes before advancing the checkpoint.

```java
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Mono;

public interface OrderEventHandler {

    // Contract: completes successfully once the side effect is durably persisted.
    Mono<Void> apply(ChangeStreamEvent<Order> event);
}
```

Suggested implementation:

```java
public Mono<Void> apply(ChangeStreamEvent<Order> event) {
    return switch (event.getOperationType()) {
        case INSERT, REPLACE -> {
            Order body = event.getBody();
            if (body == null) {
                yield Mono.error(new IllegalStateException(
                        "Missing fullDocument for insert/replace"));
            }
            yield projection.upsert(body);
        }
        case UPDATE -> projection.applyUpdate(event);
        case DELETE -> projection.deleteByDocumentKey(event);
        default -> Mono.empty();
    };
}
```

The snippet illustrates logic for an implementation that has its own `projection.upsert`, `projection.applyUpdate`, and `projection.deleteByDocumentKey` methods. Those methods must return `Mono<Void>` and handle idempotency. Switch expressions fit modern Java; on older Java versions, use a traditional `switch` or `if` statements.

For `DELETE`, `fullDocument` is typically absent: extract the ID from `documentKey` (e.g., via the raw event) to delete the projection or emit a tombstone. Do not call `event.getBody().getId()` for this operation.

For `UPDATE`, depending on system policy:

- Apply `updatedFields` and `removedFields` directly from `updateDescription`; handle nested fields, arrays, and schema evolution.
- Use `updateLookup` to obtain the current state when the projection only needs the "latest state", accepting that intermediate states may be skipped.
- Re-read the source document by `documentKey` if you only need eventual final-state synchronization; if already deleted, handle as a tombstone.

**Do not automatically drop events where `getBody() == null`** when business logic still needs to react to UPDATE or DELETE.

## 8. Managing Subscriptions Across the Application Lifecycle

A consumer typically runs long-term and needs a clear owner. When the application starts, start the subscription. When the application stops, cancel it. Never open a new stream per HTTP request.

Simple lifecycle management example:

```java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;

@Component
public class OrderChangeStreamRunner {

    private final OrderEventConsumer consumer;
    private final AtomicReference<Disposable> current =
            new AtomicReference<>();

    public OrderChangeStreamRunner(OrderEventConsumer consumer) {
        this.consumer = consumer;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        Disposable subscription = consumer.consume()
                .subscribe(
                        ignored -> { },
                        error -> System.err.println(
                                "Order change stream stopped: " + error),
                        () -> System.out.println(
                                "Order change stream completed")
                );

        Disposable previous = current.getAndSet(subscription);
        if (previous != null) {
            previous.dispose();
        }
    }

    @PreDestroy
    public void stop() {
        Disposable subscription = current.getAndSet(null);
        if (subscription != null) {
            subscription.dispose();
        }
    }
}
```

In production, replace `System.out` with a logger carrying correlation metadata, add guards against repeated `start()` calls, and monitor stream termination errors. The snippet shows subscription ownership; it does not yet include retry policy, checkpointing, or leader election.

**Note:** `@EventListener(ApplicationReadyEvent.class)` only indicates when the application begins creating the subscription; it does not guarantee the application is ready to consume events yet. For systems requiring true readiness, track health/readiness state separately based on cursor opening or confirmed event receipt.

### 8.1. What if multiple instances run?

Each instance subscribing to a Change Stream independently can receive the same events; MongoDB does not split events across instances like a consumer group. Depending on requirements:

- If every instance needs notifications, broadcasting may fit.
- If only one instance may update a shared projection, use **distributed lease/leader election**, including lease expiration and fencing to prevent two active owners at once.
- If you need work partitioning, design a separate coordination/queue mechanism rather than assuming Change Streams load-balance themselves.

## 9. Resume Tokens: Recovering After Restarts

### 9.1. Why `retryWhen` is not enough

The driver can automatically resume certain eligible network errors. However, applications also face scenarios such as:

- Service restarts or deployments.
- Business side effects failing after receiving an event.
- Oplog retention expiring so the token is no longer usable.
- Filter or stream scope changes incompatible with the prior token.
- Collection drop/rename causing stream invalidation.

If you merely restart the stream from "now", events occurring while the service was down can be missed. Production consumers therefore need **durable checkpoints**.

### 9.2. Choosing when to save checkpoints

Core rule for a sequential consumer:

```text
event from MongoDB
     │
     ▼
business processing (Mono<Void>)
     │
     ├─ error ──> DO NOT write new token
     │
     ▼ success
persist resume token durably
     │
     ▼
allowed to receive next event
```

If you write the token **before** the side effect, crashing mid-way causes the event to be skipped on restart. If you write the token **after** the side effect, crashing before checkpointing can reprocess the event. That is why consumers must be **idempotent** and generally provide **at-least-once** semantics for business processing.

Resume tokens do not guarantee "exactly once" for external side effects (sending email, HTTP, Kafka, payment systems). For those operations, use an idempotency key or a proper outbox/inbox pattern.

### 9.3. Checkpointed consumer pattern

Define two clear dependency contracts:

```java
import org.bson.BsonDocument;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Mono;

public interface ResumeTokenStore {
    Mono<BsonDocument> load(String consumerId);
    Mono<Void> save(String consumerId, BsonDocument token);
}

public interface OrderChangeProcessor {
    Mono<Void> process(ChangeStreamEvent<Order> event);
}
```

- `load` emits a token if one exists; returns `Mono.empty()` if no checkpoint exists yet.
- `save` must complete only once the checkpoint is durably persisted to the system's required level.
- `process` executes idempotently and completes only after required side effects finish.
- Store tokens in a separate collection, such as `consumer_offsets`, **not** inside the watched `orders` collection, to avoid self-triggering a feedback loop on checkpointing.

Coordinated example:

```java
import java.util.Optional;

import org.bson.BsonDocument;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class OrderEventConsumer {

    private static final String CONSUMER_ID = "order-projector-v1";

    private final ReactiveMongoTemplate template;
    private final ResumeTokenStore tokens;
    private final OrderChangeProcessor processor;

    public OrderEventConsumer(
            ReactiveMongoTemplate template,
            ResumeTokenStore tokens,
            OrderChangeProcessor processor
    ) {
        this.template = template;
        this.tokens = tokens;
        this.processor = processor;
    }

    // Each new subscription must reload the checkpoint from storage.
    public Flux<Void> consume() {
        return Flux.defer(() ->
                tokens.load(CONSUMER_ID)
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty())
                        .flatMapMany(saved -> changeEvents(
                                saved.orElse(null)))
                        .concatMap(this::processAndCheckpoint)
        );
    }

    private Flux<ChangeStreamEvent<Order>> changeEvents(
            BsonDocument resumeToken
    ) {
        ChangeStreamOptions options = resumeToken == null
                ? ChangeStreamOptions.builder().build()
                : ChangeStreamOptions.builder()
                        .resumeToken(resumeToken)
                        .build();

        return template.changeStream("orders", options, Order.class);
    }

    private Mono<Void> processAndCheckpoint(
            ChangeStreamEvent<Order> event
    ) {
        return processor.process(event).then(
                Mono.defer(() -> {
                    BsonDocument token = event.getResumeToken();

                    if (token == null) {
                        return Mono.error(new IllegalStateException(
                                "Change stream event missing resume token"));
                    }

                    return tokens.save(CONSUMER_ID, token);
                })
        );
    }
}
```

Key aspects of this structure:

1. `Flux.defer` ensures that upon resubscription, the **load checkpoint → open stream** sequence executes fresh.
2. `Optional.empty()` represents the case with no token yet; never create `Mono.just(null)` because Reactor forbids `null` elements.
3. `resumeToken(...)` instructs MongoDB to resume after the saved token; use the builder API compatible with your Spring Data version.
4. `concatMap` starts processing the next event only after both `processor.process` and `tokens.save` for the previous event finish.
5. If processing or saving the checkpoint errors, the publisher emits `onError`; the subscription owner decides whether to retry or stop with an alert.
6. Change `CONSUMER_ID` when an independent consumer needs its own position/stream definition.

**Example scope:** this is an architectural pattern requiring implementations of `ResumeTokenStore`, `OrderChangeProcessor`, and startup/retry policies. It is not a runnable end-to-end service without those components.

### 9.4. Store tokens as BSON without arbitrary conversions

Resume tokens are typically `BsonDocument`. When storing as BSON/Extended JSON, preserve exact data types:

```java
String encoded = token.toJson();
BsonDocument decoded = BsonDocument.parse(encoded);
```

This illustrates serialization/deserialization via BSON Extended JSON. In real applications, pick the proper schema and codec for your storage, storing `consumerId`, namespace scope, and stream configuration metadata alongside it. Do not rely on `token.toString()` as a default persistence contract without verifying round-trip fidelity.

When multiple workers could write the same checkpoint, use leases/fencing and atomic conditional writes so a stale consumer cannot overwrite a newer consumer's token progress.

## 10. Resuming After Errors and Retry Rules

### 10.1. Distinguishing transient errors from unrecoverable ones

| Error category | Examples | Appropriate handling |
| --- | --- | --- |
| Transient | Network timeout, flaky connection, recoverable failover | Backoff with jitter, reopen from checkpoint |
| Business logic | DTO mapping failure, invalid ID, projection missing data | Log error / route to deliberate error handling, do not retry forever |
| Privileges or config | Missing `changeStream` privilege, wrong URI/topology | Alert and fix configuration |
| Expired token | Oplog no longer holds events at the token position | Run resync/snapshot workflow, do not silently discard checkpoint |
| Stream invalidated | Collection drop/rename depending on scope | Decide how to create a new stream; consider `startAfter` when appropriate |

Reactor lets you configure `Retry` with backoff:

```java
import java.time.Duration;
import reactor.util.retry.Retry;

Flux<Void> monitored = consumer.consume()
        .retryWhen(Retry.backoff(8, Duration.ofSeconds(2))
                .maxBackoff(Duration.ofSeconds(30))
                .filter(this::isTransientChangeStreamFailure));
```

`isTransientChangeStreamFailure(Throwable)` is **implemented by the application** to classify errors using MongoDB/driver error codes, error labels, and business rules. Do not use `retryWhen(Retry.max(Long.MAX_VALUE))` for every exception: expired tokens or misconfigurations will spin with zero progress.

When retrying a `consume()` publisher like the one above, each new subscription **reloads the checkpoint** before opening the stream. If an error occurs after successful processing but before durable token persistence, the event may be redelivered: the handler must be idempotent.

### 10.2. `resumeAfter`, `startAfter`, and operation time

MongoDB provides different ways to specify a starting position:

- **`resumeAfter`:** uses a resume token to continue from a processed event's position in a resumable stream.
- **`startAfter`:** supports opening a new stream after an `invalidate` event in certain cases; do not treat it as identical to `resumeAfter` in all circumstances.
- **`startAtOperationTime`:** starts from a valid MongoDB operation timestamp if supported by the API and topology, though still subject to oplog history.

You cannot resume if the necessary history has been truncated from the oplog. Keeping a Java-generated timestamp cannot substitute for a MongoDB token. When a token is no longer usable, the system must decide how to rebuild state from the source, accept a data gap, or use another ingestion mechanism.

### 10.3. What to log and measure

A production consumer should track:

- Consumer ID, watched collection/database, filter version, session/lifecycle, and readiness level.
- Events received, processed successfully, failed, retried, and duration from event to completion.
- Checkpoint age and distance between event time and current processing time.
- Processing latency p50/p95/p99, token save latency, and queue size if buffered.
- Active subscription count, reconnects, network errors, authorization errors, and invalid tokens.

Log tokens sparingly as needed, avoiding dumping full document contents containing sensitive data.

## 11. Preserving Business Semantics

### 11.1. At least once, not exactly once

Suppose processing succeeds, then the process dies before saving the token:

```text
T0: receive event E123
T1: update projection successfully
T2: process crashes
T3: restart from token E122
T4: event E123 is processed again
```

A safe design must tolerate repeating E123, for example:

- Upsert the projection by document ID and version.
- Insert a `processed_event` record with a suitable unique key before or inside the same MongoDB transaction as the side effect.
- Attach an idempotency key to external calls or write commands to an outbox.
- When per-document ordering must be preserved, check a valid version or sequence before writing.

Conversely, saving token E123 before updating the projection means the service could crash and skip E123 entirely on the next startup. **Checkpointing after side effects is necessary**, yet idempotency is still required to handle duplicates.

### 11.2. Transactions and Change Streams

If a MongoDB transaction modifies multiple documents, its changes appear in Change Streams only after the transaction commits. An aborted transaction produces no committed changes for consumers to process.

`watch` itself is a long-lived read source; never wrap an entire Change Streams subscription inside an infinitely open transaction. If a processor needs to update multiple related collections, it can use a short separate transaction for **a single event** if the topology supports it, while checking session, reactive context, and checkpoint alignment.

### 11.3. Guarding against out-of-order execution under concurrency

Even when MongoDB provides ordered source events, using `flatMap` can cause **processing results to complete out of order**. For a shared projection that depends on sequential order, prefer `concatMap`. If you must increase throughput, partition by key and advance checkpoints only across contiguous completed events; never blindly pick "the latest token seen".

### 11.4. Do not use Change Streams to replace transaction verification

Change Streams are useful for updating views/projections and secondary systems. If a client needs to know whether an order command committed, the application should rely on the transaction outcome and read source data with appropriate consistency guarantees, rather than waiting on a Change Stream event as the sole confirmation signal.

## 12. Backpressure and Resource Limits

Reactive Streams support `request(n)` signaling; the driver can pace event delivery according to downstream demand. However:

- MongoDB continues accepting writes and the oplog continues advancing while a consumer is slow.
- Backpressure does not extend the resumable history window in the oplog indefinitely.
- Unbounded `flatMap` or an unbounded custom queue can exhaust RAM.
- `bufferTimeout` and `onBackpressureBuffer` need bounded sizes, overflow error strategies, and matching checkpointing; arbitrarily dropping events breaks complete stream semantics.
- Blocking calls (`Thread.sleep`, `.block()`, synchronous JDBC) inside operators can stall event-loop or driver threads. When blocking code is unavoidable, isolate it on a bounded `Schedulers.boundedElastic()`, though an end-to-end reactive stack is preferred.

Example bounding independent tasks:

```java
Flux<Void> notifications = stream
        .flatMap(
                event -> notifier.publish(event)
                        .timeout(Duration.ofSeconds(5)),
                4
        );
```

**Do not treat this `flatMap` pipeline as a sequential checkpointing mechanism** if tasks can finish out of order.

Performance tuning must be measured against real workloads: document size, write rate, downstream processing duration, failover impact, and oplog retention window.

## 13. Designing Safe Filters and Mappings

Not every event should be emitted externally in raw form:

- Filter as early as possible by `operationType`, namespace, or fields supported by Change Streams.
- Avoid full document lookups when unnecessary; extra reads increase cost and latency.
- Do not include personal information, secrets, or internal fields in logs or third-party notifications unless required.
- Use actual MongoDB field names in pipeline filters, especially when entities rename fields with `@Field`.
- For entity schema evolution, define how old documents and unfamiliar events are handled; avoid crashing repeatedly on one token due to rigid mapping.
- When configuring a new pipeline, evaluate whether stored resume tokens remain compatible with the namespace, scope, and filter chain.

When updating a secondary search index: `documentKey` alone may suffice, followed by reading the latest document to rebuild the index entry. However, accept eventual consistency and the possibility that the document disappears between steps; `DELETE` must remove or tombstone the corresponding record.

## 14. Testing Change Streams with Reactor

A unit test mocking a `Flux` can verify operator logic, but it does not prove MongoDB actually emits Change Streams, supports resuming, or survives failover. You need **integration tests** on a real replica set or Testcontainers running MongoDB with replica set mode enabled.

### 14.1. Recommended test matrix

| Case | Expectation |
| --- | --- |
| Insert an order | Emits `INSERT`, maps entity |
| Update `status` | Emits `UPDATE`, observe `updateDescription` and `fullDocument` policy |
| Delete order | Emits `DELETE`, body absent but `documentKey` usable |
| Handler succeeds | Checkpoint advances after processing |
| Handler fails | Checkpoint does not advance, error surfaces or enters explicit retry mechanism |
| Restart from old token | Uncheckpointed event is reprocessed |
| Invalid / oplog-expired token | Consumer stops with alert / runs resync workflow |
| Multiple instances | Does not accidentally run two consumers writing a shared projection |
| Large event burst | Does not lose required ordering or grow RAM unboundedly |
| Schema change | Mapping and handler process cleanly or fail controllably |

### 14.2. Testing logic with `StepVerifier`

A consumer taking a `Flux` can be tested with a mock publisher. For instance, verifying that `concatMap` preserves order and processes an event only after the previous task finishes:

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class SequentialProcessingTest {

    @Test
    void concatMapWaitsForPreviousTask() {
        List<Integer> completed = new CopyOnWriteArrayList<>();

        Flux<Integer> source = Flux.just(1, 2, 3);

        Flux<Integer> result = source.concatMap(number ->
                Mono.delay(Duration.ofMillis(20))
                        .map(ignored -> number)
                        .doOnNext(completed::add)
        );

        StepVerifier.create(result)
                .expectNext(1, 2, 3)
                .verifyComplete();

        assertThat(completed).containsExactly(1, 2, 3);
    }
}
```

This test only proves Reactor behavior. It does not simulate the full driver, MongoDB resume tokens, or cluster privileges.

### 14.3. Realistic integration testing

Recommended steps:

1. Start a test MongoDB replica set and use the replica set URI.
2. Create the `orders` collection and isolate test data.
3. Open the change stream and verify the watch cursor is ready; avoid assuming `subscribe()` means the cursor is already open.
4. Insert, update, and delete data from another connection or the same client in a controlled sequence.
5. Use `take(n)` and `StepVerifier` with timeouts to bound test duration.
6. Separately test `resumeToken`: save the token after event A, stop the subscription, generate event B, then resubscribe from token A; verify B is received.
7. Use fault injection to verify post-processing checkpointing and idempotency.
8. Clean up resources, dispose subscriptions, and shut down the test replica set afterward.

Partial test checking event stream properties when an independent fixture generates data:

```java
Flux<ChangeStreamEvent<Order>> updates = template
        .changeStream(
                "orders",
                ChangeStreamOptions.builder().build(),
                Order.class
        )
        .filter(event -> event.getOperationType() != null)
        .take(3);

StepVerifier.create(updates)
        .expectNextCount(3)
        .expectComplete()
        .verify(Duration.ofSeconds(20));
```

This snippet requires an **independent fixture** emitting three events once the stream is ready; without it, the test waits until timeout. This is an integration test skeleton, not a standalone runnable test.

### 14.4. Why virtual time does not replace MongoDB

`StepVerifier.withVirtualTime` is great for testing `delay`, `timeout`, and `retryBackoff` in Reactor. However, MongoDB servers, oplogs, networks, and topology changes operate in real time. Virtual time cannot prove a resume token is still valid or that MongoDB emitted an event after a transaction commit.

## 15. Troubleshooting Common Errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `$changeStream is only supported on replica sets` | MongoDB is standalone | Set up a valid replica set or use a sharded cluster |
| No events despite writes | Not subscribed, cursor not open yet, watching wrong namespace | Verify subscription, collection, filter, and watch start time |
| Event received but `getBody() == null` | `UPDATE` without lookup enabled, or `DELETE` | Branch on `operationType`, `updateDescription`, and `documentKey` |
| Events received only when calling HTTP API | Subscription created inside handler or canceled early | Move consumer into application lifecycle |
| Errors disappear silently | Nested `subscribe()` inside `doOnNext` | Use `concatMap` / `flatMap` and propagate `Mono` |
| Events duplicated on restart | Processed but not yet checkpointed | Design idempotency and save token after processing |
| Events lost on restart | Token saved before side effect, or consumer reset to now | Fix checkpoint order; resync data if needed |
| Continuous retries making no progress | Token expired, missing privileges, or schema error | Classify errors, stop with alert, recover deliberately |
| Update result is "too new" | Using `fullDocument` update lookup | Patch from `updateDescription` if per-event state is needed |
| High CPU/RAM | Slow handler, unbounded buffer or concurrency | Bound concurrency, measure lag, optimize filters and side effects |
| Two instances overwrite each other | Both subscribed to the same stream | Add lease/fencing or design idempotent multi-consumer handling |
| Consumer stops after dropping collection | Stream invalidated | Handle `invalidate` and initialize the new namespace/stream appropriately |

## 16. Comparing Event Consumption Approaches

| Approach | Pros | Trade-offs |
| --- | --- | --- |
| `changes.subscribe(event -> log(event))` | Easy to observe in demos | No checkpointing or error handling workflow |
| `changes.concatMap(handler::apply)` | Preserves processing order, awaits side effects | A slow event blocks later events |
| `changes.flatMap(handler::apply, n)` | Good throughput for independent tasks | Out-of-order completion, complex checkpointing |
| `concatMap(process → checkpoint)` | Recoverable, clear processing semantics | Requires durable storage and idempotent handlers |
| `changeStream + outbox/queue` | Decouples side effects and supports multiple consumers with dedicated queues | Adds system components, requires consistent synchronization design |

No single Reactor operator provides end-to-end exactly-once guarantees. System guarantees depend on **processing order**, **checkpoint persistence**, **idempotency**, and **error handling**.

## 17. Practice Exercises

**Exercise 1 — Basic observation.** Create an `orders` collection with `_id`, `status`, and `customerId` fields. Open `ReactiveMongoTemplate.changeStream` and log `operationType`. Insert, update, and delete an order. Explain why `getBody()` differs across events.

**Exercise 2 — Filtering.** Receive only `insert`, `update`, `replace`, and `delete` in `ChangeStreamOptions`. Compare MongoDB-side filtering with Java-side `Flux.filter`. Give an example filtering `UPDATE` on `updateDescription.updatedFields.status` and describe what is missing when a `REPLACE` occurs.

**Exercise 3 — Sequential processing.** Create a mock handler returning `Mono.delay`, and send multiple consecutive events. Compare `concatMap` and `flatMap`. Use `StepVerifier` to prove execution order; explain why checkpoints must not use the newest token while older `flatMap` tasks are still running.

**Exercise 4 — Resume tokens.** Store tokens by consumer ID in a separate collection. Process three events, intentionally stop after the second, add a new event, then restart. Prove that only uncheckpointed events need to continue processing; if the last event repeats, the handler produces no duplicate side effects.

**Exercise 5 — Failure injection.** Make the projection fail after a partial write. Verify the checkpoint does not advance incorrectly, backoff retries execute, and idempotency works. Test an invalid token to ensure the application raises an alert instead of swallowing the error.

**Exercise 6 — Multiple instances.** Launch two consumer instances. Measure how many events each processes, then add a distributed lease so only one instance holds projector ownership. Stop the lease-holding instance and evaluate the handoff mechanism.

**Exercise 7 — Performance measurement.** With thousands of events and varying handler latencies, compare events/sec, lag, and RAM across `concatMap`, `flatMap(concurrency=4)`, and `flatMap(concurrency=16)`. Make an evidence-based decision on acceptable parallelism.

## 18. Production Readiness Checklist

Before enabling a long-running consumer, confirm:

- [ ] MongoDB runs as a replica set or sharded cluster, and the account has `find` and `changeStream` privileges.
- [ ] Collection, database, entity mapping, and Spring Data version match reality.
- [ ] Each logical consumer has its own ID and checkpoint store.
- [ ] Resume tokens are persisted **after** successful side effects, preserving BSON format.
- [ ] Side effects are idempotent; `DELETE` and `UPDATE` events without full documents are handled.
- [ ] Retry policy applies only to transient errors, and alerts fire when tokens become invalid.
- [ ] Concurrency is bounded, avoiding unbounded buffers and blocking inside the reactive pipeline.
- [ ] Subscription lifecycle is managed, with shutdown disposal and proper readiness/health reporting.
- [ ] There is a singleton consumer strategy or multi-consumer fencing/idempotency design.
- [ ] Integration tests on a replica set cover restarts, duplicates, updates/deletes, and errors.
- [ ] Lag, processing rate, checkpoint age, driver errors, and oplog retention are monitored.

## 19. References

1. [Spring Data MongoDB Reference — Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html): `ReactiveMongoTemplate.changeStream` and change-watching mechanisms.
2. [Spring Data MongoDB — ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): overloads and return types by version.
3. [Spring Data MongoDB — ChangeStreamOptions API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.html): filter and resume options.
4. [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): topology, event types, oplog, and resuming.
5. [MongoDB Manual — Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream): resume tokens, `resumeAfter`, and limitations.
6. [Project Reactor — Flux](https://projectreactor.io/docs/core/release/reference/): subscription, demand, composition, concurrency, and retry.
7. [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, and testing publishers.

### Self-Assessment

You have mastered this lesson when you can answer: **why not use `doOnNext(event -> save(...).subscribe())`; why saving the resume token before processing is dangerous; why `getBody()` can be `null`; and what happens when two instances subscribe to the same stream?** Operating Change Streams reliably comes from designing the entire lifecycle of the `Flux` and processing progress, not just calling `changeStream()`.
