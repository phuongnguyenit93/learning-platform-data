# Redis stream inbound adapter

## Learning Objectives

After this lesson, you will be able to:

- Explain how the **Redis Stream inbound channel adapter** uses a **Reactive `StreamReceiver`** to turn Redis Streams records into Spring Integration **`Message`s** on a **`MessageChannel`**.
- Distinguish standalone **`XREAD`**, consumer-group **`XREADGROUP`**, **Redis Pub/Sub inbound**, **Redis List queue inbound**, and **Redis store inbound**.
- Identify the roles of **stream key**, **Record ID**, **field/value map**, **consumer group**, **consumer name**, **`ReadOffset`**, **Pending Entries List (PEL)**, and **`XACK`**.
- Configure **`ReactiveRedisStreamMessageProducer`** with **`ReactiveRedisConnectionFactory`**, consumer group, manual acknowledgment, offset, timeout, batch size, and output channel.
- Use **`Redis.streamInboundChannelAdapter(...)`** in Java DSL; distinguish **`extractPayload(true/false)`** and stream metadata headers.
- Design a **validate → idempotent business commit → acknowledgment** handler and understand the impact of ACKing too early or too late.
- Classify parsing, network, and transient/permanent business errors; handle poison records, pending entries, reclaiming, and dead-lettering per application policy.
- Design retention, trimming, replay, backpressure, consumer concurrency, scaling, security, and observability.
- Test happy paths, offline consumers, crashes before/after commit, redelivery, pending recovery, serializer mismatches, and schema upgrades.

## 1. The problem: events must survive when consumers are offline

Suppose **OrderService** emits an **`ORDER_CREATED`** event. **FulfillmentService** needs to receive it to create a shipping request, yet may go down temporarily during deployments or network drops.

~~~text
Redis Stream key: orders:events
Stream record ID: 1795410000123-0
Fields:
  eventId       = evt-order-1001
  eventType     = ORDER_CREATED
  schemaVersion = 1
  orderId       = O-1001
  tenantRef     = T-1
~~~

With standard **Redis Pub/Sub**, notifications published while a consumer is offline **are not retained for replay to that subscriber**. With **Redis Streams**, the publisher appends a **record with an ID into a data structure stored in Redis**; a consumer can later read records not yet removed by retention/trimming.

Spring Integration supports the **Redis Stream Inbound Channel Adapter** to convert those stream records into Spring Messages:

~~~mermaid
flowchart LR
    P["OrderService<br/>XADD"] --> R[("Redis Stream<br/>orders:events")]
    R --> RX["Reactive StreamReceiver<br/>XREADGROUP"]
    RX --> A["Redis stream<br/>inbound adapter"]
    A --> C["Spring Integration<br/>MessageChannel"]
    C --> V["Validate + idempotency"]
    V --> H["Fulfillment handler"]
    H --> DB[("Business DB")]
    H -. "ACK after commit" .-> R
~~~

**The goal is not merely receiving a message**, but distinguishing three separate milestones:

1. Redis stored the record via **`XADD`**.
2. The consumer received the record via **`XREADGROUP`**; the record sits in the **PEL** if un-ACKed.
3. The business handler completed and the consumer invoked **`XACK`** appropriately.

An event can sit at state 1 or 2 without **ever completing business processing**. Never equate “the adapter received a message” with business success.

This lesson belongs to the **Adapter Redis** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. Within the context of connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s, Redis Streams is a **message-driven source based on reactive stream polling**, whose record persistence, consumer groups, and acknowledgments differ from File/SFTP, HTTP, JMS, AMQP, Kafka, Redis Pub/Sub, and Redis Lists.

## 2. What are Redis Streams?

A Redis Stream is an **append-oriented** data structure with **ordered-ID records**. Each record holds field/value pairs. Common command:

~~~redis
XADD orders:events * eventId evt-order-1001 eventType ORDER_CREATED schemaVersion 1 orderId O-1001
~~~

Redis returns the record ID, for example:

~~~text
1795410000123-0
~~~

That is the **Redis Stream ID**, not the business `eventId`. It usually has two parts formatted as **`millisecondsTime-sequence`**, assigned by Redis when using `*`; treat record IDs as transport identifiers rather than authoritative domain timestamps or payment IDs.

### 2.1. What does a stream record contain?

~~~text
Redis Stream record
  stream key: orders:events
  record ID: 1795410000123-0
  fields:
    eventId: evt-order-1001
    eventType: ORDER_CREATED
    schemaVersion: "1"
    orderId: O-1001
~~~

Redis Streams do not have built-in AMQP-style standard properties like **`contentType`/`correlationId`/`replyTo`**. If these values are part of your contract, define them explicitly in **record fields** or an encoding/metadata convention.

### 2.2. Redis Stream ID vs. `eventId`

| Identifier | Creator | Scope | Used for |
| --- | --- | --- | --- |
| **Redis Stream record ID** | Redis `XADD` / client following stream rules | One record in one stream | Offset, `XACK`, PEL, delivery tracing |
| **`eventId`** | Producer / business service | One business event across retries | Idempotency, audit, reconciliation |
| **Spring `MessageHeaders.ID`** | Spring Messaging runtime | One internal Spring Message | Internal integration observability/routing |
| **`correlationId`** | Per business contract | Request/workflow if needed | Business correlation or tracing |
| **`traceId`/`spanId`** | Observability instrumentation | Trace/span | Distributed tracing |

If a producer **`XADD`s the same business event twice**, Redis may assign **two different record IDs**, even though both contain the same `eventId`. Hence consumers still require **idempotent processing**.

### 2.3. `XADD` does not mean the business handler finished

A successful `XADD` confirms the Redis write under current server/client conditions. It does not guarantee:

- The record stays forever, since streams can be trimmed/deleted.
- Any consumer is online.
- Any consumer has ACKed.
- Databases, object storage, or payment providers committed.
- Redis replicated/persisted to the desired durability across all failover scenarios.

For tight RPO/RTO requirements, review Redis persistence, replication, and failover policies alongside producer acknowledgments.

## 3. Comparing the four Redis inbound types

| Endpoint/model | Data source | How it receives | When consumer is offline | ACK/recovery |
| --- | --- | --- | --- | --- |
| **Redis Pub/Sub inbound** | Channel notification | `SUBSCRIBE`/`PSUBSCRIBE` | New messages are not kept for offline subscribers | No Pub/Sub consumer ACK/replay |
| **Redis queue inbound** | Redis List | Blocking `POP` (usually `BRPOP`) | Unpopped items remain in List | Destructive `POP`; must build processing/ACK |
| **Redis store inbound** | List/Set/ZSet/Map/Properties | Spring Integration Poller receives **`RedisStore` view** | Current store may remain | Polling/view does not claim individual items |
| **Redis Stream inbound** | Redis Stream | Reactive `StreamReceiver`, `XREAD`/`XREADGROUP` | Records remain readable within retention | Consumer group PEL/`XACK`, recovery must be designed |

### 3.1. Do not mechanically attach a Spring Poller to stream inbound

The Redis Stream inbound adapter uses a **reactive `StreamReceiver`** with an **`XREAD`/`XREADGROUP`** loop, typically configured with **`pollTimeout`** for Redis blocking reads. It is **not** a `RedisStoreMessageSource` requiring `Pollers.fixedDelay(...)` like Redis store inbound.

A message-driven adapter can **actively read** from Redis; “message-driven” does not require Redis to send `PUBLISH` to a listener. What matters is **who owns the receive loop**: here it is `StreamReceiver`, not a Spring Integration `SourcePollingChannelAdapter`.

### 3.2. Streams do not automatically make side effects exactly-once

If a worker commits to the DB and crashes before `XACK`, the record stays in the PEL and can be reclaimed. If the consumer calls `XACK` before DB commit, a crash marks the record ACKed even though business work failed.

Therefore, design Redis Streams around **at-least-once with manual ACK/recovery**, paired with **`eventId` and idempotent business handlers**—never claim end-to-end exactly-once out of the box.

## 4. Standalone `XREAD` vs. consumer-group `XREADGROUP`

Redis Streams offer two primary reading modes.

### 4.1. Standalone `XREAD`

~~~redis
XREAD COUNT 10 BLOCK 1000 STREAMS orders:events 0-0
~~~

This reads records after the specified ID. The client manages offsets itself; Redis **does not maintain a consumer-group PEL** for standalone `XREAD`.

If two independent applications both `XREAD` the same stream from their respective offsets, both receive the same records; this is not competing consumers.

### 4.2. Consumer-group `XREADGROUP`

~~~redis
XGROUP CREATE orders:events fulfillment-v1 0-0 MKSTREAM
XREADGROUP GROUP fulfillment-v1 worker-a COUNT 10 BLOCK 1000 STREAMS orders:events >
~~~

Breakdown:

- **`fulfillment-v1`**: consumer group with its own progress and pending state.
- **`worker-a`**: consumer name inside the group.
- **`COUNT 10`**: maximum records Redis returns in one read command, not the number of business commits.
- **`BLOCK 1000`**: Redis wait timeout for data, not business retry backoff.
- **`>`**: inside a consumer group, requests records **never yet delivered to any other consumer in the group** per group progress.

If a worker crashes after `XREADGROUP` but before `XACK`, the record **remains in the PEL**. Another worker calling `XREADGROUP` with **`>`** **will not automatically re-read those pending records**; you need an explicit pending read/claim mechanism.

### 4.3. Different groups receive independent logical copies

~~~mermaid
flowchart LR
    R["Redis Stream<br/>orders:events"] --> G1["Group fulfillment-v1"]
    R --> G2["Group analytics-v1"]
    G1 --> A["Worker fulfillment A"]
    G1 --> B["Worker fulfillment B"]
    G2 --> C["Analytics worker C"]
~~~

Within the **same group**, workers split records; **across groups**, each group tracks independent progress. Each group can process every record for its own purpose, while duplicate deliveries still happen on retries/recovery.

Never create a **brand-new group on every application restart** if you intend to resume pending state from the existing group.

## 5. Consumer groups, PEL, and `XACK`

The **Pending Entries List (PEL)** is state kept by Redis for records delivered by a group to a consumer that are **not yet ACKed**.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Redis Stream + group PEL
    participant A as Consumer A
    participant B as Business DB
    P->>R: XADD eventId=evt-1001
    A->>R: XREADGROUP GROUP fulfillment-v1 worker-a >
    R-->>A: Record ID 1795410000123-0
    Note over R,A: Record delivered, now in PEL
    A->>B: Validate + commit business
    B-->>A: Commit OK
    A->>R: XACK orders:events fulfillment-v1 1795410000123-0
    Note over R,A: XACK removes pending entry for group
~~~

### 5.1. `XACK` does not delete the record from the stream

`XACK` **removes a record ID from a consumer group's PEL**; it is not `XDEL` and does not shrink stream length. The record remains in the stream for other groups to read or for retention-bounded replay.

### 5.2. State after a crash

| Crash point | Redis record | Group PEL | Business outcome |
| --- | --- | --- | --- |
| Before `XADD` | Absent if unwritten | None | Producer decides retry/outbox |
| After `XADD`, before group delivery | Present unless trimmed | Not yet pending | Can be received later |
| After `XREADGROUP`, before business commit | Present unless trimmed | **Pending** | Unknown / incomplete |
| After business commit, before `XACK` | Present unless trimmed | **Pending** | Completed, yet may duplicate |
| After `XACK` | May still exist | No longer pending for group | Confirms ACK only, not business state by itself |

**Safe ACK policy is normally after the durable commit milestone**; when a provider outcome is unknown after a timeout, reconcile before ACKing or retrying per contract.

### 5.3. Do not treat pending count as completed count

A low Redis PEL can result from **early `autoAck`**, stream trimming, or handlers ACKing right on receive. It does not prove every order was fulfilled.

Metrics must separate **`XADD`**, **delivered**, **business committed**, **`XACK`**, **pending idle**, and **reclaimed**.

## 6. `ReadOffset`: choosing where consumption starts

**`ReadOffset`** directly determines whether a consumer reads the intended backlog. Spring Data Redis provides strategies such as **`latest()`**, **`from(recordId)`**, and **`lastConsumed()`**.

| Mode | Design meaning | Watch out for |
| --- | --- | --- |
| **`ReadOffset.latest()`** | Reads new records from the current point per Redis's latest offset definition | May miss records added before start or between polls |
| **`ReadOffset.from(id)`** | Reads records after the specified ID | Requires storing/checkpointing the ID and intentional positioning |
| **`ReadOffset.lastConsumed()`** | Inside a consumer group: resumes group progress, typically for undelivered records | Does not automatically scan the PEL of delivered-but-unACKed records |

### 6.1. Adapter defaults

Per the Spring Integration API, **`ReactiveRedisStreamMessageProducer`** defaults to **`ReadOffset.latest()`** for standalone `XREAD`. When switched to a **consumer group** by setting a consumer name while the offset is still the default `latest`, the adapter switches appropriately to **`lastConsumed()`**.

This is crucial: never glance at Java code missing `setReadOffset` and assume the consumer group will read history from ID `0-0`. **Group creation offset** and **worker read offset** are two separate decisions.

### 6.2. Is the group created from the start or the end of the stream?

Redis CLI shows both options:

~~~bash
# Start the group from the beginning of the retained stream:
redis-cli XGROUP CREATE orders:events fulfillment-v1 0-0 MKSTREAM

# Example on a different group name, receiving only records appended after creation:
redis-cli XGROUP CREATE orders:events analytics-new '$' MKSTREAM
~~~

Here **`0-0`** defines the initial offset when the group is created, whereas **`$`** marks the tail at creation time. Never run both commands with the same group name expecting Redis to recreate an existing group.

When Spring Integration sets **`setCreateConsumerGroup(true)`**, the endpoint can create the group/stream if missing; test the exact **initial offset** and behavior with pre-existing data in your version. If reading historical backlog is required, **provision the group with an explicit offset before the adapter starts** and let the adapter attach to the existing group.

### 6.3. Consumer group offset is not PEL recovery

A common design bug:

~~~text
Worker A reads msg-1 -> pending in PEL
Worker A crashes
Worker B starts and runs XREADGROUP ... >
Worker B receives msg-2, msg-3

msg-1 remains stuck pending under A.
~~~

The consumer group tracks delivered/unacknowledged state, yet **new deliveries** do not clear dead workers' PEL entries. You need **`XPENDING` + `XCLAIM`/`XAUTOCLAIM`** or a dedicated recovery process.

### 6.4. Standalone `latest` has gaps between polls

Spring Data Redis warns that `ReadOffset.latest()` can miss records added during the “dead time” between `XREAD` calls. Reactive `StreamReceiver` also applies backpressure that pauses polling when downstream demand is zero.

If missing records cannot be tolerated in standalone consumption, track offsets via **last seen ID/checkpoint**, or use consumer groups with retention and PEL recovery. Never assume a reactive `Flux` + `latest` provides complete durable replay.

### 6.5. Do not equate OFFSET with a business checkpoint

Once the Redis group delivers a record, **last-delivered ID** advances even though the handler has not committed yet. Your true business checkpoint lives in **`eventId`, database state, idempotency**, and **successful `XACK`** per policy.

## 7. Stream inbound is reactive: `StreamReceiver` architecture

Spring Integration Redis Stream inbound was introduced in **Spring Integration 5.4** as **`ReactiveRedisStreamMessageProducer`**. It uses **Spring Data Redis `StreamReceiver`** to produce a stream of records and emit Spring Messages to an output channel.

~~~mermaid
flowchart LR
    REDIS[("Redis Stream")] -->|"XREAD/XREADGROUP"| REC["StreamReceiver"]
    REC --> FL["Reactive Flux of Records"]
    FL --> ADP["ReactiveRedisStreamMessageProducer"]
    ADP --> MSG["Spring Message<br/>payload + headers"]
    MSG --> MC["MessageChannel"]
    MC --> HAND["Business / Validation"]
    HAND -. "ACK callback" .-> REDIS
~~~

### 7.1. Reactive transport does not make every handler non-blocking

**`StreamReceiver`** reads asynchronously and honors Reactor backpressure, yet wiring it to a **`DirectChannel`** that runs blocking JDBC/HTTP calls inside the handler still creates **blocking** segments.

Clarify:

- Are you using a reactive output channel/`FluxMessageChannel`?
- Do handlers invoke blocking APIs?
- Which Reactor threads or `boundedElastic`/thread pools execute heavy work?
- When downstream slows down, are more records pulled into the PEL than workers can process?
- In an async flow, when is the acknowledgment callback invoked?

Never take the name **`ReactiveRedisStreamMessageProducer`** as a guarantee that the entire pipeline is non-blocking or automatically backpressures business services.

### 7.2. Standalone `XREAD` vs. `XREADGROUP`

By default per the adapter API, it can read as a standalone **`XREAD`** client; to switch to consumer-group **`XREADGROUP`**, set **`consumerName`** and **`consumerGroup`**. Consumer names should be **unique across simultaneously active instances in the same group**.

Never assign the exact same `consumerName` to every replica unless you intentionally designed recovery/ownership around it and verified Redis behavior. For example, use **`worker-a`**, **`worker-b`** rather than naming every container **`worker-1`**.

### 7.3. `StreamReceiverOptions`

Spring Data Redis **`StreamReceiverOptions`** configures transport behavior such as:

- **`pollTimeout`**: `BLOCK` wait duration for records.
- **`batchSize`**: `COUNT` per read call.
- **serialization context**: encoding for keys/fields/values.
- **target type / object mapper**: mapping records to DTOs when appropriate.
- **`onErrorResume`**: error-handling strategy on receive/deserialization errors in supported versions.

In Spring Integration **5.5+**, the adapter also exposes matching direct setters. **Do not configure both a pre-built `StreamReceiverOptions` and direct setters from the same group** when the API forbids mixing them.

### 7.4. Poll timeout is not a business retry interval

Setting `pollTimeout=200ms` means Redis `XREADGROUP` blocks up to 200ms waiting for records. It does NOT mean:

- The consumer retries business logic after 200ms.
- PEL entries get claimed after 200ms.
- The Redis Stream trims after 200ms.
- Task processing has a sub-200ms SLA.

Retries, backoff, and reclaiming require dedicated mechanisms.

### 7.5. `batchSize` is not a commit batch

`batchSize=10` asks Redis for up to 10 records per read; the handler can process and ACK each individually, or batch per business contract. **Never ACK all 10 records when only 9 actually committed.**

## 8. Dependencies and Redis `ConnectionFactory`

With Spring Boot and compatible dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-redis</artifactId>
    </dependency>
</dependencies>
~~~

Spring Boot starter artifacts depend on your Boot generation; if your environment lacks a dedicated reactive starter, include the matching Redis/Lettuce/Reactor starter from the BOM. **The key requirement is an actual `ReactiveRedisConnectionFactory`**, not solely a synchronous `RedisConnectionFactory`.

### 8.1. Local/test Redis config

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

This is an illustrative test configuration. Production requires TLS, secret management, Redis ACLs, Sentinel/Cluster, and proper timeouts. Property namespaces may vary across Spring Boot versions; verify against your actual BOM/configuration metadata.

### 8.2. `ReactiveRedisConnectionFactory` vs. `RedisTemplate`

| Component | Role |
| --- | --- |
| `ReactiveRedisConnectionFactory` | Redis connections for reactive operations / `StreamReceiver` |
| `ReactiveRedisTemplate` / `ReactiveStreamOperations` | Reactive Redis Streams producer/consumer |
| `StringRedisTemplate` | Synchronous Spring Data Redis helper convenient for reading/writing String fields in labs |
| `ReactiveRedisStreamMessageProducer` | Spring Integration endpoint emitting Spring Messages from stream records |
| `MessageChannel` | Where `IntegrationFlow` processes received records |

A **`LettuceConnectionFactory`** can implement both sync and reactive APIs depending on configuration/version. Do not assume every `RedisConnectionFactory` supports reactive operations. Inject an explicit **`ReactiveRedisConnectionFactory`** when configuring the adapter.

### 8.3. Avoid automatic JDK serialization

For cross-service record fields, prefer **UTF-8 String fields / typed JSON / Avro / Protobuf** per contract. Never push native Java-serialized objects from one producer and enable trust-all deserialization in another consumer.

### 8.4. Stream and group addressing

In our example:

~~~text
Stream key:     orders:events
Consumer group: fulfillment-v1
Consumer name:  fulfillment-pod-a
EventId:        evt-order-1001
Record ID:      1795410000123-0
~~~

The **stream key** identifies the Redis data structure, the **group** tracks independent delivery state, the **consumer name** owns pending entries, and **`eventId`** is the business identity. Never reuse `consumerName` as `eventId` or name groups after ephemeral pod names on every deploy.

## 9. Test producer: `XADD` a record with an explicit contract

Synchronous Spring Data Redis example with `StringRedisTemplate`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamPublisher {

    public static final String STREAM = "orders:events";
    private final StringRedisTemplate redisTemplate;

    public OrderStreamPublisher(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public RecordId publishCreated(String eventId, String orderId) {
        if (eventId == null || eventId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing event identity");
        }

        Map<String, String> fields = new LinkedHashMap<>();
        fields.put("eventId", eventId);
        fields.put("eventType", "ORDER_CREATED");
        fields.put("schemaVersion", "1");
        fields.put("orderId", orderId);

        MapRecord<String, String, String> record =
            StreamRecords.newRecord()
                .in(STREAM)
                .ofMap(fields);

        return redisTemplate.opsForStream().add(record);
    }
}
~~~

**Verification note:** Across Spring Data Redis generations, generic signatures on `StreamRecords` builders and type inference can vary. When compiling, adapt to your library version and serializer while preserving the **stream key + field map + `RecordId`** contract.

### 9.1. Inspecting with Redis CLI

~~~bash
redis-cli XADD orders:events '*' eventId evt-order-1001 eventType ORDER_CREATED schemaVersion 1 orderId O-1001
redis-cli XRANGE orders:events - +
redis-cli XLEN orders:events
~~~

Read commands do not perform `XACK`. **`XLEN`** counts retained records, not pending/ACK counts or business `DONE` counts.

### 9.2. Do not treat Record ID as the default `eventId`

If a producer times out unsure whether `XADD` succeeded, a retry creates a second record with a **different Record ID**. Consumers must recognize both records share the **same `eventId`** when business rules require deduplication.

### 9.3. Database transactions and `XADD`

~~~text
DB commit -> crash -> XADD never sent
~~~

For order events that must never be lost, use a **transactional outbox** or durable event source to publish after commit. A successful `XADD` **is not atomic with a JDBC transaction**.

### 9.4. Stream retention

Do not let streams grow unbounded. Use `XADD MAXLEN` or `XTRIM`, factoring in downtime windows, consumer throughput, and audit/replay needs. **Trimming too aggressively can delete records while PEL metadata still exists**, leaving recovery without payloads.

## 10. Java configuration: `ReactiveRedisStreamMessageProducer`

The example below uses **manual ACK** and a **pre-provisioned consumer group** in test Redis, avoiding reliance on auto-creation offset choices.

Before starting the application:

~~~bash
redis-cli XGROUP CREATE orders:events fulfillment-v1 0-0 MKSTREAM
~~~

If the group already exists, Redis returns **`BUSYGROUP`**; never delete/recreate a production group just to re-run setup commands.

### 10.1. `MessageChannel` receiving stream records

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class OrderStreamChannelConfig {

    @Bean
    public MessageChannel ordersStreamInput() {
        return new DirectChannel();
    }
}
~~~

### 10.2. Dedicated adapter bean

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.integration.redis.inbound.ReactiveRedisStreamMessageProducer;
import org.springframework.messaging.MessageChannel;

@Configuration
public class OrderStreamInboundConfig {

    @Bean
    public ReactiveRedisStreamMessageProducer ordersStreamInbound(
            ReactiveRedisConnectionFactory redisFactory,
            @Qualifier("ordersStreamInput")
            MessageChannel ordersStreamInput) {

        ReactiveRedisStreamMessageProducer adapter =
            new ReactiveRedisStreamMessageProducer(
                redisFactory, OrderStreamPublisher.STREAM);

        adapter.setConsumerGroup("fulfillment-v1");
        adapter.setConsumerName("fulfillment-local-a");
        adapter.setCreateConsumerGroup(false);
        adapter.setAutoAck(false);
        adapter.setReadOffset(ReadOffset.lastConsumed());
        adapter.setPollTimeout(Duration.ofMillis(300));
        adapter.setBatchSize(10);
        adapter.setExtractPayload(false);
        adapter.setOutputChannel(ordersStreamInput);
        adapter.setAutoStartup(true);

        return adapter;
    }
}
~~~

**Meaning of each setting:**

| Setting | Lab value | Meaning |
| --- | --- | --- |
| `streamKey` | `orders:events` | Stream being read |
| `consumerGroup` | `fulfillment-v1` | Uses pre-provisioned group |
| `consumerName` | `fulfillment-local-a` | Consumer identity; must be unique per concurrent replica |
| `createConsumerGroup` | `false` | Avoids implicitly creating a group with an unintended offset |
| `autoAck` | `false` | Business flow decides when to ACK |
| `readOffset` | `lastConsumed` | Reads new records per group progress |
| `pollTimeout` | `300 ms` | `BLOCK` timeout reading stream |
| `batchSize` | `10` | Max `COUNT` per read |
| `extractPayload` | `false` | Spring Message payload preserves **`Record`** so handler sees ID/fields |
| `outputChannel` | `ordersStreamInput` | Emits Spring Messages into the flow |

**Version constraint:** **`setPollTimeout`** and **`setBatchSize`** were added in Spring Integration 5.5+; version 5.4 may require **`setStreamReceiverOptions(...)`** instead. Never mix `setStreamReceiverOptions` with those individual setters on the same bean if your version marks them mutually exclusive.

**Scaling note:** The example hardcodes `consumerName` for readability. Across multiple pods, generate **distinct, reasonably stable** consumer names per operational strategy; never copy `fulfillment-local-a` onto every instance.

### 10.3. Adapter lifecycle

`ReactiveRedisStreamMessageProducer` implements **`SmartLifecycle`**. When the Spring context starts, it subscribes/receives according to `autoStartup`. Across stops/restarts, the subscriber reconnects, yet **the consumer group's PEL must still be recovered separately** for delivered records not yet `XACK`ed.

### 10.4. Do not attach a Spring Integration Poller

This is **not** a valid configuration for this source:

~~~text
Redis Stream inbound -> Pollers.fixedDelay(2000) to simulate XREADGROUP
~~~

Reactive `StreamReceiver` already drives the read/blocking loop. Redis `pollTimeout` is completely distinct from `RedisStoreMessageSource`'s `Pollers.fixedDelay`.

## 11. Java DSL: `Redis.streamInboundChannelAdapter(...)`

To express the entire adapter in Spring Integration Java DSL, **`Redis.streamInboundChannelAdapter`** provides equivalent options:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;

@Configuration
@EnableIntegration
public class OrderStreamDslConfig {

    @Bean
    public IntegrationFlow orderStreamInboundDsl(
            ReactiveRedisConnectionFactory factory,
            FulfillmentStreamHandler handler) {

        return IntegrationFlow.from(
            Redis.streamInboundChannelAdapter(
                    factory, OrderStreamPublisher.STREAM)
                .consumerGroup("fulfillment-v1")
                .consumerName("fulfillment-local-a")
                .createConsumerGroup(false)
                .autoAck(false)
                .readOffset(ReadOffset.lastConsumed())
                .pollTimeout(Duration.ofMillis(300))
                .batchSize(10)
                .extractPayload(false))
            .handle(handler, "handle")
            .get();
    }
}
~~~

**Important:** **`OrderStreamInboundConfig`** in section 10 and **`OrderStreamDslConfig`** here are **two alternatives for a single subscriber**. Running both in the same context creates two independent consumers in the same group—do not mistake those duplicate deliveries for broker retries.

Java DSL supports **`.channel(c -> c.flux())`** for end-to-end reactive channels. The example above attaches a synchronous handler directly to illustrate **post-commit acknowledgment**; switching to a reactive flow requires tracking downstream completion timing and callback ownership carefully.

### 11.1. When to choose the bean API vs. DSL?

| `ReactiveRedisStreamMessageProducer` bean | Java DSL |
| --- | --- |
| Easy to inspect every setter in IDE/Javadocs | Concise flow wiring handlers/routers cleanly |
| Easy to wire explicit output channels and bean lifecycles | Endpoint specs sit right beside topology |
| Easy to separate transport tests from business tests | Expresses EIP flows with transformers/filters cleanly |
| Must guard against duplicate bean flows yourself | Must check API spec for your exact version |

Both use the exact same Redis `StreamReceiver` underneath; **neither adds extra automatic broker delivery guarantees**.

## 12. Payload: `extractPayload(true/false)`

A Redis stream record can be kept intact or unwrapped to only its value/fields as the Spring Message payload.

| Config | Spring Message payload | When appropriate |
| --- | --- | --- |
| **`extractPayload(true)`** (default) | Record's value (e.g., `Map`/DTO depending on serializer) | Handler only needs business fields |
| **`extractPayload(false)`** | Full Redis Stream `Record` | Handler needs stream key, Record ID, and value in one object |

Even with **`extractPayload(true)`**, the adapter populates **stream/record metadata** in Spring `MessageHeaders`. Do not try to guess message IDs by looking up an `"id"` key inside the business field map.

### 12.1. `RedisHeaders` populated by the adapter

Notable headers emitted by Spring Integration Redis Stream inbound:

| Header | Meaning |
| --- | --- |
| **`RedisHeaders.STREAM_KEY`** | Redis stream key |
| **`RedisHeaders.STREAM_MESSAGE_ID`** | Redis Stream record ID |
| **`RedisHeaders.CONSUMER_GROUP`** | Consumer group (when configured) |
| **`RedisHeaders.CONSUMER`** | Consumer name |
| **`IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK`** | ACK callback when `autoAck=false` |

Framework headers serve routing, observability, and ACKing; **never treat them as business `eventId`, authentication, or tenant authorization**.

### 12.2. Records do not necessarily contain a JSON body

When `XADD` writes fields like `eventId`/`eventType`/`orderId`, the default payload may be a deserialized **`Map`**, not a JSON String. Never force `ObjectMapper.readValue(String)` when the producer did not serialize JSON.

An alternative contract option:

~~~text
Stream fields:
  eventId = evt-order-1001
  eventType = ORDER_CREATED
  schemaVersion = 1
  payloadJson = {"orderId":"O-1001", ...}
~~~

Here the handler parses `payloadJson` cleanly and validates the schema. Never embed a JSON string inside a field and then let Jackson double-serialize it without testing raw bytes.

### 12.3. Data types through serializers

At the protocol level, Redis field values are bytes; Spring Data Redis serializers determine the Java types received. If the producer uses `StringRedisTemplate`, configure a matching String-compatible receiver or verify your version's defaults. If using **`ObjectRecord` + `HashMapper`**, enforce trusted target types, field names, and schema migration rules.

Never blindly cast every value to `String` before running a producer–consumer contract test.

## 13. Handler: commit business state, then ACK

Our handler accepts a **`Message<?>`** containing a `MapRecord`, validates the business event, commits via the service, and finally ACKs.

### 13.1. Business service interface

~~~java
public interface FulfillmentBusinessService {

    // Implementation must enforce idempotency by eventId,
    // committing durable state before returning normally.
    void applyOrderCreated(String eventId, String orderId);
}
~~~

When backed by JDBC/JPA, place transactions on the appropriate **Spring-managed service method**, with a unique constraint on `eventId` and idempotency checks. Never assume an interface guarantees transactions by itself.

### 13.2. `FulfillmentStreamHandler`

~~~java
import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.acks.SimpleAcknowledgment;
import org.springframework.integration.redis.RedisHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Service;

@Service
public class FulfillmentStreamHandler {

    private final FulfillmentBusinessService businessService;

    public FulfillmentStreamHandler(
            FulfillmentBusinessService businessService) {
        this.businessService = businessService;
    }

    public void handle(Message<?> springMessage) {
        if (!(springMessage.getPayload()
                instanceof MapRecord<?, ?, ?> record)) {
            throw new IllegalArgumentException(
                "Expected a Redis MapRecord payload");
        }

        Map<?, ?> fields = record.getValue();
        Object eventId = fields.get("eventId");
        Object eventType = fields.get("eventType");
        Object version = fields.get("schemaVersion");
        Object orderId = fields.get("orderId");

        if (!(eventId instanceof String)
                || ((String) eventId).isBlank()
                || !"ORDER_CREATED".equals(eventType)
                || !"1".equals(version)
                || !(orderId instanceof String)
                || ((String) orderId).isBlank()) {
            throw new IllegalArgumentException(
                "Invalid or unsupported order event");
        }

        Object rawAck = springMessage.getHeaders().get(
            IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK);
        if (!(rawAck instanceof SimpleAcknowledgment acknowledgment)) {
            throw new IllegalStateException(
                "Expected manual acknowledgment callback");
        }

        // Business service commits idempotent durable state.
        businessService.applyOrderCreated(
            (String) eventId, (String) orderId);

        // Only after business transaction returns successfully:
        acknowledgment.acknowledge();

        Object recordId = springMessage.getHeaders().get(
            RedisHeaders.STREAM_MESSAGE_ID);
        System.out.println("Fulfilled stream record: " + recordId);
    }
}
~~~

**The flow above assumes** field values deserialize to `String` because producer and receiver both use String serialization. If using other serializers, add the proper transformer/contract validation. This is an **illustrative example**, not a production-ready fulfillment service.

### 13.3. Why retrieve the callback from a header?

With **`autoAck(false)`** in a consumer group, the adapter places **`SimpleAcknowledgment`** in the header keyed by **`IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK`**. The business handler decides when to ACK. Never invent a custom String header `"ack=true"` expecting Redis `XACK`.

### 13.4. ACK must follow the commit milestone

The safe order is normally:

~~~text
Validate record
  -> check idempotency/eventId
  -> commit database side effect
  -> call acknowledgment.acknowledge()
~~~

If the handler throws an exception before ACKing, the record **remains pending in the PEL**. It **does not automatically re-deliver right away** just because Java threw; you need a recovery policy.

### 13.5. ACK callback is not a JDBC transaction

ACK belongs to the Redis group, while business commit belongs to the database/external service. If Redis ACK fails after DB commit:

- The record remains pending.
- A reclaimer can redeliver it.
- The idempotent service must recognize `eventId` is already `DONE` and skip duplicate side effects.
- The handler can then ACK the already-completed record during recovery.

If an ACK outcome is unknown due to a network timeout, inspect the PEL/state rather than blindly retrying side effects.

### 13.6. Never ACK before async processing completes

If a handler submits work to an executor and immediately calls `acknowledgment.acknowledge()`, Redis considers the record handled while the task sits in an in-memory queue. A process crash loses the business work.

For async processing:

- Carry the callback/record ID until the worker actually commits and ACKs afterward, **or**
- Persist to a durable inbox/job table first, ACK Redis only after the durable handoff commits, and let workers process the inbox.

Never serialize the callback object as business JSON or forward it over outbound adapters; it is a runtime handle tied to the active delivery.

## 14. Designing the business contract and versioning

For a stream shared across multiple services and application versions, define a **record schema** independent of Java class names.

### 14.1. Sample `ORDER_CREATED` contract

| Field | Wire type | Required | Rule |
| --- | --- | --- | --- |
| `eventId` | UTF-8 String | Yes | Business ID stable across retries |
| `eventType` | UTF-8 String | Yes | Allowlist: `ORDER_CREATED` |
| `schemaVersion` | Numeric string or declared type | Yes | Consumer accepts only supported versions |
| `orderId` | UTF-8 String | Yes | Validate format/length, tenant ownership |
| `occurredAt` | ISO-8601 UTC String | Recommended | Domain timestamp; do not rely solely on stream ID |
| `traceparent` | W3C Trace Context String | Optional | Observability only, grants no authorization |
| `tenantRef` | Validated reference string | Use-case dependent | Never trust producer-supplied headers/fields blindly |

Example:

~~~bash
redis-cli XADD orders:events '*' eventId evt-order-1001 eventType ORDER_CREATED schemaVersion 1 orderId O-1001 occurredAt 2026-11-23T02:00:00Z
~~~

### 14.2. Typed event envelope

Another design compatible with HTTP/Kafka/AMQP:

~~~json
{
  "eventId": "evt-order-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "orderId": "O-1001",
    "tenantRef": "T-1"
  }
}
~~~

The producer can store this envelope in a **`payloadJson` field**, alongside top-level `eventId`/`eventType`/`schemaVersion` for Redis-level inspection. When duplicating fields, enforce a **source-of-truth rule** if outer fields and the envelope disagree—fail fast or quarantine, never pick arbitrarily.

### 14.3. Do not rely on Redis Record ID for authorization

A Redis-assigned Record ID does not prove which tenant owns an order. Stream key, group, and consumer metadata do not replace authentication/authorization either. Consumers must validate inputs and verify against an authoritative business source.

### 14.4. Schema compatibility during rolling deployments

| Producer | Consumer | What to test |
| --- | --- | --- |
| v1 | v1 | Reads existing records |
| v1 | v2 | New consumer still reads v1 while supported |
| v2 | v1 | New producer emits backward-compatible data or old consumer rejects cleanly |
| v2 | v2 | New contract works end to end |
| Outer field v2, `payloadJson` v1 | Any | Conflict detected |
| Unknown `eventType` | Any | Never misrouted into privileged handlers |

Specifically, older records may sit in the stream or PEL **after deploying a new version**; test mixed-version compatibility, not only same-version pairs.

### 14.5. Sizes and limits

A Redis Stream record can carry many fields/bytes; cap payload size, field count, JSON nesting depth, string lengths, and batch sizes. Never store images, giant binary blobs, or serialized `Throwable`/Java classes in a stream when object storage references work instead.

## 15. `ErrorChannel` and errors across layers

The receive path spans multiple error boundaries:

~~~mermaid
flowchart TD
    R["Redis XREADGROUP"] --> RX["StreamReceiver"]
    RX --> DE["Deserialize Record"]
    DE --> AD["Inbound adapter"]
    AD --> C["MessageChannel"]
    C --> V["Validate contract"]
    V --> H["Business handler"]
    RX -. "Network, ACL, timeout" .-> E1["Receiver error recovery"]
    DE -. "Serializer / hash mapper" .-> E2["ErrorMessage / errorChannel"]
    V -. "Invalid version/schema" .-> E3["Business error policy"]
    H -. "DB / provider transient" .-> E3
    E1 --> OPS["Observe / alert / recover"]
    E2 --> OPS
    E3 --> OPS
~~~

### 15.1. Errors before a Spring Message is built

A record can fail **deserialization** inside `StreamReceiver`/the adapter. At that point, the service activator in `IntegrationFlow` **never receives a Spring Message**, so a handler `try/catch` cannot catch it.

Spring Integration Redis Stream inbound exposes **`errorChannel`/`onErrorResume`** paths depending on version. Under manual ACK, an **`ErrorMessage`** for a failed record can carry **`ACKNOWLEDGMENT_CALLBACK`**. The error handler must decide:

- Can the record be fixed/re-read?
- Can the raw record be written to a **durable dead-letter stream/table**?
- Should the record stay pending for operator/recovery handling?
- Should ACK run only after **proving the quarantine/rejection decision was durably saved**?

Never auto-ACK all deserialization errors merely to shrink the PEL.

### 15.2. `StreamReceiver` `onErrorResume`

Starting in Spring Integration **5.5**, APIs expose receiver options/`onErrorResume`; by default per the docs, extracted errors can be forwarded as `ErrorMessage`s to an error channel.

**Never configure an `onErrorResume` that returns an empty publisher and swallows all exceptions** when serializer/network failures must be visible; that blinds monitoring and can leave records stuck in the PEL.

### 15.3. `ErrorChannel` is not a DLQ

`ErrorChannel` is a **Spring Messaging** mechanism for routing exception/error messages. On its own, it does NOT:

- Persist raw records to durable storage.
- Track retry counts or enforce max attempts.
- Route stream records to a Redis DLQ.
- `XACK` pending entries after business commit.
- Reclaim pending entries from dead consumers.

If an error flow merely logs an exception and returns, the record **stays pending**. Conversely, if the error flow ACKs improperly, the record **disappears from the PEL** even though nothing saved it for investigation.

### 15.4. Do not apply RabbitMQ-style NACK

Redis Streams provide **`XACK`** and claim/re-read commands, not a broker-native NACK equivalent to RabbitMQ's **`basic.nack(requeue=true)`**. Under manual ACK:

- **Business success:** `XACK` via callback.
- **Transient failure:** leave pending and schedule bounded recovery/retry.
- **Permanent failure:** durably save raw record/error metadata in quarantine, then ACK original per policy.
- **Unknown outcome:** check business state/idempotency before retrying.

Never read an ACK callback interface name and assume every `REJECT`/`REQUEUE` action maps to AMQP-like Redis semantics; check the Redis adapter implementation and use Redis PEL/`XCLAIM`/`XAUTOCLAIM` for recovery.

### 15.5. Exception propagation and `DirectChannel`

With `DirectChannel`, the handler runs synchronously in the dispatch path; exceptions propagate or become `ErrorMessage`s per configuration. Yet **a Java exception does not reset the group's last-delivered ID** and does not make the record reappear on the next `XREADGROUP >`.

### 15.6. Async handlers and ACK timing

With `ExecutorChannel`/`FluxMessageChannel`, dispatch returns before business work finishes. Preserve the **exact record's ACK callback** and invoke it only after durable handoff/commit—never when the upstream send returns.

Never turn the ACK callback header into an outgoing Kafka/HTTP header; it is a runtime object with no cross-protocol contract.

## 16. Pending Entries List: inspection and recovery

Redis provides commands to inspect and process pending entries.

### 16.1. `XPENDING`

~~~bash
redis-cli XPENDING orders:events fulfillment-v1
redis-cli XPENDING orders:events fulfillment-v1 - + 10
~~~

Output includes pending counts, ID ranges, owners, idle times, and delivery counts per command form. **Never treat `XPENDING` output as a business transaction log**; it is Redis group metadata.

### 16.2. `XINFO GROUPS` and `XINFO CONSUMERS`

~~~bash
redis-cli XINFO GROUPS orders:events
redis-cli XINFO CONSUMERS orders:events fulfillment-v1
~~~

These commands help inspect group progress, consumers, pending ownership, and idle durations, yet group lag or pending counts **do not capture** trimmed records, external side effects, or duplicate business `eventId`s.

### 16.3. `XCLAIM` / `XAUTOCLAIM`

When consumer A crashes, another consumer/reclaimer can **claim pending records idle past a threshold**:

~~~bash
# Illustrative XAUTOCLAIM:
redis-cli XAUTOCLAIM orders:events fulfillment-v1 worker-reclaimer 60000 0-0 COUNT 20
~~~

Here **`60000`** is min-idle-time in milliseconds; **`0-0`** is the start cursor, and **`COUNT 20`** caps work per call. Output includes the next cursor and claimed entries per Redis version; handle cursor iteration, batching, errors, and trimmed records.

**Never run reclaim commands against production groups just to experiment**: it transfers ownership of potentially active work, risking duplicate or concurrent side effects.

### 16.4. Reclaiming does not prove the previous worker is dead

A record idle for 60 seconds can stem from:

- A crashed worker.
- A worker legitimately processing a slow task.
- A network partition or missing heartbeat.
- A handler that committed business state yet failed `XACK`.

After claiming, the record **may be reprocessed**. Enforce idempotency keys, business state checks, and fencing/lease policies when side effects are sensitive.

### 16.5. New records and pending recovery are two separate loops

~~~mermaid
flowchart TD
    START["FulfillmentService"] --> NEW["Inbound adapter<br/>XREADGROUP >"]
    START --> REC["Recovery worker<br/>XPENDING/XAUTOCLAIM"]
    NEW --> PROC["Idempotent processing"]
    REC --> PROC
    PROC --> ACK["XACK after success"]
    PROC --> ERR["Retry / durable dead-letter"]
~~~

A **`ReactiveRedisStreamMessageProducer`** consuming new group deliveries must not be assumed to **reclaim all old pending entries automatically**. Build and test a dedicated recovery worker or operational tooling when SLAs require it.

### 16.6. Trimmed pending records

The PEL may retain a delivered ID while the raw record was removed by `XTRIM`/`XDEL`/retention. `XAUTOCLAIM` handles references to deleted records differently across Redis versions. Once the payload is gone, recovery cannot reconstruct it verbatim from pending metadata alone.

Therefore, **monitor retention alongside pending idle/lag**. Never configure tiny size limits when consumers might stay offline for days.

## 17. Retries, poison records, and dead-lettering

### 17.1. Error classification

| Error | Should retry? | Handling approach |
| --- | --- | --- |
| Malformed field map / JSON | Usually no hot retry | Quarantine raw record, alert on schema |
| Unsupported `schemaVersion` | Not immediately | Compatibility policy, replay after consumer upgrade |
| Unknown tenant / `eventType` | No | Reject/forensics, inspect producer |
| Transient DB error | Bounded | Exponential backoff, keep pending / recover |
| Provider 429/503 | Bounded | Retry/backoff/circuit breaker |
| Provider timeout, outcome `UNKNOWN` | Needs reconciliation | Avoid repeating side effects blindly |
| Redis connectivity failure | Transport recovery | Does not imply business rolled back |
| Record trimmed before recovery | Cannot replay verbatim from stream | Reconcile from source of truth |

### 17.2. An application-defined error stream

Redis Streams lack built-in **RabbitMQ DLX routing**. An application can create a dedicated Redis Stream:

~~~text
orders:events:dead
~~~

Each dead-letter record captures:

~~~json
{
  "originalStream": "orders:events",
  "originalRecordId": "1795410000123-0",
  "eventId": "evt-order-1001",
  "reason": "UNSUPPORTED_SCHEMA_VERSION",
  "failedAt": "2026-11-23T03:30:00Z",
  "attempts": 4
}
~~~

**Recommended sequence:** durably write and verify the **dead-letter payload/error state**, then `XACK` the original. If dead `XADD` succeeds yet original `XACK` fails, recovery might dead-letter a second time; deduplicate DLQ entries by `eventId`/`originalStream`/`recordId`.

### 17.3. Retrying is not immediately re-reading in a loop

If a malformed record always throws, a recovery worker continuously `XAUTOCLAIM`ing and reprocessing it creates a hot loop. Implement:

- A retry budget and durable attempt count.
- Delay/backoff, `nextAttemptAt`, or a retry scheduler.
- Transient vs. permanent error classification.
- Final dead state once attempts are exhausted.
- Operator replay tooling after fixing root causes.

Redis PEL's delivery count does not replace a full business retry ledger, especially when republishes create new record IDs or distinct failure reasons must be tracked.

### 17.4. When ACK fails after dead-lettering succeeded

If a record is `XADD`ed to the dead stream and the connection drops before `XACK`ing the original:

- The original remains pending.
- The next reclaim sees `eventId` was already dead-lettered.
- The recovery worker can **`XACK` the original without creating a duplicate dead-letter** using durable state.

This requires **idempotent dead-letter handling**, not merely a `try/catch` around `XACK`.

### 17.5. `ErrorChannel` must have clear ownership

Assign explicit owners:

| Component | Responsibility |
| --- | --- |
| Inbound adapter | Read/deserialize and emit Spring Messages |
| Business handler | Validate, idempotent commit, ACK on success |
| Error handler | Classify malformed raw records, durable dead-letter or leave pending |
| Recovery worker | Claim eligible pending records, enforce retry policy |
| Operator | Investigate/replay dead jobs with audit trail |

If handler retries, `errorChannel` republishes, and reclaimer claims act simultaneously on the same failure without shared state, one event can trigger multiple side effects.

## 18. Retention, `XTRIM`, `XDEL`, and replayability

A Redis Stream **should not grow forever** unless you knowingly accept unbounded memory/storage growth. Base retention on **processing SLAs, worst-case downtime, replay/audit needs, and Redis durability**.

### 18.1. Length-based `XTRIM`

~~~bash
# Keep approximately at most 100000 records (syntax per Redis version):
redis-cli XTRIM orders:events MAXLEN '~' 100000

# Inspect:
redis-cli XLEN orders:events
redis-cli XINFO STREAM orders:events
~~~

**`MAXLEN ~`** performs approximate trimming for Redis efficiency. It **does not guarantee the stream still contains every record unconsumed by a group**.

### 18.2. `XADD MAXLEN`

Publishers can also apply trimming on append:

~~~bash
redis-cli XADD orders:events MAXLEN '~' 100000 '*' eventId evt-1002 eventType ORDER_CREATED schemaVersion 1 orderId O-1002
~~~

**Never blindly copy `100000` into production.** Estimate capacity:

~~~text
Required retained records ≈ peak append rate (records/second)
                          x recovery window (seconds)
                          x safety factor
~~~

For example, 100 records/s peak with a 3-hour recovery target ≈ 1,080,000 records **before adding safety margin, replay, audit logs, and memory overhead**. For bursty workloads, size from measured peaks rather than averages.

### 18.3. Trimming can affect the PEL

`XTRIM` or `XDEL` can remove **payload records** from the stream while PEL metadata remains, depending on Redis version/command options. When that happens:

- `XPENDING` may still reference the ID.
- Recovery has no raw fields left to replay the business record.
- `XAUTOCLAIM` handles missing-record references per Redis version.
- Another slower group that hadn't read the record loses it.

Because newer Redis versions have options controlling reference handling on delete/trim, **verify the exact semantics of your running Redis server**. Never assume a single default retains history across all versions.

### 18.4. `XACK` does not delete records; `XDEL` does not ACK business work

| Command | Typical effect |
| --- | --- |
| `XADD` | Appends a new record |
| `XREAD`/`XREADGROUP` | Reads; for groups, delivers and adds to PEL |
| `XACK` | Acknowledges ID for a group, clears pending |
| `XDEL` | Deletes record from stream per policy |
| `XTRIM` | Bounds retention by pruning older records |
| `XGROUP DESTROY` | Destroys the entire group state |

**Never use `XDEL` instead of `XACK`** to “clear the PEL,” and never run `XGROUP DESTROY` on a live group just to wipe pending entries without recovery.

### 18.5. Retention across multiple groups

If one stream serves a fast `fulfillment` group and a slow `analytics` group, trimming based on `fulfillment` speed will drop records `analytics` still needs. Size retention for the **slowest required group**, offline windows, and safety margin.

### 18.6. Replay does not mean repeating side effects

An operator may replay old records into a new group or stream, yet business services must:

- Preserve the **original `eventId`** when representing the same event.
- Check whether it was already processed.
- Distinguish corrected data from verbatim replay.
- Record an audit/replay reason.
- Never re-send emails or re-charge cards merely because a Redis record was un-ACKed.

## 19. Redis persistence, replication, and failover

Redis Streams live in Redis memory/storage; durability depends on **RDB/AOF, `fsync`, replication, Sentinel/Cluster, and infrastructure policies**.

### 19.1. `XADD` returning an ID does not prove absolute durability

If a primary returns success and loses power before flushing/replicating per required guarantees, records can be lost during failover within RPO. Never assume:

~~~text
XADD returned ID == every replica persisted permanently
~~~

For high-value business events, choose proper Redis persistence/durability policies, run failover tests, and consider a durable producer outbox.

### 19.2. Group state must also be protected

Consumer group metadata and PELs live in Redis. If group state is lost on rollback/failover or operator reset, consumers may re-read or skip records depending on offsets. A business **idempotency ledger** independent of Redis protects against duplicates even if Redis group history changes.

### 19.3. Redis Cluster

A Redis Stream lives on the shard determined by its key's hash slot. If scripts/transactions touch multiple keys (main stream, dead stream, state hash), Redis Cluster requires keys in multi-key atomic operations to map to **the same hash slot** when enforced by the command/script.

Example namespace:

~~~text
orders:{fulfillment}:events
orders:{fulfillment}:dead
orders:{fulfillment}:state
~~~

The **`fulfillment`** hash tag co-locates those keys on one slot, yet **does not create a distributed transaction** with a DB or Kafka. Do not force every stream in the company onto one slot, or you create a hotspot.

### 19.4. Sentinel/failover and unknown outcomes

An `XACK`/`XADD` may succeed on the server while the client times out before receiving the response. When an outcome is **`UNKNOWN`**, never assume it failed to apply. Check:

- Did `XACK` remove the ID from the PEL?
- Was `eventId` recorded in the business DB?
- Was the producer outbox record marked dispatched?
- Was a duplicate `XADD` created?

Retry using **idempotency and reconciliation**, not blind sleeps and unconditional resends.

### 19.5. Consumer names and failover

Redis consumer names are not an automatic Kubernetes health registry. When pod names change across deploys, old consumers' PEL entries do not transfer automatically; a **reclaimer** must find stale owners and claim them.

## 20. Backpressure, `batchSize`, and concurrency

Reactive `StreamReceiver` supports demand-driven consumption, yet **backpressure on a `Flux`** does not solve every queueing or reliability issue.

### 20.1. Load diagram

~~~mermaid
flowchart LR
    P["XADD 500 rec/s"] --> R["Redis Stream"]
    R --> AD["StreamReceiver COUNT 20"]
    AD --> C["MessageChannel"]
    C --> EX["Executor / reactive pipeline"]
    EX --> DB["Business DB<br/>100 rec/s"]
    DB -. "ACK" .-> R
~~~

When producers write 500 records/s while business processing handles 100 records/s, backlogs grow. Measure **group lag, pending count, in-flight work, and age**; raising `batchSize` or consumer concurrency will not help if the DB is already saturated.

### 20.2. `batchSize` is a Redis read hint

`batchSize=20` caps how many records Redis returns per `COUNT`, not total in-flight tasks across executors/threads or how many records ACK together. If processing 20 records concurrently, each record must **manage its own ACK/error outcome**.

### 20.3. Consumer concurrency inside one group

Multiple **consumer names** in one group compete for new records:

~~~text
Group fulfillment-v1:
  worker-a
  worker-b
  worker-c
~~~

Redis distributes new records across active `XREADGROUP` consumers. It guarantees neither strict round-robin nor business completion order. If `orderId` `O-1001` has events A then B, concurrent workers can finish B before A.

### 20.4. Ordering and versioning

If business logic requires per-`orderId` ordering:

- Include a **business sequence/version** in the payload.
- Validate the current version during database updates.
- Partition work by key or serialize per-entity processing when needed.
- Account for retries causing older events to arrive late.
- Never use Redis Stream IDs as a global business commit order across multiple producers.

A stream has ordered IDs, yet **does not guarantee completion order of side effects** across concurrent group consumers.

### 20.5. Blocking code in reactive paths

Avoid running slow blocking JDBC calls directly on Redis reactive I/O threads whenever possible. Use an appropriate worker execution model or bounded scheduler, yet tie **the ACK call** to business completion—never to task submission.

### 20.6. Output channel impacts ACK timing

| Channel | Characteristics | Risk if ACK is misplaced |
| --- | --- | --- |
| `DirectChannel` | Synchronous dispatch | Blocking handler stalls transport thread |
| `ExecutorChannel` | Submits task to executor | ACKing right after submit loses work on crash |
| `QueueChannel` | Buffers Spring Messages for downstream poller | Non-durable by default; ACKing before durable handoff loses work |
| `FluxMessageChannel` | Reactive handoff/demand | Completion and ACK must track the exact record/reactive signal |

A `QueueChannel` backed by a persistent `MessageStore` can provide durable handoff, provided **messages and needed metadata serialize safely** and ACK runs only after persistence succeeds. Never serialize a live native ACK callback as long-lived payload data; use stream key/`recordId` and explicit recovery.

### 20.7. Redis Streams prefetch is not RabbitMQ prefetch

Do not look for a RabbitMQ **`prefetchCount`** knob on Redis Stream inbound. Redis Streams use `XREADGROUP COUNT`/`BLOCK` and `StreamReceiver` demand/backpressure; PEL and consumer groups follow their own model. Copying mental models from AMQP/JMS/Kafka gives a false sense of in-flight control.

## 21. Lifecycle: start, stop, restart, and rolling deployments

### 21.1. Startup

~~~mermaid
sequenceDiagram
    participant APP as Spring Application
    participant E as Stream inbound endpoint
    participant R as Redis
    participant H as Business handler
    APP->>E: Initialize / start
    E->>R: Connect / verify consumer group
    E->>R: XREADGROUP BLOCK/COUNT
    R-->>E: New record
    E->>H: Spring Message + metadata
    H->>R: XACK after business commit
~~~

**`autoStartup=true`** only tells the endpoint to start with the context; it does not prove the Redis group connected properly, records parsed cleanly, or pending recovery finished. Enforce readiness/health checks per policy.

### 21.2. Graceful stop

Recommended sequence:

1. Stop accepting new records or drain the subscription per lifecycle.
2. Allow in-flight handlers to finish within a bounded timeout.
3. Persist durable business state and ACK completed items.
4. Leave un-ACKed records in the PEL for the recovery worker.
5. Never delete the consumer group or stream key during deployments.
6. After restart, inspect `XPENDING` and stale consumers.

If tasks run longer than the shutdown grace period, some records remain pending—which is precisely why **recovery and idempotency** exist.

### 21.3. Scaling up and down

Keep consumer group names **stable per workload** and consumer names **unique per active instance**. When scaling down, inspect pending entries owned by retired consumers. Never confuse active pod count with pending-owner entries retained by Redis.

### 21.4. Group creation and migrations

When upgrading versions/schemas:

- Keep the existing group to continue group progress.
- Create a new group with an **intentional offset** when replay is required.
- Never delete the old group before reconciling pending entries and retention.
- Define how old consumers and old record schemas are handled.
- If a group is created at `$`, pre-existing records will not be delivered as new group messages under that initial offset.

### 21.5. Network errors while reading

`StreamReceiver` can recover connections/reads depending on client and `onErrorResume` policy. However, **a recovered connection** does NOT mean:

- Dead workers' pending records were auto-claimed.
- Trimmed records were replayed.
- Consumer group offsets rewound automatically.
- ACK callbacks for pre-crash work re-ran automatically.

Verify each condition in tests and monitoring.

## 22. Security: ACLs, tenant boundaries, and serializers

Redis Streams sit outside the Spring Integration app boundary, so received fields and metadata **are not inherently trusted input**.

### 22.1. Redis ACLs and network

Separate permissions by role:

| Actor | Functionally required permissions |
| --- | --- |
| Producer | `XADD` on permitted streams |
| Consumer group worker | `XREADGROUP`, `XACK` scoped to allowed stream/group |
| Recovery worker | `XPENDING`/`XCLAIM`/`XAUTOCLAIM` for allowed group |
| Admin/bootstrap | `XGROUP CREATE`, retention config when authorized |
| Operator | `XINFO`, inspect errors, audited replay; no default `FLUSHDB`/`XGROUP DESTROY` |

Redis ACL rules vary by Redis version and the exact commands/scripts issued. Never grant admin permissions to every worker just so **`setCreateConsumerGroup(true)`** works.

In production, enforce TLS, credential rotation, secret managers, network/port restrictions, and audits on delete/trim/group resets.

### 22.2. Tenant and `eventType` do not authenticate permissions

Suppose a producer writes:

~~~text
eventType=ORDER_CREATED
tenantRef=another-tenant
orderId=O-999
~~~

The consumer must not treat `tenantRef` as proof the caller is authorized to create fulfillment for that tenant. Verify **order ownership** and policies against an authoritative source or a verified producer identity/channel authorization. Stream groups and Redis key names do not replace business authorization.

### 22.3. Serializer trusted types

When stream writers lie outside the same trust boundary, avoid native Java deserialization and unrestricted polymorphic type mapping. Use:

- String field values or JSON/schema formats.
- Allowlisted `HashMapper` target DTOs.
- Maximum key/value lengths.
- JSON nesting/array depth limits.
- Validation of field enums, IDs, and numeric ranges.
- Explicit schema migrations.

Never enable arbitrary Jackson default typing on fields written by external producers.

### 22.4. Redis stream field names are not Spring headers

A Redis record field named **`"acknowledgmentCallback"`** does not become a trusted `SimpleAcknowledgment` object. The ACK callback header is injected by the **adapter** into the Spring Message at runtime. Avoid unconditionally mapping raw record fields into sensitive internal headers.

### 22.5. PII, logging, and dead-letter retention

Never log entire records containing emails, shipping addresses, or tokens. For dead-letter streams, enforce retention limits, read access controls, encryption per infrastructure standards, data deletion policies, and replay audits. **DLQs often hold more sensitive error data than normal streams.**

### 22.6. Rate limiting and resource abuse

A producer may `XADD` too rapidly or push oversized records, exhausting Redis memory, consumer PELs, and downstream services. Enforce upstream rate limits, size validation, stream retention, bounded batch/concurrency, quotas, and alerts.

## 23. Monitoring: lag, pending, ACK, and business outcomes

Never build dashboards around **`XLEN`** or `StreamReceiver` delivery counts alone. A consumer group has multiple stages to track.

| Signal | Purpose | Limitation |
| --- | --- | --- |
| **`XADD` rate** | How many records producers append | Not unique business event count |
| **`XLEN`** | Records currently in stream | Not PEL count or group lag |
| **Group last-delivered ID** | Group read progress | Can run ahead of business commits |
| **Consumer group lag** | Estimated undelivered records | Can be incomplete under trim/delete; version-dependent |
| **`XPENDING` total** | Delivered records not yet ACKed | Does not show whether business committed |
| **Oldest pending idle** | Detects stale consumers | Could be a valid slow job |
| **`XACK` rate** | Acknowledgment rate | Does not prove business commit if `autoAck` is premature |
| **Business completion rate** | Records completing side effects | Most important for SLAs |
| **Duplicate skipped rate** | Idempotency protecting retries | May spike after crashes/reclaims |
| **DLQ ingress** | Poison/exhausted records | Needs an owner and replay policy |
| **Error rates** | Serializer, schema, Redis I/O, DB, external APIs | Must be categorized |
| **Processing latency** | Receive → durable commit → ACK time | Track p95/p99 and timeouts |

### 23.1. Illustrative metrics

~~~text
redis_stream_inbound_received_total{stream="orders-events",group="fulfillment-v1"}
redis_stream_inbound_decode_failed_total{reason="INVALID_UTF8"}
redis_stream_inbound_ack_total{result="success"}
redis_stream_inbound_ack_failed_total
redis_stream_inbound_pending_oldest_seconds
redis_stream_inbound_reclaimed_total
redis_stream_inbound_group_lag
fulfillment_event_committed_total
fulfillment_event_duplicate_skipped_total
fulfillment_event_failed_total{reason="INVALID_SCHEMA"}
fulfillment_event_processing_duration_seconds
~~~

These are **application-instrumented metric names**, not all emitted out of the box by Spring Integration. Use low-cardinality labels like stream alias, group, and bounded reason enums; never put arbitrary `eventId`/`recordId`/`tenantId` in metric labels.

### 23.2. Operational Redis CLI commands

~~~bash
redis-cli XINFO STREAM orders:events
redis-cli XINFO GROUPS orders:events
redis-cli XINFO CONSUMERS orders:events fulfillment-v1
redis-cli XPENDING orders:events fulfillment-v1
redis-cli XLEN orders:events
~~~

These commands inspect metadata; running them in production must respect ACLs, audits, and query cost. On large streams/groups, use bounded command forms rather than unbounded scans.

### 23.3. Pending does not shrink

If business successes rise while `XPENDING` keeps growing:

1. Is `autoAck` truly `false`?
2. Does the handler receive `ACKNOWLEDGMENT_CALLBACK`?
3. Does the handler invoke `acknowledge()` after commit?
4. Is Redis `XACK` failing or timing out with unknown outcomes?
5. Do stream, group, and `recordId` match?
6. Are old records owned by dead consumer names waiting for reclaim?

Do not merely add workers to shrink pending counts; if workers never ACK, pending entries keep piling up.

### 23.4. Low lag yet slow business progress

When `XREADGROUP` pulls fast, the group's last-delivered ID stays near the stream tail while thousands of records sit **pending**. Monitor both **group lag** and **PEL/in-flight/business completion**. A dashboard showing near-zero group lag can falsely report “no backlog.”

### 23.5. Low ACK rate while PEL is also low

Check whether the adapter has **`autoAck(true)`** ACKing prematurely or is running standalone `XREAD` instead of `XREADGROUP`. Without a consumer group, **a group's `XPENDING` does not track standalone reads**.

### 23.6. Trace correlation

Carry `eventId` and `traceparent` in record fields or propagation contracts and log them in structured logs per policy. Stream ID/group/consumer can be logged as metadata, yet never use trace context for authorization or business deduplication.

## 24. Testing: unit, contract, and Redis integration

A stream inbound test suite must verify **real Redis with groups/PEL/`XACK`**, not just unit-test a `Map`-handling service method.

### 24.1. Test matrix

| Test | Setup | Assertion |
| --- | --- | --- |
| **`XADD` happy path** | Producer appends valid record | Redis returns `RecordId`, `XRANGE` shows fields |
| **Consumer group creation** | Create group at `0-0` before records | `XREADGROUP` receives backlog per contract |
| **Group starts at `$`** | Existing backlog, group created at tail | Does not receive pre-existing backlog as new records |
| **Standalone `XREAD`** | No `consumerName` set | Creates no group pending entries |
| **Manual ACK** | `autoAck=false`, handler commits | PEL shrinks after callback/ACK |
| **No ACK** | Handler throws before callback | Record remains in PEL, not auto-redelivered by `>` |
| **Auto ACK** | `autoAck=true`, handler fails after receive | Demonstrates window where record is ACKed despite failed side effect |
| **Payload extraction** | `extractPayload=true` | Handler gets value/fields; stream headers still present |
| **Full Record** | `extractPayload=false` | Handler gets `Record` with ID and value |
| **Header contract** | Group `XREADGROUP` | `RedisHeaders.STREAM_KEY`/`STREAM_MESSAGE_ID`/`CONSUMER_GROUP`/`CONSUMER` valid |
| **Serializer mismatch** | Producer/receiver formats differ | Conversion error surfaced |
| **Malformed field** | Invalid `schemaVersion` | Error path triggered; record not accidentally ACKed |
| **Bad deserialization** | Payload breaks mapper | `ErrorChannel` follows proper ACK/DLQ policy |
| **Business idempotency** | Two records sharing `eventId` | Side effect commits once per business key |
| **Crash before commit** | Kill worker after `XREADGROUP` | PEL retains record; reclaim recovers |
| **Crash after commit** | Kill before `XACK` | Reclaim delivers duplicate; handler skips and ACKs |
| **Crash after `XACK`** | Check record still in stream | `XACK` does not `XDEL` |
| **Two consumers same group** | `worker-a`/`worker-b` run `XREADGROUP` | New records distributed, not broadcast to both |
| **Two separate groups** | `fulfillment` and `analytics` | Each group maintains independent progress |
| **Pending reclaim** | `worker-a` dies, idle > threshold | `XAUTOCLAIM` transfers ownership properly |
| **Long-running job** | Worker still running as idle climbs | Policy prevents duplicate side effects |
| **Poison record** | Invalid schema across attempts | Durable dead-letter saved; original ACKed per policy |
| **DLQ and ACK failure** | Dead `XADD` succeeds, `XACK` times out | Dead-letter deduplicated on retry |
| **Trim while pending** | `XTRIM` un-ACKed record | Exposes risk of losing raw payload |
| **Retention/backlog** | Consumer offline long | Records remain if retention suffices and can be read later |
| **Redis failover** | Restart test Redis | Group/PEL/records survive per configured RPO |
| **`ReadOffset.latest`** | Standalone polling with pause | Does not promise reading every record |
| **`ReadOffset.lastConsumed`** | Group + manual ACK | Reads new records per group; pending needs separate reclaim |
| **Async Channel** | ACK before worker finishes | Exposes work-loss risk on crash |
| **Backpressure** | Producer outpaces handler | PEL/lag/backlog grows cleanly without OOM |
| **Wrong `consumerName`** | Two replicas share name | Observe ownership/operational confusion |
| **Wrong stream/group** | Misconfigured Redis key | No messages received or clear Redis error |
| **ACL denied** | Redis user lacks `XREADGROUP`/`XACK` | Clear adapter/error metrics, no fake ACK |
| **Cross-slot Lua** | Redis Cluster with keys in different slots | Does not silently partially execute |
| **Rolling schema change** | v1/v2 producers & consumers | Compatibility, poison policy, and replay verified |

### 24.2. Testing manual ACK with Redis CLI

On test Redis:

~~~bash
redis-cli XGROUP CREATE test:orders:events test-fulfillment 0-0 MKSTREAM
redis-cli XADD test:orders:events '*' eventId evt-test-1 eventType ORDER_CREATED schemaVersion 1 orderId O-1
redis-cli XREADGROUP GROUP test-fulfillment worker-a COUNT 1 STREAMS test:orders:events '>'
redis-cli XPENDING test:orders:events test-fulfillment
~~~

Note the Redis ID returned by `XREADGROUP`, e.g., **`1795410000123-0`**, then ACK that exact record:

~~~bash
redis-cli XACK test:orders:events test-fulfillment 1795410000123-0
redis-cli XPENDING test:orders:events test-fulfillment
redis-cli XRANGE test:orders:events - +
~~~

After `XACK`, the pending ID leaves the group's PEL, yet the record **remains visible in `XRANGE`**. This test cleanly distinguishes `XACK` from `XDEL`.

### 24.3. Testing startup timing

With a consumer group created at `0-0` and sufficient retention, `XADD` **before the Java adapter starts** is still readable via `XREADGROUP`. This differs from Redis Pub/Sub.

However, if the group is created at `$` after events already exist, that backlog is skipped per group position. Tests must control **ordering: create stream, create group, `XADD`, start adapter**—never rely on random `Thread.sleep` calls.

### 24.4. `CountDownLatch` capture helper

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.messaging.Message;

public final class StreamMessageCapture {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<Message<?>> captured =
        new AtomicReference<>();

    public void accept(Message<?> message) {
        captured.set(message);
        latch.countDown();
    }

    public Message<?> awaitMessage() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError(
                "Redis stream message not received");
        }
        return captured.get();
    }
}
~~~

**This is only a helper**, not a full integration test. Wire the helper into an isolated `IntegrationFlow`, spin up a test Redis server/container, create the group with an explicit offset, configure matching serializers, and verify ACK/PEL with Redis commands or Spring Data Redis APIs.

Never point a test queue/stream/group at one shared with production consumers or competing workers.

## 25. Business idempotency: effectively-once processing

Redis Stream + manual ACK protects **delivered-but-unacknowledged** state, yet does not govern transactions in a database or third-party service. You need a **business idempotency boundary**.

### 25.1. Durable inbox in `FulfillmentService`

Example table:

~~~sql
CREATE TABLE fulfillment_inbox (
    event_id       VARCHAR(80) PRIMARY KEY,
    event_type     VARCHAR(80) NOT NULL,
    order_id       VARCHAR(80) NOT NULL,
    status         VARCHAR(20) NOT NULL,
    processed_at   TIMESTAMP NULL
);
~~~

Inside one JDBC transaction:

1. Validate `eventId`/`orderId` and authorization.
2. Rely on the unique constraint on **`event_id`** to handle races across workers.
3. If the event is already `DONE`, skip new business side effects and return idempotent success.
4. Otherwise, create the shipment or persist durable work intent.
5. Commit inbox + business state together.
6. **Only after the transaction commits cleanly**, ACK the Redis record.

This illustrates the design, not full production DDL/indexes/locking. On PostgreSQL you might use **`INSERT ... ON CONFLICT`**; on other RDBMSs choose compatible syntax and test transaction isolation under concurrent workers.

### 25.2. A DB transaction does not cover external APIs

Suppose the handler calls a `ShippingProvider` API:

~~~text
Send HTTP createShipment(idempotencyKey=evt-order-1001)
  -> timeout
~~~

You do not know whether the provider created the shipment. Retrying without an idempotency key or status lookup can create two shipments. Safeguards:

- Pass a provider-supported **business idempotency key**.
- Persist request/response state durably.
- On `UNKNOWN` responses, query status before retrying.
- Never ACK Redis right after submitting an async request before a durable handoff milestone.

### 25.3. ACKing a duplicate can still be the right action

An `XADD` record is redelivered after a crash. The Fulfillment DB shows `eventId` is already `DONE`. The handler:

~~~text
Validate eventId
  -> find DONE in durable inbox
  -> skip external side effect
  -> ACK Redis record
~~~

This is an **idempotent consumer**: Redis provides at-least-once delivery, while business side effects do not repeat for the same `eventId`.

### 25.4. Same `eventId`, different content

If two stream records carry the same `eventId` yet different `orderId` or tenant values, never silently ignore them as valid duplicates. Store a **payload hash/version** or verify business identity; when the same ID has conflicting content, raise a security/contract alert or quarantine for investigation.

### 25.5. Never purge the inbox too early

If the inbox retains `eventId`s for 24 hours while the stream allows replays after seven days, consumers forget `DONE` events and re-execute side effects. **Idempotency ledger retention must be greater than or equal to the maximum duplicate/replay window**, or backed by a stronger business uniqueness rule.

## 26. Real-world architectural scenarios

### 26.1. Case A – Orders → Fulfillment, every record must be processed

~~~mermaid
flowchart LR
    O["OrderService DB"] --> OB[("Transactional outbox")]
    OB --> PUB["Outbox publisher"]
    PUB --> STR[("Redis Stream<br/>orders:events")]
    STR --> G["Group fulfillment-v1"]
    G --> SI["Stream inbound adapter"]
    SI --> INBOX[("Fulfillment inbox + DB")]
    INBOX --> ACK["XACK after commit"]
    ACK -.-> STR
    G --> REC["Pending reclaimer"]
    REC --> INBOX
~~~

**Sound design:** Stable group, manual ACK, durable inbox, PEL recovery, and ample retention. Even if `XADD` succeeded while the outbox publisher timed out and sent a duplicate `eventId`, `FulfillmentService` deduplicates it.

**Avoid:** `autoAck=true` and treating `XPENDING=0` as proof shipments were created.

### 26.2. Case B – One stream, two independent groups

**Requirement:** Both Fulfillment and Analytics must receive `OrderCreated`.

~~~text
Redis Stream orders:events
    |
    +-- Group fulfillment-v1 --> Fulfillment workers A/B
    |
    +-- Group analytics-v1   --> Analytics workers X/Y
~~~

Each group has **independent read progress, PEL, and ACK**. Slow analytics need not block fulfillment, yet **stream retention must cover both groups**. Never delete raw records just because fulfillment ACKed while analytics still needs them.

### 26.3. Case C – SFTP import → Redis Streams

**Requirement:** An SFTP CSV holds 10,000 orders; a parser emits events to a stream.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter<br/>poller"] --> PAR["CSV parser/validation"]
    PAR --> DB[("Import DB + outbox")]
    DB --> XADD["Redis Stream outbound<br/>XADD"]
    XADD --> STR[("orders:events")]
    STR --> RIN["Redis Stream inbound"]
    RIN --> H["Idempotent processor"]
    H --> DB
~~~

The **SFTP poller** scans source files, while **`StreamReceiver`** reads stream records. Do not substitute a Redis store polling adapter or Redis Pub/Sub subscriber as though they had PEL/`XACK`.

Never mark the entire file import `DONE` just because 10,000 records were `XADD`ed; track **business completion** per event, or explicitly define the import milestone as “successfully queued.”

### 26.4. Case D – Redis Stream inbound → Kafka outbound

A bridge might run:

~~~text
Redis XREADGROUP
  -> Spring Message
  -> Kafka producer
  -> Kafka broker ACK
  -> Redis XACK
~~~

**Two failure windows:**

- Redis `XACK` before Kafka ACK → Redis thinks it's done while Kafka may not have saved it: **event loss**.
- Kafka ACK succeeds then Redis `XACK` fails → record stays pending and the bridge resends: **duplicate Kafka event**.

Order operations as **Kafka publish confirmed before Redis ACK**, while Kafka consumers deduplicate by `eventId` or use a durable bridge/outbox/inbox. **Kafka's idempotent producer** has its own scope and does not form an atomic transaction across a Redis consumer group and Kafka broker.

### 26.5. Case E – Redis Stream inbound → AMQP outbound

Same principle:

~~~text
XREADGROUP -> transform -> RabbitTemplate/outbound adapter
           -> publisher confirm/return policy
           -> XACK after durable handoff
~~~

Publisher confirms, mandatory returns, unroutable messages, and RabbitMQ consumer business ACKs are **separate milestones**. For reliable handoffs, verify queue/broker routing and enforce `eventId`/idempotency; never `XACK` Redis merely because outbound `MessageChannel.send()` returned without throwing in every configuration.

### 26.6. Case F – Best-effort cache invalidation

If you only emit a “cache changed” signal needing no backlog or PEL, Redis Pub/Sub inbound can be simpler than Streams. If you need post-downtime replay or audited event IDs, Streams fit better—at the cost of **retention, consumer groups, ACKs, and recovery**. Choose by SLA, not throughput alone.

### 26.7. Case G – Multi-tenant shared stream

Sharing one stream across tenants reduces key count yet widens the trust boundary:

- Consumers must validate `tenantRef` per policy.
- Never treat `tenantRef` as authorization proof.
- Rate-limit per tenant/producer.
- Prevent one noisy tenant from starving others.
- Consider per-tenant stream/group isolation when SLAs or compliance demand it.

Never create unbounded per-tenant consumer groups without managing group metadata/PELs and retention.

## 27. Troubleshooting: stream consumer doesn't receive or doesn't ACK

### 27.1. No records received despite Redis `XLEN > 0`

Check in order:

1. Do publisher and consumer target the same Redis **host/port/database/cluster**?
2. Is the **stream key** exact (case-sensitive)?
3. Does the group exist? Was it created at **`0-0` or `$`**?
4. Is the adapter running **standalone `XREAD` or `XREADGROUP`**? Is `consumerName` set?
5. Is **`ReadOffset`** set to `latest` or `lastConsumed`?
6. Are the records sitting in the existing **PEL** rather than new deliveries?
7. Are Redis ACLs valid for `XREADGROUP`/`XACK`?
8. Can the serializer decode the fields?
9. Does `MessageChannel` have an active subscriber/handler?
10. Is the handler throwing errors or is `errorChannel` swallowing exceptions?
11. Did Redis retention trim records before the consumer read them?

**`XLEN > 0` does not mean the group will receive all those records**; the group offset may already be at the end or records may sit pending under another consumer.

### 27.2. Records arrive yet pending keeps growing

Common causes:

- `autoAck(false)` is set, yet the handler never invokes the callback.
- Handler throws before business commit.
- ACK is called, yet Redis I/O fails or times out.
- Async business work never completes.
- An old consumer name died, leaving pending entries owned by an inactive consumer.
- Schema failures keep records sitting in limbo for investigation.

Inspect **`XPENDING`, `XINFO CONSUMERS`, business state by `eventId`, and error metrics**—do not simply add more concurrent consumers.

### 27.3. Handler runs twice for the same event

Possible causes:

- Producer re-`XADD`ed the same `eventId` under a new Record ID.
- Recovery reclaimed a record after a crash or ACK failure.
- Two integration paths/handlers subscribe to one event.
- An operator replayed an old event.
- The group was reset or its offset changed.

Fix: **idempotent business keys**, tracing `recordId` and producer attempts. Never claim Redis Streams guarantee exactly-once without idempotent side-effect handling.

### 27.4. Serializer errors never appear in the business handler

The failure occurred **before the adapter built a Spring Message**. Inspect `StreamReceiver` `onErrorResume`/`errorChannel`, trusted serializers, producer format, and ACK policy on `ErrorMessage`s—don't just add `try/catch` inside the service activator.

### 27.5. New consumer skips old records

The group may have been created at **`$`** or a standalone receiver used **`latest()`**. Create a new group from **`0-0`** only when replay is intentional and idempotency is ready. Never arbitrarily reset a live production group's offset with unresolved pending entries.

### 27.6. `XAUTOCLAIM` fails to rescue records

Check:

- Has `min-idle-time` elapsed?
- Are stream key and group right?
- Is cursor iteration completing?
- Were the records trimmed/deleted?
- Is another consumer reclaiming concurrently?
- Does the reclaimer actually commit and ACK after claiming?

### 27.7. Redis group lag near 0 while CPU/DB are overloaded

The group delivered nearly the whole stream, leaving a huge PEL/in-flight backlog. Measure business latency, ACK rate, and oldest pending age. Raising `batchSize` for slow workers worsens pending backlogs and memory pressure.

### 27.8. `XACK` returns 0

`XACK` returns `0` when the ID is no longer pending in that group (already ACKed, wrong group/ID, etc.). Never retry business side effects just because `XACK` returned `0`; verify metadata and business state.

### 27.9. Redis consumer group `BUSYGROUP`

When a group already exists, `XGROUP CREATE` with the same name returns `BUSYGROUP`. That usually means provisioning already occurred; never drop and recreate the group. Test `setCreateConsumerGroup(true)` idempotency on your version.

### 27.10. Handler gets a `Map` without the Redis Record ID

With `extractPayload(true)`, payload is the value; Stream ID resides in **`RedisHeaders.STREAM_MESSAGE_ID`** inside Spring `MessageHeaders`. To get the raw record itself, switch to **`extractPayload(false)`** and verify types/serializers. Never cast a `Map` payload to `MapRecord`.

### 27.11. Works locally, fails when scaled out

A hardcoded `consumerName` collides across replicas. A newly created group might initialize at an unexpected offset. Serializers/ACLs may differ between local and production Redis. Test with **two consumers in the same group**, pending ownership, shutdowns, and reclaiming—never only a single instance.

## 28. Common misconceptions

**“Redis Stream inbound is the same as Redis Pub/Sub inbound.”** No: Streams persist records per retention and support groups/PEL/`XACK`; Pub/Sub notifications have no subscriber backlog.

**“Redis Stream inbound reads a Redis List with `BRPOP`.”** No: it uses **`XREAD`/`XREADGROUP`** against a Redis Stream key.

**“Redis store inbound and stream inbound both use `Pollers.fixedDelay`.”** Store inbound is a polling `MessageSource`/view; stream inbound runs a **`Reactive StreamReceiver`** loop.

**“`XADD` succeeding means `FulfillmentService` finished processing.”** `XADD` only writes the record to Redis; business processing is a separate milestone.

**“Redis Record ID is the `OrderCreated` `eventId`.”** Record IDs and business `eventId`s have different scopes; `XADD` retries assign new Record IDs.

**“`ReadOffset.latest()` is always safe for reading history.”** It targets new records and can skip items during standalone gaps/dead time; use explicit offsets/checkpoints.

**“`ReadOffset.lastConsumed()` automatically recovers all PEL records.”** It does not claim other consumers' pending entries; you need explicit recovery.

**“`consumerName` doesn't matter in a group.”** `consumerName` owns PEL entries and must be managed across scaling and restarts.

**“Each replica should create a fresh consumer group.”** Each group gets its own copy of records rather than sharing work within one group, while bloating group metadata.

**“Two consumer groups split a stream evenly.”** Different groups track independent progress; competing consumption happens **within the same group**.

**“Consumer groups give exactly-once business delivery by default.”** Redeliveries occur after crashes/ACK loss; idempotency is still required.

**“`autoAck=true` is safe as long as the handler uses `@Transactional`.”** Auto-ACK fires independently before DB commits and does not enlist in JDBC transactions.

**“Manual ACK means calling `XACK` as soon as `MessageChannel.send` returns.”** ACK only after durable business commit/handoff, never after async submission.

**“Un-ACKed records automatically reappear on the next `XREADGROUP >`.”** Pending records do not revert to new deliveries; read pending entries or reclaim them.

**“`XACK` deletes data from the Redis Stream.”** `XACK` only updates the group's PEL; it is not `XDEL`/`XTRIM`.

**“`XDEL` acts as ACK for all groups.”** `XDEL` deletes the raw record; per-group ACK state is separate and deleting early drops data for other groups.

**“Streams keep records forever despite `XTRIM`/`MAXLEN`.”** Retention evicts records, including payloads needed for pending recovery.

**“Pending count = unprocessed records.”** Pending covers delivered-but-unACKed records, including ones already committed where `XACK` failed.

**“Group lag = 0 means zero work remaining.”** PEL/in-flight may be huge; measure business completion too.

**“Kafka `prefetchCount` or RabbitMQ `basic.nack` work identically in Redis Streams.”** Redis uses `COUNT`/`BLOCK`/PEL/`XACK`/`CLAIM` and has no AMQP NACK semantics.

**“The ACK callback is a custom Redis field.”** It is a Spring Integration runtime header, not an arbitrary field `XADD`ed by producers.

**“Setting a String header `ack=true` makes Redis ACK.”** Only invoking the framework callback or Redis `XACK` API actually ACKs.

**“Logging in `ErrorChannel` quarantines the record.”** Logging does not build a durable DLQ; save raw error state explicitly and decide on ACKing.

**“Redis Streams have a DLX like RabbitMQ.”** Applications can build a dead stream, yet Redis provides no automatic DLX routing out of the box.

**“`XAUTOCLAIM` only reclaims truly unprocessed records.”** It can reclaim a record whose business state already committed while `XACK` failed; enforce `eventId`/idempotency.

**“Min idle > 60 seconds proves the old worker is dead.”** The old worker may simply be slow; enforce ownership, leases, fencing, and idempotent side effects.

**“During Redis failover, every `XADD`/`XACK` either clearly succeeds or clearly fails.”** Connection timeouts produce `UNKNOWN` outcomes.

**“Setting `batchSize=100` guarantees 100 business commits.”** `COUNT` only caps read size, not transaction or ACK batching.

**“Reactive adapter guarantees all downstream handlers are non-blocking.”** If a handler runs blocking JDBC/HTTP calls, the flow still blocks.

**“Putting the ACK callback in an in-memory `QueueChannel` is durable.”** The callback is a runtime object, and default `QueueChannel` is non-durable.

**“A consumer group created at `$` reads prior backlog.”** Groups created at the tail only see new records; use `0-0` to read retained history.

**“Every record visible in `XRANGE` will be delivered to every group.”** Group offsets and read strategies differ and may skip older records as new deliveries.

**“Two records with different stream IDs must be two distinct business events.”** They can carry the same `eventId` from a producer retry or replay.

**“A shared stream's `tenantRef` field is enough to authorize access.”** `tenantRef` is untrusted input requiring verification against trusted sources.

**“Running `XGROUP DESTROY` fixes stuck pending entries harmlessly.”** Destroying a group erases group progress and PELs; plan migrations and recovery instead.

**“Testing the happy path proves at-least-once.”** Test crashes, group offsets, PEL recovery, trimming, duplicates, unknown ACKs, and rolling schemas.

## 29. Production design checklist for Redis Stream inbound

| Category | Questions to answer |
| --- | --- |
| **Use case** | Do you need replay/PEL/ACK, or is best-effort Pub/Sub enough? |
| **Stream key** | Are Redis instance/db/namespace and `STREAM` key type right? |
| **Producer contract** | Are `XADD` fields, `eventId`, `eventType`, `schemaVersion`, and serializer clear? |
| **Reactive source** | Do `ReactiveRedisConnectionFactory`/`StreamReceiver` match version and lifecycle? |
| **Adapter wiring** | Is only one intended `Redis.streamInboundChannelAdapter` or `ReactiveRedisStreamMessageProducer` active? |
| **Mode** | Standalone `XREAD` or `XREADGROUP`? Is `consumerName` set? |
| **Group** | Is the group stable, created at `0-0` or `$`, and pre-provisioned? |
| **Offset** | Does `ReadOffset.latest`/`lastConsumed`/`from(id)` fit the backlog policy? |
| **Manual ACK** | Is `autoAck=false` set and does the handler receive `ACKNOWLEDGMENT_CALLBACK`? |
| **Business boundary** | Does `XACK` happen after durable commit/handoff, never after async submit? |
| **Payload** | Are `extractPayload(true/false)` and `MapRecord`/`ObjectRecord` tested? |
| **Headers** | Do `RedisHeaders.STREAM_KEY`/`STREAM_MESSAGE_ID`/`CONSUMER_GROUP`/`CONSUMER` have expected types? |
| **Serialization** | Do producer and receiver agree on key/field/value serializers and schema? |
| **Schema validation** | Is there a clear error policy for malformed/unsupported data? |
| **PEL recovery** | Who runs `XPENDING`/`XAUTOCLAIM`? Are min idle, cursor, batch, owner, and metrics set? |
| **Idempotency** | Are unique `eventId` and business transaction/durable inbox enforced? |
| **Unknown outcomes** | Do `ACK`/`XADD`/provider timeouts verify state before retrying? |
| **Retry** | Where are attempts, backoff, and final failed state persisted durably? |
| **Dead-letter** | Is the DLQ a durable stream/table, ACKing original only after safe persistence? |
| **Retention** | Do `XTRIM`/`MAXLEN` retain enough backlog/pending data for the slowest group? |
| **Concurrency** | How are out-of-order completions across concurrent consumers handled via versions? |
| **Backpressure** | Are `batchSize`, reactive demand, handler capacity, and executor bounds measured? |
| **Lifecycle** | How do start/stop, draining, stale consumer names, and restart recovery work? |
| **Redis HA** | Are persistence, replication, Cluster/Sentinel, failover, and RPO/RTO verified? |
| **Security** | Are TLS, Redis ACLs, stream/group permissions, and tenant authorization enforced? |
| **Monitoring** | Are group lag, `XPENDING`, oldest idle, `XACK` rate, business `DONE`, and DLQ tracked? |
| **Testing** | Tested on real Redis with crash-before-commit, crash-after-commit, reclaim, trim, and duplicates? |
| **Compatibility** | Tested old producer / new consumer, v1 pending records, and API/serializer versions? |

### 29.1. If you remember only three rules

1. **Consumer group progress is not business completion**: a delivered record may sit uncommitted in the PEL.
2. **Manual ACK after durable commit**, paired with idempotency because crashing after commit before `XACK` creates duplicates.
3. **PEL recovery and retention are separate**: pending entries require controlled reclaiming, and raw records must still exist to recover.

### 29.2. When should you NOT use Redis Streams?

If you only need cache invalidation backed by TTL/reconciliation without backlogs, Pub/Sub has lower operational overhead. If you need multi-year event-sourcing/audit retention, extreme throughput, or complex cross-datacenter durability/transactions, evaluate Kafka/JMS/AMQP/database logs for your infrastructure.

**No transport eliminates the need to design idempotency and business transactions** in distributed systems.

### 29.3. Minimum bar for a trustworthy demo

~~~text
1. Test Redis, stream key, and group created at offset 0-0.
2. Producer XADDs eventId/eventType/schemaVersion/orderId.
3. Stream inbound with autoAck=false + unique consumerName.
4. Handler validates schema + durable inbox / unique eventId.
5. ACK callback invoked after commit.
6. Recovery worker runs XPENDING/XAUTOCLAIM on stale records.
7. Retention sized safely and pending/business completion monitored.
8. Integration tests simulating crashes on both sides of commit/XACK.
~~~

Without recovery, a demo may pass the happy path while pending records after a crash **risk being stranded indefinitely**.

## 30. Self-check questions

1. What responsibility does the Redis Stream inbound adapter hold at the boundary between Redis and Spring Integration?
2. How do Redis Streams differ from Pub/Sub in record retention and replay?
3. How does Redis List blocking `POP` differ from `XREADGROUP` regarding pending/ACK tracking?
4. Does Redis store inbound return a `RedisStore` view or a Stream Record?
5. How does Spring Integration Redis Stream inbound use Spring Data Redis's `StreamReceiver`?
6. What components does a Redis Stream record contain besides its field/value map?
7. Why can't a Redis Record ID serve as the sole business `eventId` in all cases?
8. What does a successful `XADD` prove, and what does it NOT prove?
9. How does standalone `XREAD` differ from `XREADGROUP`?
10. When do multiple consumers in one group split work vs. multiple independent groups reading the same stream?
11. What is the PEL? When does a record enter the PEL?
12. How does `XACK` affect the PEL vs. the raw Redis Stream record differently?
13. If a handler commits to the DB and crashes before `XACK`, what can happen during recovery?
14. If `autoAck` runs before DB commit and the JVM dies, what is the risk?
15. Why is manual ACK + idempotency more important than simply enabling manual ACK alone?
16. In what scenarios do `ReadOffset.latest()` and `ReadOffset.lastConsumed()` differ?
17. Why can standalone `latest` miss records between polls during dead time/backpressure?
18. How does `XGROUP CREATE` with `0-0` differ from `$` when a backlog already exists?
19. Does a group's last-delivered ID equal the count of business-committed events?
20. When `worker-a` dies, why doesn't `worker-b` calling `XREADGROUP` with `>` automatically pick up `worker-a`'s pending entries?
21. What information does `XPENDING` inspect?
22. Why does `XAUTOCLAIM` require `min-idle-time` and a cursor?
23. Why doesn't a long-idle record prove the old worker is dead?
24. When reclaiming a record that already committed business state yet wasn't ACKed, how should the handler respond?
25. Which `RedisHeaders` does Spring Integration automatically attach to the Spring Message?
26. What is `IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK`? Does it reside inside Redis record fields?
27. How does `extractPayload(true)` differ from `extractPayload(false)`?
28. If a producer writes field values using `StringRedisTemplate` while a consumer uses a different serializer, where can errors occur?
29. Why can deserialization errors occur before the handler receives a Spring Message?
30. Does `ErrorChannel` automatically provide a Redis DLQ, retry budget, and `XACK`?
31. For permanent schema errors, in what order should records move to quarantine before `XACK`?
32. Why can dead `XADD` succeeding while original `XACK` fails produce a duplicate dead-letter?
33. Does `batchSize=20` put all 20 records into a single business transaction?
34. When producers outpace consumers, which metrics reveal whether backlog sits in new messages vs. the PEL?
35. When group lag is near 0, how can thousands of tasks still remain unfinished?
36. Do Redis Streams provide RabbitMQ's `basic.nack(requeue=true)` with identical semantics?
37. How can Redis `XTRIM` impact the payload of a pending record?
38. How do `XACK`, `XDEL`, and `XTRIM` differ?
39. Why must retention be sized for the slowest required consumer group rather than the fastest?
40. During Redis failover, how can an `XADD`/`XACK` timeout yield an `UNKNOWN` outcome?
41. What does Redis Cluster require when running Lua/multi-key commands across multiple keys?
42. When scaling from one to three pods, how must group names and consumer names be managed?
43. Where must a Redis Stream inbound handler using `ExecutorChannel` place its ACK?
44. When is a durable inbox needed before ACKing?
45. Which races/duplicates does a unique constraint on `eventId` protect against?
46. If the same `eventId` arrives with two different payloads, how should it be handled?
47. In a bridge, if Kafka ACK succeeds yet Redis `XACK` fails, what is the consequence?
48. If Redis `XACK` runs before Kafka ACK, what can be lost?
49. Why is tracing metadata not authentication/authorization?
50. Which integration test proves manual ACK shrinks the PEL at the right moment?
51. Which integration test proves `XACK` does not delete raw stream records?
52. Which integration test proves a dead worker's pending record can be reclaimed?
53. Which integration test proves a stable `eventId` protects business state from duplicates?
54. What risks arise from creating a group at `$` while a stream already contains data?
55. What should you check if `XPENDING` grows even while business `DONE` increases?
56. How should a stream shared by `Fulfillment` and `Analytics` groups manage retention and ACLs?
57. When should a Redis Stream be treated as an intermediate transport rather than the source of truth?
58. If a record is trimmed before PEL recovery, where do you recover the original payload from?
59. Why can't Redis group offsets alone establish exactly-once side effects?
60. Design a minimal Redis Stream inbound flow with manual ACK, durable business state, and pending recovery.

## 31. References and version scope

Official sources to consult before adopting code in a project:

- [Spring Integration – Redis Support, Redis Stream Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/redis.html): Java DSL, `ReactiveRedisStreamMessageProducer`, `autoAck`, consumer groups, stream headers, error channels.
- [Spring Integration – ReactiveRedisStreamMessageProducer Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/redis/inbound/ReactiveRedisStreamMessageProducer.html): Constructors, `ReadOffset`, ACK configuration, `StreamReceiverOptions`, and version-specific setters.
- [Spring Integration – RedisStreamInboundChannelAdapterSpec Javadoc](https://www.springframework.org/spring-integration/docs/7.1.x-SNAPSHOT/api/org/springframework/integration/redis/dsl/RedisStreamInboundChannelAdapterSpec.html): Java DSL methods such as `consumerGroup`, `consumerName`, `autoAck`, and `createConsumerGroup`.
- [Spring Data Redis – Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): `XREAD`/`XREADGROUP`, `StreamReceiver`, `ReadOffset`, `XACK`, PEL, and backpressure considerations.
- [Redis – Streams data type](https://redis.io/docs/latest/develop/data-types/streams/): `XADD`, consumer groups, delivery semantics, and retention.
- [Redis – XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): Reclaiming pending entries, min idle, cursors, and version-dependent results.

**Version boundaries to note:** Spring Integration introduced Reactive Redis Stream inbound in **5.4**; **5.5** added receiver options/direct setters such as `pollTimeout`, `batchSize`, and error resume. Redis servers/clients also vary by version for commands like `XAUTOCLAIM` and trimming/reference options. In real implementations, pick a **consistent BOM**, verify APIs for your active version, and **run integration tests against real Redis**. This lesson does not substitute for project-specific builds, tests, or deep Content QA.

## Summary

The **Redis stream inbound adapter** brings **Redis Stream records** through **Spring Data Redis Reactive `StreamReceiver`** into a **Spring Integration `MessageChannel`**. Depending on configuration, it reads via **`XREAD`** or **`XREADGROUP`**; with consumer groups, Redis maintains a **Pending Entries List (PEL)** and supports per-record **`XACK`**. That is the fundamental difference from Redis Pub/Sub notifications, destructive Redis List `POP`s, and `RedisStoreMessageSource` collection views.

**Manual ACK** is vital when business reliability matters. In Spring Integration, **`autoAck(false)`** injects **`ACKNOWLEDGMENT_CALLBACK`** into Spring `MessageHeaders`; handlers must **validate → commit durable business state → ACK**. Crashing before commit leaves the record pending; crashing after commit before `XACK` causes reprocessing. You therefore need **stable `eventId`s, unique constraints/idempotency, a pending reclaimer, and error/dead-letter policies**—not just a consumer group flag.

Throughput and durability depend on far more than `batchSize` or consumer counts. Design **group creation offsets, `ReadOffset`, retention/`XTRIM`, `StreamReceiver` backpressure, graceful shutdown, Redis persistence/failover, ACLs, schema compatibility, tracing, and monitoring of PEL/lag/business outcomes**. `XACK` is not `XDEL`, group last-delivered ID is not business commit, and Stream ID does not replace `eventId`.

When integrating Redis Streams with File/SFTP, HTTP, JMS, AMQP, Kafka, or databases in the **SPRING_INTEGRATION_ADAPTERS** module, always distinguish **written to stream**, **delivered to group**, **business-committed**, and **ACKed/cleaned up**. A reliable system needs recovery policies for every crash window, a durable source of truth, and tests covering happy paths as well as duplicates, replays, trimming, and failovers. Choose Redis Stream inbound when you truly need **record history, consumer-group delivery, and controlled recovery**—not merely because the adapter name contains the word “stream.”
