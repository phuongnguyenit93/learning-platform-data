# Redis queue inbound adapter

## Learning Objectives

After this lesson, you will be able to:

- Explain how the **Redis queue inbound adapter** brings data from a Redis **List** into a **Spring Integration MessageChannel**; distinguish it from the Redis Pub/Sub inbound adapter.
- Understand **blocking pop** mechanics, how to pair **LPUSH/BRPOP** or **RPUSH/BLPOP**, FIFO ordering, and the impact when multiple consumers read from the same queue key.
- Configure **RedisQueueMessageDrivenEndpoint**, **RedisConnectionFactory**, output channel, transformer, and service activator; distinguish a message-driven endpoint based on blocking reads from an actual Spring Integration poller.
- Build a payload contract, serializer/charset, `eventId`, `schemaVersion`, and rules for handling missing or malformed messages.
- Analyze the data-loss window when **popping from a List before the business transaction commits**, even when Redis persistence is enabled; understand the limits of retries and `errorChannel`.
- Design more reliable approaches using **BLMOVE/LMOVE to a processing list**, application-level ACK, a reclaimer, idempotent consumers, or **Redis Streams consumer groups**.
- Organize concurrency, retry/backoff, poison message handling, monitoring of ready/processing/dead messages, security, and graceful shutdown.
- Test with real Redis for FIFO ordering, competing consumers, crash-after-pop, duplicates, malformed payloads, reconnects, and recovery capability.

## 1. Scenario: Redis List as a work queue

Suppose **CatalogService** needs to ask **ImageWorker** to generate a thumbnail after receiving a product image. Instead of sending a synchronous HTTP request and waiting for image processing, `CatalogService` pushes a task into a **Redis List** named:

~~~text
Key: catalog:thumbnail:pending
Value: {"eventId":"evt-thumb-1001","schemaVersion":1,
        "productId":"P-1001","imageKey":"images/P-1001/original.jpg"}
~~~

`ImageWorker` wants to receive that task and execute processing:

~~~mermaid
flowchart LR
    P["CatalogService"] -->|"LPUSH task"| L["Redis List<br/>catalog:thumbnail:pending"]
    L -->|"Blocking POP"| A["Redis queue<br/>inbound adapter"]
    A --> C["Spring Integration<br/>MessageChannel"]
    C --> V["Validate / transform"]
    V --> H["Thumbnail service activator"]
    H --> OBJ[("Object storage")]
    H --> DB[("Catalog DB")]
~~~

The **Redis queue inbound adapter** is the boundary that ingests messages from a Redis List-based queue. From Spring Integration's perspective, this endpoint is a **message producer**: it pulls items from Redis and emits **Spring Messages** into an output channel for downstream transformers/routers/service activators to process.

A design point to check immediately: **If the adapter pops a task from Redis and the JVM crashes before writing the thumbnail, is the task still in the queue?** With a direct destructive pop, the answer is usually **no**. This is a critical difference between a simple List queue and a message broker with consumer ACKs, pending state, and redelivery.

This lesson belongs to the **Adapter Redis** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module studies inbound/outbound adapters, gateways, pollers, `MessageChannel`, and integration with File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. Even though they share the name “adapter,” **delivery guarantees depend on the source system**—you cannot infer AMQP/Kafka guarantees merely because Spring Integration received a message.

## 2. Redis Lists and queues: understand the data structure before using the adapter

A Redis **List** is an ordered sequence of elements. Commands exist to push and pop elements at both ends:

| Command | Basic behavior | Queue usage |
| --- | --- | --- |
| **LPUSH key value** | Prepends `value` at the left head | Producer adds tasks in `LPUSH`/`BRPOP` pattern |
| **RPUSH key value** | Appends `value` at the right tail | Producer adds tasks in `RPUSH`/`BLPOP` pattern |
| **LPOP key** | Removes and returns the leftmost element | Nonblocking consumer in `RPUSH`/`LPOP` pattern |
| **RPOP key** | Removes and returns the rightmost element | Nonblocking consumer in `LPUSH`/`RPOP` pattern |
| **BLPOP key timeout** | Waits for an element then removes/returns from left | Blocking consumer in `RPUSH`/`BLPOP` pattern |
| **BRPOP key timeout** | Waits for an element then removes/returns from right | Blocking consumer in `LPUSH`/`BRPOP` pattern |
| **LLEN key** | Counts items remaining in the List | Measures ready backlog, not in-flight tasks |
| **LMOVE/BLMOVE** | Atomically moves an item between two Lists | `ready` → `processing` pattern enabling recovery |
| **LREM key count value** | Removes elements matching `value` from a List | Can act as application ACK after processing, requires proper ID/sync |

### 2.1. Two equivalent FIFO patterns when pushing/popping from opposite ends

**Pattern A – producer `LPUSH`, consumer `BRPOP`:**

~~~text
LPUSH task-A
LPUSH task-B
LPUSH task-C

List left -> right:
  [task-C, task-B, task-A]

BRPOP retrieves: task-A, then task-B, then task-C
~~~

**Pattern B – producer `RPUSH`, consumer `BLPOP`:**

~~~text
RPUSH task-A
RPUSH task-B
RPUSH task-C

List left -> right:
  [task-A, task-B, task-C]

BLPOP retrieves: task-A, then task-B, then task-C
~~~

Both patterns achieve FIFO order according to the order in which Redis executes the push commands. **Do not mix `LPUSH` with `BLPOP`** and expect FIFO: operating on the same end produces LIFO.

### 2.2. A Redis List does not track pending/ack state on its own

When **BRPOP** returns an item, that element has already been removed from the List. Redis does not remember that **consumer X is processing task A** to wait for an ACK from the business handler.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Redis List
    participant I as Inbound adapter
    participant H as Thumbnail handler
    P->>R: LPUSH task-A
    I->>R: BRPOP pending timeout
    R-->>I: task-A (removed from List)
    I->>H: Spring Message(task-A)
    H--xH: Process crash
    Note over R,H: task-A is no longer in pending List
~~~

**Distinguish** Redis persistence from acknowledgment: Redis can durably persist the List's state, but once a `POP` command is applied, the persisted state afterward is **the List without the popped item**. AOF/RDB does not turn a `POP` into an un-ACKed delivery.

### 2.3. Queue FIFO does not equal work completion order

Even if Redis returns item A before item B, two workers can take different amounts of time:

~~~text
Worker 1 receives A -> takes 10 seconds
Worker 2 receives B -> takes 1 second

Completion: B finishes before A
~~~

If business rules require ordered updates for the same `productId`, use a version/sequence or per-business-key locking. **Redis List FIFO does not guarantee global completion order under concurrency.**

### 2.4. A queue key is not a Pub/Sub channel

The name **catalog:thumbnail:pending** in a Redis List is a **data-storage key**. `LPUSH` modifies the List; it **does not `PUBLISH`** a Redis Pub/Sub notification on a channel of the same name.

A subscriber running `SUBSCRIBE catalog:thumbnail:pending` will **not receive** `LPUSH`ed items. Conversely, a Redis queue inbound adapter reading a List does not receive `PUBLISH` messages like a Pub/Sub inbound adapter.

## 3. Differences between Redis queue inbound, Redis Pub/Sub, and Redis Streams

| Criterion | Redis List queue inbound | Redis Pub/Sub inbound | Redis Streams consumer |
| --- | --- | --- | --- |
| Data source | Redis List key | Redis Pub/Sub channel/pattern | Redis Stream key |
| Writing data | `LPUSH`/`RPUSH` | `PUBLISH` | `XADD` |
| Reading | `BLPOP`/`BRPOP` or appropriate List ops | `SUBSCRIBE`/`PSUBSCRIBE` callback | `XREAD`/`XREADGROUP` |
| Items retained when consumer offline? | **Yes**, if unpopped and Redis retains data | **No**, Pub/Sub has no subscriber backlog | **Yes**, within retention limits |
| Multiple consumers on same source | Compete to pop each item | Every matching subscriber receives | Consumer groups distribute records |
| Broker-managed ACK | None on simple List `POP` | None | `XACK` for consumer group |
| Pending/redelivery | Must build processing list/reclaimer | None | PEL/pending + claim/recovery |
| Loss risk after app receives? | **Yes**, crash after `POP` | **Yes**, after callback or while offline | Depends on ACK/retention/design |
| Best suited for | Simple task queues that can be recovered/rebuilt | Best-effort cache invalidation | Events/jobs needing history and explicit recovery |

### 3.1. Do not call every Redis inbound adapter Pub/Sub

Redis Pub/Sub inbound uses listeners and topic patterns; the **Redis queue inbound adapter** consumes items from a **List**. Both adapters may emit Spring Messages into a `DirectChannel`, but **everything before the `MessageChannel` is completely different**.

### 3.2. Streams are not just “a List with extra fields”

Redis Streams provide record IDs, consumer groups, pending entry tracking, and commands like `XACK`/`XCLAIM`/`XAUTOCLAIM`. Those capabilities do not appear automatically when pointing a Redis queue inbound adapter at a List. If requirements demand pending tracking/ACKs, choose **Streams** or implement and operate a custom reliable queue protocol.

### 3.3. A List retains data while consumers are offline, yet still has a loss window

~~~text
Scenario 1:
  Worker is offline before POP.
  Producer LPUSHes task.
  -> Task remains in List for the worker to pick up later.

Scenario 2:
  Worker just BRPOPped task.
  Worker crashes before business commit.
  -> Task already left the List; it does not automatically return.
~~~

A basic Redis List queue **differs from Pub/Sub by buffering a backlog while workers are offline**, yet **still falls short of end-to-end at-least-once** if it uses a direct destructive pop before processing.

## 4. Message-driven via blocking POP, not a Pub/Sub callback

The name **message-driven endpoint** sometimes leads learners to think Redis actively pushes messages to the client via `PUBLISH`. For a List queue, the consumer can **block waiting for Redis to return an item** via a List read command.

~~~text
RedisQueueMessageDrivenEndpoint
   -> Redis connection
   -> blocking List pop, e.g. BRPOP
   -> item retrieved from Redis
   -> build Spring Message
   -> output MessageChannel
~~~

It is considered **message-driven in the Integration endpoint model** because it runs a listening/blocking-read loop and emits messages as items arrive, **without requiring a periodic Spring Integration Poller** like File inbound.

### 4.1. Blocking read is not `poller.fixedDelay`

| Concept | Role |
| --- | --- |
| Blocking Redis pop | Redis command that waits until an item arrives or timeout expires |
| Redis queue message-driven endpoint | Manages the queue receive loop and emits Spring Messages |
| Spring Integration poller | Scheduler periodically calling `receive()` on a `PollableMessageSource` |
| Internal `QueueChannel` poller | Poller pulling Spring Messages from a `QueueChannel`, not necessarily reading Redis |

If a framework version offers a **polled Redis store source**, that is a different endpoint model; do not attach a poller to `RedisQueueMessageDrivenEndpoint` just because it reads from a List.

### 4.2. What is the blocking timeout for?

In a blocking Redis pop, the timeout allows the receive loop to check shutdown/reconnect state depending on the implementation. Timeout **does not mean business retry backoff**, nor does it **create a delivery ACK**. Do not apply an untested `receive-timeout` to an environment with specific SLAs and client versions.

### 4.3. Which component should be used?

Spring Integration Redis provides a dedicated endpoint commonly known as **RedisQueueMessageDrivenEndpoint** for Redis List queue inbound. Versions may differ in constructors/DSL setters, serializers, and task executors. The examples below follow the endpoint structure found in Spring Integration generations; when adopting it in a project, verify the API of your **actual dependency version** rather than copying from another version.

Although you can write your own `RedisTemplate.opsForList().rightPop(...)` loop, the dedicated adapter manages **lifecycle**, **output channel**, and integration wiring more consistently. However, the adapter **cannot provide delivery guarantees that Redis List `POP` does not offer**.

## 5. Message contract: a Redis List item is bytes, not a Spring Message

A Redis List stores values as serialized data. A Spring Message exists only **once the inbound endpoint creates it**.

~~~mermaid
flowchart LR
    DTO["Task DTO"] --> SER["Serializer"]
    SER --> B["Redis List bytes"]
    B --> POP["Queue inbound endpoint"]
    POP --> MC["Spring Message<br/>payload + headers"]
    MC --> TR["Transformer / parser"]
    TR --> H["Thumbnail handler"]
~~~

### 5.1. Choose an explicit schema

Example task JSON:

~~~json
{
  "eventId": "evt-thumb-1001",
  "eventType": "THUMBNAIL_REQUESTED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "productId": "P-1001",
    "imageKey": "images/P-1001/original.jpg"
  }
}
~~~

| Field | Role | Rule |
| --- | --- | --- |
| `eventId` | Idempotency key | Stable across retries/requeues |
| `eventType` | Job type | Allowlist; do not infer solely from queue key |
| `schemaVersion` | Contract version | Consumer rejects unsupported versions |
| `occurredAt` | Domain request time | Not equivalent to Redis `POP` time |
| `productId` | Business identity | Validate format/tenant permissions |
| `imageKey` | Object storage reference | Allow only valid namespaces/paths |

### 5.2. Redis Lists have no AMQP headers

A Redis List value does not inherently carry basic properties like AMQP's `messageId`/`correlationId`/`replyTo`/`contentType`. If cross-system metadata is needed, place it in the **payload envelope** or design a matching serialization scheme.

Spring Integration may generate `MessageHeaders.ID` and `timestamp` for a **new** Spring Message, but those fields **do not replace a durable business `eventId`** when a task must be retried or picked up by another worker.

### 5.3. Align push/pop direction and serializers

If the producer uses `StringRedisTemplate`:

~~~java
stringRedisTemplate.opsForList()
    .leftPush("catalog:thumbnail:pending", json);
~~~

then the consumer must read the exact same Redis key with a **compatible byte encoding**. With a `BRPOP` consumer, `LPUSH`/`BRPOP` preserves FIFO. With a `BLPOP` consumer, use `RPUSH`/`BLPOP` for FIFO.

**Do not guess the pop end from a class name alone:** inspect the implementation/API of the Spring Integration Redis version in use and write an ordering integration test with at least three items before finalizing the push side.

### 5.4. JSON serializer vs. Java object serialization

Avoid native Java serialization as an interchange contract between services or with untrusted data. Prefer **UTF-8 JSON/Avro/Protobuf** with `schemaVersion`, size limits, and a target type allowlist.

If a producer serializes an already-serialized JSON String a second time with a JSON serializer, the Redis List can end up holding a **JSON string literal** instead of a JSON object. If the converter/handler decodes twice or mismatches charsets, events can fail even though `LPUSH` succeeded.

## 6. Dependencies and RedisConnectionFactory configuration

Example dependencies with Spring Boot and Spring Integration Redis:

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

Use **Spring Boot dependency management/BOM** to manage compatible versions of Spring Data Redis, Spring Integration, and the Redis client. APIs can vary across versions; compile against the actual version in use.

### 6.1. Local/test Spring Boot properties

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

This is a local example. Production requires TLS, ACLs, Sentinel/Cluster, client pool/resources, and timeouts matched to the real infrastructure. Redis **has no RabbitMQ-style vhost**; establish explicit key namespaces/prefixes and permissions on the Redis instance.

Different Spring Boot generations may use different Redis property names; check the documentation for your exact Boot version rather than copying properties verbatim during upgrades.

### 6.2. RedisConnectionFactory does not consume queues by itself

**RedisConnectionFactory** creates Redis connections; it does not know which queue key to read or invoke service activators. The **RedisQueueMessageDrivenEndpoint** (or custom List-reading component) is responsible for reading the queue and emitting Spring Messages.

### 6.3. Scope of transport configuration

When a Redis endpoint uses a shared List key:

~~~text
Redis URL/host
  -> Authentication/ACL
  -> Key: catalog:thumbnail:pending
  -> List push/pop contract
  -> Payload bytes + serializer
  -> Spring Integration output MessageChannel
~~~

Matching the queue name alone is not enough if the publisher targets a different Redis instance, different database index, different ACLs, or an incompatible serializer.

## 7. Publisher example: LPUSHing a thumbnail job

The producer pushes JSON into a Redis List using **StringRedisTemplate**. Producer **LPUSH** is chosen to illustrate a consumer reading from the `BRPOP` end.

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailJobPublisher {

    public static final String PENDING_QUEUE =
        "catalog:thumbnail:pending";

    private final StringRedisTemplate redisTemplate;

    public ThumbnailJobPublisher(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public long enqueueJson(String json) {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException(
                "Thumbnail job JSON must not be blank");
        }

        Long size = redisTemplate.opsForList()
            .leftPush(PENDING_QUEUE, json);

        if (size == null) {
            throw new IllegalStateException(
                "Redis did not return a queue length");
        }
        return size;
    }
}
~~~

**`enqueueJson` returns the List length after `LPUSH`**, not the number of workers that processed it successfully. A successful Redis command does not prove the thumbnail exists in object storage.

### 7.1. Enqueueing a job with Redis CLI

On a **test** Redis instance:

~~~bash
redis-cli LPUSH catalog:thumbnail:pending '{"eventId":"evt-thumb-1001","eventType":"THUMBNAIL_REQUESTED","schemaVersion":1,"data":{"productId":"P-1001","imageKey":"images/P-1001/original.jpg"}}'
redis-cli LLEN catalog:thumbnail:pending
~~~

If a worker is running, `LLEN` may drop back to **0 very quickly** because the item was already popped. **`LLEN=0` does not prove the job completed business processing.**

### 7.2. Publisher failures and ambiguous outcomes

If the network drops around an `LPUSH`, the producer may not know whether Redis accepted the value. Retrying an `LPUSH` with the same JSON **can create two identical List items**.

Therefore, the producer must supply a **stable `eventId`**, and the consumer needs idempotency if side effects must not repeat. Do not generate a new `eventId` per retry for the same business task when deduplication is desired.

### 7.3. LPUSH is not atomic with a DB commit

If `CatalogService` saves task metadata in the database and then `LPUSH`es:

~~~text
DB commit -> process crash -> LPUSH never happened
~~~

the job may never be enqueued. If it `LPUSH`es before commit and the DB rolls back, a worker may run for a non-existent record. For critical delivery requirements, consider a **transactional outbox** or a durable state source with a worker dispatching jobs post-commit, combined with idempotency.

## 8. Spring Integration Redis queue inbound endpoint

In Spring Integration Redis versions supporting this API, the dedicated endpoint is typically **RedisQueueMessageDrivenEndpoint**. It is configured with a **Redis queue key**, **RedisConnectionFactory**, and **output channel**.

### 8.1. Creating a DirectChannel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ThumbnailQueueChannelConfig {

    @Bean
    public MessageChannel thumbnailInput() {
        return new DirectChannel();
    }
}
~~~

### 8.2. Registering RedisQueueMessageDrivenEndpoint

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.integration.redis.inbound.RedisQueueMessageDrivenEndpoint;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ThumbnailRedisQueueInboundConfig {

    @Bean
    public RedisQueueMessageDrivenEndpoint thumbnailRedisQueueInbound(
            RedisConnectionFactory connectionFactory,
            @Qualifier("thumbnailInput")
            MessageChannel thumbnailInput) {

        RedisQueueMessageDrivenEndpoint endpoint =
            new RedisQueueMessageDrivenEndpoint(
                ThumbnailJobPublisher.PENDING_QUEUE,
                connectionFactory);

        endpoint.setOutputChannel(thumbnailInput);
        return endpoint;
    }
}
~~~

**Compatibility note:** This is a **Java configuration pattern for API generations that provide `RedisQueueMessageDrivenEndpoint` with that constructor**. Depending on version, packages, constructors, serializers, receive timeouts, or DSL options may vary. Verify against your project's actual dependencies and compile; if the API differs, adapt to your version rather than guessing setters or using reflection.

**Important:** Configuring this endpoint does not automatically provide ACKs/DLQ or manage a processing list. If the implementation reads via destructive pop, business side effects carry the **post-pop job-loss window** described in section 2; evaluate processing paths and reliability needs before going to production.

### 8.3. Verify the read direction

The lab uses `LPUSH`/`BRPOP` for FIFO. Do not assume solely from the bean above that every endpoint version uses `BRPOP`, shares the same default serializer, or uses the same blocking timeout. Push A, B, C into a test queue and observe the received order; if the endpoint pops from the opposite end, **adjust the producer side** or configure the endpoint per its official API.

### 8.4. Do not attach a poller to a message-driven endpoint

`RedisQueueMessageDrivenEndpoint` receives data via its own blocking-read loop. **`Pollers.fixedDelay(...)`** only makes sense for a **polled message source** or a downstream `QueueChannel` needing its own consumer; do not add a poller to this endpoint expecting retries or message persistence.

### 8.5. One endpoint, one clear responsibility

If multiple Spring beans register endpoints reading **the same Redis List**, they become **competing consumers**. That can be right for distributing work, but wrong if you expect each bean to receive every item like Pub/Sub broadcast.

Do not simultaneously run **`RedisQueueMessageDrivenEndpoint`** and a manual `BLPOP` consumer on the same queue during an integration test when trying to verify the dedicated adapter alone: the two consumers will race for items, making test results nondeterministic.

## 9. Spring Integration flow: receive payload, validate, and invoke service

The queue inbound endpoint emits Spring Messages to **thumbnailInput**. We connect that channel to a handler:

~~~mermaid
flowchart LR
    POP["Redis queue inbound"] --> CH["thumbnailInput<br/>DirectChannel"]
    CH --> V["PayloadDecoder"]
    V --> J["JSON parser + schema validation"]
    J --> H["ThumbnailJobHandler"]
    H --> B["Idempotent processing"]
~~~

### 9.1. Java DSL without casting before knowing the serializer

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class ThumbnailQueueFlowConfiguration {

    @Bean
    public IntegrationFlow thumbnailQueueFlow(
            ThumbnailJobHandler thumbnailJobHandler) {

        return IntegrationFlow.from("thumbnailInput")
            .handle((payload, headers) -> {
                final String json;

                if (payload instanceof String) {
                    json = (String) payload;
                } else if (payload instanceof byte[]) {
                    json = new String(
                        (byte[]) payload, StandardCharsets.UTF_8);
                } else {
                    throw new IllegalArgumentException(
                        "Unsupported Redis queue payload type: "
                            + payload.getClass().getName());
                }

                thumbnailJobHandler.handle(json);
                return null;
            })
            .get();
    }
}
~~~

**Why not assume a `String` payload?** A Redis List stores bytes; the adapter may use its own serializer and emit `String`, `byte[]`, or another `Message` representation depending on version and configuration. This code **accepts only the two types listed**; if the dedicated adapter emits another object type or tries to deserialize with an incompatible serializer, adjust the endpoint's converter/serializer and test. Never silently call `toString()` on an unknown object type.

Handling `String`/`byte[]` identifies the type in the handler but **does not enforce strict UTF-8 decoding**. If the contract requires rejecting invalid UTF-8 byte sequences, use a `CharsetDecoder` with `CodingErrorAction.REPORT` or an equivalent validator.

### 9.2. When the default serializer is incompatible with StringRedisTemplate

There is no rule guaranteeing `RedisQueueMessageDrivenEndpoint` and `StringRedisTemplate` share **the same default serializer**. Some versions/endpoints are designed to receive messages serialized by the corresponding outbound adapter; others configure serializers separately.

If consumer tests fail with deserialization errors even though the raw Redis List item is valid JSON, check:

1. The actual **raw bytes** `LPUSH`ed by the producer.
2. The **`RedisSerializer`** configured on the inbound endpoint.
3. Whether the endpoint expects a serialized **Spring `Message`** or just a text/binary payload.
4. Whether the implementation pops from **LEFT or RIGHT**.
5. Whether the same serializer contract is configured on both inbound and outbound sides.

Proceed only after producer–consumer **pass a contract test**. Do not “fix” things by trying to parse Java-serialized bytes as UTF-8.

### 9.3. Splitting into transformer and service activator

In a production flow, it is good practice to separate:

~~~text
thumbnailInput
  -> PayloadDecoder (bytes/String -> JSON text)
  -> JsonToThumbnailJob transformer (JSON -> DTO)
  -> BeanValidation/SchemaValidator
  -> ThumbnailJobHandler
~~~

Benefits: each stage produces specific errors for logging/quarantine, is easy to unit test, and avoids coupling the business handler to low-level payload types.

### 9.4. Handler return is not a Redis List ACK

Once an item has been popped from a Redis List, the service activator returning cleanly **does not send a special Redis ACK** for that item. With direct List pop, Redis modified the queue state **before** the handler ran. If the handler throws an exception, Redis does not automatically NACK/requeue under this pattern either.

## 10. Model, validation, and business handler

A thumbnail job should have a stable `eventId` and `schemaVersion`, rather than letting the Redis queue key dictate all business semantics.

### 10.1. DTO and parser

~~~java
public record ThumbnailJob(
        String eventId,
        String eventType,
        int schemaVersion,
        Data data) {

    public record Data(
            String productId,
            String imageKey) {
    }
}
~~~

~~~java
public class InvalidThumbnailJobException
        extends RuntimeException {

    public InvalidThumbnailJobException(String message) {
        super(message);
    }

    public InvalidThumbnailJobException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

### 10.2. ThumbnailJobHandler

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailJobHandler {

    private final ObjectMapper objectMapper;
    private final ThumbnailProcessingService processingService;

    public ThumbnailJobHandler(
            ObjectMapper objectMapper,
            ThumbnailProcessingService processingService) {
        this.objectMapper = objectMapper;
        this.processingService = processingService;
    }

    public void handle(String json) {
        if (json == null || json.length() > 16_384) {
            throw new InvalidThumbnailJobException(
                "Thumbnail task is missing or too large");
        }

        final ThumbnailJob job;
        try {
            job = objectMapper.readValue(json, ThumbnailJob.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidThumbnailJobException(
                "Malformed task JSON", ex);
        }

        if (job == null
                || job.eventId() == null
                || !job.eventId().matches("[A-Za-z0-9_-]{1,80}")
                || !"THUMBNAIL_REQUESTED".equals(job.eventType())
                || job.schemaVersion() != 1
                || job.data() == null
                || job.data().productId() == null
                || !job.data().productId()
                    .matches("[A-Za-z0-9_-]{1,80}")
                || job.data().imageKey() == null
                || !job.data().imageKey().startsWith("images/")) {

            throw new InvalidThumbnailJobException(
                "Unsupported thumbnail task contract");
        }

        processingService.process(job);
    }
}
~~~

~~~java
public interface ThumbnailProcessingService {
    void process(ThumbnailJob job);
}
~~~

**`ThumbnailProcessingService` is an interface** that you must implement (ImageMagick, Java image libraries, object storage, database, or worker API). The example does not initialize an object storage/client and does not assume all side effects belong to a single transaction.

### 10.3. Validation of `imageKey` here is not sufficient for production

Checking `startsWith("images/")` is only a minimal example. If `imageKey` becomes a filesystem path or object storage key:

- Never use the raw key to open a local file without path traversal checks.
- Verify the tenant/owner of the product.
- Whitelist buckets/prefixes/content types.
- Limit image file size, pixel dimensions, and processing time.
- Never execute shell commands via string concatenation from inputs.

Even an internal Redis List key can receive invalid or malicious data if another producer has write permissions.

### 10.4. Jackson, Spring beans, and transactions

`ObjectMapper` must be provided via Spring configuration (e.g., Spring Boot JSON auto-configuration or an explicit bean). When updating the DB inside `ThumbnailProcessingService`, use **`@Transactional` on a Spring-proxied service bean** if a database transaction is needed.

**A database transaction does not cover the Redis pop that already occurred earlier.** If the service throws/rolls back, the popped item does not automatically reappear in the pending queue.

### 10.5. Idempotency before side effects

If a producer `LPUSH`es the same `eventId` twice or a reclaimer returns a task to the queue after a failure, `processingService` may encounter duplicates. One possible schema:

~~~text
thumbnail_jobs
  event_id VARCHAR PRIMARY KEY
  product_id VARCHAR
  state VARCHAR  -- NEW / PROCESSING / DONE / FAILED
  output_key VARCHAR
  updated_at TIMESTAMP
~~~

Combine:

- A unique constraint on `eventId`.
- An idempotent output object key, e.g., derived from `productId` + image version.
- Processing state and reconciliation capability.
- If the task is already `DONE`, create no new side effects; return an idempotent result.

Avoid the “`SELECT` to check if `eventId` exists then `INSERT`” pattern without a unique constraint, as multiple workers can race.

## 11. Quick test with Redis CLI: FIFO and destructive POP

On a **test** Redis instance:

~~~bash
redis-cli DEL test:thumbnail:pending
redis-cli LPUSH test:thumbnail:pending task-A
redis-cli LPUSH test:thumbnail:pending task-B
redis-cli LPUSH test:thumbnail:pending task-C
redis-cli LLEN test:thumbnail:pending
redis-cli BRPOP test:thumbnail:pending 1
redis-cli BRPOP test:thumbnail:pending 1
redis-cli BRPOP test:thumbnail:pending 1
redis-cli LLEN test:thumbnail:pending
~~~

Expected logic:

~~~text
Before pop: LLEN = 3
Pop 1: task-A
Pop 2: task-B
Pop 3: task-C
After pop: LLEN = 0
~~~

**Only run `DEL` on test keys you are allowed to delete.** Never run it on production keys holding real work.

If you point a running Redis queue inbound adapter at the same test queue, the adapter will race with Redis CLI to pop items, yielding nondeterministic results. When testing the pop direction of an endpoint, use an isolated test queue and only the single consumer required by the scenario.

### 11.1. Testing Redis with an offline worker

1. Stop the queue inbound endpoint before the producer `LPUSH`es.
2. Push two tasks into the Redis List.
3. Verify `LLEN=2` when no other consumers are running.
4. Start the inbound endpoint.
5. Observe the tasks arriving at the `MessageChannel`/handler.

If Redis retains the List data per infrastructure setup and nobody else pops it, items stay in the List while the worker is down. This is an advantage of a List queue over Redis Pub/Sub notifications.

### 11.2. Testing crash after POP

1. Let the consumer pop a task.
2. Intentionally kill the process before the handler finishes.
3. Observe that **the pending List may no longer contain the task**.
4. Restart the consumer and verify **it does not automatically re-receive** that task from the pending List.

This is an essential experiment for understanding reliability. If you must avoid losing jobs after pop, use the **processing list** pattern or Redis Streams in later sections rather than just turning on Redis AOF/RDB.

## 12. The data-loss window of destructive POP

A direct Redis List queue flow typically follows this sequence:

~~~text
Producer LPUSHes job
  -> Redis List holds job
  -> Consumer BRPOPs, removing job from List
  -> Adapter creates Spring Message
  -> DirectChannel invokes handler
  -> Handler executes side effects
  -> Business commit
~~~

**Redis removes the job from the pending List before the business commit milestone.** Even though `DirectChannel` is synchronous, the `POP` command is a separate event outside the database or object storage transaction.

### 12.1. Failure timing matrix

| Failure point | Redis pending List state | Business state | Risk |
| --- | --- | --- | --- |
| Before `LPUSH` | Job absent | Unprocessed | Producer must retry/outbox |
| `LPUSH` succeeded, not yet `POP`ped | Job present if Redis retains state | Unprocessed | Worker can pick up later |
| `POP` finished, Spring Message not yet built | Job gone | Unprocessed | **Task lost** |
| Dispatched to `DirectChannel`, handler unfinished | Job gone | Uncertain | **Task lost on crash** |
| Database rollback after `POP` | Job gone | Uncommitted | **No broker redelivery** |
| Database committed, before logging success | Job gone | Committed | Hard to observe outcome; producer retry can duplicate |
| Producer re-`LPUSH`es same `eventId` | May add second item | Possibly already processed | Needs idempotent consumer |

**Redis persistence does not solve `POP` followed by business rollback**: Redis knows nothing about an external business transaction. Spring `@Transactional` on a service activator cannot roll back a Redis `POP` either.

### 12.2. Is “enabling AOF” enough?

RDB/AOF and replication help Redis recover **Redis data state** under configured conditions. They do not restore an element after **`BRPOP` has already removed it**.

Furthermore, Redis persistence/replication carries varying guarantees across crashes or failovers. Never claim an `LPUSH` is durably persisted on every node simply because Redis returned success; evaluate AOF/`fsync` settings, replication/failover behavior, and your system's RPO/RTO requirements.

### 12.3. Can we retry the handler inside the listener?

Yes. A `RetryTemplate` or retry advice can retry a database/API operation a few times **after `POP`**, as long as the process stays alive. This mitigates brief transient glitches, yet:

- Cannot recover a task after a process crash.
- Does not prevent producer duplicates.
- Can hold the receiving thread for a long time, lowering throughput.
- If the payload is permanently invalid, hot retries accomplish nothing.

**In-process retry is different from durable Redis redelivery.** Even if all 3 retry attempts execute and fail, the item does not automatically return to the pending List.

### 12.4. Does ErrorChannel save the item?

Spring Integration's `errorChannel` can route an **`ErrorMessage`** when an endpoint/flow supports and configures it. However, it **does not create a Redis ACK/NACK** for the popped item, nor does it return the item to the List.

If replay after error is required, you must persist the payload/job metadata durably and define clear ownership transfer. When using an error flow to republish into a Redis List, account for **duplicates, failed republish results, and infinite recursion/retries**.

## 13. Reliable queue with a processing List: core principle

To avoid the window where “once `POP`ped, no backup copy remains for recovery,” a common pattern uses **two Redis Lists**:

~~~text
catalog:{thumbnail}:ready
catalog:{thumbnail}:processing
~~~

We move a job from `ready` to `processing` **in a single atomic Redis operation**, instead of deleting it outright from Redis:

~~~mermaid
flowchart LR
    PUB["Producer"] -->|"LPUSH"| Q["ready List"]
    Q -->|"BLMOVE RIGHT LEFT"| W["processing List"]
    W --> H["Worker process"]
    H -->|"Commit + ACK via LREM"| DONE["Done"]
    W -->|"Worker crash / timeout"| RC["Reclaimer"]
    RC -->|"Controlled requeue"| Q
~~~

### 13.1. Redis BLMOVE

On Redis versions supporting **BLMOVE**:

~~~redis
BLMOVE catalog:{thumbnail}:ready catalog:{thumbnail}:processing RIGHT LEFT 2
~~~

This command **waits** for an element from the right of the `ready` List and **moves** it to the left of the `processing` List in a single Redis operation. The value is returned to the worker for processing.

If it times out with no item, the client receives an empty result; that is not a business failure. If the connection drops, you must determine whether the job was moved into `processing` before assuming safety.

### 13.2. Business ACK by removing from processing

After processing and committing:

~~~redis
LREM catalog:{thumbnail}:processing 1 job-payload
~~~

This is an **application-designed ACK**, not a native Redis List ACK/consumer group. You must ensure the removed element is the **exact job**. If two payloads are byte-for-byte identical, `LREM` removes a matching element without knowing “which worker's job” it belonged to; use unique task IDs/envelopes and proper ownership.

**`LREM` runs after commit**, never before critical side effects. Removing first and crashing afterward brings back the same recovery gap as direct `POP`.

### 13.3. What if a crash occurs after commit but before LREM?

~~~text
BLMOVE ready -> processing
  -> DB commit / thumbnail created
  -> process crashes before LREM
  -> processing List still holds the job
  -> reclaimer moves job back to ready
  -> worker reprocesses it
~~~

This yields **application-level at-least-once delivery if the reclaimer works properly and Redis retains data**, not exactly-once. You need idempotency—such as a unique `eventId`, deterministic output key, and a business state machine.

### 13.4. Do not assume RedisQueueMessageDrivenEndpoint uses BLMOVE by default

**The dedicated queue inbound endpoint in section 8 must not be assumed to implement a two-List reliable queue.** If you adopt a `BLMOVE`/processing-List design, build a receiver/endpoint tailored to **`BLMOVE`** or use a component/framework that genuinely implements that two-phase protocol.

Do not run `RedisQueueMessageDrivenEndpoint` popping from `ready` **alongside** a `BLMOVE` worker reading `ready` on the same queue expecting every job to have processing tracking. The direct-pop endpoint will grab some jobs without touching the processing List, breaking the reliability contract.

### 13.5. Redis Cluster and hash slots

`BLMOVE`/`LMOVE` are **multi-key** operations. In Redis Cluster, the involved keys must share **the same hash slot**. Naming convention:

~~~text
catalog:{thumbnail}:ready
catalog:{thumbnail}:processing
catalog:{thumbnail}:dead
~~~

The text inside braces is a **hash tag** ensuring these keys map to the same slot in Redis Cluster. Do not pick two keys in different slots and expect cross-slot `BLMOVE` to work.

### 13.6. BRPOPLPUSH and Redis versions

Older documentation may use **BRPOPLPUSH** (blocking move from right of source to left of destination). Newer Redis versions provide **BLMOVE** with explicit source/destination ends; when maintaining an existing system, verify Redis server/client versions and deprecation status of the older command before migrating.

## 14. Reliable processing needs a reclaimer and leases, not just BLMOVE

A processing List preserves the job after a worker crash, but Redis does not decide on its own **when a “stuck” job should be reclaimed**.

### 14.1. What are the reclaimer's responsibilities?

- Track which jobs were claimed from `ready`.
- Store/query the claim timestamp or last heartbeat.
- Determine whether the owner/worker is still alive.
- When a lease expires, return the job to `ready` or a final `dead` queue **in a controlled way**.
- Avoid requeuing a valid long-running job just because it takes longer than average.
- Cap attempt counts; distinguish permanent failures from recoverable ones.

A List of JSON payloads **does not inherently record claim time and owner** unless the application stores metadata. You may need a hash/job table/sorted set to track leases and deadlines; metadata updates must stay consistent with the claim operation.

### 14.2. A common bug when a reclaimer acts too early

~~~mermaid
sequenceDiagram
    participant W1 as Worker 1
    participant R as Redis
    participant RC as Reclaimer
    participant W2 as Worker 2
    W1->>R: Claim task-10 (processing)
    W1->>W1: Image processing exceeds lease
    RC->>R: Lease expired -> requeue
    W2->>R: Claim task-10
    W2->>W2: Process task-10
    W1->>W1: Finish task-10
    Note over W1,W2: Both workers may execute side effects
~~~

Coordinated mitigations:

1. **Heartbeat/lease extension** during long-running jobs.
2. **Fencing token/version** if side effects are vulnerable to stale owners.
3. **Idempotent outputs** keyed by `eventId`/`productId`/`imageVersion`.
4. **Owner verification** on ACK or state transition.
5. Realistic deadlines/timeouts rather than blindly requeuing everything after a fixed interval.

### 14.3. Two separate Redis commands leave a race window

For example, a worker runs:

~~~text
BLMOVE ready -> processing
HSET task:{id} owner=worker-1 claimedAt=...
~~~

If the process crashes **between the two commands**, the processing List holds the job while the hash metadata was never written. If the reclaimer only scans the hash, the job can be orphaned.

To build a strict reliable queue, consider **Lua scripting/transactions where appropriate, a reconcilable job registry**, or choosing Redis Streams consumer groups instead of rebuilding claim/ACK/reclaim from scratch. **Atomic `BLMOVE` only makes the move step atomic; it does not make the whole workflow atomic.**

### 14.4. Requeue and dead-letter cannot rely on key names alone

Redis Lists have no native DLX like RabbitMQ. To store failed jobs in **`catalog:{thumbnail}:dead`**, the application must perform the transfer itself and record the failure reason.

When operating on a processing List, you must **move the exact job** from `processing` to `dead`/`ready`—never run a blind `LMOVE` that could grab another worker's item.

### 14.5. Lua pattern to move a failed item to a dead List

Conceptual example: move only a specific payload, assuming the payload carries a unique identifier inside the processing List.

~~~lua
-- KEYS[1]: processing list
-- KEYS[2]: dead list
-- ARGV[1]: serialized job payload, unique for the claimed job

local removed = redis.call('LREM', KEYS[1], 1, ARGV[1])
if removed == 1 then
    redis.call('LPUSH', KEYS[2], ARGV[1])
end
return removed
~~~

The script executes atomically with respect to other Redis operations on the relevant server/shard, eliminating the gap between `LREM` and `LPUSH`. However, it **does not** check lease ownership or attempt count, cannot distinguish identical byte payloads across workers, and does not itself guarantee durability across every Redis crash/failover mode. Production requires ownership policies and full state reconciliation.

In Redis Cluster, all keys in a multi-key script must also reside in the same hash slot.

### 14.6. Conclusion on reliable List queues

To turn a simple List queue into a reliable work queue, you must manage **claiming, processing, ACK, timeouts, a reclaimer, duplicates, poison messages, dead-lettering, and monitoring**. That can be reasonable for a small system with clear criteria, yet complexity rises fast.

If you already need all of those features, evaluate **Redis Streams, RabbitMQ/AMQP, Kafka, or JMS** before maintaining a custom queue protocol.

## 15. Retries, poison jobs, and final error state

A task may fail due to a **permanent data error** or a **transient infrastructure error**. Your retry policy must distinguish the two before using a Redis queue for work dispatch.

| Error group | Example | Handling approach |
| --- | --- | --- |
| **Malformed payload** | Broken JSON, missing `eventId`, bad `schemaVersion` | Do not hot-retry; quarantine payload/metadata for investigation |
| **Business validation** | Missing `productId`, unauthorized `imageKey` | Record rejection per contract; may require data fix |
| **Transient dependency** | Object storage returns 503, DB connection timeout | Bounded retry with backoff, then durable retry |
| **Quota/rate limit** | Resize service hits concurrency or bandwidth limit | Backpressure, delay, worker concurrency limits |
| **Unknown outcome** | Network drops near object storage write completion | Reconcile via deterministic output key; do not assume failure |
| **Poison task** | Payload consistently triggers an exception | Route to final dead list/error table after classification |
| **Permanent configuration** | Wrong credentials/bucket, missing permissions | Alert and fix configuration; do not retry indefinitely |

### 15.1. Bounded retries inside the service activator

For brief transient errors, Spring Retry can be used at the processing boundary:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.support.RetryTemplateBuilder;

@Configuration
public class ThumbnailRetryConfig {

    @Bean
    public RetryTemplate thumbnailRetryTemplate() {
        return new RetryTemplateBuilder()
            .maxAttempts(3)
            .exponentialBackoff(250L, 2.0, 2000L)
            .retryOn(TransientThumbnailException.class)
            .build();
    }
}
~~~

~~~java
public class TransientThumbnailException extends RuntimeException {
    public TransientThumbnailException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Inside the handler/flow, invoke:

~~~java
thumbnailRetryTemplate.execute(context -> {
    thumbnailJobHandler.handle(json);
    return null;
});
~~~

**`maxAttempts(3)`** typically covers the initial attempt plus up to two retries. Retry only exceptions classified as transient; **never use `retryOn(RuntimeException.class)`** if it would repeatedly re-run invalid data thousands of times.

### 15.2. Why this retry does not guarantee recovery

`RetryTemplate` executes in JVM memory after the queue inbound endpoint has popped the job. If the JVM dies on attempt 2, local retry state is lost. In direct-`POP` mode, the Redis pending List has already lost the job too.

To retry across restarts, **a copy of the job must remain in a durable store** (processing List, Stream, database task table, etc.) with a component responsible for re-claiming it per policy.

### 15.3. Never infinitely requeue back into the same List

A common anti-pattern:

~~~text
catch (Exception ex) {
    redisTemplate.opsForList().leftPush(pendingKey, sameJson);
}
~~~

If a task has an invalid schema, the queue immediately receives the exact same task again; the consumer enters a **hot loop** burning CPU, memory, Redis traffic, and logs. Moreover, **re-`LPUSH`ing** is a brand-new publish to the List, not an atomic rollback of `POP` tied to the business transaction.

Bounded retries require a durable attempt counter, backoff/`nextAttemptAt`, and a final resting place for failed tasks.

### 15.4. Designing a dead list / error table

Redis Lists have no native **dead-letter exchange** like RabbitMQ. You can design:

~~~text
catalog:{thumbnail}:ready
catalog:{thumbnail}:processing
catalog:{thumbnail}:dead
~~~

A dead job should carry metadata:

~~~json
{
  "eventId": "evt-thumb-1001",
  "attempts": 4,
  "errorCategory": "IMAGE_UNSUPPORTED_FORMAT",
  "lastErrorAt": "2026-11-23T03:00:00Z",
  "originalPayload": {
    "eventType": "THUMBNAIL_REQUESTED",
    "schemaVersion": 1
  }
}
~~~

The `attempts`/`errorCategory` fields here are an **application-managed contract**, not generated by Redis List. If a payload must be edited before replay, keep an audit trail and decide whether `eventId` stays the same according to your idempotency contract.

### 15.5. Delayed retry is not built into Redis Lists

A Redis List has no per-element timeout **to automatically move back to `ready`**. You can use a Redis Sorted Set scored by `nextRetryAt` with a scheduler moving due jobs to `ready`, or use a durable job table/Redis Streams.

When the scheduler reads and moves items from delayed to `ready`, ensure **jobs are not lost between the two operations** and **not duplicated outside policy**. This may require Lua scripts/transactions, unique job IDs, durable state, and idempotency.

### 15.6. Pick a single owner for error handling

An item removed via direct `POP` is no longer in the `ready` List. Do not let the **Spring Integration error flow**, **handler catch block**, **task retry scheduler**, and **operator replay** each independently `LPUSH` back without shared state, or a single failure can spawn multiple copies of the task.

Define clearly:

- Who records the failed state?
- Who is allowed to schedule a new retry attempt?
- When is the retry budget exhausted?
- Who confirms a task is `DONE`?
- Who is authorized to replay dead jobs?
- When outcomes are unknown, where do we reconcile before retrying?

## 16. Concurrency, competing consumers, and FIFO order

Multiple consumers can read from the same Redis List key. Each Redis `POP` command is atomic at the Redis command level, so **the same List element cannot be successfully popped by two consumers simultaneously**. Yet that does not guarantee business side effects execute exactly once.

~~~mermaid
flowchart TD
    P["LPUSH tasks A/B/C/D"] --> Q["Redis List ready"]
    Q -->|"POP"| W1["Worker 1"]
    Q -->|"POP"| W2["Worker 2"]
    Q -->|"POP"| W3["Worker 3"]
    W1 --> H1["Process A"]
    W2 --> H2["Process B"]
    W3 --> H3["Process C"]
~~~

### 16.1. One key, multiple workers

Workers split List items based on when Redis executes each `POP`. There is no concept of every worker receiving the entire List like Pub/Sub.

If both Warehouse and Analytics **must** receive an event, do not put two consumers on the same List expecting broadcast. Create two separate queues/lists, an event log with multiple consumer groups, or an exchange/broker that supports fan-out.

### 16.2. Processing order in a cluster

Even when the queue is FIFO at pop time:

- Worker 1 may process task A slower than Worker 2 processes B.
- A worker crash may send task A into recovery while B already marks `DONE`.
- Retries and reclaimers may re-insert an older item at a different end of the queue.
- Object storage/DB calls may finish out of order.

If a `productId` has multiple image versions, use a **monotonic version/token** so older outputs do not overwrite newer ones. A simple Redis List does not guarantee causal ordering in business state.

### 16.3. Processing capacity is not just Redis throughput

For example, with three workers where each resize task takes two seconds:

~~~text
3 workers / 2 seconds per task ≈ 1.5 tasks/second
~~~

This is an ideal estimate assuming parallel execution with no resource contention. Redis can pop very rapidly, while object storage, image CPU, memory, or DB may be the real bottleneck. Adding more consumers will not help if the downstream system is already saturated.

### 16.4. No RabbitMQ-style prefetch

Redis List blocking pop **does not have `prefetchCount`/consumer ACK** like a Spring AMQP listener container. The number of **in-flight** tasks depends on the number of receive loops/threads, internal buffering channels, executors, and worker concurrency.

If you use an `ExecutorChannel` with an unbounded worker queue, the endpoint can pop tasks rapidly and pile unfinished work into memory. Redis ready `LLEN` drops while crash-loss risk rises. **Low `LLEN` does not prove the system is keeping up or finishing work.**

### 16.5. DirectChannel, ExecutorChannel, QueueChannel

| Channel | Execution timing | Risk with Redis POP |
| --- | --- | --- |
| **DirectChannel** | Synchronous handler in flow | Minimal in-memory buffering, still loses item on crash after `POP` |
| **ExecutorChannel** | Dispatched to executor thread/queue | `POP` completes while task sits in memory; crash loses it |
| **QueueChannel** | Buffers Spring Messages for internal poller | Not durable without a `MessageStore`, still has pre-store gap |
| **PublishSubscribeChannel** | Internal fan-out to multiple subscribers | One Redis job triggers multiple side effects; not a consumer group |

A **Spring Integration poller on a `QueueChannel`** only consumes buffered Spring Messages; it does not turn a Redis List inbound adapter into a durable ACKed queue.

## 17. ErrorChannel and transaction boundaries

Exceptions can occur at different steps:

~~~mermaid
flowchart TD
    R["Redis List POP"] --> A["Redis queue inbound adapter"]
    A --> M["Spring Message"]
    M --> C["MessageChannel"]
    C --> T["Transformer / parse"]
    T --> H["Business handler"]
    R -. "Network / Redis WRONGTYPE" .-> E1["Transport / endpoint errors"]
    A -. "Serializer failure" .-> E1
    T -. "Malformed payload" .-> E2["Spring Integration error handling"]
    H -. "DB / object store error" .-> E2
    E1 --> REC["Observe / reconcile"]
    E2 --> REC
~~~

### 17.1. Errors before creating the Spring Message

If the Redis connection fails or the serializer cannot decode an item before the adapter builds a Spring Message, **the service activator may never be invoked**. A handler `try/catch` cannot catch every transport error.

Configure and monitor endpoint error handling per your Spring Integration version, logging key name, serializer, error category, and Redis connectivity in line with security policies.

### 17.2. Errors in the handler do not automatically PUT BACK

If `DirectChannel` calls a handler, the handler throws `RuntimeException`, and `errorChannel` logs it, the popped item **does not automatically return to `ready`**. Even if the exception propagates back to the endpoint, Lists have no `NACK` command by `eventId`.

Do not treat seeing a Spring `ErrorMessage` as proof that Redis retained a copy of the task.

### 17.3. Database transaction boundaries

~~~text
Redis List POP  (separate Redis command)
   -> Spring Message
   -> @Transactional business method
   -> DB commit/rollback
~~~

Spring DB `@Transactional` does not automatically roll back a Redis `POP`, and Redis `MULTI`/`EXEC` does not turn image resizing, object storage, and JDBC into a single cross-system atomic transaction.

When side effects span multiple systems, use outbox/inbox tables, state machines, idempotency keys, reconciliation, or compensating actions.

### 17.4. In what scope can effectively-once be achieved?

You can aim for **effectively-once side effects** on a database record using a unique constraint on `eventId` inside one transaction. However:

- That does not recover tasks lost after a direct `POP`.
- External object storage/APIs outside the DB may still leave `UNKNOWN` outcomes after timeouts.
- Reclaimer/producer retries can still generate duplicate deliveries.
- Redis Lists do not provide end-to-end exactly-once guarantees.

**More accurately:** Redis List direct `POP` lets one consumer fetch an item once at the Redis operation level, while business correctness requires its own safeguards.

### 17.5. Does a durable inbox after POP solve everything?

A consumer can `POP` and then insert the job into a database inbox before doing business work:

~~~text
POP Redis List
   -> DB insert inbox
   -> DB-level ACK / worker reads inbox
~~~

This protects jobs **once successfully inserted into the inbox**, yet leaves a **`POP` → DB insert** window where a process crash loses the item. If the SLA forbids losing jobs, change the claim point to preserve a copy in Redis (processing List/Streams), or have the producer write directly to a durable source read by workers.

## 18. Endpoint lifecycle, Redis downtime, and graceful shutdown

A Redis queue inbound adapter follows Spring Integration and Redis client lifecycles. Verify:

1. On application start, does the endpoint auto-start with the context?
2. If Redis is not yet ready, how does the endpoint retry connecting?
3. When a blocking `POP` is waiting, does stopping cancel/exit within a reasonable time?
4. During Redis failover, is the connection re-established and does the receive loop resume?
5. If an item was `POP`ped right before shutdown, what state is the handler in?

### 18.1. Offline workers and Redis List backlog

If workers are offline **before `POP`**, producers can keep `LPUSH`ing items into the Redis List (provided Redis is available and memory/eviction policies permit). When workers come back online, they can pick up unpopped items.

Unlike Redis Pub/Sub, a List queue maintains a **backlog**. Yet that backlog is bounded by memory, `maxmemory`/eviction policy, persistence/replication, and operations. Never treat a Redis List as infinite storage by default.

### 18.2. Redis reconnect does not mean jobs were safely processed

After reconnecting, the endpoint can read items **still in the `ready` List**. Items popped before a JVM crash will not reappear on their own unless you have a processing List/reclaimer or another source to recover from.

### 18.3. Graceful shutdown

A sound plan:

- Stop receiving/claiming new jobs via the endpoint lifecycle.
- Let active handlers finish within a controlled timeout.
- Under reliable processing, record `DONE` state and ACK/remove the processing item after business commit.
- On timeout, allow leases/reclaimer to reprocess safely using `eventId` and ownership.
- Close resources via Spring lifecycle without breaking a shared `RedisConnectionFactory`.
- After restart, inspect ready backlog, stuck processing jobs, and the retry scheduler.

**Never equate a clean `stop()` return with zero misplaced tasks.** Measure in-flight state and verify recovery paths.

### 18.4. WRONGTYPE when a queue key is overwritten accidentally

A Redis key used as a List might be `SET` to a String or incompatible data structure by another client. List commands will then fail with **WRONGTYPE**. A Redis queue inbound endpoint cannot repair key types automatically.

Use clear namespaces, restrict ACL write permissions, and never reuse queue key names for text caches or sets. In test environments you can check **`TYPE key`** before running, whereas in production you must not blindly `DEL` keys to “quick-fix” because that destroys queued jobs.

### 18.5. Redis Cluster/Sentinel

When running Redis Sentinel or Cluster:

- Verify compatibility of blocking List commands with client/node routing.
- Multi-key operations like `BLMOVE` require keys in the same hash slot in Redis Cluster.
- Test reconnect/failover and Redis persistence/replication RPO.
- Do not assume a Redis connection timeout means the task was not popped; the command outcome may be **UNKNOWN** if the connection dropped after the broker executed the command but before the client got the response.
- When claim outcomes are unknown, a processing list/reconciliation helps determine whether the job was moved.

## 19. Security and data limits

A Redis List queue may be read/written by multiple services depending on ACLs. Never treat an internal queue as an inherently trusted input source.

### 19.1. Redis ACLs and key namespaces

In production, define:

- Which queue keys producers are permitted to **`LPUSH`/`RPUSH`**.
- Which keys consumers are permitted to **`BLPOP`/`BRPOP`** or `BLMOVE` from/to.
- Where the reclaimer is permitted to modify processing/dead lists and update lease state.
- Which operators have permission to view/edit/replay dead jobs.
- Whether dangerous Redis commands like `FLUSHDB` or arbitrary `DEL` are restricted by policy.
- Connections using TLS, credentials loaded from a secret manager/environment, and network access restrictions.

**Redis ACLs do not replace business validation.** A service authorized to `LPUSH` does not guarantee every `imageKey` or `tenantId` it sends is valid.

### 19.2. Object storage paths and tenant boundaries

In the thumbnail example, **`imageKey`** is producer-supplied data. If the consumer has write access to object storage:

1. Verify `productId` belongs to an authorized tenant.
2. Validate namespace/prefix and object key format.
3. Use only allowlisted buckets/containers.
4. Bound file types/sizes, pixel counts, and decoding resources.
5. Never pass `imageKey` into an unescaped/unvalidated shell command.
6. Prevent older tasks from overwriting thumbnails of a newer `productVersion`.

**Do not use a Redis queue key or `eventType` as user authentication evidence.** Ownership and authorization must come from trusted sources and service policies.

### 19.3. Avoid arbitrary object deserialization

Never use native Java serialization to deserialize Redis data when different producers or teams can write to the queue. Prefer JSON/Protobuf/Avro schemas with trusted target DTOs, validation, and byte-size limits.

If using `ObjectMapper`, restrict polymorphic type handling and never enable indiscriminate default typing on untrusted data.

### 19.4. Sensitive payloads and the dead list

Dead jobs are often retained longer than pending jobs. When storing failures:

- Never copy credentials, access tokens, or still-valid signed object URLs into the dead List.
- Enforce retention limits and role-based access control.
- Avoid logging full raw payloads containing PII.
- Have policy-compliant data export/deletion workflows.
- On replay, audit who performed it, when, and which task.

### 19.5. Rate limits and resource exhaustion

A Redis List can grow rapidly if producers outpace consumers. Set queue length thresholds, payload size limits, producer-side throttling, and capacity alerts.

Scaling worker concurrency without bounds can overload object storage, CPU, memory, or databases. Keep executor queues bounded with clear rejection policies rather than merely driving Redis pending `LLEN` down.

## 20. Monitoring: ready, processing, dead, and business outcomes

With a Redis List queue, **`LLEN` of the `ready` List** only reflects items still sitting in that list. Understanding the pipeline requires multiple signals:

| Signal | Meaning | Interpretation |
| --- | --- | --- |
| **`LLEN ready`** | Unclaimed/unpopped items | Growing backlog may mean slow/offline workers |
| **`LLEN processing`** | Moved items awaiting ACK in reliable queue | May indicate active or stuck jobs |
| **`LLEN dead`** | Quarantined jobs per app policy | Needs an owner and replay procedure |
| Enqueue rate | Rate producers add jobs | Not the completion rate |
| Pop/claim rate | Rate adapters/workers pull jobs | Can be high even when business logic fails |
| Handler success rate | Rate of successful business completions | Compare against enqueue and retries |
| Handler error/retry | Errors by category, attempt counts | Distinguish poison vs. transient |
| Job processing latency | Time from claim to outcome | Track p95/p99 and timeouts |
| Oldest job age | Longest waiting or processing job | Requires timestamp in payload/metadata |
| Redis command errors | `WRONGTYPE`, timeout, ACL, cross-slot | Configuration/Redis issues |
| Reclaim count / lease expiry | Jobs reclaimed | Detects crashed/hung workers or overly short leases |
| Duplicate skipped | Idempotency protecting side effects | Spikes after crashes/retries can be normal |

### 20.1. Do not treat LLEN=0 as completed count

Suppose a Redis List had 100 tasks, the inbound adapter feeds a fast `ExecutorChannel`, and the executor queue holds 100 items in memory:

~~~text
Redis pending LLEN = 0
Executor pending tasks = 100
Thumbnail success = 0
~~~

If the application crashes, those tasks are lost because Redis already popped them. A dashboard showing only pending `LLEN` would report “zero backlog,” misleading operators. Measure **in-flight/processing** alongside business success.

### 20.2. Suggested metrics

~~~text
thumbnail_queue_enqueued_total
thumbnail_queue_popped_total
thumbnail_queue_processing_total
thumbnail_queue_completed_total
thumbnail_queue_failed_total{reason="INVALID_SCHEMA"}
thumbnail_queue_retry_total{reason="DEPENDENCY_TIMEOUT"}
thumbnail_queue_reclaimed_total
thumbnail_queue_duplicate_skipped_total
thumbnail_queue_processing_duration_seconds
~~~

These are **illustrative metric names**, not all exported out of the box by Spring Integration. Avoid putting **`eventId`, `productId`, or `imageKey`** in metric labels due to high cardinality; those belong in controlled logs/traces.

### 20.3. Monitoring long wait times

In a lease-based reliable queue, a job sitting in `processing` without a heartbeat for too long requires investigation:

- Worker crashed?
- Side effect hung?
- Redis disconnected?
- Valid job processing an unusually huge image?
- Lease too short and reclaimer triggered duplicate work?

Do not automatically requeue every processing job simply because it stayed there for a few seconds; rely on SLAs, worker state, and idempotency/fencing.

### 20.4. Useful logging without leaking data

~~~text
queue=catalog:thumbnail:pending
eventId=evt-thumb-1001
eventType=THUMBNAIL_REQUESTED
schemaVersion=1
attempt=2
workerId=image-worker-03
state=FAILED_RETRYABLE
durationMs=1800
errorCategory=OBJECT_STORAGE_TIMEOUT
~~~

**`attempt`** here is application-managed state; Redis List `POP` does not track delivery counts. When using a direct-`POP` endpoint without durable attempt state, do not log an overall attempt count as if it were accurate across restarts.

### 20.5. SLA-based alerting

Alert when:

- Ready backlog grows continuously over a sustained window.
- Many processing jobs exceed their lease deadline.
- Redis command timeouts/connection retries increase.
- Retry-exhausted/dead jobs spike.
- Thumbnail processing success drops even while dequeue rate stays high.
- Redis memory/`maxmemory` approaches limits.
- Product projection/cache staleness breaches SLA and reconciliation falls behind.

Thresholds should be calibrated from real workloads and benchmarks rather than copying arbitrary numbers into production.

## 21. End-to-end testing with real Redis

Unit testing `ThumbnailJobHandler` proves parsing and validation logic. It does not prove `RedisQueueMessageDrivenEndpoint` **reads the right Redis key, right List end, right serializer, and right lifecycle**. You need isolated integration tests against a real Redis server, such as a test Redis instance or Redis Testcontainers matching your project.

### 21.1. Test matrix

| Scenario | Setup | What to verify |
| --- | --- | --- |
| **Happy path** | `LPUSH` valid job, endpoint running | Spring Message reaches handler, thumbnail processed |
| **FIFO 3 items** | Push A, B, C per publisher contract | Pop order matches `LPUSH`/`BRPOP` or `RPUSH`/`BLPOP` |
| **Wrong serializer** | Send JSON bytes differing from endpoint expectation | Conversion error caught before business handler |
| **Wrong key** | Producer `LPUSH`es to key other than endpoint's | Task from wrong key is not received |
| **Wrong Redis instance/db** | Publisher/consumer target different connections | Not received; misconfiguration detected |
| **WRONGTYPE** | Queue key overwritten as String | Adapter surfaces clear error without deleting data |
| **Consumer offline** | `LPUSH` before endpoint starts | Task stays in List until worker starts, if no other consumer |
| **Crash after direct POP** | Kill worker after `POP` before commit | Task may vanish from ready List; no automatic redelivery |
| **Crash before POP** | Kill worker before reading | Job remains pending |
| **Duplicate LPUSH** | Producer retries same `eventId` | Business side effect does not repeat |
| **Invalid JSON/schema** | Send malformed payload | Error policy avoids infinite retry; no native DLQ assumed |
| **Downstream transient error** | Mock object storage 503 then success | Bounded `RetryTemplate`, correct side effect |
| **Downstream permanent error** | Invalid/unauthorized `imageKey` | Quarantined or marked clearly as failed |
| **Multi-worker competing** | Two consumers read same List | Each Redis item popped by one worker, not broadcast |
| **Long-running jobs** | A takes 10s, B takes 1s | Completion order is not assumed FIFO |
| **Executor queue full** | Burst beyond worker capacity | Tasks not silently dropped without alert/recovery |
| **BLMOVE claim** | Use ready/processing Lists | Atomic move; processing tracks app-unacked state |
| **Crash after BLMOVE** | Kill worker before business commit | Processing holds job for reclaimer per policy |
| **Crash after commit before LREM** | Kill after DB commit | Reclaim may redeliver; idempotency prevents duplication |
| **Lease timeout** | Worker takes longer than lease | Test fencing/idempotency preventing double side effects |
| **Dead job transition** | Invalid task exhausts retries | Exact job moves processing → dead with proper audit |
| **Redis Cluster** | `BLMOVE` keys in different hash slots | Cross-slot failure detected |
| **Reconnect/failover** | Restart test Redis | Receive loop recovers per client; check unknown outcomes |
| **Graceful shutdown** | Stop while handler is active | In-flight handled per policy; no false completion report |
| **ACL** | Consumer lacks read access on queue key | Meaningful error and alert |
| **Monitoring** | Measure enqueued, popped, completed, dead | `LLEN=0` not treated as success |

### 21.2. Testing callbacks with CountDownLatch

When testing a Spring Integration flow in a test context, you can swap the business handler for a test sink to observe payloads:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ThumbnailCapturingSink {

    private final AtomicReference<String> payload =
        new AtomicReference<>();
    private final CountDownLatch latch = new CountDownLatch(1);

    public void accept(String value) {
        payload.set(value);
        latch.countDown();
    }

    public String awaitPayload() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Redis queue item not received");
        }
        return payload.get();
    }
}
~~~

**This is only a helper**, not a full integration test. Tests need a Spring context with the endpoint, real Redis, matching Redis serializers, an isolated test queue, and a way to wire the sink into the test `IntegrationFlow`. Never use the compilation of a helper to claim the adapter subscribes/consumes properly.

### 21.3. Tests should not rely on fixed Thread.sleep

A Redis queue endpoint has a start/connect/blocking-receive lifecycle. In an integration test:

1. Ensure test Redis is ready.
2. Create the endpoint and output channel/handler.
3. Confirm the endpoint has started and is ready to receive.
4. `LPUSH` the task into the test key.
5. Await the latch/condition with a reasonable timeout.
6. Assert `eventId`/payload and side effects.
7. Inspect List/processing state per the model under test.

With a List queue, a task `LPUSH`ed before the consumer comes online **can still be picked up afterward** if Redis retains the List; do not blindly apply Redis Pub/Sub timing rules.

### 21.4. Which tests are most valuable?

**Crash after direct `POP` before DB commit** demonstrates item loss in a simple queue. **Crash after `BLMOVE` before commit** shows the copy remaining in the processing List for recovery. **Crash after commit before `LREM`** demonstrates duplicate delivery risk and why idempotency is mandatory.

These three tests generally yield far more architectural value than pushing 100 JSON messages on the happy path.

### 21.5. Never run failure tests on production queues

Never `DEL` production keys, intentionally trigger `WRONGTYPE` on live queues, or restart shared Redis instances for testing. Use dedicated key namespaces or isolated test Redis servers (remember Redis has no RabbitMQ-style vhost), least-privilege test credentials, and controlled cleanup of test data.

## 22. Architectural scenarios: choosing queue inbound for the right problem

### 22.1. Case A – Thumbnails rebuildable from the database

**Context:** `CatalogService` already saved the original image, metadata, and `NEEDS_THUMBNAIL` state in the database. A Redis List merely notifies `ImageWorker` promptly that work is ready.

~~~mermaid
flowchart TD
    U["Upload image"] --> DB[("Catalog DB<br/>NEEDS_THUMBNAIL")]
    DB --> P["LPUSH thumbnail task"]
    P --> Q["Redis List pending"]
    Q --> A["Redis queue inbound adapter"]
    A --> H["ImageWorker"]
    H --> OBJ[("Object storage thumbnail")]
    H --> D["Mark DONE in DB"]
    DB --> R["Periodic reconciliation"]
    R -->|"Remaining NEEDS_THUMBNAIL"| P
~~~

In this case, Redis List direct `POP` **can be acceptable** if:

- The database is the source of truth for unfinished jobs.
- The worker generates thumbnails idempotently per `productId`/`imageVersion`.
- A periodic scheduler scans records still in `NEEDS_THUMBNAIL` and re-enqueues them.
- Duplicates are handled cleanly during retries/reconciliation.
- The SLA tolerates reconciliation latency.

**If a task is lost after `POP`**, the database still records it as not `DONE`, so the scheduler recovers it. This **does not make `POP` itself reliable**; the system achieves recovery via an **external durable state source**.

### 22.2. Case B – Best-effort marketing email delivery

**Context:** An internal system sends promotional notifications, allows campaign-level retries, and has an authoritative source table. A Redis List queue can distribute lightweight jobs.

However, when sending emails:

- A request timeout does not prove the SMTP/provider did not send.
- Retries can send duplicate emails without a campaign-recipient idempotency key.
- List `POP` has no native dead-letter queue.
- Provider quotas require backoff, rate limiting, and monitoring.

Even for best-effort workloads, document **which messages may be lost** and whether a campaign/job table exists to re-run them.

### 22.3. Case C – Payment processing where zero loss is mandatory

**Context:** `PaymentService` receives charge tasks. If a worker dies after `POP` before the transaction, the task cannot be lost; if it dies after commit, the customer cannot be charged twice.

**Do not use Redis List direct `POP` as the sole mechanism**. Consider:

~~~mermaid
flowchart LR
    REQ["Payment request"] --> DB[("Payment DB transaction<br/>+ outbox")]
    DB --> PUB["Outbox publisher"]
    PUB --> MQ["Durable broker / Redis Stream"]
    MQ --> C["Idempotent consumer"]
    C --> PAY["Payment provider with idempotency key"]
    C --> DB
~~~

If you still build reliable Lists yourself, you must implement processing claims, leases/fencing, durable attempt state, post-commit ACKs, recovery, and reconciliation proven by failure tests. Development and operational costs often outweigh the simplicity of a Redis List.

### 22.4. Case D – SFTP import → Redis work queue

**Context:** An SFTP inbound adapter syncs CSV files locally, a parser generates jobs, and a producer `LPUSH`es them into a Redis List while workers process each row.

~~~mermaid
flowchart LR
    SF["SFTP inbound adapter<br/>poller"] --> CSV["CSV parser/validator"]
    CSV --> DB[("Import DB<br/>row states")]
    DB --> Q["Redis List pending"]
    Q --> RI["Redis queue inbound"]
    RI --> H["Row processor"]
    H --> DB
~~~

Do not delete the source file or mark the import complete merely because **`LPUSH` returned a queue length**. Maintain per-row/`eventId` state; a scheduler can retry rows not yet `DONE` if tasks are lost after `POP`.

### 22.5. Case E – Redis queue inbound → HTTP outbound adapter

**Context:** A worker pops a job and calls an external HTTP API:

~~~text
Redis List -> queue inbound adapter -> DirectChannel
           -> HTTP outbound gateway/adapter -> External API
~~~

Because HTTP can time out even when the target system **already completed processing**, you need an idempotency key and a way to query result status from the provider. With direct `POP`, a post-pop failure can lose the job; with recovery/retries, the HTTP call may run again. The key is **idempotent side-effect design**, not just tweaking Redis retries.

### 22.6. Case F – Redis queue inbound → AMQP/Kafka outbound

If an endpoint consumes a Redis List and forwards to RabbitMQ/Kafka:

~~~text
Redis POP
  -> Spring Message
  -> AMQP/Kafka outbound adapter
  -> broker destination
~~~

If Redis `POP` completed but the AMQP publisher confirm / Kafka producer ack has not reached the required durability milestone, a process crash loses the event in the middle. Conversely, the target broker may have stored it while the producer result is `UNKNOWN`, causing an app retry to duplicate it.

**Do not equate `MessageChannel.send` success with an AMQP publisher confirm or Kafka ACK.** For bridges that cannot lose messages, use a durable source/handoff, transactional outbox, or a model supporting ACKs and retries on both sides.

## 23. Common misconceptions with Redis queue inbound

**“Redis queue inbound is the same as Redis Pub/Sub inbound.”** False. List queues read items using List operations; Pub/Sub receives notifications from `PUBLISH`/`SUBSCRIBE`.

**“LPUSH notifies subscribers `SUBSCRIBE`d to the same name.”** `LPUSH` writes to a Redis List key; it does not `PUBLISH` on a Pub/Sub channel.

**“A Redis List is always FIFO regardless of which ends you push/pop.”** FIFO requires pushing at one end and popping at the opposite end; `LPUSH`/`BLPOP` on the same end produces LIFO.

**“Blocking POP means Redis holds delivery until the handler ACKs.”** With `BRPOP`/`BLPOP`, the item is removed as soon as the command returns; there is no native ACK.

**“Redis persistence automatically recovers a job that was `BRPOP`ped before the handler committed.”** Persistence preserves Redis state; it does not roll back a `POP` alongside a DB transaction.

**“Redis List queues have DLX/DLQ like RabbitMQ.”** Redis Lists have no native dead-letter exchange; a dead list is an application-designed contract.

**“Redis queue inbound must have Spring `Pollers.fixedDelay`.”** A message-driven endpoint runs its own blocking-read loop; a separate poller adds no durability.

**“Using `QueueChannel` after inbound prevents task loss.”** Default `QueueChannel` is non-durable; `POP` already occurred before the task entered the internal queue.

**“ExecutorChannel always increases reliability.”** An executor holds queued tasks in memory and loses them on a process crash.

**“Pending `LLEN = 0` means all tasks are finished.”** Tasks may still be in flight, lost after `POP`, or sitting in an executor queue.

**“RetryTemplate can replay jobs after a restart.”** An in-JVM `RetryTemplate` is not a durable attempt log; direct `POP` already removed the item from the Redis List.

**“Simply `LPUSH`ing back in a `catch` block creates safe retries.”** It risks hot loops, duplicates, and losing retry state across crashes.

**“`BLMOVE` provides built-in consumer ACKs and a reclaimer.”** `BLMOVE` only atomically moves items between Lists; the application must manage processing, leases/ACKs, and reclaiming.

**“`LREM` from processing after commit guarantees exactly-once.”** Crashing after commit before `LREM` can trigger a requeue; you need an idempotent consumer.

**“`LMOVE`ing any element from processing to dead moves the exact failed job.”** It may grab another worker's element; you must match exact job identity and ownership.

**“Storing `attemptCount` in a Java object is enough to cap retries across restarts.”** You need durable attempt state or a durable source to recover across crashes.

**“Once a worker leases a job, no other worker can process it twice.”** A lease can expire while the old worker is still running; you need fencing/idempotency.

**“Redis Streams differ from Redis Lists only in syntax.”** Streams have record IDs, pending/ACKs, and consumer-group semantics, fundamentally different from direct List `POP`.

**“One List with two consumers broadcasts every item to both.”** Redis `POP` atomically hands each item to one consumer, not fan-out.

**“FIFO queue means FIFO completion order when three workers run concurrently.”** Jobs can finish out of order; use domain sequences when order matters.

**“Adding `eventId` to JSON automatically prevents duplicates.”** `eventId` only helps when the handler enforces unique constraints or real idempotency logic.

**“Spring's `MessageHeaders.ID` stays stable across Redis retries.”** A Spring Message can be recreated with a new ID; use a stable business `eventId`.

**“Redis queue inbound always receives UTF-8 Strings in every version.”** Match producer and inbound endpoint serializers; payloads may be bytes or serialized messages.

**“Just put an AMQP-style `contentType` header in a Redis List.”** List values lack an AMQP basic properties table; put schema metadata in the envelope or custom mapping.

**“Wrapping business logic in `@Transactional` rolls back `BRPOP`.”** A DB transaction cannot put an item back into a Redis List.

**“Redis Cluster `BLMOVE` keys can be named anything.”** Multi-key commands must hash to the same hash slot.

**“A dead list is a permanent dumping ground requiring no management.”** It needs retention policies, ACLs, capacity monitoring, alerts, replay, and auditing.

**“Increasing worker concurrency always lowers total latency.”** Downstream CPU, storage, DB, or provider rate limits can saturate and increase failures.

**“Reconnecting to Redis means work lost after `POP` before a crash is recovered.”** Reconnecting only allows reading items still in Redis, not items already popped and lost.

**“Passing happy-path tests proves at-least-once delivery.”** You must test crashes between claim/commit/ACK, reclaimers, duplicates, Redis failovers, and unknown outcomes.

## 24. Redis queue inbound design checklist

| Category | Questions to verify before production |
| --- | --- |
| **Use case** | Can a job lost after `POP` be recovered/rebuilt from another source? |
| **Redis primitive** | List, Stream, or Pub/Sub? Is the right inbound adapter chosen? |
| **Queue key** | Are namespace, environment, key type, and Redis connection correct? |
| **Push/pop** | Are `LPUSH`/`BRPOP` or `RPUSH`/`BLPOP` aligned and FIFO-tested? |
| **Serializer** | Do producer and Redis inbound endpoint share the same wire format? |
| **Payload** | Are `eventId`/`eventType`/`schemaVersion`, max size, and charset validation clear? |
| **Endpoint** | Do `RedisQueueMessageDrivenEndpoint` APIs/constructors match your version? |
| **MessageChannel** | `DirectChannel`, `ExecutorChannel`, or `QueueChannel`? Where could tasks be lost? |
| **Reliability** | Is the crash-after-`POP` window acceptable? If not, what replaces it? |
| **Processing List** | Does `BLMOVE` share a hash slot, with owner/lease/ACK/reclaim? |
| **Idempotency** | Where are unique `eventId`, deterministic output, and `DONE` state stored? |
| **Retry** | Are classifier, max attempts, backoff, and durable `nextRetryAt` in place? |
| **Poison jobs** | Is there a dead list/error table with retention, replay, and ownership? |
| **Concurrency** | How many workers, how many in-flight jobs per worker, and what is downstream capacity? |
| **Transaction** | What failure gaps exist across Redis claim, DB commit, and object storage side effects? |
| **Lifecycle** | How do start/stop/reconnect/failover and in-flight work behave? |
| **Security** | Are Redis ACL key patterns, TLS, credentials, and payload authorization enforced? |
| **Cluster** | Do `BLMOVE` source/destination keys map to valid hash slots? |
| **Monitoring** | Are ready/processing/dead, success/retry/reclaim, oldest age, and alerts tracked? |
| **Testing** | Are there integration tests with real Redis and fault injection across claim/commit/ACK? |

### 24.1. Quick decision guide

**Choose Redis List queue inbound** when tasks can be handled by competing consumers, backlog must be buffered while workers are offline, and you have **accepted or compensated for** the loss window between `POP` and business commit.

**Choose Redis Streams or an ACK-capable broker** when you need pending state, post-crash replay, and structured tracking of attempts and recovery.

**Choose Redis Pub/Sub inbound** when you need to broadcast notifications to online subscribers without per-consumer backlogs.

### 24.2. When is DirectChannel enough?

`DirectChannel` fits fast, synchronous, simple handlers. However, `DirectChannel` **cannot turn destructive `POP` into transactional delivery**. When tasks run long or must retry across restarts, pick a durable source/processing protocol first before deciding on the internal channel.

### 24.3. When to stop building a custom reliable List queue?

If your design already requires:

~~~text
processing list + ACK + leases + heartbeat
  + reclaimer + pending dashboard + retry budget
  + dead queue + delivery-count monitoring
  + duplicates + consumer ownership
~~~

then evaluate Redis Streams, RabbitMQ, JMS, or Kafka against your workload and operations. **The cost of building and maintaining a reliable List queue** can far exceed adopting a primitive that provides these concepts natively.

## 25. Self-check questions

1. Which Redis primitive does the Redis queue inbound adapter read from? How does it differ from Redis Pub/Sub inbound?
2. Why can `RedisQueueMessageDrivenEndpoint` be considered message-driven even though it uses Redis blocking `POP`?
3. Which two push/pop pairs preserve FIFO order? What happens if you operate on the same end of the List?
4. How does `BRPOP` differ from `RPOP`? Is `BRPOP`'s timeout parameter a business retry backoff?
5. Why doesn't `LPUSH`ing to a Redis List notify a subscriber `SUBSCRIBE`d to a channel of the same name?
6. When a worker is offline before `POP`, does a Redis List hold tasks for future workers? Under what conditions?
7. When a worker `BRPOP`s an item and the JVM crashes before DB commit, what happens to the item in the pending List?
8. Why doesn't enabling Redis AOF/RDB give a `POP` command consumer acknowledgment?
9. How does direct Redis List `POP` differ from a Redis Streams consumer group regarding pending/ACK/recovery?
10. Where does `RedisQueueMessageDrivenEndpoint` send items inside Spring Integration? Why is it a message producer from Integration's viewpoint?
11. When should you configure a Spring Integration poller, and when should you not?
12. If a producer uses `StringRedisTemplate` while the inbound endpoint uses a different serializer, what errors can occur?
13. Why should you not assume the payload after the adapter is always a UTF-8 `String`?
14. What do `eventId` and `schemaVersion` in the payload protect against? Why doesn't Spring's `MessageHeaders.ID` replace `eventId`?
15. Does `LPUSH` returning the List length prove the thumbnail was created?
16. If the Redis connection drops around an `LPUSH`, how can a producer retry create a duplicate?
17. Why don't direct `POP` + `@Transactional` service form an atomic transaction across Redis and the DB?
18. For a task with an invalid schema, what is the risk of retrying by pushing directly back into the same List inside `catch`?
19. What does `RetryTemplate.maxAttempts(3)` guarantee inside the JVM? What does it fail to guarantee across a restart?
20. Does logging an exception in `errorChannel` automatically put a `POP`ped item back into the Redis List?
21. How can `ExecutorChannel` widen the post-`POP` data-loss window?
22. How does a default `QueueChannel` differ from a Redis List backlog or Redis Streams in durability?
23. When multiple workers read the same Redis List, does every worker receive every item?
24. Why does FIFO at Redis `POP` time not guarantee business completion order?
25. Do Redis Lists have native prefetch/ACK comparable to a RabbitMQ consumer?
26. How does `BLMOVE source destination RIGHT LEFT` differ critically from `BRPOP` regarding data retention?
27. Does a processing List recover a job if a worker dies right after claim? Why is a reclaimer still necessary?
28. If the DB committed but the worker crashed before `LREM` from processing, how does duplicate risk arise?
29. Why does a job need a stable `eventId`, unique constraint, or deterministic output key?
30. If the processing List contains two elements with identical serialized payloads, what ownership issue does `LREM` have?
31. What metadata does a reclaimer need to detect a stuck job?
32. Why can an overly short lease cause two workers to process the same job?
33. How do fencing tokens and idempotency work differently when a stale worker is still running?
34. Why don't `BLMOVE` and writing owner metadata in two separate Redis commands form an atomic claim workflow?
35. What does Redis Cluster require for `BLMOVE` source/destination keys? What do hash tags do?
36. How does an application-built dead List differ from RabbitMQ's native DLX/DLQ?
37. If a Redis List queue has `LLEN=0` while an executor holds 100 tasks, has the system completed those 100 tasks?
38. What metrics besides ready `LLEN` must be tracked to know whether the system is keeping up and not losing jobs?
39. How should Redis `WRONGTYPE`/ACL/timeout errors be handled at the transport boundary?
40. In an SFTP → Redis queue → handler flow, why can't you mark the import successful right after `LPUSH`?
41. In a Redis queue → Kafka bridge, what data-loss gap exists between `POP` and the Kafka producer acknowledgment?
42. If thumbnail jobs can be rebuilt from the database, how does periodic reconciliation compensate for post-`POP` losses?
43. For payment tasks that must never be lost, what durable handoff/ACK/idempotency model should be chosen?
44. What distinct lessons do crash-after-`POP`, crash-after-`BLMOVE`, and crash-after-DB-commit-before-`LREM` tests prove?
45. When should you migrate from a custom reliable Redis List queue to Redis Streams or a dedicated broker?

## Summary

The **Redis queue inbound adapter** brings items from a **Redis List key** into a **Spring Integration MessageChannel**, allowing transformers, filters, routers, and service activators to process them per the application contract. Unlike Redis Pub/Sub inbound which receives notifications via `SUBSCRIBE`, queue inbound pulls work via **List `POP`**, typically using a **blocking read** mechanism with competing workers claiming individual elements. You must align **push/pop direction**, serializer/charset, payload schema, and endpoint lifecycle to avoid ordering bugs or conversion failures.

**Most critical warning:** With a **direct destructive `POP`** List queue, the item is removed from Redis **before the business handler commits**. Redis can retain a pending backlog while workers are offline, yet does not provide native ACKs, pending entries, DLQs, or JDBC transaction rollbacks. `RetryTemplate`, `DirectChannel`, `QueueChannel`, and `errorChannel` **do not solve** the post-`POP` job-loss window on their own. If business rules cannot afford lost tasks, use a durable source and an appropriate claim/recovery mechanism.

The **`BLMOVE ready → processing`**, **post-commit application ACK**, **reclaimer/lease**, bounded retries, final dead state, and idempotent consumer pattern can improve reliability, but significantly increases implementation and operational complexity. When requirements clearly call for pending tracking, replay, and consumer groups, evaluate **Redis Streams**, AMQP, JMS, Kafka, or durable database job tables accordingly.

In the **SPRING_INTEGRATION_ADAPTERS** module, when connecting Redis with File, SFTP, HTTP, AMQP, Kafka, or databases, always distinguish four milestones: **enqueued into Redis**, **popped/claimed**, **durably persisted in the next stage**, and **business side effect completed**. Only when error contracts, transactions, idempotency, monitoring, and crash testing are thoroughly defined can a Redis queue inbound flow operate and recover reliably.
