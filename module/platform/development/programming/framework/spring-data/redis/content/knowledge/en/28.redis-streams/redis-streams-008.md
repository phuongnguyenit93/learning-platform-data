# Configuring `StreamMessageListenerContainer` in Spring Data Redis

**Redis Streams** lets an application write events to a stream and have one or more consumers process them in record ID order. If a Java application had to manually write `XREAD` or `XREADGROUP` loops and manage threads, connections, offsets, and stopping conditions itself, infrastructure code would quickly become tangled with business logic. **Spring Data Redis** provides `StreamMessageListenerContainer` to organize **polling Redis Streams on background tasks** and dispatching messages to a `StreamListener`.

Configuring the container requires answering more questions than merely connecting to Redis: whether the stream already exists, whether to read directly or through a consumer group, which offset to start at, how many threads to use, how many records to fetch per poll, when to call `XACK`, where messages go when a listener throws an error, and how to recover pending entries after an instance dies.

This lesson presents a complete `StreamMessageListenerContainer` configuration, how to register consumer groups, how to tune operational options, and how to implement practical, retryable message processing.

## 1. Where `StreamMessageListenerContainer` Fits in the System

A producer using Redis Streams might write an order-created event:

```text
Producer (Order Service)
        |
        | XADD orders:events * eventType OrderCreated orderId 42
        v
Redis Stream: orders:events
        |
        | XREAD / XREADGROUP, potentially BLOCKing on each poll
        v
StreamMessageListenerContainer
        |
        | dispatches Record to StreamListener
        v
OrderEventHandler
        |
        +--> business processing
        +--> XACK confirmation (if using consumer group, manual ACK)
```

**The container is not the stream itself nor a separate broker.** It runs inside the Spring process, using Redis connections and an executor to read the stream and invoke callbacks when records arrive.

Components:

| Component | Responsibility |
|---|---|
| `RedisConnectionFactory` | Provides Redis connections via the configured client |
| `StreamMessageListenerContainer<K,V>` | Coordinates asynchronous polling and delivers records to listeners |
| `StreamMessageListenerContainerOptions<K,V>` | Configures batch size, poll timeout, executor, serializers, and error handling |
| `StreamOffset<K>` / `ReadOffset` | Specifies the stream and starting read position |
| `Consumer.from(group, name)` | Identifies the consumer group and consumer identity |
| `StreamListener<K,V>` | Receives and processes each record |
| `Subscription` | Represents a stream-read registration that can be managed or cancelled |
| `StringRedisTemplate.opsForStream()` | Sends `XADD`, `XACK`, or other stream commands as needed |

`StreamMessageListenerContainer` is an imperative-style API, **not** Reactive Redis's `StreamReceiver`. Both support receiving messages, yet their threading, backpressure, and callback models differ.

## 2. “Asynchronous” in the Container Does Not Mean Redis Never Blocks

A common misconception from seeing the name listener container is assuming Redis reads never use blocking commands.

In reality, the container typically runs polling loops with `XREAD` or `XREADGROUP` using the `BLOCK` parameter. Redis can hold the request for a period of time waiting for new messages. The difference is that **the blocking wait runs on the container's background task**, without blocking the application thread handling HTTP requests.

```text
HTTP thread:
  calls service/registers listener -> continues serving HTTP

Container polling task:
  XREADGROUP BLOCK 2000 COUNT 20
           |
           +--> Messages available: read and invoke listener
           |
           +--> 2 seconds elapsed: loop back to next poll
```

Therefore:

- `pollTimeout` controls the **maximum wait duration of a single blocking poll** (depending on the API and how the Redis client sends commands).
- `batchSize` controls the maximum number of records requested in one poll cycle.
- The executor determines the thread resources running reads and callbacks.
- A slow callback can reduce how many messages its polling loop/subscription processes.
- The container must be properly started and stopped to release background tasks and connections.

Do not set a huge `pollTimeout` and expect shutdown or config changes to always react instantaneously. Conversely, an overly short timeout causes excessive empty polls and extra overhead.

## 3. Preparing the Stream and Consumer Group Before Starting

This lesson uses:

```text
Stream key:      orders:events
Consumer group:  orders-workers
Consumer name:   orders-api-1
```

There are two choices: reading the stream **without a group**, or reading **inside a consumer group**. For multi-instance systems that must divide message processing, a consumer group is usually the right choice.

### 3.1. Creating the Group with `redis-cli`

On a test Redis instance:

```bash
redis-cli XGROUP CREATE orders:events orders-workers 0-0 MKSTREAM
```

Meaning:

- `orders:events`: Redis Stream key.
- `orders-workers`: group name.
- `0-0`: the group starts from the beginning of stream history so existing messages can be delivered when consumers read new group messages.
- `MKSTREAM`: if the stream does not yet exist, Redis creates an empty stream.

If `0-0` is replaced with `$`, the group initializes at the **current last ID**, meaning messages that already existed before group creation are generally not delivered as new messages to the group. This is an important initial deployment decision.

If the group already exists, Redis may return `BUSYGROUP`. Preparing the group during application startup or deployment should be **idempotent**, distinguishing “group already exists” from genuine Redis errors—never unconditionally deleting and recreating the group on every startup.

Verify:

```bash
redis-cli XINFO GROUPS orders:events
```

### 3.2. Writing Test Messages

```bash
redis-cli XADD orders:events '*' eventType OrderCreated orderId 42 version 1
redis-cli XADD orders:events '*' eventType OrderPaid orderId 42 version 2
```

Each message gets a Redis-assigned **record ID**, such as `1730000000000-0`. This ID is not `orderId`; it denotes the entry's position in the stream, whereas `orderId` is business data inside the message map.

You can inspect:

```bash
redis-cli XRANGE orders:events - +
redis-cli XLEN orders:events
```

`XLEN` is the number of entries still in the stream, **not** the number of messages awaiting ACK in a group. Confirming with `XACK` also **does not automatically delete entries from the stream**.

## 4. Declaring Dependencies and Core Beans

Assume the Spring Boot application already has a Redis connection and uses `spring-boot-starter-data-redis`. Key classes belong to Spring Data Redis packages:

```java
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainerOptions;
import org.springframework.data.redis.stream.Subscription;
```

In a real environment, `RedisConnectionFactory` is configured by Spring Boot from URI/host/port, TLS, credentials, and pooling if applicable. The container uses this connection factory; **do not create a separate Redis client per message**.

### 4.1. Creating an Executor with Clear Thread Naming

```java
package example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class StreamExecutorConfiguration {

    @Bean("redisStreamExecutor")
    public ThreadPoolTaskExecutor redisStreamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("redis-stream-poll-");

        return executor;
    }
}
```

The numbers 4/8/64 are **illustrative values**, not fixed recommendations. Each subscription may need a long-lived polling task, especially with blocking reads. If there are fewer threads than active subscriptions, some subscriptions will lack a thread to start polling.

For listeners performing heavy business work, separate polling and processing in an appropriate architecture; however, if offloading work to another executor, **do not ACK before that work completes durably**.

## 5. Configuring `StreamMessageListenerContainerOptions`

A typical options configuration:

```java
StreamMessageListenerContainerOptions
        <String, MapRecord<String, String, String>> options =
        StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(2))
                .batchSize(20)
                .executor(redisStreamExecutor)
                .build();
```

Meaning:

| Option | Role | Considerations |
|---|---|---|
| `pollTimeout(Duration)` | Wait duration per Redis poll | Message detection latency and ability to stop/exit the poll loop |
| `batchSize(int)` | Maximum records requested per read | Throughput, batch processing time, unacknowledged message count |
| `executor(TaskExecutor)` | Where polling/callback tasks run | Subscription count, blocking duration, saturation |
| Serializers | How keys, fields, and values are decoded | Must match the producer to avoid wrong strings/bytes |
| Error handling | How read/deserialize/callback errors are captured and handled | Never treat listener failures as successful processing |
| Object mapping/target type | Converts records to Java types when using object records | Schema and converter compatibility |

Exact builder APIs may vary by Spring Data Redis version, yet these choices cover the essential deployment aspects. With `MapRecord<String, String, String>`, producer and listener agree on string fields and values.

### 5.1. Do Not Confuse `batchSize` with an Unacknowledged Message Cap

`batchSize(20)` affects **how many entries are requested per read**, not a Redis-enforced cap of 20 unacknowledged entries across the whole group.

A repeatedly failing handler or a consumer killed mid-flight can make the **Pending Entries List (PEL)** grow over time. Measure and manage the PEL independently of batch size.

### 5.2. Serializers Are Part of the Message Protocol

Redis Stream entries contain bytes. If the producer uses `StringRedisTemplate` to write field `eventType` and value `OrderCreated` as strings, the consumer must decode them compatibly.

Conversely, when a producer uses binary or custom JSON serializers, the listener cannot infer types solely from Java generic names. In projects using `ObjectRecord`, you must also define converters, type metadata, schema evolution, and target types.

Agree on a contract:

```text
Stream: orders:events
Field:  eventType  -> UTF-8 string
Field:  orderId    -> UTF-8 decimal string
Field:  version    -> UTF-8 decimal string

RecordId assigned by Redis
Consumer group: orders-workers
ACK after processing and persisting state successfully
```

## 6. Container Bean with Consumer Group and Start/Stop Lifecycle

The following example uses a clearly named listener, a dedicated executor, and a Spring-managed lifecycle.

```java
package example.orders;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainerOptions;

@Configuration
public class OrderStreamContainerConfiguration {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "orders-workers";

    @Bean(initMethod = "start", destroyMethod = "stop")
    public StreamMessageListenerContainer
            <String, MapRecord<String, String, String>>
    orderStreamContainer(
            RedisConnectionFactory connectionFactory,
            @Qualifier("redisStreamExecutor") TaskExecutor executor,
            OrderStreamListener listener) {

        var options = StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(2))
                .batchSize(20)
                .executor(executor)
                .build();

        var container = StreamMessageListenerContainer.create(
                connectionFactory, options);

        container.receive(
                Consumer.from(GROUP, "orders-api-1"),
                StreamOffset.create(STREAM, ReadOffset.lastConsumed()),
                listener
        );

        return container;
    }
}
```

In this example:

1. Spring creates `RedisConnectionFactory` and the executor.
2. The bean method builds the container with options.
3. `container.receive(...)` registers the subscription for the stream, group, and listener.
4. `initMethod = "start"` tells Spring to start the container when the bean is ready; depending on version lifecycle support, startup can also be managed with a dedicated lifecycle mechanism, but **never accidentally call `start` twice**.
5. `destroyMethod = "stop"` stops polling tasks when the application context closes.

**Prerequisite:** the `orders-workers` group must already be created before the consumer begins executing `XREADGROUP`. The container bean is not responsible by default for creating the group. If the group does not exist, reading may fail with `NOGROUP`.

### 6.1. Consumer Names Must Be Managed

`Consumer.from(GROUP, "orders-api-1")` identifies a member of the group. In multi-instance environments, **do not share the same consumer name across all instances** if you need clear visibility and pending-entry attribution.

Example:

```text
orders-workers:
    orders-api-1
    orders-api-2
    orders-worker-batch-1
```

Consumer names should be configured from the instance/pod ID or a stable operational identifier per deployment policy. Redis does not prevent two processes from using the same name, yet they will be treated as the same consumer identity, complicating PEL analysis and message recovery.

### 6.2. Adding Multiple Subscriptions

One container can register multiple subscriptions if needed. However, **each polling subscription consumes resources**: adding subscriptions is not free, and a small executor cannot serve unlimited streams/consumers.

If you need to handle 20 streams or 20 subscriptions, size threads, connections, and blocking levels appropriately. When using multiple consumers in the same group to share load, give each subscription a distinct consumer identity and avoid inadvertently having separate groups duplicate-process events when only one execution was intended.

## 7. Writing a `StreamListener` with Manual Acknowledgment

With a consumer group, a message delivered to a consumer that is **not yet ACKed** stays in the Pending Entries List until confirmed or handled by a suitable recovery mechanism.

A listener implementation:

```java
package example.orders;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamListener
        implements StreamListener
                <String, MapRecord<String, String, String>> {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "orders-workers";

    private final OrderEventService orderEventService;
    private final StringRedisTemplate redisTemplate;

    public OrderStreamListener(
            OrderEventService orderEventService,
            StringRedisTemplate redisTemplate) {
        this.orderEventService = orderEventService;
        this.redisTemplate = redisTemplate;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        String eventType = message.getValue().get("eventType");
        String orderId = message.getValue().get("orderId");

        // This method must be idempotent in case the message is redelivered.
        orderEventService.process(
                message.getId().getValue(),
                eventType,
                orderId
        );

        // ACK only after required business effects have completed.
        redisTemplate.opsForStream().acknowledge(
                STREAM,
                GROUP,
                message.getId()
        );
    }
}
```

Explanation:

- `message.getId()` retrieves the **Redis stream record ID**, not the payload's `orderId`.
- `message.getValue()` provides the deserialized fields and values.
- `orderEventService.process(...)` executes business logic, such as writing to a database or calling a verifiable operation.
- `XACK` is sent **after** `process` succeeds.
- If `process` throws an exception, the subsequent ACK line does not run; the message stays pending for reprocessing.

For simplicity, the example omits retry logic inside the listener. In production, log the stream, group, consumer, record ID, error type, and have a plan for poison messages. Do not log sensitive payload fields.

### 7.1. Manual ACK Does Not Mean Exactly-Once

There is a failure window:

```text
T1  Consumer receives message ID 100-0
T2  Business result writes to database successfully
T3  Process dies before XACK
T4  Message remains pending
T5  Another consumer reclaims and reprocesses 100-0
```

If business processing is not idempotent, a single event can produce duplicate effects. Hence Redis Streams + consumer groups + manual ACK are typically designed around **at-least-once semantics at the application layer** when retries/reclaiming exist. Use an event ID or business idempotency key to detect prior processing.

For example, with a database you can create a `processed_events(consumer_group, stream_record_id, processed_at)` table with a unique constraint. Within the same SQL transaction as the business update, insert the processed event ID. If the record is redelivered, the service checks or conditionally inserts, skips duplicate side effects, and can still ACK.

Persisting idempotency state and business updates in the same database transaction provides far stronger guarantees than keeping an in-memory boolean in the JVM.

## 8. `receive()` vs. `receiveAutoAck()`: How Do They Differ?

When registering a consumer group, Spring Data Redis provides a message path with **manual ACK** and an **auto-acknowledgment** path (depending on API/version).

Manual ACK example:

```java
container.receive(
        Consumer.from("orders-workers", "orders-api-1"),
        StreamOffset.create("orders:events", ReadOffset.lastConsumed()),
        listener
);
```

Auto-ACK example:

```java
container.receiveAutoAck(
        Consumer.from("orders-workers", "orders-api-1"),
        StreamOffset.create("orders:events", ReadOffset.lastConsumed()),
        listener
);
```

Design differences:

| Criterion | Manual ACK via `receive` | Auto ACK via `receiveAutoAck` |
|---|---|---|
| Who decides when to send ACK? | Business processing code | Container/framework per auto-ack mechanism |
| Can ACK wait until after DB commit? | Yes, when structured properly | Do not assume ACK reflects committed business transactions |
| Suitable for | Critical messages needing retry/reclaim | Lightweight work accepting limited delivery guarantees |
| When handler fails | Can remain pending if not ACKed | Acked/non-pending behavior depends on auto-ack semantics; inspect carefully |
| Is idempotency needed? | Yes | Still needed if duplicates can arise across layers |

Do not use auto-ACK merely to “save a few lines of code” when business operations must not be lost. For critical flows, prefer **manual ACK after processing succeeds** paired with a clear reclaim/retry policy.

## 9. Choosing the Right `ReadOffset` for the Read Mode

`ReadOffset` is not just a syntactic detail. It determines **which messages Redis returns**, and using the wrong offset can cause missed messages or unintended replays.

### 9.1. Consumer Group: `ReadOffset.lastConsumed()`

```java
container.receive(
        Consumer.from("orders-workers", "orders-api-1"),
        StreamOffset.create(
                "orders:events",
                ReadOffset.lastConsumed()),
        listener
);
```

In a consumer group, `lastConsumed()` is commonly used to read **new entries not yet delivered to the group**, corresponding to `XREADGROUP ... STREAMS orders:events >`.

When a worker restarts, the group already has its read position and Pending Entries List. Simply re-registering with `lastConsumed()` **does not mean pending entries from a previously crashed consumer will automatically be reprocessed**.

### 9.2. Reading Without a Group

```java
container.receive(
        StreamOffset.create(
                "orders:events",
                ReadOffset.from("0-0")),
        listener
);
```

This example receives from an explicit offset without attaching a consumer group. In the non-group model, each subscription reads entries from its own offset; there is no `XACK` or consumer-group PEL for this read path.

`ReadOffset.latest()` fits when you only care about entries appearing after reading starts and accept skipping history. Be cautious when polling with the latest offset, because misusing semantics across polls or pauses in reading can miss messages arriving in between.

### 9.3. Do Not Change Offsets Without Knowing the Requirement

| Goal | Approach |
|---|---|
| Distribute messages across multiple workers | Consumer group, `ReadOffset.lastConsumed()` |
| Read history from the start in test environments | Starting offset like `0-0`, depending on group/non-group |
| Monitor only new messages | Latest offset, accepting no history replay |
| Recover delivered but unacknowledged messages | Inspect PEL and use claim/retry, not just offset changes |
| Replay the entire stream as a batch | Use a dedicated replay cursor/group; avoid corrupting production offsets |

Changing a group's offset with `XGROUP SETID` alters which new messages are delivered to the entire group. It is a data-impacting administrative operation, not a casual fix for a buggy consumer.

## 10. Pending Entries List and Recovering Unacknowledged Messages

A Redis consumer group stores delivered-but-**unacknowledged** messages in the PEL. When a listener fails or the application crashes after receiving messages, those messages do not vanish just because the container stopped.

Inspect:

```bash
redis-cli XINFO GROUPS orders:events
redis-cli XINFO CONSUMERS orders:events orders-workers
redis-cli XPENDING orders:events orders-workers
```

To inspect specific pending entries:

```bash
redis-cli XPENDING orders:events orders-workers - + 10
```

The output shows record IDs, owning consumers, idle times, and delivery counts per the command format.

### 10.1. Why Pending Entries Are Not Re-Read Automatically via `>`

When a consumer group reads new entries with `>`, Redis selects entries **never yet delivered to the group**. An entry already in the PEL does not turn back into a new entry on its own. Restarting the container with `ReadOffset.lastConsumed()` does not automatically clear backlogged PEL messages.

A **recovery flow** is needed:

1. Inspect the PEL by group and idle time.
2. Identify entries idle long enough to be eligible for reclaiming.
3. Transfer ownership of pending entries to an active consumer.
4. Re-run business processing idempotently.
5. ACK upon completion.

### 10.2. `XAUTOCLAIM`

Example using Redis CLI in a test environment:

```bash
redis-cli XAUTOCLAIM orders:events orders-workers orders-recovery-1 60000 0-0 COUNT 100
```

Meaning:

- `orders:events`: stream.
- `orders-workers`: group.
- `orders-recovery-1`: consumer receiving ownership.
- `60000`: requires messages to have been idle for at least 60,000 ms.
- `0-0`: cursor to begin scanning pending entries.
- `COUNT 100`: desired processing count per batch.

You must continue with the cursor returned by Redis when further scanning is needed; `XAUTOCLAIM` does not guarantee scanning all backlogged messages in one call.

**Idle thresholds must not be too short.** If a legitimate handler takes longer than 60 seconds to process a message, a recovery worker may reclaim it while the first handler is still working, causing duplicate parallel processing. Choose thresholds from real processing durations, paired with ownership/idempotency and a proper retry policy.

### 10.3. Poison Messages and Dead-Letter Handling

A message with a bad schema or unrecoverable business state can fail repeatedly. Infinite reclaiming prevents the PEL from draining and wastes resources.

Design:

- Maximum attempt count or criteria for unrecoverable errors.
- Logging of ID, error type, timestamp, and attempt history.
- A dedicated dead-letter stream or error table for investigation.
- Once the error event copy is durably persisted to the dead-letter target, decide to ACK the original message per an explicit policy.
- Replay capability after fixing code or source data.
- Never silently ACK/drop a message just because an error is hard to handle without an audit trail.

The container receiving messages is only one part of the system; **retry, reclaim, and DLQ behavior do not appear automatically just by creating a container**.

## 11. Subscription Lifecycle: Register, Run, Cancel, Stop

A subscription is created with:

```java
Subscription subscription = container.receive(
        Consumer.from("orders-workers", "orders-api-1"),
        StreamOffset.create("orders:events", ReadOffset.lastConsumed()),
        listener
);
```

To receive messages, the container must be in the running state. When configured as a bean with `initMethod="start"`, Spring normally manages the lifecycle. You can use:

```java
container.start();
container.stop();
```

in an alternative lifecycle management strategy when not using init/destroy methods. Avoid combining auto-start declarations with ad-hoc `start()` calls in multiple places.

`Subscription` provides registration management, including cancelling a subscription when polling the stream is no longer needed; exact APIs may vary by version, so follow your dependency's contract.

### 11.1. Graceful Shutdown

During rolling-restart deployments:

1. Stop accepting new HTTP/command traffic or drain the instance from the load balancer if needed.
2. Stop/cancel subscriptions so no new messages are fetched.
3. Allow in-flight handlers to finish within the graceful shutdown window.
4. ACK completed messages; leave incomplete ones pending for recovery.
5. Shut down executors and release connections.

Do not assume `container.stop()` automatically waits for every in-flight business task to finish. If the process is killed mid-flight, received-but-unacknowledged messages will require reclaiming after restart. Align graceful shutdown settings with Kubernetes/systemd timeouts and the longest expected handler duration.

### 11.2. Do Not Create a New Container Per Request

The container is a long-lived background component suited to being a **singleton bean**. Creating containers, executors, and subscriptions inside individual HTTP requests leaks threads and connections and spawns uncontrolled consumers.

When multiple streams follow the same pattern, one container can manage multiple subscriptions, or containers can be grouped by operational profile; base this decision on resources, poll frequency, and fault isolation needs.

## 12. Handling Container and Listener Errors

Distinguish at least three error categories:

| Error type | Examples | Handling approach |
|---|---|---|
| **Redis read error** | Network drop, timeout, permission error, Redis failover | Retry/reconnect per policy, monitor active subscriptions |
| **Deserialization error** | Producer changed schema/serializer, malformed payload | Record problematic record, send to DLQ, or fix schema |
| **Business error** | Database timeout, duplicate message, invalid data | Do not ACK before success; idempotency, retry, DLQ |

Container options support error handling; in supporting versions you can configure an error handler to capture exceptions from polling/processing tasks. **Do not rely solely on exception logs to assume a subscription is still running**: certain errors can stop or cancel a subscription depending on configuration. Monitor actual subscription health.

Example useful log structure:

```text
stream      = orders:events
group       = orders-workers
consumer    = orders-api-1
recordId    = 1730000000000-0
operation   = process
errorType   = DatabaseTimeout
attempt     = 3
durationMs  = 1200
action      = leave-pending
```

Avoid logging full payloads containing sensitive data; IDs and error metadata are usually enough for investigation.

### 12.1. Is Catching and Swallowing Exceptions Dangerous?

```java
@Override
public void onMessage(MapRecord<String, String, String> record) {
    try {
        orderEventService.process(...);
    } catch (Exception e) {
        log.error("Processing failed", e);
        // Do not ACK on the failure branch.
    }
}
```

With manual ACK, the message stays pending if unacknowledged; however, if the listener merely swallows the error and no recovery worker exists, the message can be forgotten indefinitely. Ensure an explicit pending-handling path exists rather than stopping at “logged the error”.

## 13. Throughput, `batchSize`, and Executor Sizing

Suppose messages arrive at 500 messages/s and each message takes an average of 20 ms to process. A single subscription processing sequentially on one thread has a theoretical throughput around:

```text
1 / 0.020 seconds ≈ 50 messages/second
```

This is a rough estimate ignoring Redis latency, I/O, retries, networking, database overhead, and batching. If processing truly runs sequentially on one thread, raising `batchSize` from 20 to 200 will not magically produce 500 messages/s.

Levers to consider:

- Increase the number of **consumer identities** within the same group to partition messages.
- Ensure the executor has enough threads for blocking-read subscriptions.
- Reduce per-message processing time or offload to a bounded worker pool.
- Tune `batchSize` to balance round trips against how long messages sit unacknowledged.
- Measure Redis CPU, database load, network, pending counts, and consumer lag.
- Apply backpressure / stop fetching when downstream is overloaded instead of buffering unbounded messages in memory.

**Never ACK before offloaded work finishes.** If a listener merely submits to a thread pool and ACKs immediately, a process crash can lose queued in-memory tasks that Redis already treats as confirmed.

### 13.1. Consumer Groups Are Not Pub/Sub Broadcasts

Within one group, consumers **divide** newly delivered messages; each entry is normally delivered to one consumer in the group at a time. If two independent systems must both receive every event, they generally need **two separate consumer groups**.

```text
Stream orders:events
    |
    +--> Group orders-payment-workers
    |         payment-worker-1
    |         payment-worker-2
    |
    +--> Group orders-analytics-workers
              analytics-worker-1
              analytics-worker-2
```

Each group has its own offset and PEL. ACKing in the analytics group does not substitute for ACKing in the payment group.

## 14. Managing Retention: `XACK` Does Not Delete Stream Entries

Redis Streams separates:

1. **Stream storage:** physical entries remaining in the stream.
2. **Consumer group delivery state:** which entries were delivered and are pending.
3. **ACK state:** confirmation that a group processed a message per application protocol.

Example:

```bash
redis-cli XLEN orders:events
redis-cli XPENDING orders:events orders-workers
```

After `XACK`, pending count can decrease while `XLEN` stays unchanged. Without a retention policy, a stream can grow indefinitely over time.

Administrative commands:

```bash
redis-cli XTRIM orders:events MAXLEN '~' 100000
redis-cli XINFO STREAM orders:events
```

`XTRIM` removes entries from the stream; if entries are deleted while a group still needs them, data for replay or reclaim may be incomplete. Size retention around the slowest consumer group, outage windows, replay requirements, and Redis memory capacity.

Never assume “message is ACKed” means it can immediately be deleted for all groups. One stream may serve multiple independent groups running at different speeds with separate PELs.

## 15. Creating Groups Inside the Application

Stream/group initialization can run at application startup. However, you must handle concurrency when **multiple instances start simultaneously**.

A sound startup flow:

```text
Application startup
   |
   +--> Verify Redis connectivity
   |
   +--> Ensure stream/group exists
   |       |
   |       +--> Missing: create group with chosen offset
   |       |
   |       +--> Already exists: preserve existing offset and PEL
   |       |
   |       +--> Auth/network error: report error, retry, or fail startup
   |
   +--> Register subscription
   |
   +--> Start container
```

If using `StringRedisTemplate.opsForStream().createGroup(...)`, check overloads for your Spring Data Redis version and whether the stream must already exist; `MKSTREAM` in `redis-cli` creates an empty stream and group in one command.

Especially important: **never delete and recreate the group on every application restart**. Doing so can lose the PEL or reset the delivery position, breaking recovery.

In production systems, creating groups via a centrally managed migration/deployment step often gives better control over initial offsets and avoids pod startup races.

## 16. When to Use `StreamMessageListenerContainer` vs. Manual Reads?

| Problem | Approach |
|---|---|
| Service continuously processing events on background threads | `StreamMessageListenerContainer` |
| A batch job running for a few minutes then exiting | `StreamOperations.read(...)` directly, managing its own cursor |
| End-to-end reactive application | Consider `StreamReceiver` and reactive Redis APIs |
| Need manual ACK and consumer groups | Container `receive(...)` + ACK + recovery |
| Need to handle pending messages from dead instances | Add `XPENDING`/`XAUTOCLAIM`/recovery flow |
| Need to replay a stream by historical ID | Dedicated offset/group and retention design |
| Need to broadcast to multiple independent systems | One consumer group per system |
| Only need ephemeral notifications without history | Redis Pub/Sub may fit better, without PEL/replay |

The container solves **how to listen**, not all requirements around storage, idempotency, retries, and business logic.

## 17. Observing and Monitoring Stream Systems

A container “running” does not guarantee healthy processing. A subscription may remain active while the handler fails continuously or the executor is starved for threads.

Metrics to collect:

| Metric | Meaning |
|---|---|
| Consumer lag | New messages not yet delivered/processed per the relevant measure |
| PEL size | Messages delivered to the group but not yet ACKed |
| Oldest pending idle | Age of oldest pending entry; signals dead or stuck consumers |
| Processing latency | Time from receiving a record to completing business work |
| ACK latency | Time until message acknowledgment succeeds |
| Retry/reclaim count | How often messages are reprocessed |
| Poison/DLQ count | Messages unprocessable under the contract |
| Polling errors | Redis connectivity, permission, or deserialization errors |
| Executor active/queue | Thread resource utilization |
| Stream length | Entries currently retained in the stream |
| Consumer last activity | Distinguishes existing consumers from ones actively receiving messages |

Note that `XINFO GROUPS` reports `lag` in supporting Redis versions, though its interpretation can be affected by trimming, group offsets, and stream structure. PEL size is also not the total unprocessed business backlog under all conditions. Never reduce overall system health to a single metric.

Diagnostic commands:

```bash
redis-cli XINFO STREAM orders:events
redis-cli XINFO GROUPS orders:events
redis-cli XINFO CONSUMERS orders:events orders-workers
redis-cli XPENDING orders:events orders-workers
redis-cli XLEN orders:events
```

## 18. Common Issues

### 18.1. `NOGROUP` Immediately When the Container Starts

**Symptom:** listener receives no messages; Redis returns an error indicating the consumer group does not exist.

**Cause:** the container started before the group was created, or the app connected to the wrong Redis database/instance.

**Resolution:** verify `XINFO GROUPS` and perform idempotent group creation during startup. Never reset a group that already has pending messages.

### 18.2. Container Registered Properly, Yet No Messages Arrive

Check:

- Has the container called `start()`?
- Was the subscription created before startup?
- Does the executor have free threads for polling tasks?
- Is the stream key exact?
- Was the group created with `$` while only old messages exist from before creation?
- Did the group already deliver the messages to another consumer?
- Are the messages sitting in pending rather than as new entries?

`XRANGE` proves the stream contains entries; **it does not prove the group still has new entries available via `>`**.

### 18.3. Only Processing New Messages, Missing Earlier Ones

If the group was created with `$`, pre-existing messages are not automatically fetched as new entries. If a non-group consumer sets `ReadOffset.latest()`, it may also intentionally skip history.

Base the solution on actual replay requirements; never change production offsets without checking retention and the PEL.

### 18.4. Pending Messages Growing Continuously

Handlers may be throwing errors without ACKing; or ACKs are failing, consumers died, business logic is too slow, or poison messages are stuck. Check `XPENDING`, event IDs, delivery counts, and application status; implement reclaim/retry instead of just increasing batch size.

### 18.5. Messages Processed Twice

Redis Streams consumer groups do not automatically guarantee business-level exactly-once processing. A process can commit DB work and die before ACK; recovery redelivers the message.

Design idempotency around the stream record ID or business event ID with a unique constraint in the authoritative store. Do not rely on “seen IDs in an in-memory `HashMap`” to survive restarts.

### 18.6. One Subscription Occupies a Thread for Too Long

Blocking polls and callbacks run on executor resources. If the executor is too small, one slow subscription or blocking handler can starve other subscriptions of threads.

Measure processing durations, pool size, queue depth, and subscription counts. Adding threads will not fix a downstream database bottleneck if every message still runs a slow transaction.

### 18.7. Serializer Mismatch Between Producer and Consumer

Producer writes hash fields with a binary serializer while the listener expects `MapRecord<String,String,String>`. Keys/values may look corrupted or fail decoding.

Define the field/value contract and configure matching serializers on both sides. Never call `toString()` on a byte array and assume it is valid JSON.

### 18.8. Failing to Stop the Container on Application Shutdown

A blocking task holding a connection or running a handler can prolong shutdown or get killed before ACKing. Tie container lifecycle and graceful shutdown into deployment configuration.

### 18.9. Using the Same Consumer Name on Every Pod

Redis treats calls with the same name as the same consumer identity, making per-instance pending ownership and metrics hard to separate. Configure unique consumer names or an explicit naming policy.

### 18.10. Thinking `XACK` Deleted the Message

`XACK` clears pending status for one group, while the entry can remain in the stream because other groups still need it. Use a dedicated trim/retention policy instead of tying physical deletion directly to ACK logic.

## 19. End-to-End Practice in a Test Environment

### Step 1 — Create the Stream and Group

```bash
redis-cli XGROUP CREATE orders:events orders-workers 0-0 MKSTREAM
```

If the group already exists from an earlier exercise, do not reset it blindly; use a fresh stream/group name or isolate test data.

### Step 2 — Start the Application

Ensure the container registered the subscription and started. Check application logs to confirm the listener is active with no `NOGROUP` or deserialization errors.

### Step 3 — Send Two Events

```bash
redis-cli XADD orders:events '*' eventType OrderCreated orderId 42 version 1
redis-cli XADD orders:events '*' eventType OrderPaid orderId 42 version 2
```

Record the record ID Redis returns for each `XADD`.

### Step 4 — Observe the Listener and ACK

Once the handler processes successfully, inspect:

```bash
redis-cli XPENDING orders:events orders-workers
redis-cli XINFO GROUPS orders:events
```

If the handler ACKed properly, processed records are no longer in the group's PEL. Yet:

```bash
redis-cli XRANGE orders:events - +
```

can still return ACKed entries because nothing has trimmed them.

### Step 5 — Trigger a Controlled Processing Failure

In a lab environment, make the handler throw an exception before ACK for a specific event. Observe pending messages, delivery count, listener errors, and subscription behavior.

Create a separate recovery consumer using `XAUTOCLAIM` once the idle threshold passes. Let it succeed and ACK. Verify whether business effects duplicated if the event partially processed before failing.

### Step 6 — Test Multiple Instances

Run two instances with different consumer names in the same group. Send multiple events and observe via `XINFO CONSUMERS` how messages are distributed. If both instances must process every event, use **two separate groups**, not two consumers in one group.

### Step 7 — Test Shutdown

Stop one instance while a slow message is processing; observe remaining pending entries, then reclaim them on another instance per policy. The goal is verifying recovery under failure rather than only testing the happy path.

## 20. Self-Check Knowledge Questions

**1. Does the container read Redis in a strictly non-blocking manner?**

No. The container runs polling loops on application background tasks; `XREAD`/`XREADGROUP` commands can still use `BLOCK` for `pollTimeout`.

**2. Do you need to call `start()`?**

You must ensure the container is actually started—via Spring lifecycle hooks or an explicit call—and stopped on shutdown. Calling `receive(...)` alone only registers the subscription and does not guarantee polling is running.

**3. Why must the group exist before reading?**

`XREADGROUP` requires an existing group; otherwise Redis returns `NOGROUP`. The container does not replace group creation by default.

**4. What is the difference between initializing a group at `0-0` vs. `$`?**

`0-0` lets the group start from stream history; `$` places the cursor at the current tail, generally skipping entries created before the group existed on the new-message read path.

**5. Why does `ReadOffset.lastConsumed()` not automatically handle all pending messages after a crash?**

Because reading new entries for the group differs from reading entries already delivered and sitting in the PEL. Pending entries must be tracked and reclaimed/retried separately.

**6. When should `XACK` be called?**

With manual ACK and reliable processing requirements, ACK after required business processing completes. If failure occurs before ACK, the message retains a chance to be reprocessed via recovery flows.

**7. Does ACK delete the record from the stream?**

No. ACK confirms consumer group state; physically deleting or trimming entries requires a separate policy.

**8. Do consumer groups guarantee exactly-once business processing?**

No. Messages can be redelivered if a process dies between business writes and ACK; idempotency is required.

**9. Does increasing `batchSize` automatically multiply a slow callback's throughput several times over?**

No. Batch size mainly governs how many entries are requested per poll; throughput still depends on handler speed, executor threads, Redis, database capacity, and consumer count.

**10. When multiple applications all need every event, should they share one group or use multiple groups?**

Usually multiple independent groups; consumers within one group split new entries rather than broadcasting every entry to every consumer.

## 21. Production Deployment Checklist

- `StreamMessageListenerContainer` is a background polling component suited to being a bean with an explicit lifecycle, never instantiated per HTTP request.
- Initialize streams/groups idempotently before `XREADGROUP`; choose `0-0` or `$` according to history-reading requirements.
- With consumer groups, use `Consumer.from(group, consumerName)` and `ReadOffset.lastConsumed()` for new entries, while **never forgetting the PEL**.
- Size `pollTimeout`, `batchSize`, executors, and serializers for real load; measure throughput rather than blindly bumping numbers.
- Use manual `XACK` after processing succeeds when reliable retries are needed; design idempotency for redelivered messages.
- Implement a pending recovery flow using `XPENDING`/`XAUTOCLAIM`, appropriate idle thresholds, and dead-letter handling for poison messages.
- Monitor subscription health, executor saturation, consumer lag, pending size, processing latency, and Redis errors.
- Remember `XACK` does not delete physical entries; configure retention/`XTRIM` respecting all consumer groups sharing the stream.
- With multiple instances, assign distinct consumer identities and plan graceful shutdown and crash recovery.
- Distinguish the imperative container from reactive `StreamReceiver`; pick the model matching your application architecture.

**Successful configuration is not just seeing a listener receive one message.** A reliable Redis Streams setup must also prove it starts at the right offset, never loses pending entries, safely handles duplicate deliveries, exposes backlog observability, and recovers cleanly from Redis errors or restarts.

## References

- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): stream records, consumer groups, `StreamMessageListenerContainer`, and offset semantics.
- [Spring Data Redis — StreamMessageListenerContainer API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/stream/StreamMessageListenerContainer.html): registering listeners and lifecycle.
- [Spring Data Redis — StreamMessageListenerContainerOptions API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/stream/StreamMessageListenerContainer.StreamMessageListenerContainerOptions.html): polling and deserialization options.
- [Redis — Streams Introduction](https://redis.io/docs/latest/develop/data-types/streams/): Redis Stream and consumer group model.
- [Redis — XGROUP CREATE](https://redis.io/docs/latest/commands/xgroup-create/): creating groups and choosing initial IDs.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): reading in consumer groups, `BLOCK`, `COUNT`, and pending entries.
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/): acknowledging consumer group records.
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/): inspecting the Pending Entries List.
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): reclaiming sufficiently idle pending messages.
- [Redis — XTRIM](https://redis.io/docs/latest/commands/xtrim/): capping stream length per retention policy.
