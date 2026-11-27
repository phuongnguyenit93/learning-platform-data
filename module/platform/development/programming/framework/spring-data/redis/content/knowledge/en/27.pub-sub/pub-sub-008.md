# Message Loss When a Subscriber Disconnects

In **Spring Data Redis**, Redis Pub/Sub is commonly used to broadcast real-time notifications between applications: one service emits an order-change event, and other services subscribed to the channel receive the notification and react. This approach is simple and low-latency, yet carries a crucial limitation: **Redis Pub/Sub does not store messages to replay for disconnected subscribers**.

If a subscriber loses network connectivity, stops for a new release deployment, has not yet finished subscribing to the channel, or fails to process a message, events emitted during that window can be **permanently lost for that subscriber**. Reconnecting only restores receiving **new messages**; it creates no backlog to catch up on.

This lesson examines Pub/Sub delivery limits, windows where messages are easily dropped in Spring Data Redis, how to observe and test them, and alternative designs when the business genuinely needs every event processed.

## 1. Pub/Sub is a live notification channel, not a durable queue

Redis Pub/Sub has two roles:

- **Publisher:** sends content to a channel using the `PUBLISH` command.
- **Subscriber:** subscribes to a channel via `SUBSCRIBE` or a channel pattern via `PSUBSCRIBE` and receives messages while connected and subscribed.

Example:

```text
                    Redis Pub/Sub
                          |
           PUBLISH orders.events.v1
                          |
            +-------------+-------------+
            |             |             |
         App A          App B          App C
        SUBSCRIBE      SUBSCRIBE      DISCONNECTED
            |             |             |
       Receives event Receives event  Does not receive
                                      |
                                  Reconnects
                                      |
                                Receives only events
                                published after
                                re-subscribing
```

Redis Pub/Sub does not maintain a per-subscriber queue, has no durable message IDs, has no business processing acknowledgments, and has no "re-read from last position" mechanism like an event log system.

The core property is **at-most-once delivery under the Pub/Sub model**: once Redis broadcasts a message, Redis Pub/Sub will not automatically re-send it if a subscriber missed it or failed to handle it. In practice, an application might re-publish events via its own logic and cause duplicates, yet that is **not managed redelivery by Redis Pub/Sub**.

### Quick comparison table

| Property | Redis Pub/Sub |
|---|---|
| Real-time notifications to connected subscribers | Yes |
| Stores messages for offline subscribers | No |
| Re-read by message ID or offset | No |
| Confirm successful processing via ACK | No |
| Track list of pending messages | No |
| Redis auto-resends when callback fails | No |
| Used for "something just changed" notifications | Suitable |
| Used as sole source for non-lossy business flows | Unsuitable |

A channel can have multiple online subscribers. Each subscriber can receive the same message, but that does not make the message retained data once all subscribers leave.

## 2. Scenario of message loss when a subscriber is offline

Suppose `notification-service` is subscribed to `orders.events.v1` to update an order status table:

```text
Time         Publisher                  Subscriber
---------------------------------------------------------------
10:00:00     PUBLISH order-100:CREATED   Connected -> receives
10:00:05     PUBLISH order-100:PAID      Connected -> receives
10:00:10     --                          Lost Redis connection
10:00:12     PUBLISH order-100:PACKED    Offline -> lost
10:00:15     PUBLISH order-100:SHIPPED   Offline -> lost
10:00:20     --                          Reconnected
10:00:21     PUBLISH order-100:DELIVERED Online -> receives
```

After reconnecting, the subscriber sees the sequence:

```text
CREATED -> PAID -> DELIVERED
```

It **does not automatically receive `PACKED` and `SHIPPED`**. If the application uses Pub/Sub only to wake a worker that reads the latest state from the database, missing two intermediate notifications may be acceptable when a catch-up sync path exists. However, if each message means "execute one payment", "deduct inventory once", or "send a mandatory email", losing a message is a serious business bug.

Distinguish clearly:

- **Current state:** often you only need to know the order is now `DELIVERED`.
- **Mandatory events:** some workflows must process every individual event, even if the final state has already moved on.

Pub/Sub fits the first category when an authoritative data store can be queried again.

## 3. Try it immediately with Redis CLI

You can reproduce this on a test Redis instance without writing any Java.

### Terminal A: subscribe to the channel

```bash
redis-cli SUBSCRIBE orders.events.demo
```

Terminal A enters channel-listening mode. When a publisher sends, terminal A prints the message.

### Terminal B: publish an event while A is online

```bash
redis-cli PUBLISH orders.events.demo "order-1:CREATED"
```

Terminal A receives `order-1:CREATED`. The integer returned by `PUBLISH` reflects how many subscribers Redis counted as receiving the message per command semantics and current topology; **it is not the number of successful business executions**.

### Stop the subscriber

In Terminal A, press `Ctrl+C` to exit `redis-cli SUBSCRIBE`. Then Terminal B publishes more messages:

```bash
redis-cli PUBLISH orders.events.demo "order-1:PAID"
redis-cli PUBLISH orders.events.demo "order-1:SHIPPED"
```

When no matching subscribers remain, Redis still accepts the publish commands. Pub/Sub **builds no backlog** for the terminal that just exited.

### Re-subscribe

Terminal A runs again:

```bash
redis-cli SUBSCRIBE orders.events.demo
```

A **does not receive** the two earlier `PAID` and `SHIPPED` messages. When Terminal B publishes a new one:

```bash
redis-cli PUBLISH orders.events.demo "order-1:DELIVERED"
```

A will receive `DELIVERED`.

This is a design characteristic of Redis Pub/Sub, not a bug in Spring Boot configuration, the Lettuce driver, or `MessageListener` handling.

## 4. Integrating Redis Pub/Sub with Spring Data Redis

Spring Data Redis supports channel subscriptions via `RedisMessageListenerContainer`. The container manages establishing subscriptions and delivering messages to configured `MessageListener` instances.

Example Spring Boot dependencies for Redis:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Illustrative Redis connection configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

For production environments, configure host, TLS, credentials, timeouts, and topology matching your infrastructure; do not put secrets into source code.

### 4.1. Subscriber with RedisMessageListenerContainer

```java
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisPubSubConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(RedisPubSubConfiguration.class);

    @Bean
    public MessageListener orderEventListener(
            OrderEventHandler handler) {

        return (Message message, byte[] pattern) -> {
            String payload = new String(
                    message.getBody(),
                    StandardCharsets.UTF_8);

            // Handler processes according to the app's payload contract.
            handler.onNotification(payload);
        };
    }

    @Bean
    public RedisMessageListenerContainer messageListenerContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener orderEventListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                orderEventListener,
                new ChannelTopic("orders.events.v1"));

        // Log callback errors; there is no Pub/Sub ACK for replay.
        container.setErrorHandler(error ->
                log.error("Redis Pub/Sub listener failed", error));

        return container;
    }
}
```

Handler interface:

```java
public interface OrderEventHandler {
    void onNotification(String payload);
}
```

If the handler throws an exception, the error handler can log it, yet **Redis does not put that message back into a queue**, because Pub/Sub has no durable queue. Logging successfully also does not bring back a lost message.

The container manages subscriptions during the Spring lifecycle and connection recovery per driver/configuration settings, yet **reconnect does not equal replay**.

### 4.2. Publisher with StringRedisTemplate

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long publish(String payload) {
        Long subscribers =
                redis.convertAndSend("orders.events.v1", payload);
        return subscribers == null ? 0L : subscribers;
    }
}
```

`convertAndSend` sends `PUBLISH` using the template's serializer. With `StringRedisTemplate`, the illustrative payload is serialized as a string.

**The return value does not confirm business processing.** Redis may include a subscriber in the recipient count, yet the application may close the connection immediately afterward, fail in its callback, crash, or fail to commit data. In Redis Cluster, counting subscribers also depends on topology and node processing scope. Never treat a positive number returned by `PUBLISH` as proof that "every consumer finished processing."

### 4.3. Consistent serialization between publisher and subscriber

`Message.getBody()` provides byte data. If the publisher emits JSON, the subscriber can deserialize JSON according to a versioned schema. If the publisher uses Java/JDK serialization or another serializer, reading UTF-8 strings as in the example will not work properly.

The communication contract should define:

- Channel name and version, e.g., `orders.events.v1`.
- Encoding and format, e.g., UTF-8 JSON.
- Required fields and payload version.
- Distinction between notifications and source data.
- ID format, tenant, and security requirements.

A message received cleanly at the TCP layer can still fail processing if the payload is incompatible.

## 5. When can a Spring subscriber miss messages?

Message loss does not happen only when the Redis server crashes. Message-loss windows can occur during normal operations:

| Situation | What can happen | Why is the message lost? |
|---|---|---|
| App starts up before subscription finishes | Publisher emits before subscription takes effect | Redis does not buffer for unsubscribed receivers |
| Rolling deployment | Old instance stops while new instance is not ready | A gap exists with no listener from that instance |
| Temporary Redis disconnect | Container is attempting to reconnect | Messages published during the outage are not replayed |
| Network partition or failover | Subscription drops and re-establishes | Redis Pub/Sub has no offset for catching up |
| Slow consumer | Client buffer grows, may be disconnected past limit | Unprocessed messages have no durable ACK/retry |
| Callback throws exception | Payload was delivered/received, but handler failed | Redis is unaware of business processing status |
| Process crashes after receiving | Handler did not finish side effects | No mechanism to reclaim the message after restart |
| Subscriber uses wrong channel or serializer | Fails to receive or decode messages | Wrong subscription/contract, no automatic replay |

### Startup gap

An application may already report HTTP "healthy" before listeners finish subscribing. If publishers emit immediately during this window, events can be missed by that instance.

Do not treat Spring application startup events, bean creation, or an open Redis TCP connection as proof that **subscriptions are ready on the exact channels**. If business workflows require strict startup readiness, establish real readiness checks supported by your library, infrastructure, and architecture.

Even with real startup readiness, **subsequent disconnect windows still cannot be recovered** by Pub/Sub alone.

### Reconnect gap

Suppose:

```text
T0  Subscription is active.
T1  Connection drops.
T2  Publisher sends event A.
T3  Publisher sends event B.
T4  Listener container reconnects and re-subscribes to the channel.
T5  Publisher sends event C.
```

The subscriber can receive C, yet misses A and B. "Retry reconnecting until it works" only restores online status at T4; it cannot reach back to events between T1 and T4.

## 6. Pub/Sub has no processing ACK and no replay

In an ACK-based queue system, a consumer typically receives a message, processes it, and acknowledges completion; if the consumer stops before ACKing, the message can be redelivered. Redis Pub/Sub **has no such ACK step**.

```text
Pub/Sub:
Publisher -> Redis -> Subscriber -> Handler
                       |
                       +-- handler error
                       |
                       +-- Redis does not know and does not resend

ACK-based queue/stream:
Publisher -> Durable log -> Consumer -> Handler -> ACK
                 |                    |
                 |                    +-- failure before ACK
                 +-- can retain message for reprocessing
```

You cannot work around the lack of ACKs by wrapping the callback in `try/catch` and "re-throwing" so Redis resends. Throwing can assist logging or application error policies, yet **Redis Pub/Sub has no un-ACKed queue**.

### Distinguish published, received, and processed

Separate three states:

1. **Published:** Redis accepted the `PUBLISH` command.
2. **Received:** the subscriber connection received and passed the message to the client/handler.
3. **Processed:** business logic completed its work, such as writing to a database or sending a notification.

A successful `PUBLISH` result proves neither state 2 nor state 3 for any subscriber. A `"Received message"` log also does not prove state 3 if the handler has not finished yet.

## 7. When is message loss acceptable?

Not every Pub/Sub channel needs message-queue reliability. Redis Pub/Sub remains an excellent fit for notifications that can be missed while the system stays correct via another sync path.

Examples where losing some notifications is usually acceptable:

- UI notification "new data available" prompting clients to call an API for current state.
- Wake-up signal for a worker that **already polls the data source periodically**.
- Dashboard updates that refresh on a timer.
- Cache invalidation with a short enough TTL and reconciliation; missed signals bound staleness by policy.
- Non-critical instantaneous status notices where users can refresh to view current state.

Examples where you should **not** use Redis Pub/Sub as the sole channel:

- Deducting inventory exactly once per order.
- Sending mandatory invoices after payment.
- Processing refunds or financial settlements.
- Executing workflows that require every step event.
- Building audit trails or compliance logs.
- Data synchronization where one lost message causes permanent drift.

**Principle:** If missing an event still allows the system to self-heal from a source of truth, Pub/Sub can act as a "fast signal." If **every single event** must be processed with an audit trail of completion, you need a system that persists messages and consumption state.

## 8. Mitigations when still using Pub/Sub

For notification-only channels, you can improve resilience with the measures below. They **do not turn Pub/Sub into a durable queue**, yet help the system self-repair when signals are missed.

### 8.1. Subscriber re-reads current state on reconnect

Instead of treating the payload as a mandatory command, the publisher sends the ID of the changed entity:

```json
{
  "eventId": "evt-00981",
  "eventType": "ORDER_CHANGED",
  "orderId": "o-1001",
  "version": 42
}
```

The subscriber receives the notification and queries the source database/API for the current state. Upon reconnect, the subscriber actively triggers a **state sync pass**, rather than expecting Redis to return old events.

```text
Online subscribe  --------> Receive notification -> read latest state
       |
       +-- disconnected
       |
       +-- reconnect ---------> Re-read state/snapshot from source
                                |
                                +-- Resume receiving new notifications
```

This suits caches or **rebuildable** projections. However, if the source is huge, you cannot scan everything on every reconnect. You will need checkpoints, version/update timestamps, change indexes, or a durable log to sync incrementally.

### 8.2. Periodic sync to repair missed updates

Run a reconciliation schedule independent of Pub/Sub:

```text
On notification:
  -> quickly refresh relevant record

Every few minutes:
  -> reconcile state against source of truth
  -> repair missing or stale records
```

When a notification is missed, reconciliation brings the system back to the right state within a committed time bound. This does not recover **individual lost events**; it recovers the **latest state** or state derivable from the source.

### 8.3. Use versions to detect stale data

Suppose the source stores `order.version = 42`, and the notification payload also carries `version = 42`. A subscriber holding version 38 notices it needs to reload state. Versions prevent slow updates from overwriting newer state.

Yet **checking versions only when a new notification arrives is not enough**: if all notifications are missed and there is no reconciliation/polling, the subscriber will never know a newer version exists. Versioning must be paired with active checks or a durable log.

### 8.4. Enable monitoring for reconnects and offline gaps

Record disconnect timestamps, subscription recovery timestamps, and listener error counts. If an offline window crosses a threshold, trigger reconciliation or alert.

Monitoring disconnects helps **detect data-loss risk**, though it does not create messages to re-read.

## 9. Hybrid pattern: persist events first, use Pub/Sub to wake consumers

When you prioritize fast reaction time without depending on ephemeral messages, design two paths:

1. **Durable path:** write the event to Redis Streams or a persistent event store/queue.
2. **Fast path:** publish a Pub/Sub hint merely saying "new record available."
3. When a subscriber receives the notification, it reads the **durable source** from its checkpoint. If Pub/Sub is missed, a polling/reconnect loop still catches up.

```text
Business service
       |
       v
Write event to durable log / stream
       |
       +----------------------------+
       |                            |
       v                            v
PUBLISH "new event"            Stream stores event
       |                            |
       v                            |
Online subscriber                   |
       |                            |
       v                            |
Read stream from checkpoint <-------+
       |
       v
Process and record position/ACK
```

The critical detail is **write order**: in a log-backed system, the event must be durably persisted **before** the "event available" notification is published. If you publish the notification first and try to persist afterward and crash in between, subscribers may wake up with no durable data to process.

Still, writing to a business database and then writing to a Redis stream in two separate operations **does not create a single atomic transaction**. When events must originate atomically from a database transaction, consider a transactional outbox or another reliable sync mechanism.

## 10. Redis Streams as the option when catch-up is needed

**Redis Streams** is a different data structure from Pub/Sub. Each event is appended with `XADD`, receives a stream ID, and stays in the stream until deleted or trimmed by policy. Consumers can read from a known position, or use **consumer groups** to coordinate processing and ACKs.

### 10.1. Comparing Pub/Sub and Streams

| Property | Redis Pub/Sub | Redis Streams |
|---|---|---|
| How to emit | `PUBLISH` | `XADD` |
| Messages retained for re-reading | No | Yes, for the lifetime of the stream entry |
| Event ID | None at Pub/Sub infrastructure level | Has stream ID |
| Processing ACK | No | Yes, with consumer groups via `XACK` |
| Pending tracking | No | Has Pending Entries List per consumer group |
| Consumer offline then returns | Misses messages emitted while offline | Can re-read if entries remain and offsets/groups are managed properly |
| Delivering to multiple independent groups | Each online subscriber receives | Each consumer group tracks its own progress |
| Duplicate possibility on recovery | No internal redelivery | Possible; requires idempotency |
| Retained forever without config | No | No: retention/trim, memory, and persistence govern it |

Redis Streams is better suited for events that must be fully processed, yet **does not automatically guarantee once-only processing**. A consumer can execute side effects successfully and crash before `XACK`; when the message is reprocessed, side effects can repeat without idempotency.

### 10.2. Appending an event to a stream

```bash
redis-cli XADD stream:orders:v1 '*' \
    eventId evt-00981 \
    type ORDER_PAID \
    orderId o-1001 \
    version 42
```

Redis returns an ID formatted as `<milliseconds>-<sequence>`, e.g., `1780000000000-0` (illustrative value). The message remains a stream entry until an explicit delete or trim operation removes it.

Unlike `PUBLISH`, consumers do not need to be online **at the exact moment of `XADD`** to read the event.

### 10.3. Creating a consumer group and reading events

In Redis CLI:

```bash
redis-cli XGROUP CREATE stream:orders:v1 order-workers 0 MKSTREAM
```

The `0` argument instructs the group to start from the beginning of the current stream. Using `$` when creating the group excludes entries written before group creation from the group's "new events" stream; choose the starting position according to business needs.

Worker A reads new events:

```bash
redis-cli XREADGROUP GROUP order-workers worker-a \
    COUNT 10 BLOCK 2000 STREAMS stream:orders:v1 '>'
```

Components:

- `GROUP order-workers worker-a`: `worker-a` belongs to consumer group `order-workers`.
- `COUNT 10`: reads up to 10 events in one batch.
- `BLOCK 2000`: waits up to ~2 seconds if no new events exist.
- `STREAMS ... >`: requests new events not yet delivered to any consumer in the group per consumer group semantics.

Process the event successfully, then ACK:

```bash
redis-cli XACK stream:orders:v1 order-workers 1780000000000-0
```

**ACK must happen after business side effects complete per the contract.** If you ACK first and the application crashes, the stream no longer knows the event is awaiting processing, even though business logic never ran.

### 10.4. Consumer crashes and the Pending Entries List

When a consumer group delivers an event to a worker that has not yet called `XACK`, the event belongs to the group's **pending** entries. Inspect with:

```bash
redis-cli XPENDING stream:orders:v1 order-workers
```

When a worker dies, another worker can reclaim pending events that have been idle long enough using mechanisms such as `XAUTOCLAIM`:

```bash
redis-cli XAUTOCLAIM stream:orders:v1 order-workers worker-b \
    60000 0-0 COUNT 100
```

This example targets messages idle for at least 60,000 ms; consumer `worker-b` takes over ownership of matching events.

Key detail: if worker A already performed the side effect and died before ACKing, worker B can reprocess the event. Hence, **using an event ID or business operation ID for idempotent processing** is mandatory when duplicate effects are unacceptable.

### 10.5. Do Streams preserve events in every situation?

No. Distinguish "having persistence and replay mechanisms" from "100% absolute durability":

- `XTRIM` or `XADD MAXLEN` can evict older events before consumers finish reading them.
- Stream retention policies, memory limits, and cleanup operations must match how long subscribers may be offline.
- Redis persistence, replication, and failover affect durability after crashes.
- Reading from the wrong group position, ignoring pending entries, or ACKing too early can still lose business operations.
- A consumer group splits work among consumers **within the same group**, rather than giving every consumer in the group its own copy. If independent systems must all process every event, typically create separate groups.

Therefore, when replacing Pub/Sub with Streams, design **retention, offsets, pending recovery, ACKs, idempotency, and Redis durability** together to match your business SLOs.

## 11. Spring Data Redis Streams example: producer and consumer

Spring Data Redis supports `StreamOperations` via `RedisTemplate`/`StringRedisTemplate`. Example producer persisting events before any consumer reads:

```java
import java.util.Map;

import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DurableOrderEventPublisher {

    private static final String STREAM = "stream:orders:v1";

    private final StringRedisTemplate redis;

    public DurableOrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId appendOrderPaid(
            String eventId,
            String orderId,
            long version) {

        return redis.opsForStream().add(
                STREAM,
                Map.of(
                        "eventId", eventId,
                        "type", "ORDER_PAID",
                        "orderId", orderId,
                        "version", Long.toString(version)));
    }
}
```

`RecordId` indicates the stream ID returned when `XADD` succeeds. A producer may still need a separate **business event ID** to handle retries/duplicates, because appending an event twice produces two distinct stream IDs.

A consumer can use a pre-created group, read, and ACK after the handler finishes:

```java
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamConsumer {

    private static final String STREAM = "stream:orders:v1";
    private static final String GROUP = "order-workers";

    private final StringRedisTemplate redis;
    private final DurableOrderHandler handler;

    public OrderStreamConsumer(
            StringRedisTemplate redis,
            DurableOrderHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public void pollOnce(String consumerName) {
        List<MapRecord<String, Object, Object>> records =
                redis.opsForStream().read(
                        Consumer.from(GROUP, consumerName),
                        StreamReadOptions.empty()
                                .count(10)
                                .block(Duration.ofSeconds(2)),
                        StreamOffset.create(
                                STREAM,
                                ReadOffset.lastConsumed()));

        if (records == null || records.isEmpty()) {
            return;
        }

        for (MapRecord<String, Object, Object> record : records) {
            // Handler must support idempotent processing by eventId.
            handler.handle(record.getValue());

            // ACK only after processing succeeds.
            redis.opsForStream().acknowledge(
                    STREAM, GROUP, record.getId());
        }
    }
}
```

Handler interface:

```java
import java.util.Map;

public interface DurableOrderHandler {
    void handle(Map<Object, Object> payload);
}
```

This example illustrates synchronous polling APIs. In Spring Data Redis, you can use `StreamMessageListenerContainer` or corresponding reactive APIs to manage the read loop instead of building your own loop. Regardless of API choice, the principles stay the same:

1. The group must be created once (or idempotently) before reading.
2. New events are fetched at the group's offset.
3. The handler completes side effects before ACKing.
4. Include a path to recover **pending entries on crashes**, not just a loop reading new events.
5. Handle deserialization/validation and Redis errors per your retry policy.
6. Prevent duplicate side effects when an event is redelivered.

This snippet **does not yet implement pending recovery, retry policies, or dead-letter handling**; add those when building reliable production workflows.

## 12. Pub/Sub + Streams: fast notifications, processing backed by a durable log

Some systems already use Pub/Sub for fast reaction and do not want to discard it entirely. One approach is:

1. Producer runs `XADD` to append the event to a stream.
2. Producer runs `PUBLISH` with a short notification containing the ID/stream name after the append succeeds.
3. Subscriber receives the Pub/Sub hint and triggers reading the stream from its checkpoint.
4. A periodic poll still reads the stream even if no notification arrives.
5. After reconnecting, the subscriber resumes from its group/checkpoint position.

```text
Producer
   |
   +-- XADD stream:orders:v1 -------------> Event stored in stream
   |                                             |
   +-- PUBLISH orders.notify.v1                  |
                   |                             |
                   v                             |
             Online subscriber                   |
                   |                             |
                   +-- Wake up ------------------+
                                                 |
                                                 v
                                           XREADGROUP / XACK
                                                 |
                                           Process business logic

Offline subscriber:
   Misses notification
   -> once back online / polling, still reads event kept in stream
```

**Notifications are only a latency optimization; the stream is the source of recovery.** If Pub/Sub is missed, the poll loop must still run. If polling only triggers upon receiving a notification, the architecture can still stall after a single missed notification.

### Avoiding a gap between "subscribe" and "catch-up"

A safe design handles startup races. If using notifications alongside a separate cursor, avoid the sequence:

```text
1. Drain the entire backlog.
2. Only then call SUBSCRIBE.
```

An event arriving between steps 1 and 2 may not be processed until the next poll. To avoid depending on exact subscription timing, keep an offset-based stream read loop active or sync backlog from the checkpoint after the subscription is active.

When using consumer groups, Redis Streams itself already supports blocking reads for new events; in many cases you do not need an extra Pub/Sub channel just to wake consumers. Add one only if you have measured a clear benefit and accept the operational cost of maintaining both mechanisms.

## 13. Transactional outbox when events are tied to database changes

Suppose an application processes a payment:

```text
1. UPDATE orders SET status = 'PAID'
2. PUBLISH "ORDER_PAID" via Redis Pub/Sub
```

There is a dangerous gap: the database can commit successfully, then the process crashes before `PUBLISH`. The event is never emitted even when subscribers are always online. This is a **dual-write** failure, not merely a subscriber disconnect failure.

Even if you push the event into a stream via a separate Redis command after the database commits, the dual-write gap remains:

```text
DB COMMIT succeeds
     |
     +-- process crashes before XADD
     |
     v
Stream has no event, nothing to replay
```

A common solution is the **transactional outbox**:

```text
Inside the same database transaction:
   UPDATE orders ...
   INSERT INTO outbox_events(..., status='NEW')
              |
              v
         DB COMMIT
              |
              v
     Outbox dispatcher reads event
              |
              v
       XADD Redis Stream
              |
              v
     Mark outbox event as sent
              |
              v
   Consumer processes + idempotency + ACK
```

Because the event is saved inside the source transaction, a durable record remains after commit for the dispatcher to retry. However, the dispatcher could send the event and crash before marking it sent, so **duplicate emissions can occur**. Consumers need idempotency keyed by the business event ID.

If you do not want to use Redis Streams, the outbox can publish to another durable broker depending on your organization's throughput, retention, routing, ordering, and operational needs.

## 14. Never treat Redis Pub/Sub as an exactly-once delivery system

Three frequently confused concepts:

- **At-most-once:** no automatic retries; missing one delivery means the message is gone for that subscriber.
- **At-least-once:** retries/redeliveries increase processing odds; consumers must tolerate duplicates.
- **Exactly-once effect:** the business side effect occurs once; this is an end-to-end requirement usually achieved via idempotency or transactions/data constraints.

Redis Pub/Sub targets **at-most-once delivery**, not at-least-once. Redis Streams with consumer groups, pending recovery, and ACKs can support **at-least-once processing**, yet do not automatically guarantee once-only side effects in external databases.

### Example: sending email after payment

If a consumer re-receives `ORDER_PAID` after a crash:

```text
Attempt 1: sends email successfully
           crashes before ACK

Attempt 2: receives pending message again
           sends email a second time if eventId is not checked
```

Store an idempotency key or delivery status per your contract in a system capable of deduplicating. That is why **switching from Pub/Sub to Streams solves message recovery, yet you still must safeguard business correctness**.

## 15. When is a dedicated message broker needed?

Redis Streams is viable for many workloads, yet not every requirement should be solved with Redis.

Consider RabbitMQ, Kafka, or a managed message queue service if your system requires:

- Long retention or time-based event replay.
- Many independent consumer groups at high throughput.
- Complex routing, dead-letter queues, delayed retries, and rich consumer management.
- Dedicated operational SLAs for durability, replication, and auditing.
- High-volume event streams, partitioning, per-partition ordering, and partition-based scale-out.
- Isolating queue resources from Redis instances serving caches, sessions, or hot keys so one workload cannot impact another.

SLA, latency, throughput, infrastructure cost, and operational skills should all be compared. No broker guarantees once-only business effects merely because it supports ACKs; idempotency and business transactions remain essential.

## 16. Monitoring Pub/Sub health in Spring

Because Pub/Sub has no queue depth or pending offset, monitoring must rely heavily on **connection state, timing, and consumer-side effects**.

| Metric/signal | Question to answer |
|---|---|
| Subscriber connected/ready | Is the listener subscribed to the right channels? |
| Reconnect count | Are Redis connections dropping frequently? |
| Offline duration | During what window were events at risk of being missed? |
| Publisher count | How many notifications did the app attempt to publish? |
| Subscriber receive count | How many notifications did the app receive? |
| Handler success/error count | Are received messages failing during processing? |
| Last received timestamp | Has the subscriber gone unusually silent? |
| Business event gap/version lag | Is receiver state lagging or missing updates vs. source? |
| Reconciliation repairs | How many records had to be re-synced? |
| Redis disconnected clients / output buffers | Are slow subscribers or weak networks getting disconnected? |

**Do not directly subtract `handler success count` from `PUBLISH return count` and assume the difference equals lost events.** Channel subscriber counts fluctuate, a single message can go to multiple clients, and measurements in Redis Cluster are complex.

### Redis CLI for investigation

```bash
redis-cli PUBSUB CHANNELS
redis-cli PUBSUB NUMSUB orders.events.v1
redis-cli INFO clients
redis-cli INFO stats
```

These commands reflect point-in-time status within the queried Redis node/topology scope. They **do not provide a list of messages lost while offline**.

For application subscriptions, add per-instance metrics and logs recording subscription start times, reconnect counts, and reconciliation status.

Note: Redis Pub/Sub buffers messages for connected clients, yet this is **not a durable queue**. An overly slow subscriber can cause Redis to close its connection due to output buffer limits; unprocessed events still have no ACK for replay.

## 17. Evaluating with controlled disconnect tests

A feature described as "auto-reconnect" must be verified with real failure scenarios, because the business requirement is not just restoring connections—it is **recovering missed data**.

### Scenario A — Stopping the subscriber while the publisher keeps publishing

1. Start publisher and subscriber in a test environment.
2. Publish a message with `eventId = e1` and confirm the subscriber receives it.
3. Stop the subscriber or sever the subscriber's Redis network connection.
4. Publish `e2`, `e3`, and `e4`.
5. Restart the subscriber.
6. Publish `e5`.
7. Observe that the subscriber only receives messages while its subscription is actually active, and `e2–e4` are not replayed by Pub/Sub.

### Scenario B — Callback fails after receiving

1. Keep the subscriber online.
2. Send a valid payload while configuring the handler to simulate failure after starting execution.
3. Observe `MessageListener` or the handler throwing an exception.
4. Confirm Redis Pub/Sub does not automatically redeliver the event via an ACK mechanism.

Verify the business outcome, not just callback logs.

### Scenario C — Deploying two versions

1. Instance A runs the old version; instance B runs the new version.
2. Publish messages while A closes its subscription and B has not finished subscribing.
3. Check whether an event-reception gap occurs.
4. If the system uses reconciliation/Streams, confirm B still recovers accurate state once ready.

### Scenario D — Subscriber slower than publisher

1. Have the publisher emit messages faster than the subscriber can process them.
2. Monitor the listener's thread pool/queue, client buffers, and connection errors.
3. Check when disconnects occur and whether events go unprocessed.
4. Verify that fallback source reads do not depend on receiving every individual message.

### Scenario E — Recovery using Streams

1. Create a stream and consumer group.
2. Run `XADD` for several events while the consumer is offline.
3. Start the consumer and read events retained in the stream.
4. Crash the consumer after performing side effects and before `XACK`.
5. Recover pending entries on another consumer.
6. Confirm idempotency logic prevents duplicate side effects.

The outcomes of Scenarios A and E demonstrate the fundamental difference between **live-only Pub/Sub** and **Streams with group persistence and replay**.

## 18. Common mistakes

### 18.1. "RedisMessageListenerContainer auto-reconnects, so no messages are lost"

The container restores subscriptions; it does not provide a backlog. Events published during the offline window are still lost in Pub/Sub.

### 18.2. "PUBLISH returns 1, meaning the recipient finished processing"

The return count is not a business ACK. The subscriber may not have processed it yet, may crash, or may fail after receiving.

### 18.3. "When the subscriber fails, throw an exception so Redis re-sends"

Pub/Sub has no callback-exception-driven redelivery. To retry, persist the message and processing state elsewhere.

### 18.4. "Having multiple subscriber replicas means no loss"

Multiple replicas reduce the probability of having **zero** online subscribers, yet do not guarantee any single instance receives every event. If each replica maintains a local projection/cache, an offline instance still holds stale data upon returning.

### 18.5. "Re-sending from the publisher is enough"

The publisher does not know exactly which subscribers succeeded. Retrying without business event IDs/idempotency can cause duplicate side effects.

### 18.6. "Switching to Redis Streams is automatically exactly-once"

Streams provides storage and replay, yet ACKing before or after side effects still creates loss or duplicate cases if designed poorly.

### 18.7. "Creating a consumer group at the end of the stream processes all old events"

Initializing a group with `$` generally skips entries already present at creation time for the new-message stream. Choose the starting offset based on replay/cutover requirements.

### 18.8. "Once ACKed, you can trim the stream freely"

One consumer group ACKing does not mean every other group has processed the entry. Retention must account for the lag of every group needing the data.

### 18.9. "Putting eventId in Pub/Sub prevents loss"

Event IDs enable deduplication, gap detection in some scenarios, and reconciliation, yet do not create a durable copy to recover lost events.

### 18.10. "Redis keyspace notifications are an event log"

Redis keyspace/keyevent notifications also rely on Pub/Sub and are not persisted for offline subscribers. Never use them as an audit log or sole source for mandatory workflows.

## 19. Architectural decision tree

```text
Application needs to receive Redis events?
                   |
                   v
If a subscriber is offline, can notifications be missed?
                   |
             +-----+-----+
             |           |
            Yes          No
             |           |
             v           v
      Redis Pub/Sub    Need durable event storage
      may be suitable      |
             |             v
             |       Redis Streams / broker
             |             |
             |             v
             |       Consumer groups/offsets,
             |       ACK, pending recovery
             |             |
             |             v
             |       Idempotency and retention
             |             |
             +------+------+ 
                    |
                    v
  If a notification is missed, can state be synced from source?
                    |
              +-----+-----+
              |           |
             Yes          No
              |           |
              v           v
       Reconcile/poll   Need a durable event path,
       on reconnect     not just Pub/Sub
              |
              v
       Monitor offline gaps,
       handler errors, and state lag
```

### Suggested approach by problem

| Problem | Baseline approach |
|---|---|
| Notify UI that "catalog changed" so it refreshes | Pub/Sub + state-reading API, with periodic refresh |
| Invalidate caches across multiple services with bounded TTL | Pub/Sub as fast hint + TTL/reconciliation |
| Sync rebuildable projections | Pub/Sub + reconciliation, or stream for efficient catch-up |
| Send mandatory email after payment | Durable queue/stream + ACK/retry/idempotency |
| Process every single order event reliably | Stream/event log + retention and checkpoints |
| Emit messages tied to database transactions | Outbox + dispatcher + durable messaging |
| Need event history for auditing | Durable event store with proper retention/audit, not plain Pub/Sub |

## 20. Conclusion

In Spring Data Redis, **`RedisMessageListenerContainer` does not turn Redis Pub/Sub into a system with message persistence and replay**. It manages listening and subscription recovery; when a subscriber goes offline, messages published during that interval are not re-sent upon reconnection. Likewise, a successful `PUBLISH` or a handler receiving a message never proves that business logic completed.

For **live notifications that can tolerate loss**, Pub/Sub remains simple and effective when the application has a path to read current state, sync upon reconnect, and monitor offline gaps. For **events that must never be lost**, use Redis Streams or a durable message broker with ACKs, pending recovery, retention, and idempotency; when events tie to database changes, consider a transactional outbox to close the dual-write gap.

**Decision rule:** Try shutting down every subscriber while the publisher keeps emitting events. If the system cannot recover correct business state after subscribers return, then **Pub/Sub is insufficient as the sole channel** for that flow.
