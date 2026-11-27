# Redis queue outbound adapter

## Learning Objectives

After this lesson, you will be able to:

- Explain how the **Redis queue outbound channel adapter** takes a Spring Integration Message from a `MessageChannel` and **pushes a value into a Redis List** using `LPUSH` or `RPUSH`.
- Accurately distinguish Redis queue outbound from Redis **Pub/Sub outbound (`PUBLISH`)**, **store outbound (collection writes)**, **Stream outbound (`XADD`)**, and **queue outbound gateways (request–reply)**.
- Pick **`LPUSH`/`BRPOP`** or **`RPUSH`/`BLPOP`** to preserve FIFO; recognize that pushing and popping on the same end yields stack-like behavior.
- Configure **`RedisQueueOutboundChannelAdapter`** and **`Redis.queueOutboundChannelAdapter(...)`** with `RedisConnectionFactory`, serializer, `extractPayload`, `leftPush`, and `queue`/`queue-expression`.
- Write **UTF-8 JSON** conforming to `eventId`, `schemaVersion`, `attempt`, and business ID contracts; align serializers with Redis queue inbound.
- Understand the boundaries separating **enqueued**, **dequeued**, **business-committed**, and **ACKed**; recognize item-loss risk after destructive `POP`.
- Design **idempotency**, bounded retries, outboxes/reconciliation, poison-item handling, ACLs, monitoring, lifecycle, and recovery on Redis/client failures.
- Test queue direction, payload bytes, dynamic queue routing, competing consumers, duplicates, Redis failovers, and crash windows against real Redis.

## 1. The problem: sending work from Spring Integration to a Redis List

Suppose **CatalogService** receives a new image over HTTP or SFTP. The service does not want to generate thumbnails synchronously on the request thread. After saving the original image and metadata, it creates a **thumbnail job** for **ImageWorker** to process:

~~~text
Redis key: catalog:{thumbnail}:pending
Payload:
{
  "eventId": "evt-thumb-1001",
  "eventType": "THUMBNAIL_REQUESTED",
  "schemaVersion": 1,
  "productId": "P-1001",
  "imageVersion": 5,
  "objectKey": "tenant-a/products/P-1001/v5/original.jpg"
}
~~~

Flow:

~~~mermaid
flowchart LR
    SRC["HTTP / SFTP / File inbound"] --> VALID["Validate + persist metadata"]
    VALID --> OUT["Spring Integration<br/>MessageChannel"]
    OUT --> AD["Redis queue outbound<br/>RedisQueueOutboundChannelAdapter"]
    AD -->|"LPUSH"| REDIS[("Redis List<br/>catalog:thumbnail:pending")]
    REDIS -->|"BRPOP"| IN["Redis queue inbound"]
    IN --> HAND["ImageWorker<br/>thumbnail handler"]
    HAND --> DB[("Product DB + object storage")]
~~~

The **Redis queue outbound adapter** is the **producer-side** endpoint: it receives a Spring Message, selects a Redis List key, serializes the target value, and executes a push command. It **does not wait for `ImageWorker` to finish**, return a thumbnail, or generate acknowledgments. Once the data is written to the List, the producer finishes its **enqueue** responsibility under the contract.

This lesson belongs to the **Adapter Redis** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module focuses on connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s, alongside File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. Here the focus is **pushing work items into a Redis List**—never mistaking a Redis List for an ACK-capable message broker simply because an adapter was attached.

## 2. Nature of Redis Lists: `LPUSH`, `RPUSH`, `BLPOP`, `BRPOP`

A Redis List holds an ordered sequence of values from **left/head** to **right/tail**. Core commands:

| Command | Effect | Removes item from List? |
| --- | --- | --- |
| `LPUSH key value` | Prepends item on the **left** | No |
| `RPUSH key value` | Appends item on the **right** | No |
| `LPOP key` | Pops item from the **left** | **Yes** |
| `RPOP key` | Pops item from the **right** | **Yes** |
| `BLPOP key timeout` | Blocks and pops from the **left** | **Yes** when item received |
| `BRPOP key timeout` | Blocks and pops from the **right** | **Yes** when item received |
| `LLEN key` | Counts items remaining in List | No |
| `LRANGE key start stop` | Inspects a range (diagnostics) | No |

### 2.1. `LPUSH` paired with `BRPOP` yields FIFO

Suppose the producer sends A, B, C:

~~~text
LPUSH A        [ A ]
LPUSH B        [ B, A ]
LPUSH C        [ C, B, A ]
BRPOP          [ C, B ]  -> A
BRPOP          [ C ]     -> B
BRPOP          [ ]       -> C
~~~

The item pushed **first** is popped first, assuming **no out-of-contract producers/consumers interact** and speaking strictly of **List pop order**, not completion order.

### 2.2. `RPUSH` paired with `BLPOP` also yields FIFO

~~~text
RPUSH A        [ A ]
RPUSH B        [ A, B ]
RPUSH C        [ A, B, C ]
BLPOP          [ B, C ]  -> A
BLPOP          [ C ]     -> B
BLPOP          [ ]       -> C
~~~

This fits well when integrating with an external worker whose contract expects **`BLPOP`**.

### 2.3. Pushing and popping the same end produces LIFO

~~~text
LPUSH A, LPUSH B, LPUSH C -> [ C, B, A ]
BLPOP -> C, then B, then A
~~~

**You cannot simply set `leftPush(true)` and assume FIFO.** You must also verify whether the receiving side uses **`rightPop(true)`** or **`rightPop(false)`**.

### 2.4. Defaults of the two Spring Integration adapters

Per the Spring Integration Redis documentation:

- Redis **queue outbound** defaults to **`leftPush=true`**.
- Redis **queue inbound** defaults to **`rightPop(true)`**.
- Pairing both defaults produces a **FIFO queue by pop order**.
- The `leftPush`/`rightPop` options were added in Spring Integration **4.3**.

| Outbound producer | Inbound consumer | Popped item order |
| --- | --- | --- |
| `leftPush(true)` → `LPUSH` | `rightPop(true)` → `BRPOP` | **FIFO** |
| `leftPush(false)` → `RPUSH` | `rightPop(false)` → `BLPOP` | **FIFO** |
| `leftPush(true)` → `LPUSH` | `rightPop(false)` → `BLPOP` | **LIFO** |
| `leftPush(false)` → `RPUSH` | `rightPop(true)` → `BRPOP` | **LIFO** |

With two parallel consumers, Redis atomically pops each item to **one** consumer, yet A might take 10 seconds while B takes 1 second: **completion order is no longer FIFO**.

## 3. A Redis List queue is not Redis Pub/Sub, Stream, or gateway

| Model | Outbound action | When worker is offline | Processing contract |
| --- | --- | --- | --- |
| **Redis queue outbound** | `LPUSH`/`RPUSH` into a **List** | Unpopped items stay in the List | Competing consumers, no native List `POP` ACK |
| Redis Pub/Sub outbound | `PUBLISH` to topic | Notifications are dropped for offline subscribers | Best-effort broadcast |
| Redis Stream outbound | `XADD` record to Stream | Records remain within retention | Record IDs, consumer groups/PEL/`XACK` when used properly |
| Redis store outbound | Writes to List/Set/ZSet/Map/Properties | State persists per Redis persistence/TTL | State mutation, not an automatic work claim |
| Redis queue outbound gateway | Sends request and awaits reply over Redis queue protocol | Depends on timeout/recovery | Request–reply with custom correlation |

### 3.1. Queue outbound is a one-way adapter

~~~mermaid
sequenceDiagram
    participant C as CatalogService
    participant O as Redis queue outbound
    participant R as Redis List
    participant W as ImageWorker
    C->>O: send(Message<Job JSON>)
    O->>R: LPUSH catalog:thumbnail:pending JSON
    R-->>O: Redis command result
    O-->>C: Handler returns
    W->>R: BRPOP catalog:thumbnail:pending
    R-->>W: Job JSON (removed from List)
    W->>W: Business processing
    Note over C,W: No response from ImageWorker back to producer
~~~

If the producer must send a request and await the resulting thumbnail URL, choose a **request–reply gateway** or a correlated API/async callback rather than expecting `QueueOutboundChannelAdapter` to generate replies.

### 3.2. Redis Lists have no native pending/ACK

Once **`BRPOP`** returns an item to a worker, the item **has left the List**. If the worker dies right afterward, Redis does not return it to pending automatically. A successful `LPUSH` alone **does not close the consumption-side loss window**.

### 3.3. Queue inbound is message-driven

Spring Integration Redis queue inbound runs a **listener task / blocking pop**; it **does not need a separate Spring Integration poller**. Thus:

~~~text
Redis queue outbound: MessageChannel -> Redis List PUSH
Redis queue inbound:  Redis List blocking POP -> MessageChannel
~~~

This differs from **Redis store inbound**: that source receives a **`RedisStore` view** via a poller instead of popping an item.

## 4. Components and options of the queue outbound adapter

Implementation class:

~~~java
org.springframework.integration.redis.outbound.RedisQueueOutboundChannelAdapter
~~~

In Java DSL:

~~~java
org.springframework.integration.redis.dsl.Redis
~~~

Key options:

| Option | Default | Role |
| --- | --- | --- |
| `queue` | Required (or expression) | Fixed Redis **List key** name |
| `queue-expression` | Alternative to `queue` | SpEL evaluating the Redis key as messages arrive |
| `connection-factory` | `RedisConnectionFactory` | Redis connection |
| `serializer` | Depends on payload & config | Serializes value to bytes for `LPUSH`/`RPUSH` |
| `extract-payload` | **`true`** | Pushes payload only or full Spring `Message` |
| `left-push` | **`true`** | `LPUSH` if true; `RPUSH` if false |
| `input channel` | Configured channel name | Spring `MessageChannel` feeding the handler |

**`queue` and `queue-expression` are mutually exclusive.** When using `queue-expression`, the incoming `Message` is the **root** for evaluation. Never take raw Redis keys from external clients without validation.

### 4.1. Default serializer must be understood properly

Spring Integration documentation notes that the default is normally **`JdkSerializationRedisSerializer`**, except when the payload is a **`String`** and no serializer is specified, the framework may pick **`StringRedisSerializer`**. Two different payload types passing through the same adapter **should not be assumed to share one wire format** without explicit configuration.

**Recommendation:** For cross-service JSON Strings, explicitly configure **`StringRedisSerializer`** on outbound and a matching deserializer on inbound. Never leave serializer selection as an implicit detail across Spring Boot/Spring Integration upgrades.

### 4.2. `extractPayload=true` is the default

When `true`, the Redis List stores only the serialized **`message.getPayload()`**. Spring `MessageHeaders` like `replyChannel`, `errorChannel`, `ID`, and trace context **are not placed into the List**.

When `false`, the endpoint serializes **the entire Spring `Message`**; the receiving side must agree on format/deserializer and verify that `Message`/headers are serializable and trusted. Avoid this as the default cross-service event mechanism.

## 5. Dependencies and `RedisConnectionFactory`

In a Spring Boot Maven project with compatible dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-redis</artifactId>
    </dependency>
</dependencies>
~~~

Redis configuration **for local/test only**:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

Production must configure TLS, Redis ACLs, credentials from a secret manager, network isolation, Sentinel/Cluster, retries/timeouts, and memory policies. Property names depend on Spring Boot version; use your BOM and actual configuration metadata when deploying.

### 5.1. `RedisConnectionFactory` is only transport

**`RedisConnectionFactory`** provides Redis connections. It does not create Redis Lists, poll queues, serialize POJOs to JSON, or guarantee thumbnails were generated. `RedisQueueOutboundChannelAdapter` uses the factory to push when a Spring Message arrives.

### 5.2. Redis List keys are created on push

Normally, when `LPUSH`/`RPUSH` targets a **nonexistent** key, Redis creates the List containing the pushed element. Unlike JMS destinations or RabbitMQ exchanges/bindings, no pre-provisioning is required. However:

- If the key already exists with a **different Redis type**, the command fails with **`WRONGTYPE`**.
- Redis ACLs may reject writing that key.
- Redis memory/`maxmemory` policies may fail writes or evict keys.
- Another service might have set a TTL, causing the key/list to vanish over time.

### 5.3. A Redis List key is not a Redis channel name

A Redis key named **`catalog:{thumbnail}:pending`** is a Redis List value, not a Pub/Sub channel of the same name. Calling **`LPUSH`** emits nothing to `SUBSCRIBE`; workers must use **`BRPOP`/`BLPOP`** or the Redis queue inbound adapter.

## 6. Designing the thumbnail job payload

For communication between `CatalogService` and `ImageWorker`, use a **job envelope** with a stable business ID and explicit schema.

~~~json
{
  "eventId": "evt-thumb-1001",
  "eventType": "THUMBNAIL_REQUESTED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "tenantRef": "tenant-a",
  "productId": "P-1001",
  "imageVersion": 5,
  "objectKey": "tenant-a/products/P-1001/v5/original.jpg"
}
~~~

### 6.1. `eventId` and Spring `MessageHeaders.ID` are different

| Field | What is it for? |
| --- | --- |
| **`eventId`** | Idempotency, retries, and auditing across services |
| **`eventType`** | Selecting the right business handler |
| **`schemaVersion`** | Validating/upgrading the payload contract |
| **`productId` + `imageVersion`** | Preventing stale tasks from overwriting newer image outputs |
| **`objectKey`** | Authorized object storage reference |
| **Spring `MessageHeaders.ID`** | Runtime message ID internal to the integration flow |

Spring's Message ID changes whenever a Spring Message is recreated or retried. **Never use it as a business `eventId`** when deduplicating across restarts.

### 6.2. Why not store the whole image in the Redis List?

Redis Lists live in Redis memory (subject to persistence/memory limits). Pushing multi-megabyte images inside each item causes:

- Memory pressure and replication/AOF overhead.
- Latency/network spikes during serialization, push, and pop.
- Cluttered inspection and dead-letter tools.
- Heavy decoding overhead on workers.

Instead, store images in **access-controlled object storage** and send **`objectKey`/ID/version** in the job. Consumers must still verify tenant ownership, content type, size, and path namespace before reading files.

### 6.3. Version contract

A worker running `schemaVersion=1` may receive jobs enqueued before a new deploy, or vice versa. Because queues buffer backlogs while workers are offline, rolling deployments must account for **older payloads still sitting in Redis**. Never remove required fields or redefine `imageVersion` without a migration/compatibility policy.

### 6.4. Job identity and retries

If a producer times out on `LPUSH` and retries, the same `eventId` can appear **twice in the Redis List**. Consumers need an idempotency ledger or unique business key; Redis Lists enforce no item uniqueness.

## 7. Java DSL: `Redis.queueOutboundChannelAdapter(...)`

Example configuring a flow that accepts a JSON String on **`thumbnailJobsOutbound`** and writes via **`LPUSH`** to **`catalog:{thumbnail}:pending`**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class ThumbnailRedisQueueOutboundConfig {

    public static final String QUEUE = "catalog:{thumbnail}:pending";

    @Bean
    public MessageChannel thumbnailJobsOutbound() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow thumbnailRedisQueueOutboundFlow(
            RedisConnectionFactory factory) {
        return IntegrationFlow.from("thumbnailJobsOutbound")
            .handle(Redis.queueOutboundChannelAdapter(QUEUE, factory)
                .serializer(new StringRedisSerializer())
                .extractPayload(true)
                .leftPush(true))
            .get();
    }
}
~~~

**Effect:** a `String` payload is serialized to UTF-8 bytes and **`LPUSH`**ed onto the Redis List key. There is no consumer reply, and it is not created as a Redis Stream record.

**Version check:** Factory/spec methods are documented in Spring Integration Redis docs and Javadocs. For versions with DSL changes, check your BOM, API spec, and compile before production; **`RedisQueueOutboundChannelAdapter(String, RedisConnectionFactory)`** with `setSerializer`/`setExtractPayload`/`setLeftPush` is the documented bean API counterpart.

### 7.1. Why declare a `DirectChannel`?

`DirectChannel` passes Spring Messages synchronously to the subscribed handler on the caller's thread. If Redis writes fail, exceptions propagate to the caller so upstream can react. Yet **`send` returning does not mean a business worker finished**, as the worker may not even have popped the item yet.

### 7.2. Fixed queue name

**`QUEUE`** is a **Redis List key**. The **`{thumbnail}`** braces demonstrate a Redis Cluster hash tag (useful later if multi-key atomic commands need the same slot). Hash tags **do not make `LPUSH` more durable** and are not Redis Pub/Sub channel patterns.

### 7.3. `extractPayload=true`

If the Spring Message carries headers like **`tenantId`, `traceId`, `correlationId`, `replyChannel`**, the outbound adapter in this mode **does not transmit headers as an envelope**. Include needed fields inside a validated JSON schema instead of blindly serializing all runtime Message headers.

### 7.4. `leftPush=true` must pair with `rightPop=true`

Setting **`leftPush(true)`** configures the producer. **`rightPop(true)`** belongs to the Redis queue inbound consumer. One side using defaults does not guarantee the other side uses the matching direction—especially when workers are external Node.js/Python processes.

## 8. Producer service: building JSON and sending the Spring Message

Use a typed DTO for business data and serialize explicitly at the outbound boundary:

~~~java
import java.time.Instant;

public record ThumbnailRequested(
        String eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String tenantRef,
        String productId,
        long imageVersion,
        String objectKey) {
}
~~~

Producer service using Jackson `ObjectMapper`:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailJobPublisher {

    private final ObjectMapper objectMapper;
    private final MessageChannel thumbnailJobsOutbound;

    public ThumbnailJobPublisher(
            ObjectMapper objectMapper,
            @Qualifier("thumbnailJobsOutbound")
            MessageChannel thumbnailJobsOutbound) {
        this.objectMapper = objectMapper;
        this.thumbnailJobsOutbound = thumbnailJobsOutbound;
    }

    public void enqueueNewImage(
            String tenantRef,
            String productId,
            long imageVersion,
            String objectKey) {

        if (tenantRef == null || tenantRef.isBlank()
                || productId == null || productId.isBlank()
                || imageVersion <= 0
                || objectKey == null || objectKey.isBlank()) {
            throw new IllegalArgumentException("Invalid thumbnail job");
        }

        ThumbnailRequested job = new ThumbnailRequested(
            "evt-thumb-" + UUID.randomUUID(),
            "THUMBNAIL_REQUESTED",
            1,
            Instant.now(),
            tenantRef,
            productId,
            imageVersion,
            objectKey);

        try {
            String json = objectMapper.writeValueAsString(job);
            boolean accepted = thumbnailJobsOutbound.send(
                MessageBuilder.withPayload(json).build());
            if (!accepted) {
                throw new IllegalStateException(
                    "Outbound channel rejected thumbnail job");
            }
        }
        catch (JsonProcessingException e) {
            throw new IllegalArgumentException(
                "Cannot serialize thumbnail job", e);
        }
    }
}
~~~

**Crucial note on `eventId`:** This example generates a UUID for **each new business request**. When retrying the same request after an unknown `LPUSH` result, **keep the exact same `eventId`**. Production code should generate/persist `jobId`/`eventId` inside the business transaction or outbox and retry from that record—never call a UUID-generating method again and turn a retry into a brand-new event.

### 8.1. Serialize explicitly rather than passing raw POJOs

With **`StringRedisSerializer`**, sending a `ThumbnailRequested` POJO directly causes a serializer type mismatch. Serializing to a JSON String before sending to the channel keeps the producer–consumer contract language-independent. You may use an `IntegrationFlow` transformer instead of the service, as long as conversion is unambiguous.

### 8.2. `ObjectMapper` must support `java.time`

Spring Boot usually auto-configures Jackson's `JavaTimeModule` when relevant dependencies are present, yet verify version and `Instant` serialization formatting. If the mapper lacks support for your time type, **fail before enqueueing**—do not assume Redis failed.

### 8.3. Avoid logging full `objectKey`/PII indiscriminately

Log `eventId`, `eventType`, authorized `productId`, and outcomes; never log credentials, signed URLs, emails, or tenant secrets from job payloads.

## 9. Java bean: `RedisQueueOutboundChannelAdapter` and `@ServiceActivator`

Without Java DSL, declare **`RedisQueueOutboundChannelAdapter`** directly as a `MessageHandler`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.redis.outbound.RedisQueueOutboundChannelAdapter;

@Configuration
public class ThumbnailRedisQueueHandlerConfig {

    @Bean
    @ServiceActivator(inputChannel = "thumbnailJobsOutbound")
    public RedisQueueOutboundChannelAdapter thumbnailQueueHandler(
            RedisConnectionFactory factory) {

        RedisQueueOutboundChannelAdapter handler =
            new RedisQueueOutboundChannelAdapter(
                "catalog:{thumbnail}:pending", factory);

        handler.setSerializer(new StringRedisSerializer());
        handler.setExtractPayload(true);
        handler.setLeftPush(true);
        return handler;
    }
}
~~~

**This is an alternative to section 7.** Running both the DSL flow and `@ServiceActivator` on the same `DirectChannel` causes **competing subscribers** or **duplicate enqueues** depending on topology. Keep only **one** publisher endpoint on an input channel in a lab.

### 9.1. Fixed vs. expression constructor?

Javadocs define two constructors:

~~~java
RedisQueueOutboundChannelAdapter(
    String queueName,
    RedisConnectionFactory connectionFactory);

RedisQueueOutboundChannelAdapter(
    org.springframework.expression.Expression queueNameExpression,
    RedisConnectionFactory connectionFactory);
~~~

These are **mutually exclusive alternatives**; do not configure both a fixed queue name and an expression on one endpoint expecting one to override cleanly.

### 9.2. XML namespace

For projects using Spring Integration XML:

~~~xml
<int-redis:queue-outbound-channel-adapter
    id="thumbnailRedisQueueOutbound"
    channel="thumbnailJobsOutbound"
    connection-factory="redisConnectionFactory"
    queue="catalog:{thumbnail}:pending"
    serializer="stringRedisSerializer"
    extract-payload="true"
    left-push="true"/>
~~~

The **`stringRedisSerializer`** bean must be declared separately as a `RedisSerializer`. This snippet shows endpoint configuration only, omitting full XML namespace declarations and the `RedisConnectionFactory` bean.

### 9.3. Handler has no `replyChannel`

`RedisQueueOutboundChannelAdapter` is an **outbound channel adapter**, not a **`RedisQueueOutboundGateway`**. It creates no conversation UUID and waits for no Redis List reply. When callers need thumbnail status, use a dedicated status query API or completion event.

## 10. Redis queue inbound: wiring the matching receiver

To demonstrate enqueued payloads arriving at `ImageWorker`, configure **`RedisQueueMessageDrivenEndpoint`** in the **separate worker application**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.redis.inbound.RedisQueueMessageDrivenEndpoint;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ThumbnailRedisQueueInboundConfig {

    @Bean
    public MessageChannel thumbnailJobsInput() {
        return new DirectChannel();
    }

    @Bean
    public RedisQueueMessageDrivenEndpoint thumbnailQueueInbound(
            RedisConnectionFactory factory,
            MessageChannel thumbnailJobsInput) {

        RedisQueueMessageDrivenEndpoint endpoint =
            new RedisQueueMessageDrivenEndpoint(
                "catalog:{thumbnail}:pending", factory);

        endpoint.setSerializer(new StringRedisSerializer());
        endpoint.setRightPop(true);
        endpoint.setOutputChannel(thumbnailJobsInput);
        endpoint.setAutoStartup(true);
        return endpoint;
    }
}
~~~

### 10.1. Producer vs. consumer configuration

| Side | Bean | Direction setting | Role |
| --- | --- | --- | --- |
| `CatalogService` | `RedisQueueOutboundChannelAdapter` | `setLeftPush(true)` | **`LPUSH`** item into Redis List |
| `ImageWorker` | `RedisQueueMessageDrivenEndpoint` | `setRightPop(true)` | **`BRPOP`** item from Redis List |

Both sides must target the **exact same Redis instance, database, queue key, and wire format**—not just similar class names.

### 10.2. Worker `@ServiceActivator`

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailJobConsumer {

    private final ObjectMapper objectMapper;
    private final ThumbnailBusinessService businessService;

    public ThumbnailJobConsumer(
            ObjectMapper objectMapper,
            ThumbnailBusinessService businessService) {
        this.objectMapper = objectMapper;
        this.businessService = businessService;
    }

    @ServiceActivator(inputChannel = "thumbnailJobsInput")
    public void handle(String json) throws JsonProcessingException {
        ThumbnailRequested job =
            objectMapper.readValue(json, ThumbnailRequested.class);

        if (!"THUMBNAIL_REQUESTED".equals(job.eventType())
                || job.schemaVersion() != 1
                || job.eventId() == null
                || job.eventId().isBlank()) {
            throw new IllegalArgumentException(
                "Unsupported or invalid thumbnail job");
        }

        // Implementation must be idempotent and validate tenant/objectKey.
        businessService.process(job);
    }
}
~~~

~~~java
public interface ThumbnailBusinessService {
    void process(ThumbnailRequested job);
}
~~~

**Note:** Exceptions thrown from the business handler **do not roll back `BRPOP`**. Once Redis queue inbound pops an item and the process crashes or the handler throws, there is no native Redis List ACK to ask the server to requeue. Durable retries require a processing store or rebuildable job source.

### 10.3. Why worker code does not automatically prove at-least-once

In this simple setup, pop, processing, and commit do not share an atomic Redis–database transaction:

~~~text
Redis List BRPOP -> Spring Message -> JSON parse -> DB/object storage commit
                    |
                    +-- crash here: item may be lost
~~~

Thus pairing producer and consumer proves **transport interop**, not **durable delivery** across all failures.

## 11. Serializer and `extractPayload` must match on both sides

This is a frequent bug when workers are Node.js/Python apps or Java services owned by another team.

### 11.1. Wire format matrix

| Outbound payload | Serializer | Redis List bytes | Inbound expectation |
| --- | --- | --- | --- |
| String JSON | **`StringRedisSerializer`** | UTF-8 JSON | `StringRedisSerializer` or UTF-8 bytes → JSON |
| Java POJO | `JdkSerializationRedisSerializer` | Java native serialization | Compatible JDK deserializer (not recommended cross-language) |
| DTO Jackson-serialized to String | `StringRedisSerializer` | UTF-8 JSON | String/JSON DTO |
| `byte[]` | Matching byte-array serializer | Raw bytes | `byte[]` under same contract |
| Full Spring `Message` | `Message`-supporting serializer | Container object (often JDK bytes) | Trusted deserializer + matching `expect-message` |

For queues shared across services, **UTF-8 JSON/String** is far easier to maintain than native Java serialization. Put `schemaVersion`/`eventType` inside the JSON envelope for independent upgrades.

### 11.2. Configuring both sides

~~~text
Producer:
  extractPayload=true
  serializer=StringRedisSerializer
  Spring payload=String JSON
  leftPush=true

Consumer:
  serializer=StringRedisSerializer
  expectMessage=false
  rightPop=true
  service activator receives String
~~~

**`expectMessage`** is an **inbound** setting, distinct from outbound `extractPayload`. If a producer pushes the **entire Spring `Message`** while the consumer expects a String payload, deserialization/shape errors occur. Never set `expectMessage=true` hoping to “capture extra headers” when the producer only serialized a JSON String.

### 11.3. Headers do not exist independently in Redis Lists

A Redis List value is a sequence of bytes, with no protocol headers like AMQP basic properties or Kafka record headers. If `messageId`, `traceparent`, `causationId`, or `tenantRef` must cross the boundary, **embed them in the JSON envelope** per schema and validate trusted fields.

### 11.4. JSON double-encoding

If a String already containing JSON goes through a JSON serializer for Strings, bytes become a **JSON string literal** with escaped quotes. Workers deserialize a String instead of an object. Inspect raw Redis payloads via Redis CLI or byte assertions in tests—never test only `ObjectMapper` on the producer side.

### 11.5. Default serializers do not replace an integration contract

Default serializer choice can vary by payload type or adapter/framework version. A publisher working locally on one machine does not prove a Python worker receives valid UTF-8. Run **producer–consumer contract tests** against the exact schema and raw bytes.

### 11.6. Untrusted data

Never enable unsafe polymorphic deserialization or native JDK deserialization on values multiple producers can write. For JSON parsing, bound **payload bytes, nesting depth, field types, and string lengths**, and enforce tenant authorization in the worker.

## 12. Dynamic queue routing: `queue-expression`

A system may use multiple Redis Lists for different work tiers:

~~~text
catalog:{thumbnail}:high
catalog:{thumbnail}:normal
catalog:{thumbnail}:low
~~~

**`RedisQueueOutboundChannelAdapter`** accepts either a fixed `queueName` or an **`Expression`**. `queue-expression` evaluates against the **incoming Spring `Message`** (root), enabling controlled header-based routing:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.redis.outbound.RedisQueueOutboundChannelAdapter;

@Configuration
public class ThumbnailPriorityRoutingConfig {

    @Bean
    @ServiceActivator(inputChannel = "thumbnailPriorityOutbound")
    public RedisQueueOutboundChannelAdapter thumbnailPriorityQueueHandler(
            RedisConnectionFactory factory) {

        var expression = new SpelExpressionParser()
            .parseExpression("headers['redisQueue']");

        var adapter = new RedisQueueOutboundChannelAdapter(
            expression, factory);
        adapter.setSerializer(new StringRedisSerializer());
        adapter.setExtractPayload(true);
        adapter.setLeftPush(true);
        return adapter;
    }
}
~~~

**Never combine fixed and dynamic queue configuration on one adapter.** Use the String constructor for a fixed queue; the SpEL above is built from a **developer-controlled constant expression**, never raw user input.

### 12.1. Selecting queues from an enum/allowlist

~~~java
public enum ThumbnailQueueTier {
    HIGH("catalog:{thumbnail}:high"),
    NORMAL("catalog:{thumbnail}:normal"),
    LOW("catalog:{thumbnail}:low");

    private final String redisKey;

    ThumbnailQueueTier(String redisKey) {
        this.redisKey = redisKey;
    }

    public String redisKey() {
        return redisKey;
    }
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class PriorityThumbnailPublisher {

    private final MessageChannel thumbnailPriorityOutbound;

    public PriorityThumbnailPublisher(
            @Qualifier("thumbnailPriorityOutbound")
            MessageChannel thumbnailPriorityOutbound) {
        this.thumbnailPriorityOutbound = thumbnailPriorityOutbound;
    }

    public void publish(ThumbnailQueueTier tier, String validatedJson) {
        if (tier == null || validatedJson == null
                || validatedJson.isBlank()) {
            throw new IllegalArgumentException("Invalid queue job");
        }

        boolean sent = thumbnailPriorityOutbound.send(
            MessageBuilder.withPayload(validatedJson)
                .setHeader("redisQueue", tier.redisKey())
                .build());
        if (!sent) {
            throw new IllegalStateException(
                "Cannot dispatch to outbound queue channel");
        }
    }
}
~~~

**Constraint:** With dynamic queues, key names must come from an **allowlist**. Never accept raw Redis keys from HTTP headers, forms, or tenant input and let an expression create or write to arbitrary namespaces. Restrict key patterns with Redis ACLs too.

### 12.2. Multiple queues do not automatically form a global priority queue

Three tiered Redis Lists do not create a **global priority queue** by themselves. Workers must handle queue selection, fairness, starvation prevention, concurrency, and backlog metrics; multi-key Redis `BRPOP` priority depends strictly on argument order and does not solve QoS across all workloads.

### 12.3. Dynamic queue vs. Spring Integration router

For a small set of queues, a **Spring Integration router** dispatching to fixed-queue outbound flows is easier to observe and ACL-restrict than a flexible SpEL expression. Use dynamic queues when producers genuinely need contract-governed key selection.

## 13. Enqueue success differs from business completion

Redis Lists serve well as backlogs when workers are offline, yet distinguish **status milestones**:

~~~mermaid
flowchart LR
    A["DB metadata committed"] --> B["LPUSH command success"]
    B --> C["Job in Redis List"]
    C --> D["Worker BRPOP item"]
    D --> E["Validate + process"]
    E --> F["Business DB/object storage commit"]
~~~

| Milestone | What it guarantees | What it does NOT guarantee |
| --- | --- | --- |
| Spring `MessageChannel.send` accepted | Message entered send path per channel contract | Whether Redis wrote it if async |
| `LPUSH` returned success | Redis executed push | Whether Redis `fsync`/replicated per policy, or worker received it |
| `LLEN` increased | List currently holds items | Thumbnail generation will succeed |
| `BRPOP` returned item | Worker removed item from List | Business transaction committed |
| Business commit succeeded | Side effects durable in target systems | Item will never be retried/duplicated |

**Never use Redis List length to measure completed thumbnails.** It only reflects items still sitting in the List at query time.

### 13.1. Producer sends while worker is offline

One advantage of Lists over Pub/Sub: **unpopped** items remain in the Redis List and are picked up once `ImageWorker` restarts, **provided the Redis key/data remains under configured persistence/TTL/eviction policies**.

### 13.2. Worker pops and crashes

~~~text
T0: CatalogService LPUSHes job-1001
T1: ImageWorker BRPOPs job-1001   -> item leaves pending List
T2: ImageWorker crashes before DB commit
T3: Redis pending List no longer contains job-1001
~~~

**Direct Redis List `POP` does not auto-redeliver.** The outbound adapter performed its push accurately, yet the end-to-end system still drops a job without reconciliation or a processing store.

### 13.3. The outbound adapter does not govern ACK

`RedisQueueOutboundChannelAdapter` does not manage consumer ACKs or requeues. Flipping `leftPush=true` to `false` only changes the push end; **it does not make Redis track pending state or delivery counts**.

## 14. Failure windows on the producer side

### 14.1. Errors before `LPUSH`

Caused by:

- Invalid DTO or `ObjectMapper` serialization failure.
- Spring Integration filter/router dropping the message.
- `MessageChannel` having no subscriber.
- `queueExpression` evaluating to a bad/null key name.
- `RedisSerializer` rejecting the payload type.

Here Redis never received the push command on a clear error path. Classify these before retrying network calls; JSON/schema errors are normally **non-retryable** until fixed.

### 14.2. Redis command returns an error

| Error | Symptom | Where to investigate |
| --- | --- | --- |
| Connection failure | Cannot connect to Redis | Redis address, TLS, DNS, network, failover |
| ACL `NOPERM` | Lacks `LPUSH`/`RPUSH` permission on key | Redis user, command/key patterns |
| `WRONGTYPE` | Key exists as a non-List type | Namespace ownership, migration |
| OOM/`maxmemory` | Redis rejects writes or triggers eviction | Capacity, memory limits, persistence |
| Timeout | Response took too long | Redis latency/network, unknown outcome |
| Serializer exception | Cannot encode payload | Schema/serializer configuration |
| Queue expression failure | Invalid dynamic key | Header/SpEL/routing validation |

### 14.3. Unknown outcome after `LPUSH`

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant R as Redis
    P->>R: LPUSH jobId=evt-thumb-1001
    R->>R: Push succeeds
    R--xP: Connection drop before reply
    Note over P,R: Publisher does not know command ran
    P->>R: Retry LPUSH same eventId
    R->>R: List may hold 2 items
~~~

Redis Lists do not deduplicate by `eventId`. **Keep the same `eventId` across retries**, maintain unique business job state / idempotent handlers, and track duplicate metrics—never mint a fresh UUID and treat it as an independent job.

### 14.4. `RetryTemplate` is not durable across restarts

A `RetryTemplate`/`RequestHandlerRetryAdvice` retries transient errors **inside the running JVM**, yet if the process dies mid-retry, the job is not re-sent unless the source event is persisted durably.

To survive restarts, use a **database outbox, persistent task table, or durable broker/stream**. Never infinitely retry `WRONGTYPE`, serializer mismatches, or invalid routing keys.

### 14.5. `ErrorChannel` is not a Redis dead-letter queue

Spring Integration's `ErrorChannel` receives `ErrorMessage`s per flow/concurrency setup; it **does not write a dead List**, recover events lost in a process crash, or know whether downstream workers committed. Build durable error handling if jobs cannot be lost.

### 14.6. Never blindly `LPUSH` again in every `catch`

A pattern like:

~~~java
try {
    publisher.enqueueNewImage(tenant, product, version, key);
}
catch (RuntimeException e) {
    // Do not unconditionally do this with a new eventId:
    publisher.enqueueNewImage(tenant, product, version, key);
}
~~~

creates duplicates, multiplies jobs on transient timeouts, and loses attempt tracking. **Place retries in a layer that preserves `eventId`**, with max attempts, backoff, and durable state when required.

## 15. Database commit and `LPUSH`: transactional outbox

Suppose `CatalogService` saves image metadata in a database and pushes a thumbnail job to Redis:

### 15.1. `LPUSH` before DB commit

~~~text
BEGIN DB TRANSACTION
  INSERT image_metadata(productId=P-1001, version=5)
  LPUSH thumbnail job
ROLLBACK DB
~~~

A worker may `BRPOP` before metadata commits, failing to find the row or processing a rolled-back job. Redis pushes do not roll back with JDBC transactions.

### 15.2. `LPUSH` after DB commit

~~~text
BEGIN DB TRANSACTION
  INSERT image_metadata(...)
COMMIT DB
  -> LPUSH job
~~~

This prevents workers from seeing uncommitted rows, yet leaves a window:

~~~text
DB commit succeeds
JVM crashes before LPUSH
Job metadata in DB, zero items in Redis
~~~

To guarantee thumbnails are eventually generated, jobs need a **rebuild/reconciliation source**.

### 15.3. Transactional outbox

One model:

~~~mermaid
flowchart LR
    API["HTTP/SFTP upload"] --> DB[("DB transaction:<br/>image metadata + outbox")]
    DB --> PUB["Outbox publisher<br/>durable retry"]
    PUB --> AD["Redis queue outbound"]
    AD --> LIST[("Redis List pending")]
    LIST --> WORK["ImageWorker"]
    WORK --> DB
    DB --> REC["Periodic reconcile"]
    REC --> PUB
~~~

**Within one DB transaction**, insert both image metadata and the outbox record:

~~~sql
BEGIN;

INSERT INTO image_metadata (
    product_id, image_version, object_key, status
)
VALUES ('P-1001', 5, 'tenant-a/products/P-1001/v5/original.jpg',
        'NEEDS_THUMBNAIL');

INSERT INTO outbox_events (
    event_id, event_type, payload_json, status
)
VALUES ('evt-thumb-1001', 'THUMBNAIL_REQUESTED',
        '{"eventId":"evt-thumb-1001","schemaVersion":1}',
        'PENDING');

COMMIT;
~~~

**This SQL is illustrative**, not a complete schema (which needs PKs, unique indexes, timestamps, tenant, and proper isolation). An outbox worker polls `PENDING` events, dispatches via the Redis outbound adapter, and marks `DISPATCHED` only after Redis command success.

### 15.4. Outbox does not eliminate duplicates

If Redis `LPUSH` succeeds and the outbox publisher crashes before marking `DISPATCHED`, it resends after restart. **Outboxes favor never losing publish intent by accepting duplicates**, so `ImageWorker` must be idempotent by `eventId`/`productVersion`.

### 15.5. Outbox does not solve post-`BRPOP` job loss

An outbox marked `DISPATCHED` cannot tell if a worker `BRPOP`ped the item and crashed. To guarantee eventual thumbnail creation, add:

- Business status **`NEEDS_THUMBNAIL` / `PROCESSING` / `DONE`** in the DB.
- **Periodic reconciliation** re-enqueueing jobs not `DONE` after a timeout.
- Idempotent workers to avoid duplicate side effects.
- Or replace direct `POP` with a **reliable claim/ACK protocol**, Redis Streams, AMQP, or JMS.

### 15.6. Never call `@Transactional` a distributed transaction

A JDBC transaction, Redis `LPUSH`, object storage write, and HTTP provider call do not form one atomic cross-system transaction just because they execute inside an `@Transactional` method.

## 16. End-to-end idempotency in `ImageWorker`

A job can arrive multiple times when:

- Producer retries `LPUSH` on timeout/`UNKNOWN` outcome.
- Outbox replays after a crash.
- An operator manually replays it.
- A reconciliation scheduler re-enqueues `NEEDS_THUMBNAIL` rows.
- A reliable queue reclaimer requeues after lease expiry.

**`eventId` only helps when the handler implements real checks.** Never add `eventId` to JSON assuming Redis deduplicates automatically.

### 16.1. Unique business identity

Example durable table:

~~~sql
CREATE TABLE thumbnail_jobs (
    event_id       VARCHAR(80) PRIMARY KEY,
    product_id     VARCHAR(80) NOT NULL,
    image_version  BIGINT NOT NULL,
    status         VARCHAR(20) NOT NULL,
    attempt_count  INTEGER NOT NULL,
    updated_at     TIMESTAMP NOT NULL,
    UNIQUE (product_id, image_version)
);
~~~

Create business job records with **unique constraints** or conditional updates:

- Same `eventId` already `DONE` → skip side effects.
- Same `productId`/`imageVersion` currently `PROCESSING` → check lease/owner.
- Older job version superseded by a newer version → discard obsolete work per policy.
- Client retries same business request → preserve identity.

### 16.2. Deterministic outputs

Key thumbnail output paths by **`productId`/`imageVersion`**. Re-running the same job writes the same artifact instead of spawning untracked duplicates. Still enforce **version/conditional writes** in object storage so a slow old worker cannot overwrite a newer version.

### 16.3. External side effects with `UNKNOWN` outcomes

If uploading the thumbnail succeeds right as the connection times out, retries repeat the write. Use deterministic keys, check ETags/versions/object existence, and reconcile `DONE` state—never equate “timeout” with “definitely never written.”

### 16.4. Retention bounds on idempotency state

If Redis backlogs, outboxes, or reconciliation can replay after seven days while the processed `eventId` table purges after 24 hours, old replays look brand new. Size business deduplication retention to **at least the maximum duplicate/replay window**.

## 17. Reliable List queue: `BLMOVE` and processing List

If best-effort thumbnails are insufficient and worker crash recovery is required, direct Redis List `POP` needs an additional protocol.

~~~mermaid
flowchart LR
    OUT["Redis queue outbound<br/>LPUSH"] --> READY[("ready List")]
    READY -->|"BLMOVE RIGHT LEFT"| PROCESS[("processing List")]
    PROCESS --> H["Business worker"]
    H --> DB[("Durable commit")]
    DB -->|"LREM exact item"| PROCESS
    PROCESS -. "Reclaimer on expiry" .-> READY
~~~

### 17.1. `BLMOVE` claim

Instead of `BRPOP` deleting the item from Redis, consumers run an **atomic move**:

~~~text
BLMOVE catalog:{thumbnail}:ready
        catalog:{thumbnail}:processing
        RIGHT LEFT 0
~~~

This pops from the `RIGHT` of `ready` and pushes onto the `LEFT` of `processing` inside Redis. If the worker dies before ACKing, **the item stays in `processing`** for the reclaimer per policy.

**Note:** This is an **application-built protocol**, not the default behavior of `RedisQueueMessageDrivenEndpoint`. The outbound adapter still just **`LPUSH`es** into `ready`; you must implement consumer claiming, leases, ACKs, and recovery yourself.

### 17.2. ACK via `LREM` of the exact item

After business commit, the consumer runs **`LREM processing 1 value`** to remove its claimed item. However, if `processing` holds **two byte-identical serialized values**, `LREM` cannot distinguish owners. Include unique job IDs/distinguishable representations, verify ownership, or use a keyed state structure so you never ACK another worker's job.

### 17.3. Post-commit duplicate window

~~~text
BLMOVE ready -> processing
Business DB commit succeeds
Worker crashes before LREM processing
Reclaimer moves item back -> redelivered
~~~

Idempotency is mandatory. Reliable queues choose **at-least-once delivery** with controlled duplicates over the job loss of direct `POP`.

### 17.4. Leases, reclaimer, and fencing

A processing List alone **does not know which jobs timed out**. Track:

- `eventId`, `owner`/`workerId`.
- Claim timestamp, `leaseUntil`, `attempts`.
- Status `PROCESSING`/`DONE`/`FAILED`.
- `nextRetryAt` and `lastErrorCategory`.
- Fencing token/version in case an expired worker finishes late.

The reclaimer must verify which jobs truly qualify for reclaiming rather than blindly requeuing every processing item.

### 17.5. Redis Cluster hash slots

For `BLMOVE` across **source + destination**, Redis Cluster requires multi-key commands to share **the same hash slot**. Hash tags:

~~~text
catalog:{thumbnail}:ready
catalog:{thumbnail}:processing
catalog:{thumbnail}:dead
~~~

map these keys to one slot. Using keys in different slots triggers **`CROSSSLOT`**; never suppress checks or assume Spring Data Redis bridges cross-shard transactions automatically.

### 17.6. When to choose Redis Streams or another broker?

Once you need **ready + processing + ACK + leases + retry counts + dead lists + reclaimers + metrics + auditing**, evaluate Redis Streams (consumer groups/PEL/`XACK`) or RabbitMQ/JMS/Kafka. Avoid rebuilding an entire message broker just because a Redis List is handy.

## 18. Concurrency and outbound `MessageChannel`s

### 18.1. `DirectChannel`

~~~text
Caller thread
  -> thumbnailJobsOutbound.send()
  -> RedisQueueOutboundChannelAdapter
  -> Redis LPUSH
  -> Return or exception
~~~

**`DirectChannel`** works well when you need synchronous send feedback at moderate volume. If Redis disconnects, HTTP request threads or outbox worker threads block until timeout. **`send` succeeding only confirms the current boundary**, not that `ImageWorker` created the thumbnail.

### 18.2. `ExecutorChannel`

~~~text
Caller -> ExecutorChannel -> executor memory queue
                          -> worker thread -> Redis LPUSH
~~~

With `ExecutorChannel`:

- Callers can return **before Redis `LPUSH` actually executes**.
- Push exceptions happen on executor threads, needing dedicated error handling/observability.
- Application crashes lose tasks sitting in the executor's memory queue.
- Unbounded executor queues risk `OutOfMemoryError` if Redis slows down.
- Bound threads, queue capacity, backpressure, and rejection policies.

Never use `ExecutorChannel` thinking it turns Redis pushes into durable enqueues; for durability, use an **outbox/persistent task store**.

### 18.3. Internal `QueueChannel`

Another flow might wire:

~~~text
HTTP inbound -> QueueChannel -> Spring Integration Poller
                            -> Redis queue outbound -> Redis List
~~~

This **`QueueChannel`** is a Spring Integration internal channel, distinct from the **Redis List**. Default `QueueChannel` buffers in memory and loses items on JVM crashes before Redis ever sees `LPUSH`. A persistent `MessageStore` only protects configured checkpoints and adds no Redis consumer ACK.

### 18.4. `PublishSubscribeChannel` and duplicates

If an internal `PublishSubscribeChannel` fans out one job to **two Redis queue outbound handlers pointing at the same Redis key**, the queue receives **two `LPUSH`es** for a single business event. Inspect handler/subscriber wiring and queue names before blaming Redis failovers for duplicates.

### 18.5. Two producers writing to one queue

Redis executes each `LPUSH` atomically; if two `CatalogService` replicas push concurrently, queue order reflects arrival order at Redis, **not event creation order across separate databases/threads**. When per-`productId` ordering matters, enforce sequence/versions and consumer contracts instead of relying solely on List FIFO.

### 18.6. Multiple workers competing for items

With direct Redis List `POP`:

~~~text
Redis List -> Worker A BRPOP
           -> Worker B BRPOP
           -> Worker C BRPOP
~~~

Each List item is popped by one consumer at execution time, **not broadcast to all workers**. Still, producer retries can put duplicate payloads in Redis that different workers pop concurrently—requiring idempotency.

### 18.7. FIFO is pop order, not completion order

~~~text
Job A popped 10:00:00; processing 10 s
Job B popped 10:00:01; processing 1 s

Job B finishes DONE before Job A.
~~~

If business logic demands A finish before B, serialize concurrency by domain key, use business sequences, or partition appropriately—tweaking `leftPush`/`rightPop` will not help.

## 19. Redis memory, TTL, and backlog capacity

Redis Lists typically live in Redis RAM (subject to persistence/replication config), so producers must not enqueue unboundedly when consumers fall behind.

### 19.1. Growing backlogs

~~~text
Producer enqueue rate = 500 jobs/second
Consumer success rate = 100 jobs/second

Backlog growth ≈ 400 jobs/second
                = 24,000 jobs/minute
~~~

This steady-state arithmetic omits requeues, traffic bursts, failures, outages, and in-flight jobs. Monitor growth rate, queue age, Redis memory, and downstream throughput.

### 19.2. Lists have no built-in max queue depth

Redis Lists do not enforce per-key queue limits like some brokers' queue policies. To control capacity or rate:

- Throttle/reject/slow producers before `LPUSH`.
- Use capacity-based admission control in Redis/DB without check-then-push races.
- Batch/coalesce jobs for the same `productId`/version when domain rules allow.
- Bound outbox workers and downstream concurrency.
- Pick Redis Streams/brokers with built-in retention/backpressure when needed.

Checking **`LLEN` first and then `LPUSH`** provides no hard cap under parallel publishers. Atomic caps require scripts/commands tested against your Redis topology.

### 19.3. Never truncate queues arbitrarily with `LTRIM`

~~~text
LPUSH newJob
LTRIM key 0 999
~~~

`LTRIM` silently drops older unprocessed jobs. That is **data loss**, not a retry policy. Only trim by capacity if losing those tasks is explicitly accepted in your SLA.

### 19.4. TTL and key eviction

If any component sets **`EXPIRE`** on a Redis List key, the entire key and all unpopped items vanish upon expiration. Redis **`maxmemory` eviction** can also drop keys or reject writes depending on policy; verify production Redis configuration.

**Do not assume `LPUSH` clears an existing TTL.** Appending to a List normally leaves an active TTL intact per Redis semantics. Test TTL ownership and isolate key namespaces.

### 19.5. Persistence does not create consumer ACKs

Redis RDB/AOF/replication helps recover Redis state after failures, yet **never restores an item already popped by `BRPOP` before worker commit**. Redis state durability and **end-to-end delivery reliability** are two distinct layers.

### 19.6. Capacity planning

If each JSON job is ~600 bytes, one million jobs take ~600 MB **just for raw payloads**, excluding List/allocator overhead, Redis replication/AOF buffers, indexes, and client buffers. Never size production RAM from raw payload bytes alone; benchmark with real Redis, real payloads, and peak backlogs.

## 20. Security: Redis ACLs, tenants, and job data

### 20.1. Redis ACLs and key namespaces

Minimum role separation:

| Actor | Functionally required permissions |
| --- | --- |
| Producer `CatalogService` | `LPUSH`/`RPUSH` on permitted **`ready` Lists** |
| Consumer `ImageWorker` | `BRPOP`/`BLPOP` on `ready` key, per recovery policy |
| Reliable-queue worker | `BLMOVE`, `LREM`, and permissions on `processing` key |
| Reclaimer | Read/manage `processing`/lease/attempt state |
| Operator | Inspect backlogs, audited replay of failed jobs |

Exact ACL rules depend on Redis version, commands, and key patterns. Never grant **`FLUSHALL`, `FLUSHDB`, or broad `DEL`** to workers merely to silence `NOPERM` errors. Production requires TLS, secret rotation, network policies, and least privilege.

### 20.2. Tenant boundaries

A JSON job containing **`tenantRef`** is not an authenticated request. `ImageWorker` must verify `productId` belongs to the authorized tenant, `objectKey` lies inside an allowlisted prefix/bucket, and the operation is permitted. Never trust a job simply because the Redis List key follows a convention.

### 20.3. Dynamic `queue-expression` must enforce an allowlist

`QueueExpression` resolves Redis keys at Spring Message runtime. If `redisQueue` comes straight from an HTTP request, attackers can divert Redis writes to unintended keys. Resolve queue keys from controlled enums/configs and enforce Redis ACLs.

### 20.4. Payload poisoning and deserialization

Never deserialize native Java objects from a shared Redis List writable by other producers or tenants. For JSON, enforce limits on:

- Byte size, JSON nesting depth, and field count.
- Allowlisted `eventType`/`schemaVersion`.
- Valid formats for Strings, product IDs, and object paths.
- Never indiscriminately enable Jackson polymorphic default typing.
- Clear policies for malformed/unsupported payloads.

### 20.5. Object storage references

`ImageWorker` must never turn `objectKey` into an unvalidated filesystem path or shell command. Enforce allowlisted buckets/prefixes, file size/media-type limits, image decoding limits, and path-traversal/cross-tenant checks. Avoid storing active signed URLs or access tokens inside dead lists or logs whenever possible.

### 20.6. Retry/dead storage holds sensitive data

Dead Lists often retain raw payloads and `lastError` longer than `ready` Lists. Enforce retention limits, ACLs, encryption, PII scrubbing, replay audits, and least-privilege operator access.

## 21. Monitoring: distinguishing enqueued, popped, and completed

| Signal | Meaning | What NOT to infer |
| --- | --- | --- |
| Queue outbound attempts | Messages entering handler | Redis `LPUSH` succeeded |
| Redis push success count | Redis returned success for `LPUSH`/`RPUSH` | Worker processed the job |
| Redis command errors/timeouts | Transport/serializer failures | Timeout definitely means unpushed |
| **`LLEN ready`** | Items waiting to be popped | Total business backlog = `ready` |
| **`LLEN processing`** | Claimed un-ACKed items (if custom reliable queue) | Everything is running fine |
| **`LLEN dead`** | Quarantined jobs (if custom dead List) | Jobs replay automatically |
| Consumer pop/claim rate | Rate items are pulled | Business success |
| Business completion rate | Rate side effects commit | Queue cleanup always succeeded |
| Oldest job age | Lag of oldest unprocessed job | Measured by `LLEN` alone |
| Duplicate skipped | Idempotency blocking repeats | Producer never enqueued duplicates |
| Reclaimer count | Reclaimed jobs | Old worker skipped side effects |

### 21.1. Illustrative metric names

~~~text
thumbnail_redis_queue_push_attempt_total
thumbnail_redis_queue_push_success_total
thumbnail_redis_queue_push_error_total{reason="CONNECTION_TIMEOUT"}
thumbnail_redis_queue_ready_length
thumbnail_redis_queue_processing_length
thumbnail_redis_queue_dead_length
thumbnail_redis_queue_oldest_age_seconds
thumbnail_worker_pop_total
thumbnail_worker_completed_total
thumbnail_worker_retry_total{reason="OBJECT_STORAGE_TIMEOUT"}
thumbnail_worker_duplicate_skipped_total
thumbnail_worker_reclaimed_total
thumbnail_worker_processing_duration_seconds
~~~

These are **application-instrumented metric names**, not all emitted out of the box by Spring Integration. Keep labels bounded: never put `eventId`, `productId`, raw `objectKey`, or unbounded dynamic queue keys in metric labels.

### 21.2. `LLEN=0` does not mean `DONE=100%`

~~~text
Ready LLEN = 0
Executor queued tasks = 100
Business DONE = 0
~~~

With direct-`POP` queue inbound, the Redis List empties as soon as workers pop items into memory without durable ACKs. On JVM crash, tasks vanish. Dashboards need business status, processing/reconciliation tracking, and end-to-end success—not queue length alone.

### 21.3. Monitoring Redis errors

Track Redis command latency, connection pool exhaustion, ACL/`WRONGTYPE` errors, failovers/reconnects, memory/evictions, AOF/RDB health, publish/enqueue retries, and application error categories.

### 21.4. SLA-based alerting

Alert when:

- `LLEN ready` climbs continuously past threshold for several minutes.
- Oldest unprocessed job breaches SLA.
- Queue outbound error rates or Redis response latencies spike.
- Dead jobs / retry-exhausted counts surge.
- Business success nears 0 despite high pop/claim rates.
- Redis memory approaches `maxmemory` or eviction hits queues.

### 21.5. Structured logging

~~~text
flow=thumbnailQueueOutbound
queueAlias=catalog-thumbnail-pending
eventId=evt-thumb-1001
eventType=THUMBNAIL_REQUESTED
schemaVersion=1
enqueueAttempt=2
enqueueStatus=REDIS_COMMAND_SUCCESS
durationMs=6
~~~

Never log **`BUSINESS_DONE`** on the producer after `LPUSH`; that milestone belongs to business workers and reconciliation.

## 22. Lifecycle: startup, shutdown, reconnect, and failover

### 22.1. When does the outbound handler initialize?

**`RedisQueueOutboundChannelAdapter`** is a Spring-managed `MessageHandler`. On `ApplicationContext` startup, the flow/consumer endpoint subscribes to its input channel. It does not poll Redis Lists in the background; it pushes only when a Spring Message arrives.

~~~mermaid
flowchart TD
    START["Spring context start"] --> CONN["RedisConnectionFactory initialized"]
    CONN --> FLOW["Outbound flow active"]
    FLOW --> INPUT{"Message received?"}
    INPUT -->|"Yes"| PUSH["Serialize + LPUSH/RPUSH"]
    PUSH --> FLOW
    INPUT -->|"No"| FLOW
    FLOW -->|"Stop"| END["Stop new dispatch, drain/reconcile"]
~~~

### 22.2. Startup ordering

If an HTTP/SFTP source sends messages before Redis is ready, outbound fails or stalls upstream depending on channel type. Do not equate **bean initialization complete** with Redis readiness. Verify Redis connectivity and key permissions per SLA.

For sources that can rebuild jobs from a DB, publishers can retry later. For sources **that cannot replay**, add durable handoff/outbox **before** the outbound push.

### 22.3. Graceful shutdown

When shutting down the producer:

1. Stop accepting new business commands per policy.
2. Drain in-flight direct sends or persist intent durably.
3. With `ExecutorChannel`, never report completion while jobs sit in the executor memory queue.
4. Flush critical metrics/logs within a bounded window.
5. Let Spring lifecycle close `RedisConnectionFactory` clients cleanly.
6. After restart, reconcile outbox/jobs not yet marked `DISPATCHED`.

### 22.4. Redis failover

During Redis Sentinel/Cluster failover:

- Connection drops before push → retry.
- Push succeeds yet reply is lost → `UNKNOWN` result; retry causes duplicates.
- Redis state rolls back within replication/persistence RPO.
- Client must reconnect and refresh cluster topology.

A reconnected Redis endpoint **does not know** which pre-failover business jobs succeeded or dropped. Rely on durable event ledgers and reconciliation for controlled replay.

### 22.5. Redis Cluster and `queue-expression`

Every Redis List key maps to a hash slot. Single-key `LPUSH` needs no slot alignment with other keys, yet building **`BLMOVE` `processing`/`ready`** requires shared slots. Dynamic `queue-expression` must enforce namespace/hash-tag policies if queues participate in multi-key atomic commands.

### 22.6. Never clear queues to fix consumer errors

`RedisQueueMessageDrivenEndpoint` may expose List management helpers like `getQueueSize`/`clearQueue` depending on version. **Never call `clearQueue` or `DEL` on production queues** during consumer incidents without recovery/auditing: you will destroy all unprocessed jobs.

## 23. End-to-end testing with real Redis

Unit testing `ThumbnailJobPublisher` proves JSON creation and `MessageChannel` sending; it **does not prove** `RedisQueueOutboundChannelAdapter` `LPUSH`ed the right key with the right serializer bytes or that worker inbound can decode it. Test against a real isolated Redis server, such as Testcontainers.

### 23.1. Test matrix

| Scenario | Setup | Assertion |
| --- | --- | --- |
| **Happy path** | Producer sends JSON String | Redis List holds matching item |
| **`LPUSH` direction** | Send A, B, C | `LRANGE` shows `[C, B, A]` |
| **`RPUSH` direction** | `leftPush=false` | `LRANGE` shows `[A, B, C]` |
| **FIFO with `BRPOP`** | `LPUSH` A/B/C, inbound `rightPop=true` | Pops A, B, C |
| **FIFO with `BLPOP`** | `RPUSH` A/B/C, inbound `rightPop=false` | Pops A, B, C |
| **LIFO mismatch** | `LPUSH` with `BLPOP` | Pops C, B, A; exposes contract mismatch |
| **Right queue key** | Producer/worker share key | Worker receives job |
| **Wrong key** | Producer writes different key than worker | Worker receives nothing; original key retains item |
| **String wire format** | Outbound `StringRedisSerializer` | Raw Redis value is UTF-8 JSON |
| **Serializer mismatch** | Outbound JDK, inbound String | Decoding failure surfaced |
| **`extractPayload=true`** | Spring Message has headers | List holds payload only, no headers |
| **`extractPayload=false`** | Compatible custom serializer | Whole `Message` round-trips if supported |
| **Dynamic queue** | `queueExpression` from enum/header | Pushes only to allowlisted keys |
| **Dynamic queue missing** | Missing `redisQueue` header | Fails/routes per policy without bad writes |
| **Unauthorized queue** | External input tries another namespace | Rejected before Redis; Redis ACL backup |
| **`WRONGTYPE`** | Key holds a String | Redis errors cleanly without deleting key |
| **Redis unavailable** | Stop test Redis | Outbound errors/retries observed |
| **Connection `UNKNOWN`** | Drop network near `LPUSH` | `eventId` deduped; never assumed unsent |
| **Worker offline** | Producer `LPUSH`es, worker stopped | List retains items while data/key persists |
| **Two competing workers** | Two `BRPOP` inbounds on same List | Each Redis item popped by one worker |
| **Duplicate producer retry** | `LPUSH` two JSONs with same `eventId` | Worker side effect runs once |
| **Crash before outbound send** | Kill publisher before `LPUSH` | Outbox/reconciliation resends job |
| **Crash after `LPUSH` before outbox update** | Kill publisher | Replay duplicates; worker idempotent |
| **Crash after `BRPOP` before commit** | Kill worker | Item lost from ready List without recovery |
| **`BLMOVE` claim** | Move ready → processing | Item stays in processing until ACK |
| **Crash after `BLMOVE` before commit** | Kill worker | Reclaimer recovers item |
| **Crash after commit before `LREM`** | Kill worker | Duplicate delivery blocked by idempotency |
| **Lease expiry race** | Worker A runs slow, B reclaims | Fencing/ownership prevents double effects |
| **Redis Cluster cross-slot** | Ready/processing in different slots | Cross-slot error surfaced |
| **Poison JSON** | Malformed payload | Classified error, no infinite hot loop |
| **Oversized payload** | Item exceeds size limit | Rejected/rate-limited, no OOM |
| **Backlog burst** | Producer outpaces worker | `LLEN` climbs, alerts/capacity limits trigger |
| **TTL expiry** | Queue key has TTL in test | Jobs expire; exposes misconfiguration |
| **Redis ACL** | User lacks push permission | Clear error, no security bypass |
| **Metrics** | Push + pop + business commit | Enqueued/popped/`DONE` tracked separately |

### 23.2. Redis CLI test for List direction

On isolated test Redis only:

~~~bash
redis-cli LPUSH test:thumbnail:ready A
redis-cli LPUSH test:thumbnail:ready B
redis-cli LPUSH test:thumbnail:ready C
redis-cli LRANGE test:thumbnail:ready 0 -1
# Expected: C B A
redis-cli RPOP test:thumbnail:ready
# Expected: A
redis-cli RPOP test:thumbnail:ready
# Expected: B
redis-cli RPOP test:thumbnail:ready
# Expected: C
~~~

**Never use `DEL`/`FLUSHDB` on production queues** to reset state before tests. Keep test queues in isolated Redis instances/namespaces.

### 23.3. Payload capture test with `CountDownLatch`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class ThumbnailQueueCapture {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<String> payload =
        new AtomicReference<>();

    public void accept(String json) {
        payload.set(json);
        latch.countDown();
    }

    public String awaitJson() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Redis queue item not received");
        }
        return payload.get();
    }
}
~~~

**This helper is not a complete integration test.** Start a Spring context with the outbound adapter, inbound endpoint, test Redis server, `StringRedisSerializer` on both ends, and the subscriber handler wired to `thumbnailJobsInput`. Use bounded timeouts—never sleep a fixed interval and assume the worker received it.

### 23.4. Testing the two most critical windows

Two failure windows drive the architecture:

~~~text
Window A: DB commit -> publisher crashes -> LPUSH never ran
  -> Requires outbox/reconciliation.

Window B: BRPOP -> worker crashes -> DB commit never ran
  -> Requires processing/lease/reclaimer or rebuildable job source.
~~~

A happy-path integration test proves neither window safe. When claiming at-least-once delivery, prove it with **fault injection** and idempotency assertions.

### 23.5. Never verify solely with `LLEN`

If the consumer `BRPOP`s quickly, `LLEN` may read `0` even though the adapter `LPUSH`ed. Use a latch/captured JSON, DB `eventId` state, or producer-only tests without consumers running to inspect the List. Be explicit whether you are testing **enqueue** or **end-to-end processing**.

### 23.6. Testing multi-version serializers and schemas

During rolling upgrades, v1 producer jobs still sit in the List when v2 workers start. Verify v2 workers can read v1 payloads or quarantine cleanly—never let one poison message block the whole queue.

## 24. Troubleshooting

### 24.1. `LLEN` doesn't increase after send

Check:

1. Did the Spring Message enter the right input channel?
2. Did a filter/router discard the message?
3. Is the handler registered and started?
4. Did `queueExpression` select the right key?
5. Are Redis connection/ACLs working?
6. Did the serializer throw before `LPUSH`?
7. Is another worker `BRPOP`ping immediately, dropping `LLEN` back to zero?
8. Do Redis instance and database index match?

**`LLEN=0`** does not prove `LPUSH` didn't run if a consumer is actively popping.

### 24.2. `LLEN` increases yet workers receive nothing

Likely causes:

- Worker is listening on the **wrong Redis key/instance/database**.
- Inbound endpoint hasn't started or Redis connection failed.
- Serializer mismatch prevents payloads from reaching the business handler.
- Redis queue inbound is failing inside its listener task/recovery loop.
- Key is a Redis List while the worker subscribed via Pub/Sub or `XREAD` on a Stream.
- Consumer ACL lacks `BRPOP`/`BLPOP` permissions.

Inspect inbound errors and run a test worker with verified queue key and payload serializer.

### 24.3. Workers receive items out of order

Check both **`leftPush`** and **`rightPop`**. `LPUSH` + `BLPOP` gives LIFO, not FIFO. With multiple workers, **business completion order** can also differ from pop order even when both List ends match.

### 24.4. Worker fails parsing JSON

If raw Redis bytes start with Java serialization binary headers or an escaped JSON string literal, the producer is using an incompatible serializer. Inspect raw Redis values in a test namespace, compare bytes, and configure `StringRedisSerializer` explicitly.

### 24.5. A job runs twice

Possible causes:

- Producer retried `LPUSH` after a timeout.
- Outbox publisher replayed.
- Reconciliation re-enqueued a non-`DONE` job.
- Operator replayed dead jobs.
- Reliable queue reclaimer reclaimed after lease expiry.

Check whether both shared the same **`eventId`** or only `productId`. If the same `eventId` duplicated side effects, inspect your idempotency ledger/unique constraints. If different `eventId`s shared the same `imageVersion`, add a business dedup key.

### 24.6. Job disappears after worker failure

If workers use direct `BRPOP`, the item was removed from the List before business commit. Redis persistence will not restore it. Check business state `NEEDS_THUMBNAIL`, outboxes/reconciliation, or processing stores—do not expect the adapter to supply native DLQ/requeues.

### 24.7. Queue key throws `WRONGTYPE`

Another service may have written the key as a String/Hash/Set. Run **`TYPE key`** on authorized test/monitoring Redis to inspect. Never delete production keys blindly; fix namespaces or run controlled migrations.

### 24.8. Redis times out yet the job still appears

This is an **`UNKNOWN` result**: Redis executed `LPUSH` and the reply got lost. Retries create two items. Keep `eventId` stable, track outbox state, and use idempotent workers—never treat `UNKNOWN` as guaranteed failure.

### 24.9. Redis queue memory grows unbounded

Inspect enqueue rate, worker success rate, processing duration, error/retry hot loops, payload sizes, and unexpected producer duplicates. Add throttling/capacity policies, scale workers within downstream capacity, or use TTL/reconciliation where appropriate—never `LTRIM` production queues to drop backlog if business rules forbid losing tasks.

### 24.10. Producer send succeeds yet thumbnail isn't created

That may simply be **expected async behavior**. Enqueue and business processing are separate milestones. Query job/thumbnail status in the database alongside worker metrics and queue depth—never equate `send` booleans or List length with business completion.

## 25. Real-world architectural scenarios

### 25.1. Case A – Thumbnail jobs rebuildable from the database

**Context:** Catalog DB stores the original image record and `NEEDS_THUMBNAIL` status; Redis merely accelerates `ImageWorker` dispatch.

~~~mermaid
flowchart LR
    API["HTTP/SFTP upload"] --> DB[("Catalog DB<br/>NEEDS_THUMBNAIL")]
    DB --> OUT["Redis queue outbound"]
    OUT --> Q[("Redis List pending")]
    Q --> W["ImageWorker"]
    W --> STORE[("Object storage thumbnail")]
    W --> DONE["Catalog DB status DONE"]
    DB --> REC["Periodic reconciliation"]
    REC --> OUT
~~~

**Direct `POP` is acceptable here** when:

- DB is the source of truth for unfinished images.
- When an item is lost after `BRPOP`, a scheduler finds `NEEDS_THUMBNAIL` rows and re-enqueues them.
- `ImageWorker` is idempotent by `productId`/`imageVersion`.
- Reconciliation latency fits the SLA.
- Stale counts and retries are monitored.

**Note:** Safety comes from **database + reconciliation**, not from `BRPOP` having ACKs.

### 25.2. Case B – CSV import from SFTP

**Context:** An SFTP inbound adapter syncs CSVs, a parser persists import rows in DB, and pushes row work items to a Redis List for workers.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound<br/>poller"] --> CSV["CSV parser"]
    CSV --> DB[("Import DB rows + outbox")]
    DB --> PUB["Redis queue outbound<br/>LPUSH"]
    PUB --> Q[("import:{rows}:ready")]
    Q --> WORK["Row worker<br/>BRPOP"]
    WORK --> DB
~~~

Distinguish:

- **SFTP inbound poller** discovers files on schedule.
- **Redis queue outbound** pushes each row-job to the Redis List.
- **Redis queue inbound** pulls work items for workers.
- **DB import state** determines processed/failed rows—not `LLEN`.

Never delete source files or mark the import `DONE` just because all rows `LPUSH`ed cleanly if `DONE` means every row committed.

### 25.3. Case C – Redis queue outbound → HTTP outbound

An `ImageWorker` can pull from a Redis List and call an external HTTP API:

~~~text
Redis queue outbound (producer)
  -> Redis List
  -> Redis queue inbound (worker)
  -> HTTP outbound gateway/adapter
  -> External image processor
~~~

HTTP timeouts yield **`UNKNOWN`**: the provider may have finished while the response dropped. On retries, pass an **idempotency key** or query result status; Redis Lists do not prevent duplicate HTTP calls.

### 25.4. Case D – Payments that must never be lost

**Never use direct Redis List `POP` as the sole source** for charges or ledger adjustments. Require durable producer handoffs, consumer ACK/recovery, unique `eventId`s, and idempotent side effects.

~~~mermaid
flowchart LR
    PAY["Payment DB + transactional outbox"] --> LOG["Durable broker/Stream"]
    LOG --> CON["Consumer group + ACK"]
    CON --> LEDGER[("Ledger DB + inbox")]
    LEDGER -. "ACK after durable commit" .-> LOG
~~~

If Redis Lists are mandatory, build and fault-test **ready→processing claiming, durable ACKs, leases/reclaimers, deduplication, and reconciliation**—though operational cost often exceeds adopting Redis Streams, AMQP, or JMS.

### 25.5. Case E – Multiple priority queues

~~~text
catalog:{thumbnail}:high
catalog:{thumbnail}:normal
catalog:{thumbnail}:low
~~~

Producers pick queues via an allowlisted enum. Consumers can prioritize `HIGH` while enforcing **fairness** so `LOW` never starves permanently. Track `LLEN`/oldest-age per queue; a Redis List knows nothing about business priority simply from the word `high`/`low` in its key.

### 25.6. Case F – Redis List → Kafka bridge

~~~text
Redis LPUSH
  -> Redis BRPOP
  -> Kafka outbound producer
  -> Kafka broker ACK
~~~

**Loss window:** Redis `BRPOP` removed the item before the Kafka producer received ACK/commit; crashing loses the event. **Duplicate window:** Kafka stored the record while the client got an `UNKNOWN` outcome, causing a worker retry to resend.

For lossless bridges, use a durable source/processing protocol or transactional outbox/inbox plus Kafka `eventId` deduplication. Never assume Kafka's idempotent producer forms an atomic transaction with Redis `BRPOP`.

### 25.7. Case G – Redis List for best-effort background emails

A Redis List queue works for notifications backed by a campaign/job table that supports reconciliation. Yet email provider timeouts never prove whether an email sent. Enforce `campaignRecipientKey`/idempotency where supported, rate limits, bounded retries, and dead-job policies to prevent spamming duplicates.

### 25.8. Case H – Broadcasting to three replicas

**Never use Redis queue outbound if every replica must receive the same notification.** Redis `POP` implements **competing consumers**: each List item is popped by one worker. To invalidate local caches across every replica, use **Redis Pub/Sub outbound** (with TTL/reconciliation) or a durable fan-out model with one queue per subscriber.

## 26. Common misconceptions

**“Redis queue outbound is the same as Redis Pub/Sub outbound.”** False. Queue outbound **`LPUSH`/`RPUSH`es** into a List; Pub/Sub outbound **`PUBLISH`es** to a channel.

**“A Redis List is just a Redis Stream without consumer groups.”** They are distinct Redis data types. Lists lack native record IDs, PELs, and `XACK`.

**“`LPUSH` always means FIFO for every consumer.”** FIFO holds only when the consumer pops from the **opposite end**, normally `BRPOP`.

**“`LPUSH` + `BLPOP` is FIFO.”** Operating on the same left end produces LIFO/stack ordering.

**“Redis FIFO means jobs finish in exact order.”** Workers have varying execution times; completion order can diverge.

**“Redis queue outbound automatically provisions a JMS/AMQP-like queue entity.”** A Redis List is just a key; pushing creates the List if absent.

**“A List key is a Redis topic you can `SUBSCRIBE` to.”** `LPUSH` emits no Pub/Sub notifications.

**“Queue outbound has a `replyChannel` like a gateway.”** It is a one-way adapter waiting for no business reply.

**“`MessageChannel.send` accepted means the worker finished.”** Spring dispatch/enqueue and business commit are two separate milestones.

**“Redis `LPUSH` returning success means absolute `fsync`/replication and worker ACK.”** Check Redis durability policies; List `POP` has no native ACK.

**“Redis AOF automatically recovers an item already `BRPOP`ped before commit.”** Persistence never rolls back destructive `POP`s alongside application transactions.

**“Queue inbound uses a Spring Integration Poller like store inbound.”** Redis queue inbound is a message-driven blocking listener; store inbound is a polling source/view.

**“`extractPayload=true` converts Spring headers to JSON automatically.”** It sends only payload; put cross-service headers into an explicit envelope/mapping.

**“`extractPayload=false` is the safest cross-language contract.”** Whole Spring `Message`s carry complex runtime types/headers; prefer DTO JSON.

**“The default serializer is always UTF-8 JSON.”** Non-String payloads default to JDK serialization; configure explicitly and test bytes.

**“`StringRedisSerializer` serializes any Java POJO automatically.”** Convert payloads to a JSON String first or use an appropriate typed serializer.

**“Spring `MessageHeaders.ID` is a business `eventId`.”** Runtime Message IDs change across retries/restarts; `eventId` must be business-stable.

**“Redis Lists automatically deduplicate identical `eventId`s.”** Lists allow duplicate elements; enforce business unique constraints.

**“Raising max retries always prevents job loss.”** In-JVM retries vanish on crash and risk duplicates on `UNKNOWN` outcomes.

**“An outbox prevents consumers from losing jobs after `BRPOP`.”** Outboxes protect producer enqueue intent; consumers still need reliable processing or reconciliation.

**“JDBC `@Transactional` rolls back Redis `LPUSH`.”** There is no default distributed transaction between Redis and a database.

**“`LLEN=0` means all business jobs are `DONE`.”** Workers may have popped and crashed, or tasks may sit uncommitted inside an internal executor.

**“Default `QueueChannel` and `ExecutorChannel` are durable across restarts.”** Both are in-memory by default unless configured with a persistent store.

**“One List item is broadcast to every `ImageWorker`.”** Competing consumers hand each item to one worker; broadcast is a different pattern.

**“`BLMOVE` automatically manages retry counts, leases, and ACKs.”** `BLMOVE` only atomically moves items; the application manages processing state.

**“Wiping the entire processing List on error retries safely.”** That drops active jobs from other workers; use `jobId`/ownership/reclaimers.

**“`LREM` after commit guarantees exactly-once.”** Crashing after commit before `LREM` triggers replay; idempotency is still required.

**“Taking dynamic queue names straight from raw HTTP headers is safe.”** It risks writing across tenants/keys; enforce allowlists and ACLs.

**“A `prod` Redis key prefix is a security boundary.”** Prefixes are conventions, not replacements for Redis ACLs, TLS, and network isolation.

**“Redis Cluster `BLMOVE` works across keys in any slots.”** Multi-key commands must hash to the same hash slot.

**“`LTRIM` to keep Redis queues small has no business impact.”** It deletes unprocessed jobs; only accept when explicit loss policies allow.

**“A TTL on a Redis List only delays workers.”** TTL expiry wipes all pending jobs at once.

**“One happy-path test proves end-to-end at-least-once.”** Test crashes on both sides of `LPUSH` and `BRPOP`, idempotency, recovery, unknown outcomes, and failovers.

**“Adding more workers always reduces latency.”** When databases or object storage saturate, adding workers increases retries and failures.

## 27. Redis queue outbound design checklist

| Category | Questions to verify |
| --- | --- |
| **Use case** | Can jobs lost after destructive `POP` be rebuilt? Is there an authoritative source? |
| **Right adapter** | Redis queue outbound (List `PUSH`) vs. Pub/Sub/store/Stream/gateway? |
| **Redis key** | Fixed queue or `queue-expression`; are namespace and `LIST` type right? |
| **Direction** | Do `leftPush=true/false` and consumer `rightPop=true/false` align for FIFO? |
| **Connection** | Does `RedisConnectionFactory` target the right instance/db/Cluster with TLS/credentials? |
| **Payload type** | JSON String, `byte[]`, or whole Spring `Message`? |
| **Serializer** | Do outbound and inbound both use `StringRedisSerializer` or a matched contract? |
| **Headers** | Are `eventId`, `traceparent`, `tenantRef` inside the envelope if needed across Redis? |
| **Schema** | Do `eventType`/`schemaVersion` and worker validation support rolling upgrades? |
| **`MessageChannel`** | What durable/async semantics do `Direct`/`Executor`/`QueueChannel` imply? |
| **Queue routing** | Does `queue-expression` come from an enum/allowlist, never raw input? |
| **Enqueue status** | Are channel accepted, Redis command success, and business `DONE` separated? |
| **Producer retry** | Max attempts/backoff, `UNKNOWN` outcomes, and stable `eventId`? |
| **Producer durability** | Do DB transaction/outbox/reconciliation cover crash-before-`LPUSH`? |
| **Consumer durability** | Is the `BRPOP` loss window accepted or compensated via DB reconciliation? |
| **Reliable queue** | If needed: `BLMOVE`, processing list, owner, lease, ACK, reclaimer? |
| **Idempotency** | Unique `eventId`, `productId`/`imageVersion`, deterministic output/conditional commit? |
| **Dead jobs** | Are poison JSON/invalid schemas durably stored with owner, audit, and replay? |
| **Redis persistence** | Do AOF/RDB and replicas/failover meet RPO/RTO? |
| **Redis Cluster** | Do multi-key processing/ready keys share the same hash slot? |
| **Capacity** | `LLEN`, oldest age, peak enqueue rate, worker throughput, and Redis RAM? |
| **Rate limiting** | Backpressure and bounded internal executors without data-losing `LTRIM`? |
| **Security** | Redis ACLs, key namespaces, tenant/`objectKey` validation, and secrets? |
| **Lifecycle** | Startup/readiness, shutdown, reconnect, and outbox recovery? |
| **Metrics** | Are push/claim/processing/`DONE`/reclaim/dead and queue age tracked separately? |
| **Testing** | Real Redis, direction, serializer, offline worker, duplicates, crash/failover? |
| **Documentation** | Queue owner, schema, TTL/retention, loss policy, and runbooks? |

### 27.1. Quick selection rule

**Redis queue outbound** fits when:

- You need to **hand off work items** to one of multiple competing consumers.
- Simple Redis Lists suffice because lost post-`POP` tasks can be rebuilt/reconciled, or you built reliable claiming/recovery.
- FIFO is needed by **pop order**, without confusing it with completion order.
- Serializers, `eventId`/idempotency, and monitoring are clear.

**Redis Pub/Sub outbound** fits best-effort broadcast notifications. **Redis Stream outbound** fits better when you need record IDs, consumer groups, ACKs, and replay. **AMQP/JMS/Kafka** fit depending on broker, ordering, capacity, durability, and operational needs.

### 27.2. Minimal producer–consumer contract template

~~~text
Redis key:
  catalog:{thumbnail}:pending

Producer:
  LPUSH (leftPush=true)
  StringRedisSerializer, extractPayload=true
  JSON schemaVersion=1
  stable eventId

Consumer:
  BRPOP (rightPop=true)
  StringRedisSerializer, expectMessage=false
  JSON schemaVersion=1
  idempotent handler + durable job state

Operations:
  monitor LLEN + business DONE + oldest job age
  retry/reconciliation for job loss
  alert on Redis errors, duplicates and poison jobs
~~~

### 27.3. Never slap an “exactly-once” label on the adapter

An **exactly-once processing** label only makes sense when defining **business side effects**, idempotency, durable commits, and crash-window handling. `RedisQueueOutboundChannelAdapter` **has no consumer ACK API or distributed transaction**; it simply lets Spring Integration write to a Redis List.

## 28. Self-check questions

1. Which Redis command does the Redis queue outbound channel adapter run to enqueue items?
2. How does `RedisQueueOutboundChannelAdapter` differ from `RedisPublishingMessageHandler`?
3. How does a Redis List queue differ from a Redis Stream regarding record IDs, consumer groups, and ACKs?
4. Why is Redis queue outbound **one-way** rather than a Redis queue outbound gateway?
5. Must a Redis List key be manually pre-created before `LPUSH`, or does Redis create it on push?
6. When a key already holds a Redis String, what happens when `LPUSH` runs?
7. How does `LPUSH` paired with `BRPOP` achieve FIFO behavior?
8. Does `RPUSH` paired with `BLPOP` preserve FIFO? Why?
9. Does `LPUSH` paired with `BLPOP` produce LIFO or FIFO?
10. Why does FIFO at Redis pop time not prove business completion order?
11. Which endpoints own the `leftPush(true)` and `rightPop(true)` options?
12. Does Redis queue inbound require Spring Integration `Pollers.fixedDelay`?
13. What does `extractPayload(true)` push into the Redis List by default?
14. When using `extractPayload(false)`, what must the worker align on for serializer and `expectMessage`?
15. Why doesn't Spring's `MessageHeaders.ID` replace a business `eventId`?
16. If a `String` payload omits an explicit serializer, which serializer may Spring Integration choose?
17. If payload is a POJO while serializer is `StringRedisSerializer`, what risk arises?
18. Why can pushing a JSON String through a JSON serializer cause double-encoding?
19. Do Redis Lists have protocol metadata headers like AMQP/Kafka?
20. Why does `Redis.queueOutboundChannelAdapter(...)` require a `RedisConnectionFactory`?
21. At what layer are Java DSL and direct `@ServiceActivator` equivalent?
22. If two publisher flows point at the same Redis key, how can duplicates occur?
23. How do `queue` and `queue-expression` differ, and can both be set together?
24. What trust boundary must govern a `queue-expression` reading headers from incoming Spring Messages?
25. Why is an allowlisted enum safer than a raw `redisQueue` HTTP header?
26. When a producer uses three priority Lists, how should workers handle fairness and starvation?
27. If a producer `LPUSH`es while workers are offline, under what conditions does Redis retain the items?
28. Why does direct Redis List `BRPOP` have no native consumer ACK?
29. If a worker crashes after `BRPOP` before DB commit, does the item return to the List?
30. When `LPUSH` succeeds yet the client misses the reply, how can retries create duplicates?
31. Why must you preserve the same `eventId` when retrying the same business job?
32. What does in-JVM `RetryTemplate` solve, and what does it fail to solve across crashes?
33. Which crash window between DB commit and `LPUSH` does an outbox prevent?
34. Why doesn't an outbox protect the crash window after `BRPOP`?
35. How does periodic reconciliation on `NEEDS_THUMBNAIL` compensate for lost items?
36. How do unique `eventId` or `productId`/`imageVersion` enable idempotent processing?
37. When a thumbnail output was written yet the worker timed out, why are deterministic object keys and lookups needed?
38. What does `BLMOVE` ready→processing improve over destructive `BRPOP`?
39. Does a processing List automatically manage leases, attempt counts, and reclaiming?
40. Why are exact-item `LREM`, ownership, and stable job identities needed?
41. If business logic commits yet the worker crashes before `LREM`, what risk arises?
42. What does Redis Cluster require for `BLMOVE` source/destination keys?
43. Why can TTL/eviction on a queue List lose pending jobs?
44. Does `LLEN=0` mean all jobs are `DONE`?
45. With two running consumers, is a List item broadcast or competing-popped?
46. How do `DirectChannel` and `ExecutorChannel` differ on errors and in-memory job loss?
47. Does Spring Integration's `ErrorChannel` automatically create a Redis DLQ/replay?
48. Which commands/keys must Redis ACLs restrict for producers and workers?
49. Which Redis CLI test proves `LPUSH` A/B/C followed by `RPOP` yields A/B/C?
50. Which integration test catches producer/worker serializer mismatches?
51. Which integration test proves an offline-then-restarted worker still receives pending List items?
52. Which integration test proves jobs can be lost on `BRPOP`-before-commit?
53. Which integration test proves outbox replay can duplicate while idempotency stops duplicate side effects?
54. If Redis `LPUSH` continuously outpaces workers, which metrics must be watched?
55. Why shouldn't `LTRIM` be the default capacity mechanism for queues holding mandatory jobs?
56. If Redis failover leaves an `UNKNOWN` outcome, how should operations reconcile?
57. If an internal `QueueChannel` accepted a message, has Redis queue outbound definitely `LPUSH`ed yet?
58. When should you migrate from a custom ACK/reclaimer Redis List to Redis Streams or RabbitMQ?
59. In an SFTP→Redis List→worker flow, which milestone truly marks “import completed”?
60. Design a thumbnail pipeline featuring versioned payloads, FIFO Redis List, idempotent workers, a producer outbox, and reconciliation.

## 29. References and version scope

Official references to review before adopting code:

- [Spring Integration – Redis Support](https://docs.spring.io/spring-integration/reference/redis.html): Redis Queue Outbound Channel Adapter, Java DSL/bean/XML, `queue-expression`, `leftPush`, `serializer`, and `extractPayload`.
- [Spring Integration – RedisQueueOutboundChannelAdapter Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/redis/outbound/RedisQueueOutboundChannelAdapter.html): constructors taking `String`/`Expression` + `RedisConnectionFactory`; `setExtractPayload`, `setSerializer`, `setLeftPush`.
- [Spring Integration – RedisQueueMessageDrivenEndpoint Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/redis/inbound/RedisQueueMessageDrivenEndpoint.html): Redis List consumer endpoint, `rightPop`, serializer, and lifecycle.
- [Spring Integration – Changes 4.2 to 4.3](https://docs.spring.io/spring-integration/reference/changes-4.2-4.3.html): addition of `leftPush`/`rightPop` for Redis List queue adapters.
- [Redis – Lists data type](https://redis.io/docs/latest/develop/data-types/lists/): Redis Lists, `LPUSH`/`RPUSH`/`POP`, and ordering.
- [Redis – BLMOVE](https://redis.io/docs/latest/commands/blmove/): atomic moves between Lists, `RIGHT`/`LEFT` selection, and blocking reads.
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): `RedisConnectionFactory`, serializers, and `RedisTemplate` operations.

**Version scope:** Spring Integration 3.0 introduced the Redis queue outbound adapter; `leftPush`/`rightPop` appeared in 4.3. Java DSL APIs, Redis serializers, Spring Boot properties, and Redis Cluster behavior must be **compiled and tested against your actual BOM/client/server versions** prior to production. This is **STEP 4** content and does not substitute for Gradle builds or deep academic QA in STEP 6.

## Summary

The **Redis queue outbound adapter** receives Spring Integration Messages and writes them to a **Redis List** via **`LPUSH` by default** or `RPUSH`. In Java you can use **`Redis.queueOutboundChannelAdapter(...)`** or **`RedisQueueOutboundChannelAdapter`** directly. Align **`queue name`/`queue-expression`, `RedisConnectionFactory`, `StringRedisSerializer`, `extractPayload`, and `leftPush`** with your consumer. Pairing **`LPUSH` + `BRPOP`** achieves FIFO in **pop order**, without guaranteeing business completion order under multiple workers.

Remember that **enqueue success differs from business completion**. A Redis List retains a backlog while workers are offline if data persists, yet **`BRPOP` destroys the item before handler commit** and offers no native ACK. Worker crashes after pop lose jobs; producer retries on `UNKNOWN` Redis outcomes create duplicates. **Transactional outboxes, durable business state, reconciliation, idempotent workers**, or a reliable processing protocol / Redis Streams are essential whenever jobs must complete across failures.

When integrating Redis Lists with HTTP, SFTP, File, JMS, AMQP, Kafka, and databases in **SPRING_INTEGRATION_ADAPTERS**, clearly separate **DB commit → Spring `MessageChannel` dispatch → Redis `LPUSH`/`RPUSH` → worker claim/pop → durable business commit**. A solid flow doesn't just enqueue JSON—it defines **data contracts, error boundaries, security, capacity, monitoring, and crash testing** rigorously enough to operate and recover cleanly.
