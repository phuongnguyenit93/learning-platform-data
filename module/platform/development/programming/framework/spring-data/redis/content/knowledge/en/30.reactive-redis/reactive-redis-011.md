# Pub/Sub and Streams in WebFlux Applications with Spring Data Redis

## 1. Why Does WebFlux Need to Distinguish Redis Pub/Sub from Redis Streams?

An application built with **Spring WebFlux** often handles many concurrent connections: asynchronous data APIs, Server-Sent Events (SSE), WebSockets, real-time updates, or background event processing. Spring Data Redis supports a **reactive** API based on Reactor (`Mono`, `Flux`) to communicate with Redis without tying up a thread per I/O request like synchronous APIs.

However, **reactive** describes how the application consumes and processes data streams; it **does not** change Redis's message delivery guarantees:

- **Redis Pub/Sub:** broadcasts messages to currently connected subscribers. No backlog, ACK, or per-consumer replay. Suited for droppable real-time notifications, cache-invalidation signals, and online UI updates.
- **Redis Streams:** appends records to a Redis log with IDs, supporting replay; consumer groups provide a Pending Entries List (PEL), acknowledgments (`XACK`), and pending recovery via claiming. Suited for jobs/events needing progress tracking, retries, and replay within retention limits.
- **Reactor `Flux`:** a Publisher model offering subscription, cancellation, and backpressure on the Java side. It does not turn Redis Pub/Sub into a retained messaging system, nor does it automatically ACK Redis Streams messages.

A typical real-time system:

```text
                  WEBFLUX APPLICATION
                          |
             +------------+------------+
             |                         |
             v                         v
       Redis Pub/Sub               Redis Streams
       (real-time signals)         (log + durable processing)
             |                         |
        Flux messages              Flux records
             |                         |
             v                         v
     SSE/WebSocket clients       Event-processing workers
             |                         |
       only online clients        business side effect
         receive                       |
                                       v
                                    XACK
```

Above all, **choose the mechanism based on message delivery requirements**, and only then apply WebFlux/Reactor to implement the I/O.

### Learning objectives

After this lesson, you can:

1. Explain why `ReactiveRedisTemplate` and `ReactiveRedisMessageListenerContainer` fit WebFlux applications.
2. Distinguish subscriber-level `Flux` behavior from Redis Pub/Sub and Streams storage mechanics.
3. Publish/subscribe via `ReactiveStringRedisTemplate` and `ReactiveRedisMessageListenerContainer`.
4. Stream Pub/Sub notifications as SSE while understanding SSE and slow-client limits.
5. Write and read Streams with Spring Data Redis's reactive API.
6. Understand the roles of `XREADGROUP`, `XACK`, PEL, and un-ACKed message recovery workflows.
7. Handle errors and retries without dropping messages or duplicating unintended side effects.
8. Design consumer lifecycles, backpressure, serialization, monitoring, and multi-instance deployments.
9. Avoid common mistakes such as `.block()` on the event-loop, forgetting `.subscribe()`, or ACKing before committing business state.

## 2. Three Layers to Distinguish: WebFlux, Reactive Redis, and Redis Server

Related layers that are not identical:

| Layer | Responsibility | Examples |
|---|---|---|
| Spring WebFlux | HTTP, SSE, WebSocket, request/response, event-loop | `@RestController`, `Flux<ServerSentEvent<?>>` |
| Spring Data Redis Reactive | Creates Reactive Streams Publishers for Redis commands | `ReactiveStringRedisTemplate`, `ReactiveRedisMessageListenerContainer` |
| Redis server | Stores Streams, fans out Pub/Sub, manages consumer groups/PEL | `PUBLISH`, `XADD`, `XREADGROUP`, `XACK` |
| Reactor | Composition, cancellation, error propagation, demand | `map`, `flatMap`, `concatMap`, `retryWhen`, `onBackpressure...` |
| Business logic | Defines when work is actually complete | Database commit, external API calls, idempotency |

A reactive call:

```java
Mono<Long> result = redis.convertAndSend(
    "notifications",
    "hello"
);
```

`result` is a **Publisher describing the operation**. In Reactor's common lazy model, assigning `Mono` to a variable **does not mean the command was sent immediately**. Commands usually execute when WebFlux or an explicit subscriber subscribes.

Conversely, calling:

```java
redis.convertAndSend("notifications", "hello");
```

and discarding the `Mono` can result in **nothing being published** because nobody subscribed. This is a very common pitfall when migrating from `StringRedisTemplate` (synchronous) to `ReactiveStringRedisTemplate` (reactive).

### 2.1. Reactive does not mean automatically parallel

`Flux`/`Mono` model asynchronous operation chains; they do not automatically parallelize work or guarantee multithreading.

- `map` transforms data, normally running on the thread emitting upstream signals.
- `flatMap` merges inner Publishers and can run multiple tasks in flight, depending on overload and concurrency.
- `concatMap` processes inner Publishers sequentially, useful when avoiding overlapping side effects.
- `publishOn` switches the scheduler for downstream operators.
- `subscribeOn` controls upstream subscription context; it never changes a blocking API's nature.

Calling a synchronous Redis API or blocking JDBC inside `map` can still block WebFlux event-loop threads even if the method returns `Flux`.

## 3. Dependencies and Basic Configuration

With Spring Boot and Maven, an example configuration:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
    </dependency>
</dependencies>
```

With Gradle:

```gradle
implementation 'org.springframework.boot:spring-boot-starter-webflux'
implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
```

Example `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 3s
```

These addresses and timeouts only illustrate a development environment. Production requires authentication, TLS, cluster/sentinel configuration (if used), and tailored timeouts and retries.

Spring Data Redis Reactive typically uses **Lettuce** as its reactive connector. Never assume every `RedisConnectionFactory` or Redis client fully supports all reactive APIs.

Typical components:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.listener.ReactiveRedisMessageListenerContainer;
```

`ReactiveStringRedisTemplate` fits UTF-8 text keys/values. `ReactiveRedisTemplate<K, V>` lets you configure custom serialization contexts. Even when reactive, you must still specify **byte formats for keys, channels, payloads, and Stream fields**.

### 3.1. Changing return types does not convert blocking APIs into reactive ones

Problematic example:

```java
@GetMapping("/value")
public Mono<String> value() {
    String value = stringRedisTemplate.opsForValue().get("key");
    return Mono.justOrEmpty(value);
}
```

Here `stringRedisTemplate` is blocking; the Redis command already executed and may have blocked the thread before `Mono` was created.

Equivalent reactive API:

```java
@GetMapping("/value")
public Mono<String> value() {
    return reactiveStringRedisTemplate
        .opsForValue()
        .get("key");
}
```

A WebFlux application must keep its I/O paths non-blocking to realize the concurrency advantages of the reactive model.

If legacy blocking I/O integration is unavoidable, offload it onto a suitable scheduler via `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, keeping in mind this only **isolates blocking**, rather than turning a blocking library non-blocking. Thread resources remain finite and latency must be measured.

## 4. Pub/Sub in WebFlux: Receiving Signals While Online

Redis Pub/Sub delivers messages from publishers to currently registered subscribers.

```text
Service A                     Redis                      Service B
    |                           |                            |
    | PUBLISH events.order      |                            |
    +-------------------------->|                            |
    |                           |---- Pub/Sub message ------>|
    |                           |                            |
    |                           |                     Flux onNext(...)
    |                           |                            |
    |                           |                       SSE/WebSocket
```

One publication can reach all matching subscribers (fan-out). Redis Pub/Sub requires no subscriber ACK and retains no durable entry for subscribers connecting later.

If Service B disconnects while an event is published, that event is permanently missed at the Pub/Sub layer. WebFlux and Reactor do not change this.

### 4.1. Exact channels vs. patterns

Exact channel subscription:

```redis
SUBSCRIBE orders.created
```

Pattern subscription:

```redis
PSUBSCRIBE orders.*
```

A publisher still publishes to a concrete channel:

```redis
PUBLISH orders.created '{"orderId":"o-101"}'
```

Patterns only alter the subscriber's **matching scope**. They are not wildcard queues, do not replay messages, and do not guarantee reliability.

In Spring Data Redis:

```java
new ChannelTopic("orders.created")
new PatternTopic("orders.*")
```

`ChannelTopic` represents an exact subscription; `PatternTopic` represents glob matching. If a subscriber registers both and both match, one publication can cause multiple subscription deliveries. Business handlers with side effects must avoid overlapping registrations or ensure idempotency.

## 5. Publishing Messages with ReactiveStringRedisTemplate

Suppose the system publishes JSON events as Strings:

```java
package com.example.realtime;

public record RealtimeEvent(
    String eventId,
    String type,
    String payload
) {}
```

A publisher service:

```java
package com.example.realtime;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class RealtimePublisher {

    private final ReactiveStringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public RealtimePublisher(
            ReactiveStringRedisTemplate redis,
            ObjectMapper objectMapper) {
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    public Mono<Long> publish(RealtimeEvent event) {
        return Mono.fromCallable(
                () -> objectMapper.writeValueAsString(event))
            .flatMap(json ->
                redis.convertAndSend("events.realtime", json)
            );
    }
}
```

`ObjectMapper.writeValueAsString` is local CPU work, not Redis I/O waiting. For small objects it is fast; for large payloads or heavy mapping, watch event-loop CPU usage and cap payload sizes.

Creating a publish endpoint:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PublishController {

    private final RealtimePublisher publisher;

    public PublishController(RealtimePublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/api/events")
    public Mono<ResponseEntity<Void>> publish(
            @RequestBody Mono<RealtimeEvent> request) {

        return request
            .flatMap(publisher::publish)
            .thenReturn(ResponseEntity.accepted().build());
    }
}
```

WebFlux subscribes to the `Mono` returned by the controller to complete the response, executing the Redis publish inside the reactive chain.

**Note:** `convertAndSend` returns a count related to subscribers receiving the publication per Redis semantics. That number is **not a business ACK**; it does not prove subscribers parsed the JSON or that WebSocket/SSE clients received the payload.

### 5.1. Do not call `subscribe()` arbitrarily in a controller

Avoid writing:

```java
@PostMapping("/api/events")
public Mono<Void> publish(@RequestBody RealtimeEvent event) {
    publisher.publish(event).subscribe(); // Hard-to-manage fire-and-forget.
    return Mono.empty();
}
```

With this pattern, the HTTP response finishes before publishing completes; Redis exceptions are severed from the response flow, and cancellation/shutdown become hard to control.

Prefer **returning the Publisher**:

```java
@PostMapping("/api/events")
public Mono<Void> publish(@RequestBody Mono<RealtimeEvent> event) {
    return event
        .flatMap(publisher::publish)
        .then();
}
```

Only call `.subscribe()` explicitly at a clearly managed **lifecycle boundary**, such as a background worker, start/stop lifecycle service, or consumer decoupled from HTTP requests.

## 6. Subscribing with ReactiveRedisMessageListenerContainer

To listen to Pub/Sub via the reactive API, Spring Data Redis provides `ReactiveRedisMessageListenerContainer`.

Bean configuration:

```java
package com.example.realtime;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.listener.ReactiveRedisMessageListenerContainer;

@Configuration
public class ReactivePubSubConfiguration {

    @Bean
    ReactiveRedisMessageListenerContainer reactiveRedisListener(
            ReactiveRedisConnectionFactory connectionFactory) {

        return new ReactiveRedisMessageListenerContainer(
            connectionFactory
        );
    }
}
```

Receiving messages on a channel:

```java
import org.springframework.data.redis.listener.ChannelTopic;
import reactor.core.publisher.Flux;

Flux<String> messages = listenerContainer
    .receive(new ChannelTopic("events.realtime"))
    .map(message -> message.getMessage());
```

Under standard Spring Data Redis Reactive usage, `receive(...)` returns a `Flux` of messages carrying channel metadata and payload. Exact types and overloads vary by version and serializer; when using typed receive, configure the corresponding serialization context.

Essential point: **`receive` represents a Redis Pub/Sub subscription**, whose active connection and listening depend on an actual subscriber consuming this `Flux`.

### 6.1. A subscription is a resource that must be managed

When a Reactor subscriber subscribes:

```text
Application subscriber
       |
       | subscribe()
       v
ReactiveRedisMessageListenerContainer
       |
       | Redis SUBSCRIBE
       v
Redis channel "events.realtime"
       |
       | Redis PUBLISH
       v
Flux onNext(message)
```

When the subscription is canceled or the application shuts down, listening resources must be released along the container/connection lifecycle.

Never create a new listener container or Redis connection per message. If an SSE endpoint opens a dedicated Redis subscription per HTTP client, subscriptions and network/resource consumption grow with client count; design your fan-out architecture deliberately.

### 6.2. Pattern subscriptions

You can listen to multiple channels:

```java
Flux<String> orderEvents = listenerContainer
    .receive(new PatternTopic("orders.*"))
    .map(message -> message.getMessage());
```

If you need to tell `orders.created` apart from `orders.cancelled`, preserve the actual channel name metadata instead of extracting only the body. Depending on the overload, the `ChannelMessage`/Message wrapper exposes methods for both channel and message.

Conceptual example:

```java
listenerContainer
    .receive(new PatternTopic("orders.*"))
    .doOnNext(message -> {
        // message.getChannel(): actual channel
        // message.getMessage(): payload
    });
```

Never use the pattern string `orders.*` as the actual event type.

## 7. Streaming Pub/Sub over Server-Sent Events (SSE)

SSE lets the server hold an HTTP connection open and push multiple events over time. In WebFlux, a controller can return `Flux<ServerSentEvent<T>>`.

Example:

```java
package com.example.realtime;

import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.ReactiveRedisMessageListenerContainer;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventFeedController {

    private final ReactiveRedisMessageListenerContainer container;

    public EventFeedController(
            ReactiveRedisMessageListenerContainer container) {
        this.container = container;
    }

    @GetMapping(
        path = "/api/events/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> stream() {
        return container
            .receive(new ChannelTopic("events.realtime"))
            .map(message ->
                ServerSentEvent.<String>builder()
                    .event("realtime")
                    .data(message.getMessage())
                    .build()
            );
    }
}
```

Data flow:

```text
Redis PUBLISH events.realtime
        |
        v
Reactive Redis Flux
        |
        v
Spring WebFlux handler
        |
        v
text/event-stream over HTTP
        |
        v
Browser EventSource / SSE client
```

JavaScript client example:

```javascript
const feed = new EventSource("/api/events/stream");

feed.addEventListener("realtime", event => {
  const data = JSON.parse(event.data);
  console.log(data);
});

feed.onerror = error => {
  console.error("SSE connection interrupted", error);
};

// When leaving the page or no longer listening:
feed.close();
```

**Important limitation:** late-connecting SSE clients miss earlier Pub/Sub messages. `EventSource` supports HTTP/SSE reconnection, yet **Redis Pub/Sub does not automatically replay** publications sent while disconnected.

### 7.1. SSE IDs and Last-Event-ID do not create history automatically

SSE events can carry an `id` field, e.g.:

```java
ServerSentEvent.<String>builder()
    .id(eventId)
    .event("realtime")
    .data(json)
    .build();
```

Browsers can send `Last-Event-ID` upon reconnect. However, if the backing source is purely Pub/Sub, the server **has no Redis Pub/Sub log to backfill from that ID**.

To support real resume, combine:

- Redis Streams storing event history with Stream IDs.
- Pub/Sub as a real-time notification signal.
- On HTTP reconnect, the server reads Stream entries after the client's last ID and transitions to the live feed without missing the handoff window.

This design must handle races between history queries and live subscriptions, duplicate IDs, retention, and ordering. Setting an SSE `id` alone **is never enough to enable replay**.

### 7.2. One SSE client should not mean one dedicated Redis connection

The controller example above is easy to follow, yet can create many subscriptions as HTTP client counts grow. At high scale, consider a **shared hot Flux** or centralized fan-out service:

```text
                  Redis Pub/Sub
                       |
                 1 listener/instance
                       |
               Shared event stream
                 /      |       \
                v       v        v
              SSE A   SSE B    SSE C
```

Reactor provides multicast/share tools or `Sinks.Many` for fan-out. Still, a shared Flux needs clear policies:

- Do late subscribers receive past events?
- Do slow clients grow buffers or get dropped?
- When zero clients remain, is the Redis subscription canceled?
- When Redis reconnects, how are connected clients notified?
- Across multiple WebFlux instances, does each instance subscribe on its own or use an event gateway service?

Do not blindly apply Reactor `.cache()` to an infinite Pub/Sub stream, as it risks retaining every message in memory and causing a memory leak.

## 8. Backpressure: Flux Has Demand, Yet Redis Pub/Sub Still Pushes

Reactive Streams allows downstream to tell upstream how many items it needs via `request(n)`. That mechanism works well for sources capable of pausing or pacing emission.

Redis Pub/Sub has no equivalent per-subscriber ACK/demand flow control. Publishers keep pushing messages even when an SSE client is slow.

Model:

```text
Publisher PUBLISH 10,000 msg/s
            |
            v
Redis Pub/Sub transport
            |
            v
Reactive listener -> Flux
            |
            v
SSE client reads 50 msg/s
            |
            +--> Rate mismatch must be handled:
                  buffer / drop / disconnect / coalesce
```

Therefore, whenever someone claims "we used Flux so backpressure is solved," ask **how far backpressure actually reaches**. From Java to SSE downstream there can be pacing, yet that does not slow Redis publishers or make Redis durably queue unconsumed messages.

### 8.1. Options for slow consumers

| Strategy | Behavior | Suited for |
|---|---|---|
| Bounded buffer | Temporarily holds messages in RAM | Short bursts, small payloads |
| Drop latest | Discards new messages under overload | Telemetry where sample drops are acceptable |
| Drop oldest | Discards old messages to keep recent state | Dashboards showing current state |
| Latest only | Keeps only the newest update | Values like CPU usage or presence |
| Fail/disconnect | Closes clients unable to keep up | Enforcing explicit resource limits |
| Switch to Streams | Backfills from a retained log | When messages must never vanish due to slow clients |

Illustrative example for a state stream where intermediate updates may be skipped:

```java
Flux<String> latestUpdates = container
    .receive(new ChannelTopic("metrics.current"))
    .map(message -> message.getMessage())
    .onBackpressureLatest();
```

`onBackpressureLatest()` can skip intermediate values so downstream sees fresher updates; it is **unsuitable when every message represents a business action that must be processed**.

For streams that must never drop messages, choose Streams/queues and design consumers with ACK/recovery instead of increasing buffers indefinitely.

### 8.2. Other sources of OOM

- Unbounded `.onBackpressureBuffer()` on a high-rate stream.
- `Flux.cache()` or unbounded replay on infinite streams.
- Holding thousands of SSE subscriptions without timeouts or cleanup.
- Large JSON payloads copied across multiple buffers.
- Fanning out a single message to too many WebSocket/SSE clients.
- Listener-level retries spawning overlapping pipelines without disposing old ones.

Monitor queue depth, buffer occupancy, downstream latency, reconnect rates, and active subscriber counts.

## 9. Connection Failures and Subscription Cancellation in Pub/Sub

When the Redis connection drops:

```text
t0: Subscriber is subscribed.
t1: Connection drops.
t2: Redis publishes event E.
t3: Connection recovers, subscriber re-subscribes.
```

Event E at `t2` is not replayed by Redis Pub/Sub. Even if the client automatically reconnects and re-subscribes, it only resumes receiving events **from the moment the new subscription takes effect**.

Similarly, when an HTTP SSE client disconnects:

- WebFlux cancellation cancels the downstream subscription.
- If downstream directly owns the Redis subscription, release the corresponding connection/topic registration.
- If the Redis stream is shared, one HTTP client canceling must not accidentally kill the stream for all other clients.
- If SSE reconnects automatically, distinguish "reconnected cleanly" from "no events were lost."

Emit logs/metrics distinguishing Redis disconnects, reconnects, resubscribes, SSE client closes, and handler errors.

### 9.1. `retryWhen` does not mean Pub/Sub replay

Reactor supports retries:

```java
flux.retryWhen(
    Retry.backoff(
        5,
        Duration.ofMillis(200)
    )
);
```

For a failed subscription source, retry can establish a fresh subscription if upstream supports it. However, **messages published during the outage are never recreated**.

Avoid zero-delay infinite retries, which create tight spin loops while Redis is down. Use backoff, jitter, observability, and appropriate recovery bounds.

## 10. Streams in WebFlux: From Real-Time Signals to ID-Indexed Records

Redis Streams store entries as an append log. Producer example:

```redis
XADD orders:events * eventId evt-101 orderId o-101 type CREATED
XADD orders:events * eventId evt-102 orderId o-102 type PAID
```

Redis assigns a unique ID to each entry, such as:

```text
1763000000123-0
1763000000124-0
```

Each entry holds field/value pairs and an ID. With consumer groups, entries are delivered to consumers and tracked in the PEL until acknowledged.

Compared with Pub/Sub:

```text
Pub/Sub:
  PUBLISH event -> online listeners receive -> no backlog

Stream:
  XADD event -> entry stored in Stream
            -> consumer reads by ID/group
            -> processes
            -> XACK clears pending state
            -> original entry stays until trimmed/deleted
```

Redis Streams do not automatically schedule retries, guarantee exactly-once processing, or invoke Java handlers. Those capabilities must be built via consumer lifecycle, recovery, and business logic.

## 11. Writing to Streams with the Reactive API

Spring Data Redis Reactive exposes stream operations on `ReactiveRedisTemplate` or `ReactiveStringRedisTemplate`.

Example writer service:

```java
package com.example.orders;

import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderEventWriter {

    private static final String STREAM = "orders:events";

    private final ReactiveStringRedisTemplate redis;

    public ReactiveOrderEventWriter(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<RecordId> append(
            String eventId,
            String orderId,
            String type) {

        MapRecord<String, String, String> record =
            StreamRecords
                .newRecord()
                .in(STREAM)
                .ofMap(
                    Map.of(
                        "eventId", eventId,
                        "orderId", orderId,
                        "type", type
                    )
                );

        return redis.opsForStream().add(record);
    }
}
```

Using String fields and values makes entries easy to inspect with Redis CLI. When using custom/DTO serializers, pick record types and conversion contexts matching your Spring Data Redis setup.

Usage inside an HTTP controller:

```java
@PostMapping("/api/orders/{id}/events")
public Mono<String> addEvent(
        @PathVariable("id") String orderId) {

    return writer
        .append(
            java.util.UUID.randomUUID().toString(),
            orderId,
            "CREATED"
        )
        .map(RecordId::getValue);
}
```

Because the controller returns `Mono`, WebFlux subscribes and executes `XADD`. The returned ID confirms the entry was written at the Redis command level—not that any downstream consumer has processed it.

### 11.1. Database writes and XADD are not automatically atomic

Example:

```text
1. INSERT order into database.
2. XADD orders:events.
```

If step 1 succeeds and step 2 fails, the database and Stream fall out of sync. Chaining with Reactor `then`/`flatMap` or adding `@Transactional` on the database **does not create a distributed transaction across SQL and Redis**.

For critical events, consider a **transactional outbox** in the same database transaction, paired with a durable publisher appending to the Stream. Handle duplicate publishes using `eventId` and idempotency.

## 12. Reading Streams Without a Group: By ID and Retention

A consumer can read a Stream without a consumer group using:

```redis
XREAD COUNT 10 STREAMS orders:events 0-0
```

This reads entries with IDs strictly greater than the specified checkpoint. To wait for new entries:

```redis
XREAD BLOCK 5000 STREAMS orders:events $
```

`$` starts from the tail as of when the command begins, fitting certain live-tail cases yet risking skipping entries that arrived earlier.

In Spring Data Redis, common offsets include:

```java
ReadOffset.from("0-0")
ReadOffset.latest()
ReadOffset.lastConsumed()
```

Distinguish:

- **`ReadOffset.from(id)`**: reads starting after the specified ID per Stream read semantics.
- **`ReadOffset.latest()`**: starts at the latest position at read time; prone to skipping entries between polls if misused.
- **`ReadOffset.lastConsumed()`**: tracks consumer/group consumption progress per API context, typically used with consumer groups to read undelivered new entries.

### 12.1. The `latest()` trap in polling

A reactive source may pause polling when downstream has no demand or during processing. If each poll uses `$`/`latest`, entries written during pauses can be missed.

When data loss is unacceptable, prefer **explicitly tracked IDs** or **consumer groups** with managed ACKs rather than assuming a live-tail `Flux` using `latest()` never misses an entry.

This differs sharply from Pub/Sub: Streams retain entries according to retention, yet **a consumer choosing the wrong offset can still skip existing entries**.

### 12.2. A Stream is a log, not an automatic broadcast subscription

Three independent consumers not using a group and tracking their own IDs all read the same entries. Using **a shared consumer group** distributes new entries among consumers in that group.

With two independent consumer groups, each group maintains its own progress and PEL, so both groups process the same entries for their respective responsibilities.

## 13. Creating Consumer Groups and Understanding the Pending Entries List

Create a group in a test environment:

```redis
XGROUP CREATE orders:events orders-workers 0 MKSTREAM
```

Where:

- `orders:events`: Stream key.
- `orders-workers`: consumer group name.
- `0`: group can process existing entries from the start of the Stream.
- `MKSTREAM`: creates an empty Stream if it does not already exist.

Choosing `$` instead of `0` starts the group at the current tail of the Stream, consuming only entries arriving after group creation. Picking the wrong initial offset can skip historical backlog.

Consumer reading:

```redis
XREADGROUP GROUP orders-workers worker-A COUNT 10 BLOCK 2000 STREAMS orders:events >
```

`>` requests new entries not yet delivered to any consumer in the group. Unless `NOACK` is specified, Redis tracks delivered IDs in the **Pending Entries List (PEL)**.

```text
Stream orders:events
   |
   | XREADGROUP GROUP orders-workers worker-A ... >
   v
worker-A receives entry id=1763000000123-0
   |
   +--> PEL orders-workers:
         ID           = 1763000000123-0
         Owner        = worker-A
         Idle time    = ...
         Delivery cnt = ...
   |
   +--> Application processes event
         |
         +-- Success --> XACK
         +-- Crash   --> entry stays pending
```

`XACK` only clears **pending status inside the group**; it does not delete the original entry from the Stream. Trimming the log is a separate retention decision.

### 13.1. Pending does not equal failure

A message can be pending simply because it is still being processed normally. Pending only means Redis delivered it and has not yet received an ACK. If a handler normally takes 90 seconds, an entry pending for 20 seconds does not prove the worker crashed.

Evaluate typical processing durations, consumer health, pending idle time, and delivery counts together.

## 14. Reading Consumer Groups from a WebFlux/Reactive Worker

Spring Data Redis supports `ReactiveStreamOperations` and continuous Stream consumption, including `StreamReceiver` for reactive consumption.

Fundamentally, a worker needs:

```text
Reactive source from Redis Stream
       |
       v
Flux<MapRecord<...>>
       |
       v
Validate / deserialize
       |
       v
Invoke asynchronous business logic
       |
       v
ACK via reactive Redis operation
```

Example consumer-group API structure with `StreamReceiver`:

```java
import java.time.Duration;

import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamReceiver;

StreamReceiver.StreamReceiverOptions<String, MapRecord<String, String, String>>
    options = StreamReceiver.StreamReceiverOptions
        .<String, MapRecord<String, String, String>>builder()
        .pollTimeout(Duration.ofSeconds(2))
        .build();

StreamReceiver<String, MapRecord<String, String, String>> receiver =
    StreamReceiver.create(connectionFactory, options);

Flux<MapRecord<String, String, String>> records =
    receiver.receive(
        Consumer.from("orders-workers", "worker-A"),
        StreamOffset.create(
            "orders:events",
            ReadOffset.lastConsumed()
        )
    );
```

This illustrates the receiver contract, record type, and offset. Generic builders, serialization options, and overloads vary across Spring Data Redis versions; in your project, use the exact `StreamReceiverOptions` and serialization context of your dependency version.

What matters is not one specific builder syntax, but the design decisions:

1. Use an explicit **consumer group** and consumer name.
2. Read with `ReadOffset.lastConsumed()` for new messages delivered to the group.
3. Bound poll timeout and resources.
4. Expose a `Flux` wired into the processing pipeline.
5. **ACK only after business processing succeeds.**
6. Implement a separate pending recovery path, because reading new messages never returns entries pending under another consumer.

### 14.1. Why is `StreamReceiver` different from a Pub/Sub listener?

Pub/Sub is pushed immediately by Redis with no backlog. A Stream receiver **polls** Redis to read the log by offset, lets you tune polling behavior, and plugs directly into Reactor streams.

Stream replay relies on entries remaining in the Stream and valid read offsets. That comes from the **Redis data structure**, not from a Reactor operator.

### 14.2. Polling does not block request threads like blocking APIs

Redis `XREAD`/`XREADGROUP` supports `BLOCK` to wait for new entries on the Redis server. With a reactive connector, the application does not need `Thread.sleep()` or a blocked Java request thread waiting for the reply.

Still, a blocked read consumes **a connection and server/client resources**. Configure poll timeouts, connection management, and clean shutdown appropriately. "Non-blocking Java I/O" does not mean zero operational cost.

## 15. Reactive ACK: Acknowledge Only After Processing Succeeds

Suppose we have a reactive business handler:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import reactor.core.publisher.Mono;

public interface OrderEventHandler {
    Mono<Void> handle(MapRecord<String, String, String> record);
}
```

A processing chain using `concatMap`:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

private Flux<Void> processRecords(
        Flux<MapRecord<String, String, String>> records,
        ReactiveStringRedisTemplate redis,
        OrderEventHandler handler) {

    return records.concatMap(record ->
        handler.handle(record)
            .then(
                redis.opsForStream().acknowledge(
                    "orders:events",
                    "orders-workers",
                    record.getId()
                )
            )
            .doOnNext(ackCount -> {
                if (ackCount == 0L) {
                    // Log/record metric when entry is no longer pending.
                }
            })
            .then()
            .onErrorResume(error -> {
                // Log with Stream ID and classify error.
                // Do not ACK an incomplete message.
                return Mono.empty();
            })
    );
}
```

This illustrates a service method. `records` is the source Flux from the receiver above; `handler.handle` must return a Publisher reflecting **when business processing truly finished**, not merely when work was scheduled.

Execution order:

```text
record -> handler.handle(record) completes successfully
       -> ACK returns result
       -> concatMap moves to next record
```

If `handler` errors, the ACK branch never runs. The entry stays pending and must be handled via designed retry/recovery.

### 15.1. Why not ACK immediately upon receipt?

Dangerous pattern:

```java
records.flatMap(record ->
    redis.opsForStream()
        .acknowledge(STREAM, GROUP, record.getId())
        .then(handler.handle(record))
);
```

Here ACK completes before business logic runs. If the handler fails or crashes, the PEL has already lost the record needed for retry. For reliable workflows, this ordering is wrong.

### 15.2. `flatMap` and concurrency

If you write:

```java
records.flatMap(record -> handleAndAck(record))
```

multiple messages process concurrently and may complete **out of received order**. That can be fine for independent events when higher throughput is desired, yet breaks invariants if multiple events for the same `orderId` must process in sequence.

Options:

- `concatMap` processes sequentially, preserving order within a pipeline.
- `flatMap(record -> handleAndAck(record), concurrency)` bounds in-flight tasks.
- Partition by entity key and process sequentially **per partition** if per-entity ordering is needed; bound partition counts and lifecycle to avoid unbounded memory retention.
- Rely on transactions or optimistic locking in the authoritative store under concurrent updates.

**Redis Streams do not turn work across multiple consumers into strictly ordered business execution.** Design partition keys, sequence versions, and idempotency when ordering matters.

### 15.3. Cancellation between processing and ACK

If the Reactor subscription is canceled after the side effect commits yet before `XACK`, the message stays pending and will be picked up by a recovery worker.

Even with non-blocking APIs, `.then(...)` does not create an atomic commit between a database and Redis `XACK`. Use **idempotency** whenever side effects must not repeat.

## 16. At-Least-Once Delivery and Idempotency in WebFlux

Timeline to watch for:

```text
t1: Worker reads event E from Stream.
t2: E is added to PEL.
t3: Handler calls database and commits successfully.
t4: Worker crashes before XACK.
t5: Recovery worker claims E.
t6: Handler runs E again.
```

At `t6`, if the handler is not idempotent, it could send the same email twice, award loyalty points twice, or write duplicate records.

A common strategy uses a **business event identifier**:

```json
{
  "eventId": "evt-1001",
  "orderId": "o-101",
  "type": "OrderPaid"
}
```

In the target system, record `eventId` in a store with a unique constraint or compare-and-set guard **inside the same transaction** as the durable side effect.

Conceptual SQL example:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Upon receiving E:

```text
BEGIN transaction
    INSERT processed_events(event_id = E.eventId)
    if duplicate: skip re-applying side effects
    if new: update business data
COMMIT
XACK E
```

In this design, ACK can safely be called again after seeing the event was already processed; re-invocation will not duplicate side effects. For external APIs (payments, email), use provider idempotency keys or a separate outbox/dispatch state.

### 16.1. Reactivity does not define transaction boundaries

If a handler uses R2DBC and reactive database transactions, the returned `Mono` completion must reflect transaction commit. If a handler calls `.subscribe()` on a database write and returns `Mono.empty()`, the caller can ACK too early.

Avoid:

```java
public Mono<Void> handle(Event event) {
    repository.save(convert(event)).subscribe(); // Detached side effect
    return Mono.empty();
}
```

Return the Publisher directly wired to the operation:

```java
public Mono<Void> handle(Event event) {
    return repository
        .save(convert(event))
        .then();
}
```

For multi-step updates, use reactive transaction management if everything belongs to the same transactional resource. Never assume `@Transactional` on a reactive method creates an atomic transaction across an R2DBC database and a Redis Stream.

## 17. PEL Recovery: Reading New Messages Never Fetches Old Pending Entries

A common operational surprise:

```text
worker-A reads E -> E is pending -> worker-A crashes
worker-B reads STREAMS orders:events >
```

`worker-B` using `>` reads **new** messages, yet never automatically receives entry E sitting in `worker-A`'s PEL.

Recovery is required. Redis provides:

```redis
XPENDING orders:events orders-workers
XPENDING orders:events orders-workers - + 20
```

to inspect pending entries. To transfer ownership:

```redis
XCLAIM orders:events orders-workers worker-B 60000 <entry-id>
```

Or to scan and claim automatically by idle time:

```redis
XAUTOCLAIM orders:events orders-workers worker-B 60000 0-0 COUNT 20
```

In this command:

- `60000` is the minimum idle-time threshold of 60 seconds, not a message TTL.
- `0-0` is the scan cursor inside the PEL.
- Process both the returned cursor and claimed entries.
- Claiming **does not ACK**; the recovery worker still processes each entry and calls `XACK` upon success.

### 17.1. Can recovery workers use the reactive API?

Spring Data Redis and its driver provide Stream command operations; exact reactive abstraction coverage varies by version. If a needed recovery command lacks a convenient high-level reactive wrapper, use an appropriate low-level API or a dedicated administrative worker—just never put blocking commands on the WebFlux event-loop.

A sound architecture:

```text
Normal Reactive StreamReceiver
    -> read new messages
    -> process
    -> ACK

Recovery service
    -> inspect PEL
    -> find long-idle entries
    -> XAUTOCLAIM/XCLAIM
    -> process via the same idempotent handler
    -> ACK
```

Avoid claiming too early while the original worker is still processing normally. Choose idle thresholds from real p99 processing times and business timeouts—never assume 60 seconds fits every workload.

### 17.2. Reading the same consumer's pending history

`XREADGROUP` with an ID like `0` reads pending entries belonging to **the current consumer name** in the group, whereas `>` reads new messages. A consumer restarting with the same name can proactively drain its own pending history.

However, a consumer with a different name never receives an old consumer's pending entries simply by reading from `0`. Claiming is required to transfer ownership.

### 17.3. Unprocessable messages and DLQ

If a message has a malformed payload or permanently violates an invariant, keeping it pending and retrying forever creates a poison-message loop.

One approach:

```text
Receive E
    |
    +-- OK ----------------------> XACK
    |
    +-- Retryable ---------------> pending/retry with backoff
    |
    +-- Non-retryable -----------> write to durable DLQ
                                     |
                                     v
                               XACK original entry
```

Writing to the DLQ and ACKing can fail independently. To prevent losing or duplicating DLQ entries, design idempotency or atomic handling scoped to the Redis key or target store.

## 18. StreamReceiver and Managing Background Worker Lifecycle

Unlike HTTP endpoints where WebFlux owns subscriptions, a background worker needs an **active subscriber** and an explicit lifecycle.

Conceptual model:

```text
Spring Application Start
      |
      v
Create StreamReceiver
      |
      v
Subscribe to processing Flux
      |
      v
Store Disposable subscription
      |
      +-- Running: receive and process messages
      |
Spring Application Shutdown
      |
      v
Cancel subscription / graceful stop
```

Simply defining a `Flux` `@Bean`:

```java
@Bean
Flux<?> orderMessages(StreamReceiver<?, ?> receiver) {
    return ...;
}
```

**does not mean anything subscribes or the worker runs**. A `Flux` bean is just a Publisher object; something must manage its subscription.

### 18.1. Using SmartLifecycle or a lifecycle component

You can use Spring's `SmartLifecycle` to start/stop the pipeline and retain the `Disposable`. Pseudocode showing structure:

```java
public final class OrderWorkerLifecycle implements SmartLifecycle {

    private Disposable subscription;
    private boolean running;

    @Override
    public void start() {
        if (running) {
            return;
        }

        subscription = recordsFlux
            .concatMap(this::processAndAck)
            .doOnError(this::reportFailure)
            .retryWhen(
                Retry.backoff(
                    Long.MAX_VALUE,
                    Duration.ofMillis(500)
                ).maxBackoff(Duration.ofSeconds(10))
            )
            .subscribe();

        running = true;
    }

    @Override
    public void stop() {
        if (subscription != null) {
            subscription.dispose();
            subscription = null;
        }
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

This is an **illustrative skeleton**: `recordsFlux`, `processAndAck`, and `reportFailure` must be wired to actual services, with logging, thread-safe state handling, and shutdown policies added. Default `SmartLifecycle` methods such as phase/auto-start can be overridden as needed.

In production, `.dispose()` can cancel in-flight work rather than draining gracefully. If in-flight tasks must finish before shutdown, define a shutdown deadline, stop polling, await active tasks, and let pending recovery handle anything unfinished after the timeout.

### 18.2. Which layer gets `retryWhen`?

Distinguish two error classes:

- **Redis read errors:** connection drops, polling timeouts. Re-creating the reader subscription with backoff is appropriate.
- **Per-record processing errors:** invalid payload, database failure, business rejection. One bad record should not crash the whole reader stream, nor be blindly ACKed.

Placing one generic `retryWhen` after the handler without distinguishing errors causes a single message failure to re-subscribe the entire source and leave the record pending; depending on offsets and ownership, it will not automatically reappear.

A cleaner structure handles errors **per record** with explicit retry/DLQ rules, while keeping a separate transport-level retry around the stream reader.

## 19. Ordering and Concurrency in Consumer Groups

Redis Streams preserve entry ID order inside the Stream, yet the application can lose effective order through parallel processing.

Example:

```text
Stream:
    E1: order o-9 CREATED
    E2: order o-9 PAID
    E3: order o-9 CANCELLED

Worker-A receives E1
Worker-B receives E2
Worker-C receives E3
```

If E2 finishes before E1, the system can record invalid state even though Stream ID order was intact.

Thus, "events for the same aggregate must process in order" is not automatically guaranteed just because consumers share one group.

Design options:

1. Restrict to a single consumer for streams that genuinely need global order.
2. Partition by `orderId` so events for the same order run sequentially, if added routing complexity is acceptable.
3. Include version/sequence numbers in each event and enforce optimistic concurrency control in the database.
4. Let handlers defer, ignore, or reconcile out-of-order events per domain invariants.
5. Do not raise `flatMap` concurrency if business logic demands sequential processing.
6. When using multiple Stream keys in Redis Cluster, design hash tags and routing carefully.

Trade-off: strict ordering limits throughput; higher throughput requires more sophisticated versioning and idempotency.

## 20. WebFlux SSE Backed by Streams: When Replay Is Required

For a dashboard needing recent history followed by live updates, Redis Streams suit better than raw Pub/Sub whenever replay by ID is required.

Model:

```text
Browser SSE
   |
   | Last-Event-ID: 1763000000123-0
   v
WebFlux Controller
   |
   | XREAD/XRANGE after received ID
   v
Redis Stream
   |
   +--> Emit older retained events
   |
   +--> Continue reading new events by offset
   |
   v
Flux<ServerSentEvent<...>>
```

Mapping records to SSE:

```java
Flux<ServerSentEvent<String>> feed = records
    .map(record ->
        ServerSentEvent.<String>builder()
            .id(record.getId().getValue())
            .event("order")
            .data(record.getValue().toString())
            .build()
    );
```

This snippet illustrates the mapping. `record.getValue().toString()` **is not a standard JSON serializer**; if clients expect structured JSON, use Jackson to serialize an explicit DTO or envelope.

### 20.1. Never share one consumer group across all browsers when broadcasting

If all SSE browser connections share one consumer group, Redis **load-balances** entries across group consumers, so each browser sees only a subset of entries. That fails when every browser must receive **all** feed events.

Options:

- Use per-browser `XREAD` by ID if connection count and Redis load permit.
- Run a single server-side reader fanning out to SSE clients, keeping Stream-ID resume at the gateway layer.
- Use Pub/Sub for live notifications and Streams for backfill, bridging the two without gaps or duplicates.
- When distinct service teams each need all events, use separate consumer groups—never spawn **an unbounded group per browser** without lifecycle cleanup.

Consumer groups are for **distributing work**, not broadcasting SSE streams automatically.

### 20.2. Bridging history and live updates

A naive design:

```text
1. XRANGE reads history up to current ID.
2. Subscribe to Pub/Sub.
```

can miss events published between the two steps. Reversing the order:

```text
1. Subscribe to Pub/Sub.
2. Read history from Stream.
```

can receive duplicate events across the overlap. This is a classic architectural race requiring deduplication by Stream ID, watermarks, and controlled handoff.

A simpler choice when latency and throughput allow is tailing the **Stream** continuously by ID as the single source instead of stitching two subscription types together.

## 21. Comparing Pub/Sub and Streams in WebFlux

| Criterion | Reactive Pub/Sub | Reactive Streams |
|---|---|---|
| Redis nature | Real-time broadcast | ID-indexed log |
| Primary commands | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` | `XADD`, `XREAD`, `XREADGROUP`, `XACK` |
| Typical Spring API | `ReactiveRedisMessageListenerContainer` | `ReactiveStreamOperations`, `StreamReceiver` |
| Reactor stream type | `Flux` of publications | `Flux` of Stream records |
| History retention | No | Yes, within retention bounds |
| Late-comer backfill | Not via plain Pub/Sub | Yes, if entry retained and ID/offset known |
| Consumer group ACK | No | Yes via `XACK` |
| Pending/claim | No | PEL, `XCLAIM`/`XAUTOCLAIM` |
| Broadcast to many subscribers | Natural | Needs separate readers or explicit fan-out |
| Work distribution among workers | No built-in consumer groups | Yes via `XREADGROUP` |
| End-to-end backpressure | No guarantee Redis Pub/Sub pauses for slow clients | Can tune polling/demand, still requires concurrency design |
| Retry/recovery | No default replay | Implementable via Stream/PEL |
| Exactly-once | No | Not automatic; requires idempotency |
| Memory profile | Mainly connection/output buffers | Additional log data, retention, and PEL metadata |
| Best fit | UI notifications, cache invalidation, live signals | Jobs, replayable audit/events, ACK-backed processing |

**Neither mechanism is universally superior.** If you only need to notify open UIs that state changed, Pub/Sub is simple and fast. If a message represents work that must survive crashes, use Streams or a broker with retention and ACKs.

## 22. Serialization: From Redis Bytes to Reactive DTOs

Both Pub/Sub and Streams transmit data over the Redis protocol; Java objects never cross the network automatically.

For Pub/Sub:

```text
Java event DTO
    |
    | ObjectMapper -> JSON string
    |
    | ReactiveStringRedisTemplate
    v
Redis channel + payload bytes
    |
    v
Flux<Message>
    |
    | JSON deserialize
    v
Java DTO
```

For Streams:

```text
Java event
    |
    | fields: eventId, type, payload
    v
XADD stream * field/value...
    |
    v
MapRecord / ObjectRecord depending on config
    |
    | serializer/converter
    v
Java model
```

### 22.1. Pick an explicit payload format

JSON envelope example:

```json
{
  "eventId": "evt-1001",
  "schemaVersion": 1,
  "type": "OrderCreated",
  "occurredAt": "2026-11-13T02:00:00Z",
  "payload": {
    "orderId": "o-101"
  }
}
```

Agree on:

- Encoding, usually UTF-8.
- Channel/Stream key names.
- Schema versions and backward compatibility rules.
- Business event ID (distinct from Redis Stream ID).
- Maximum payload size.
- Validation rules and handling of malformed payloads.
- Policies for redacting sensitive data in logs and metrics.

If the producer uses JDK serialization while the consumer expects String JSON, decoding fails. Similarly, if a consumer casts `record.getValue()` unchecked, differing field/value serializers will cause runtime errors.

### 22.2. `MapRecord` and `ObjectRecord`

- `MapRecord` represents a Stream entry as a map of fields/values.
- `ObjectRecord` supports mapping objects via a converter.

The choice depends on schemas and serializers. `MapRecord<String, String, String>` is transparent when all fields/values are Strings. `ObjectRecord` is convenient when object mapping is uniform, provided you understand field names, keyspaces, formats, and version compatibility.

For critical consumer groups, avoid letting a DTO or serializer change break all workers and leave older entries un-ACKed. Plan schema migrations and a DLQ clearly.

## 23. Errors and Retries in Reactor: Do Not Alter Business Semantics

Common Reactor operators:

```java
.retryWhen(...)
.onErrorResume(...)
.timeout(...)
.doOnError(...)
```

They govern the Publisher **on the application side**. They do not fix:

- Redis Pub/Sub events missed during a disconnect.
- Stream entries ACKed too early.
- Side effects committed when ACK failed.
- Unclaimed pending entries stuck in a consumer group.
- Permanently malformed payloads.
- Two workers processing the same event due to premature claiming.

### 23.1. Retrying reads vs. retrying record processing

If `XREADGROUP` loses its connection, recreating the reader with backoff helps. If the handler fails on record E, retrying the whole stream source creates unpredictable loops while E stays pending.

Separate by error class:

| Error | Approach |
|---|---|
| Redis network timeout while reading | Backoff, reconnect, preserve worker state |
| Malformed JSON payload | Do not retry forever; route to DLQ per policy |
| Database temporarily unavailable | Bounded retries, then leave pending or transition state |
| External API returns permanent error | Compensate/DLQ per business contract |
| ACK timeout after business commit | Verify state; rely on idempotency on redelivery |
| Slow SSE downstream client | Buffer/drop/disconnect or serve from Stream by ID |
| Pub/Sub subscriber drops connection | Reconnect; use another log source if backfill is required |

### 23.2. Timeouts do not prove a command did not run

Suppose a `Mono` executing `XADD` or `XACK` hits a client timeout. Redis may already have executed the command with the reply lost. Never infer "timeout means command was never sent."

With `XADD`, re-sending without idempotency creates a second Stream entry with a new ID and the same `eventId`. With `XACK`, a second attempt returns `0` because the entry is no longer pending. Downstream must still decide based on `eventId` and actual state.

## 24. Protecting the Event-Loop from Blocking Code

WebFlux typically runs a small number of event-loop threads serving many connections. If a Stream handler blocks:

```java
public Mono<Void> handle(Event event) {
    jdbcRepository.save(event); // Blocking JDBC.
    return Mono.empty();
}
```

the blocking call runs right when the method is invoked, before returning the Publisher. Use a reactive API (such as R2DBC for reactive database access) or isolate the blocking work:

```java
public Mono<Void> handle(Event event) {
    return Mono.fromRunnable(
        () -> jdbcRepository.save(event)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .then();
}
```

This is a compatibility bridge for a blocking dependency, not an optimal high-throughput architecture. `boundedElastic` has finite threads and queues; monitor it and never allow unbounded blocking calls.

### 24.1. Places that can accidentally block

- Calling `StringRedisTemplate` from a WebFlux controller.
- Using `.block()`/`.blockOptional()` on the Netty event-loop.
- Reading files or calling blocking HTTP clients inside `map`.
- Parsing huge payloads or running heavy CPU calculations on event-loop threads.
- Calling `Thread.sleep()` during retries instead of Reactor `retryWhen`.
- Holding long `synchronized` locks inside Pub/Sub receive callbacks.
- Running blocking database transactions inside a Stream handler and immediately ACKing.

Keep **I/O paths non-blocking**, bound resources, and keep business transaction boundaries clear.

## 25. Deploying Multiple WebFlux Instances

Suppose three instances run:

```text
               Redis
                |
        +-------+-------+
        |       |       |
        v       v       v
      App A   App B   App C
        |       |       |
       SSE     SSE     SSE
     clients clients clients
```

With **Pub/Sub**:

- Every instance subscribed to the channel receives matching publications.
- Each instance fans out to its connected SSE clients.
- A publication has no automatic "single consumer" like a worker queue.
- When an instance goes offline, its clients can miss events.
- If one instance registers overlapping subscriptions, it can receive duplicates.

With **Streams + one shared consumer group**:

- Instances in the group divide new entries among themselves.
- A single instance does not see every event just by joining the group.
- PEL recovery is needed when an instance crashes.
- If every instance must deliver **every** event to its own SSE clients, never use one shared consumer group as the direct broadcast source.

### 25.1. Common pattern: Redis Stream as durable source, Pub/Sub as wake-up signal

Combining both:

```text
Business Service
   |
   +--> Append event to Redis Stream
   |
   +--> Publish "new event" notification
                |
                v
        WebFlux app instances
                |
                +--> Receive Pub/Sub signal
                |
                +--> Read Stream from checkpoint ID
                |
                +--> Fan-out to SSE clients
```

Benefit: if a Pub/Sub notification is lost, readers can periodically poll the Stream from their checkpoint without relying solely on live signals.

Details to address:

- Ordering of Stream append and Pub/Sub publish, since each can fail independently.
- Where checkpoints live and how they survive restarts.
- Which events each instance/broadcast group must read.
- How backfilling by ID avoids duplicates upon reconnect.
- Retention long enough to cover instance downtime.
- Rate-limiting backfill reads to prevent spikes.

This pattern adds complexity. If business rules tolerate losing real-time notices and UIs reload state on page open, direct Pub/Sub may already suffice.

## 26. Redis Cluster and Related Constraints

Redis Cluster partitions keys by hash slot. For Streams:

- A single Stream key belongs to one hash slot.
- Commands targeting one Stream route to the slot's owning node.
- Multi-Stream reads in a single operation can hit **same hash slot** requirements.
- If a script/transaction updates a Stream, PEL-related metadata, or other data keys together, check how many slots those keys span; Redis Cluster does not offer cross-shard transactions via Lua/`MULTI` alone.

Example colocating two Streams via hash tags:

```text
orders:{tenant-7}:events
orders:{tenant-7}:dlq
```

Colocation helps when a workflow needs atomic operations within one slot, though putting an entire busy tenant into one hot slot can create bottlenecks.

### 26.1. Classic Pub/Sub vs. sharded Pub/Sub

Redis Cluster offers **classic Pub/Sub** (`PUBLISH`/`SUBSCRIBE`/`PSUBSCRIBE`) and **sharded Pub/Sub** (Redis 7+: `SPUBLISH`/`SSUBSCRIBE`).

Do not assume `ReactiveRedisMessageListenerContainer.receive(new PatternTopic(...))` automatically uses sharded Pub/Sub or supports equivalent pattern matching on sharded channels. Check which modes your Spring Data Redis and driver versions support.

Choosing classic vs. sharded Pub/Sub concerns topology, network fan-out, and pattern support; choosing Pub/Sub vs. Streams concerns retention and processing guarantees.

### 26.2. Do not infer exactly-once from client redirects

Cluster-aware Lettuce routes commands and handles redirects for many Redis commands, yet during resharding or failover timeouts and uncertain write outcomes can still occur.

Retrying `XADD` without `eventId` idempotency can duplicate business records. Retrying a handler after claiming can also duplicate side effects. Enforce idempotency at the application layer.

## 27. Retention and Replayability in Streams

Redis Streams retain entries until an explicit retention or deletion command runs. For example:

```redis
XADD orders:events MAXLEN ~ 100000 * eventId evt-101 type CREATED
```

`MAXLEN ~ 100000` sets an approximate entry cap. It does not guarantee retaining exactly 100,000 entries.

Related commands:

```redis
XLEN orders:events
XTRIM orders:events MAXLEN ~ 100000
XRANGE orders:events - + COUNT 10
```

Do not confuse:

- `XACK` removes a pending entry from the group's PEL.
- `XDEL` deletes an entry from the Stream itself.
- `XTRIM` trims the log per policy.
- `XLEN` is the retained Stream length, not a group's unprocessed backlog.

**If an entry is trimmed before a consumer processes or recovers it, the PEL may still hold its ID while its payload is gone.** Therefore, size retention around write throughput, the slowest consumer group, longest pending durations, maximum downtime, and SSE replay windows.

### 27.1. Using Redis Streams as a bounded event log

Streams fit storing a bounded event window in Redis, yet you should not assume Redis RAM can keep unlimited history forever. You must:

- Bound retention by count or age per needs.
- Monitor backlog via metrics.
- Archive long-term history elsewhere if multi-year auditing is required.
- Guard sensitive data inside payloads.
- Verify Redis backup/persistence and failover when data is critical.
- Define replay behavior when a client's last ID has already been trimmed.

If a client's `Last-Event-ID` predates the oldest retained Stream entry, respond explicitly per policy—send a fresh snapshot, signal full resync, or reject resume—rather than silently pretending history is complete.

## 28. Observability: Measure Both Reactor and Redis

A reactive app can appear "non-blocking" while dropping messages, growing backlogs, or double-processing events.

Metrics to monitor:

| Component | Metric or signal | Meaning |
|---|---|---|
| WebFlux | Active SSE connections, disconnect/reconnect counts | Real-time connection health |
| Reactor | Buffer occupancy, `onNext` rate, dropped events | Whether clients keep pace with sources |
| Pub/Sub | Message receive rate, listener errors, Redis reconnects | Stability of real-time signal delivery |
| Streams | `XLEN`, group lag | Retained backlog and undelivered entries |
| Consumer group | `XPENDING`, oldest idle time, per-consumer pending | Delivered yet un-ACKed messages |
| Recovery | Claim counts, retries, DLQ writes | Worker stability |
| Handler | Success/failure counts, p95/p99 latency | Business processing quality |
| Redis | CPU, memory, network, client buffers | Server resources |
| Serialization | JSON/schema errors | Producer/consumer compatibility health |
| Delivery | Duplicate `eventId`/idempotency hits | Rate of redelivered side effects |

Useful Redis commands:

```redis
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events orders-workers
XPENDING orders:events orders-workers
XPENDING orders:events orders-workers - + 20
XLEN orders:events
```

For Pub/Sub:

```redis
PUBSUB NUMSUB events.realtime
PUBSUB NUMPAT
```

`PUBSUB NUMSUB` mainly counts direct channel subscribers and does not prove all pattern subscribers received messages. Above all, **`PUBLISH`'s return count is not the number of successfully processed business events**.

### 28.1. Reactor Context and correlation IDs

Each event should carry an `eventId`, `traceId`, or correlation fields for tracing across Redis and downstream services. Reactor attaches `Context` to subscriptions; traditional thread-local MDC does not automatically propagate across every asynchronous hop.

Never rely solely on thread names to correlate logs from a WebFlux HTTP request to a Stream worker. When tracing across services, include correlation metadata inside payloads and use properly configured context propagation/instrumentation.

Never place sensitive data or raw auth tokens inside Redis keys, channels, or logs.

## 29. Common Issues

### 29.1. "Called convertAndSend but nobody received it"

You may have built a `Mono` without returning or subscribing to it. Check Publisher lifecycle before checking channel names. Also verify subscribers had already subscribed and point to the same Redis instance.

### 29.2. "Using WebFlux yet requests still hang"

Code may be calling `StringRedisTemplate`, blocking JDBC, or `.block()` on the event-loop. `Mono.just(blockingCall())` still runs `blockingCall()` eagerly while building the Mono.

### 29.3. "Pub/Sub listener created but no messages arrive"

Verify an actual subscriber subscribed to the `Flux`, container lifecycle, exact/pattern topic, serializer, connection, and publish timing. Pub/Sub never replays events published before subscription.

### 29.4. "SSE reconnects yet updates are lost"

SSE reconnect does not make Redis Pub/Sub replay. To backfill, use Stream IDs/offsets and log retention; setting an SSE `id` alone is insufficient.

### 29.5. "Slow SSE clients drive memory up"

Check buffers/operators and downstream subscription counts. Apply drop, coalesce, or switch to Streams as needed; avoid unbounded buffers.

### 29.6. "Scaling replicas causes each event to be processed multiple times"

When all instances subscribe to the same Pub/Sub channel, all receive every broadcast. Pub/Sub is broadcast, not a consumer group. Choose Redis Streams consumer groups to distribute work across workers.

### 29.7. "Stream worker received a message, failed, and never receives it again"

The message may still sit in the PEL; reading `>` only fetches new entries. Use `XCLAIM`/`XAUTOCLAIM` recovery or read that consumer's own pending history.

### 29.8. "After ACK, XRANGE still reads the record"

`XACK` only clears PEL status, never deleting the Stream entry. Bound log growth with a retention policy.

### 29.9. "An order event ran twice after failover"

The handler likely committed before ACK, and recovery redelivered it. Enforce idempotency via `eventId`/unique constraints and guard external side effects.

### 29.10. "Using latest() to tail a live Stream skips messages"

When gaps occur between polls, `latest()` jumps to the current tail. Read by tracked ID or consumer group with pending handling to avoid skips.

### 29.11. "Adding flatMap causes out-of-order event processing"

`flatMap` runs concurrently and can finish out of order. When events on the same entity require ordering, use `concatMap`, partitioning, or sequence checks.

### 29.12. "Infinite retryWhen still loses events"

Reactor retries never recreate lost Pub/Sub messages and never claim PEL entries automatically. Build recovery around the corresponding Redis mechanism.

### 29.13. "Wrote to a Redis Stream yet the new consumer sees nothing"

The group may have been created with `$` after the events were written, the consumer used the wrong offset, or entries were trimmed. Check group creation/`last-delivered-id` and retention.

### 29.14. "Switched StringRedisTemplate to ReactiveRedisTemplate and payloads turned into unreadable binary"

Serializer defaults changed. Align key/field/value serialization and JSON schemas; reactive does not auto-negotiate data formats.

## 30. Design Guide by Use Case

### 30.1. UI notification: "new data available"

Requirement: clients can miss a notification because opening the page loads the latest snapshot.

Choice:

```text
Business update
  -> PUBLISH notification
  -> WebFlux Pub/Sub listener
  -> SSE
  -> Browser calls API to fetch snapshot if needed
```

Benefit: simple design, minimal server state. Trade-off: disconnects drop notifications, so clients must be able to fetch current state on demand.

### 30.2. Invoice processing requiring retries

Requirement: once an invoice event arrives, it must be processed or routed to a DLQ even if workers crash.

Choice:

```text
XADD invoice:events
  -> Reactive StreamReceiver / consumer group
  -> idempotent handler
  -> XACK
  -> pending recovery + DLQ
```

Never rely solely on raw Pub/Sub for this requirement.

### 30.3. Dashboard requiring history upon reconnect

Requirement: clients send `Last-Event-ID` and want to replay events missed over the past 10 minutes.

Choice:

```text
XADD metrics:events
  -> WebFlux XREAD by ID
  -> SSE id = Stream ID
  -> on reconnect, read from last ID onward
```

Requires sufficient retention and a fallback policy if the ID has been trimmed. If using shared fan-out, resolve races between historical replay and live emissions.

### 30.4. One event triggering two independent processing groups

Example: `OrderCreated` needs both payment processing and auditing.

Use two consumer groups:

```text
Stream orders:events
  |
  +-- payment-workers group -> process payment, own ACK
  |
  +-- audit-workers group   -> write audit, own ACK
```

Each group tracks its own progress and PEL. ACKs from the payment group do not ACK for the audit group. Retention must accommodate the slower group.

### 30.5. One signal plus one durable workflow

Both can work together:

```text
Event into Stream -> durable workflow
         |
         +-- Pub/Sub notification -> real-time UI
```

If Pub/Sub publishing fails after Stream append, UIs can poll/backfill from the Stream. If Pub/Sub fires before the Stream write succeeds, UIs may observe an event not yet in the log. Define ordering and reconciliation clearly.

## 31. Hands-On Exercises: Pub/Sub and SSE

### Exercise 1 — Distinguishing lazy publishers

Write:

```java
Mono<Long> publish =
    reactiveRedisTemplate.convertAndSend(
        "lab.realtime",
        "hello"
    );
```

Do not subscribe to or return the Mono; watch the Pub/Sub subscriber. Then wire the Mono into a controller and test again. Explain the difference between describing a reactive operation and actually running it.

### Exercise 2 — Reactive listener

Configure `ReactiveRedisMessageListenerContainer`, subscribe to `ChannelTopic("lab.realtime")`, and map messages to a String Flux. Publish from Redis CLI:

```redis
PUBLISH lab.realtime hello
```

Publish both before and after the subscriber connects. Explain why messages sent prior to subscription are not replayed.

### Exercise 3 — SSE

Write endpoint `/lab/events` returning `Flux<ServerSentEvent<String>>`. Open an `EventSource` in a browser and publish a few messages. Close the tab and reopen it. Explain why messages sent while the tab was closed do not reappear automatically.

### Exercise 4 — Slow clients and backpressure

Create a message source faster than the client renders. Compare `onBackpressureLatest` with a bounded buffer. Describe which data types allow dropping (e.g., continuous sensor readings) and which must never be dropped (payment commands).

## 32. Hands-On Exercises: Streams and Acknowledgments

### Exercise 5 — Creating a Stream and group

```redis
XGROUP CREATE lab:orders lab-workers 0 MKSTREAM
XADD lab:orders * eventId evt-1 type CREATED
XADD lab:orders * eventId evt-2 type PAID
```

Have a consumer read:

```redis
XREADGROUP GROUP lab-workers worker-A COUNT 2 STREAMS lab:orders >
```

Inspect PEL:

```redis
XPENDING lab:orders lab-workers
```

ACK a real ID returned by Redis:

```text
XACK lab:orders lab-workers <ID>
```

Verify the PEL shrinks while Stream entries remain.

### Exercise 6 — From record Flux to ACK

Write a `Mono<Void>` handler simulating asynchronous work. Use `concatMap` to process each record and `then(acknowledge(...))` to ACK after handler success. Inject an intentional error into the handler. Observe that the failed entry stays pending.

### Exercise 7 — Crash recovery

Have `consumer-A` read a message without ACKing. Start `consumer-B` and read new messages with `>`. Confirm `A`'s message does not appear on `B`. Once idle time passes, run `XAUTOCLAIM` or `XCLAIM`, reprocess, and ACK.

### Exercise 8 — Idempotency

Simulate:

```text
Handler updates DB successfully.
Worker crashes before XACK.
Recovery redelivers message.
```

Design a unique key on `eventId` inside the database transaction. Explain why successful completion of a reactive handler method does not guarantee Redis `XACK` succeeded if the process crashes between steps.

### Exercise 9 — Processing order

Create three events sharing one `orderId` with increasing sequence numbers. Compare high-concurrency `flatMap` against `concatMap`. Propose adding a `version` column in the database so stale events cannot overwrite newer state.

### Exercise 10 — Resuming SSE by Stream ID

Append Stream entries and build SSE events with `id = record.getId().getValue()`. When a client reconnects with its last ID, read entries strictly newer than that ID. Discuss handling already-trimmed IDs and the transition race into the live feed.

## 33. Self-Assessment

1. Do WebFlux/Reactive Redis automatically make Pub/Sub messages durable?
2. Why might a `Mono<Long>` created by `convertAndSend` not send a Redis command yet?
3. Which Redis feature does `ReactiveRedisMessageListenerContainer` target?
4. Why does SSE `Last-Event-ID` not automatically replay Pub/Sub messages?
5. Does Reactor backpressure force Redis Pub/Sub publishers to stop emitting?
6. Why avoid `.block()` on the Netty event-loop?
7. How do `XADD` and `PUBLISH` differ in storage behavior?
8. When does `XREADGROUP ... >` place a message into the PEL?
9. Why does `XACK` not delete the original entry from the Stream?
10. Why is a shared consumer group unsuitable for broadcasting every event to every SSE client?
11. When a worker crashes before ACK, what mechanism recovers the message?
12. What risk does `ReadOffset.latest()` introduce during polling gaps?
13. Why can `flatMap` lose effective business ordering?
14. When a database commits and Redis ACK fails, what problem does idempotency solve?
15. If a Stream was trimmed before a consumer backfills, how should the client/server respond?
16. Can you declare a `Flux` bean without subscribing and expect a background worker to run?
17. Why separate transport retries from business-logic error retries?
18. If a producer appends to a Stream and publishes to Pub/Sub with two separate commands, what failure windows exist?
19. How do classic Pub/Sub and sharded Pub/Sub differ at the Redis Cluster level?
20. What approach should a system requiring guaranteed delivery choose over raw Pub/Sub?

## 34. Takeaways

- **Spring WebFlux and Reactive Redis** provide an asynchronous I/O model; **Pub/Sub and Streams** determine event delivery semantics.
- Pub/Sub fits real-time signals for online subscribers; **no backlog, ACK, or replay**.
- Streams store ID-indexed entries; consumer groups track delivered messages in **PEL**, and consumers must **`XACK` after processing succeeds**.
- With Reactor, `Mono`/`Flux` require real subscriptions. Controllers should return Publishers; background workers need explicit lifecycles and `Disposable` management.
- `ReactiveRedisMessageListenerContainer` serves Pub/Sub streams; `ReactiveStreamOperations`/`StreamReceiver` serve Streams.
- SSE over Pub/Sub does not automatically support resume. For `Last-Event-ID` backfill, store a log like Streams and manage retention/offsets.
- **Java-side backpressure does not force Redis Pub/Sub to wait for slow clients**. Choose buffer, drop, coalesce, disconnect, or switch to a retained log.
- WebFlux must not run blocking Redis/JDBC calls on the event-loop; isolate legacy blocking code and bound resources.
- Stream consumer groups **distribute work**, rather than broadcasting to every browser. Independent groups maintain independent progress.
- **`XACK` and business commits are not automatically atomic across Redis and databases**. Idempotency, outboxes, and recovery are essential for critical workflows.
- Readers fetching only new messages never pick up another worker's pending entries. Use `XPENDING`, `XCLAIM`, or `XAUTOCLAIM` for recovery.
- Be cautious with `latest()` offsets, `flatMap` concurrency, cancellations, and retention to avoid missing or misordering events.
- In Redis Cluster, verify hash slots for multi-Stream keys and driver support for classic/sharded Pub/Sub.
- Guide architecture with one first question: **"Does this message only need real-time delivery, or must it survive failures and be replayed?"**

### Official references

- [Spring Framework — Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Framework — WebFlux Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Data Redis — Redis Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Data Redis — Reactive RedisMessageListenerContainer API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/listener/ReactiveRedisMessageListenerContainer.html)
- [Spring Data Redis — StreamReceiver API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/stream/StreamReceiver.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/)
- [Redis — XREAD](https://redis.io/docs/latest/commands/xread/)
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/)
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/)
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/)
