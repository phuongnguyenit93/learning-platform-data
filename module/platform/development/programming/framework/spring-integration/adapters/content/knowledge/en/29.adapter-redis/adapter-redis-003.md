# Redis store inbound adapter

## Learning Objectives

Upon completing this lesson, you will be able to:

- Explain how the **Redis store inbound channel adapter** brings a **Redis collection view** into a **Spring Integration MessageChannel** via **periodic polling**.
- Clearly distinguish **RedisStoreMessageSource** from Redis **Pub/Sub inbound** and **Redis queue inbound**: one emits a **store view**, one receives notifications, and the other pops elements.
- List the five supported **CollectionType** values—**LIST**, **SET**, **ZSET**, **PROPERTIES**, and **MAP**—and select the appropriate one.
- Configure **RedisConnectionFactory**, **Redis.storeInboundChannelAdapter(...)**, **Pollers.fixedDelay(...)**, **MessageChannel**, transformer, and service activator.
- Use **RedisZSet.rangeByScore(...)** to query due tasks; understand why a poll does not mean a job has been claimed/ACKed.
- Analyze **key/key-expression**, serializers, snapshots vs. live views, concurrent modifications, duplicate handling, and data deletion conditions.
- Use **transaction synchronization** within its proper scope; distinguish after-commit callbacks from atomic Redis/database transactions.
- Design checkpoints, idempotency, retries, leases/claims, and alternatives using **Redis Streams** or durable work queues when tasks must not be lost.
- Test behavior when the store is empty, data changes between polls, multiple application replicas run, connections drop, and business errors occur.

## 1. What problem does the Redis store inbound adapter solve?

Suppose a **ReminderService** stores reminder tasks in a **Redis Sorted Set (ZSET)**. Each member is a **jobId**, and the score is the eligible execution time in Unix epoch milliseconds:

~~~text
Key: reminders:{notify}:due

Member             Score (epoch milliseconds)
------------------------------------------------
reminder-1001      1795402800000
reminder-1002      1795403100000
reminder-1003      1795410000000
~~~

The application wants to **periodically inspect the dataset** and pick due reminders. Rather than writing an ad-hoc scheduled method wired directly to business logic, Spring Integration provides the **Redis store inbound channel adapter** to connect a Redis store to an integration flow:

~~~mermaid
flowchart LR
    P["Reminder writer"] --> R[("Redis ZSET<br/>reminders:due")]
    T["Spring Integration Poller<br/>every 2 seconds"] --> I["RedisStoreMessageSource"]
    R -. "Bound collection view" .-> I
    I --> M["Spring Message<br/>payload: RedisStore"]
    M --> C["MessageChannel"]
    C --> Q["Query due members"]
    Q --> V["Validate / deduplicate"]
    V --> H["Reminder service"]
~~~

**The easiest point to misunderstand:** The store inbound adapter **does not automatically read, delete, and emit one element per poll**. The underlying **`RedisStoreMessageSource`** returns a **`RedisStore` view bound to the key/collection**. Subsequent steps decide **which elements to query** and **whether to delete/claim them**.

Thus, Redis store inbound differs from:

- **Redis queue inbound adapter**: receives items by popping from a Redis List.
- **Redis Pub/Sub inbound adapter**: receives messages sent by publishers to a channel.
- **Redis Streams consumer**: reads records with IDs, retention, consumer groups, and dedicated ACKs.

This lesson belongs to the **Adapter Redis** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. It places Redis into the inbound/outbound adapter, gateway, poller, and `MessageChannel` model while emphasizing message contracts, error handling, and connection lifecycles, just as when integrating File, SFTP, HTTP, JMS, AMQP, Kafka, and databases.

## 2. How it really works: Poller → MessageSource → RedisStore view

Spring Integration uses a **polling consumer** to invoke the message source's `receive` method on a schedule. For a Redis store, the source can be represented by:

~~~java
org.springframework.integration.redis.inbound.RedisStoreMessageSource
~~~

Logical flow:

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as RedisStoreMessageSource
    participant R as Redis
    participant C as MessageChannel
    participant H as Handler
    P->>S: receive()
    S-->>P: Spring Message<RedisStore view>
    P->>C: send(message)
    C->>H: Handle view
    H->>R: Query current members
    R-->>H: Members at query time
    Note over S,H: Does not auto-pop/ACK individual elements
~~~

### 2.1. A view is not a snapshot

A **RedisStore view** is a **Java object bound to Redis data**; operations like `rangeByScore` or `size` query Redis when invoked. Do not treat it as an immutable snapshot containing all elements frozen at poll time.

Example:

~~~text
10:00:00.000  Poller receives RedisZSet view
10:00:00.100  Publisher adds reminder-X
10:00:00.200  Handler calls rangeByScore(...)

The handler can see reminder-X, even though X did not exist when the poll began.
~~~

If a handler buffers the view in a `QueueChannel` and processes it seconds later, data in Redis may have changed further. Decide explicitly whether you want **reading current state**, **snapshotting values**, or **claiming individual jobs**; they are not the same.

### 2.2. Store inbound can emit messages even when there are no new jobs

A polling `MessageSource` exposing a store view can emit messages periodically regardless of whether new elements exist. Therefore:

- **One poll does not equal one new data item.**
- Poller `maxMessagesPerPoll` does not default to a per-member cap inside the Redis collection.
- If a handler processes all members every time without checkpointing, old members can be reprocessed repeatedly.

Verify the exact behavior when the key does not exist or the store is empty on your library version; **do not rely on continuous polls to infer that new jobs were created**.

### 2.3. This is polled inbound, not a message-driven queue

| Component | Who triggers it? | Data received | Needs a Spring Integration poller? |
| --- | --- | --- | --- |
| **Redis store inbound** | Poller by `fixedDelay`/`fixedRate`/trigger | `RedisStore` view | **Yes** |
| **Redis queue inbound** | Endpoint loop waiting on blocking `POP` | One popped item | **No**, for message-driven endpoint |
| **Redis Pub/Sub inbound** | Redis client listener callback | One notification | **No** |
| **HTTP inbound gateway** | Client request | Request, may require reply | **No**, not in the Poller sense |

Putting `Pollers.fixedDelay(...)` on store inbound is right. Putting the same poller on a message-driven queue inbound expecting it to add ACK/replay confuses the models.

## 3. Five Redis collection types supported by the adapter

Under the Redis Store Inbound contract, **`collection-type`** accepts:

| CollectionType | Redis structure | Example use case | Notes |
| --- | --- | --- | --- |
| **LIST** | List | Simple job/log list | View does not auto-pop items |
| **SET** | Set | Set of products to reconcile | No guaranteed ordering |
| **ZSET** | Sorted set | Jobs ordered by `dueAt`/priority score | Score supports range queries; needs safe claiming |
| **PROPERTIES** | Property-like store | Small config key/values | Does not represent an event by default |
| **MAP** | Hash/map | Record states | Live map; values may change while handler runs |

In Java, the enum is declared by **`RedisCollectionFactoryBean.CollectionType`** in Spring Data Redis in corresponding versions.

### 3.1. RedisStore API provided by Spring Data Redis

The source class returns a payload extending Spring Data Redis's **`RedisStore`**. The concrete subtype depends on `collection-type`, such as **`RedisZSet`** when `ZSET` is chosen.

Do not configure `LIST` and write a handler expecting `RedisZSet`. If the **actual Redis key** holds a different data structure than configured, Redis returns a **WRONGTYPE** error on query.

### 3.2. LIST differs from Redis queue inbound

In **store inbound with `CollectionType.LIST`**, the payload is a **view** of the List. The handler can iterate/query or explicitly delete elements under its own contract.

In **Redis queue inbound**, the endpoint typically executes blocking `POP` and returns an **item**. Choosing **`LIST`** on store inbound does not turn it into an auto-ACKing or auto-popping queue consumer.

### 3.3. SET has no ordering

`SET` is useful for storing a set of IDs to scan when order does not matter. However, when two workers scan a `SET` concurrently, they can read the same members. To make one worker responsible for one ID, use atomic claiming/locking/idempotency or a suitable data model.

### 3.4. ZSET has scores, but a score is not an acknowledgment

A `ZSET` can sort reminders by **`dueAt`** or **`priority`**. A **`ZRANGEBYSCORE`/`rangeByScore`** call only reads matching items; it neither marks a job **`PROCESSING`** nor removes it after processing.

### 3.5. PROPERTIES and MAP

These two types are helpful for referencing **properties/configs/state** in Redis and passing them through a flow for inspection/reconciliation. They are not message logs with per-item ACKs. When using hashes/maps, consider **consistency** and **serializers for hash keys/values**.

## 4. When should you choose Redis store inbound?

| Problem | Suitable? | Why |
| --- | --- | --- |
| Periodically inspecting a Redis ZSET for due items | **Yes**, if you design claim/checkpointing | Poller accesses view and queries ranges |
| Scanning a Redis SET to reconcile against a database | **Yes** | You identify new/processed members yourself |
| Watching MAP/PROPERTIES state on a schedule | **Yes** | Observes current view at query time |
| Receiving individual Redis Pub/Sub notifications | **No** | Use Redis Pub/Sub inbound |
| Pulling FIFO jobs one by one via blocking List POP | **Do not use store inbound as an auto-popping queue** | Use the appropriate Redis queue inbound |
| Requiring consumer groups, pending/ACK/replay | **Not built in** | Use Redis Streams or a supported broker |
| Running tasks that must execute exactly once | **Insufficient by adapter config alone** | Requires transactional/idempotent business design |

**Design question:** Do you want to **observe and process a collection** or **take exclusive ownership of a single task**? The answer determines whether store inbound/poller fits better than a consumer group/work queue.

## 5. Designing the data contract for a ZSET reminder

To understand the source and handler, let's use a concrete scenario: **scanning due reminders** in a Redis ZSET. Each member is a **stable ID**, the score is the due timestamp, and reminder details live in the authoritative data source.

~~~text
ZSET: reminders:{notify}:due
  reminder-1001 -> 1795402800000.0
  reminder-1002 -> 1795403100000.0

Database / domain API:
  reminder-1001 -> tenant T1, recipient R1, status PENDING
  reminder-1002 -> tenant T2, recipient R2, status PENDING
~~~

**Why store `jobId` as the ZSET member?** Embedding large JSON directly as the member makes per-ID updates/removals, reconciliation, and authorization harder. A short ID member lets you:

- Deduplicate by `jobId`.
- Enforce a unique constraint in the status table.
- Fetch the latest business details from the database.
- Avoid keeping PII inside Redis ZSETs too long.
- Reduce the risk of deserializing untrusted payloads.

### 5.1. Is the score a timestamp or a priority?

A ZSET only knows **`double` scores**, not business semantics. If using epoch milliseconds:

~~~text
score = dueAtEpochMillis
due   = score <= nowEpochMillis
~~~

If using priority, the lowest score might represent highest priority or vice versa per your contract. Never reuse one ZSET for two different score conventions without an explicit schema/version.

### 5.2. Time and timezones

For reminder schedules, the application must convert domain times to **Instant/UTC epoch milliseconds** before writing scores. Never write a local time string like `09:00` assuming the ZSET understands `Asia/Ho_Chi_Minh` or DST.

**Avoid relying on unsynchronized client clocks** across multiple nodes: synchronize clocks via NTP and define a policy for scheduling drift. Current millisecond timestamps fit within IEEE 754 `double` exact-integer precision, yet always verify range, overflow, and seconds-vs-milliseconds contracts.

### 5.3. Business state in the authoritative source

Example database table:

~~~text
reminder_jobs
  job_id          VARCHAR PRIMARY KEY
  tenant_id       VARCHAR
  due_at          TIMESTAMP UTC
  status          PENDING / PROCESSING / SENT / CANCELLED
  version         BIGINT
  attempts        INTEGER
  updated_at      TIMESTAMP UTC
~~~

Here, the Redis ZSET serves as a **secondary index accelerating due-job lookups**. If the ZSET is lost or stale, the database rebuilds it. If Redis is the sole source of jobs, persistence and claiming requirements are much stricter.

### 5.4. Avoid storing PII inside members

Do not put emails, access tokens, signed URLs, or private content inside ZSET members merely because `rangeByScore` conveniently returns Strings. Store **IDs** and fetch authorized data in the handler.

## 6. Dependencies and Redis connection setup

Example based on Spring Boot with Spring Integration Redis and Spring Data Redis:

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

Use **Spring Boot BOM/dependency management** to keep Spring Integration, Spring Data Redis, and the Redis client aligned. Some Java DSL APIs, serializers, and transaction synchronization options vary across library generations; compile and test examples against your actual version before production.

Local/test example:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

Production requires credential management, ACLs, TLS, timeouts, and the right Sentinel/Cluster topology. Redis has no RabbitMQ-style virtual host: verify the exact **Redis instance/database index/namespace** and key ownership. Different Spring Boot generations may use different Redis property keys; check your version's docs.

### 6.1. RedisConnectionFactory does not create a store inbound flow on its own

`RedisConnectionFactory` supplies connections; **`RedisStoreMessageSource`** selects the Redis key/type and the **Poller** triggers `receive`; **`MessageChannel`** routes to transformers/service activators. Without a poller, a `MessageSource` does not run on a schedule by itself.

### 6.2. Do not combine both template initialization options on the same endpoint

Store inbound can take a **`RedisConnectionFactory`** to construct a default template or a pre-configured **`RedisTemplate`** with custom serializers. XML/DSL expose corresponding options; **do not specify both `redis-template` and `connection-factory` simultaneously on the same source** when the API forbids it.

### 6.3. Serializers must match stored data

Under the default mechanism when built from a `RedisConnectionFactory`, **`StringRedisTemplate`** with **`StringRedisSerializer`** is used for key/value/hash key/hash value in matching versions.

If a producer writes data with a `RedisTemplate` using **JDK serialization** or another JSON serializer, reads may fail to decode properly. **Serializer mismatches are not caused by a slow poller**; test read/write using the exact same wire format.

## 7. Producer: writing reminders into a Redis ZSET

A sample producer writes IDs and due times with `StringRedisTemplate`:

~~~java
import java.time.Instant;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReminderIndexWriter {

    public static final String DUE_KEY =
        "reminders:{notify}:due";

    private final StringRedisTemplate redisTemplate;

    public ReminderIndexWriter(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public void schedule(String jobId, Instant dueAt) {
        if (jobId == null
                || !jobId.matches("[A-Za-z0-9_-]{1,80}")
                || dueAt == null) {
            throw new IllegalArgumentException(
                "Invalid reminder index entry");
        }

        redisTemplate.opsForZSet().add(
            DUE_KEY,
            jobId,
            (double) dueAt.toEpochMilli());
    }
}
~~~

**What this method does:** places a `jobId` member with score `dueAt` into the ZSET. Redis ZSET does not automatically notify the store inbound adapter; the poller inspects the store on schedule. **`ZADD`'s boolean return** or write success does not prove the reminder was sent.

### 7.1. Test data with Redis CLI

On an isolated test Redis instance:

~~~bash
redis-cli ZADD reminders:{notify}:due 1795402800000 reminder-1001
redis-cli ZADD reminders:{notify}:due 1795403100000 reminder-1002
redis-cli ZRANGEBYSCORE reminders:{notify}:due -inf +inf WITHSCORES
~~~

Never run `DEL`/`FLUSHDB` on production Redis for labs. To test “due” jobs, generate scores relative to the current test clock; the fixed numbers above only illustrate the structure.

### 7.2. ZADD and business transactions

If the database saves the reminder and commits, then Redis `ZADD` fails, the ZSET index is missing a job. If Redis `ZADD` runs first and the database rolls back, the ZSET holds a dangling ID.

When Redis is a rebuildable index, use periodic reconciliation against the database. If the index must stay tightly synchronized, design an **outbox/change capture**, update state tracking, and consistency checks. Never claim JDBC `@Transactional` automatically rolls back Redis `ZADD`.

### 7.3. Do not treat a ZSET score as an ACK flag

As long as a job with an old `dueAt` remains in the ZSET, subsequent polls will keep returning it. Redis does not alter scores or remove members just because a Spring Integration handler ran. To update state, the application must take explicit action: **remove**, update score, move to processing, or checkpoint in the database.

## 8. Java DSL: Redis store inbound with Pollers.fixedDelay

Here is the direct way to configure a **Redis store inbound channel adapter** using Spring Integration's Java DSL factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.support.collections.RedisCollectionFactoryBean.CollectionType;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.redis.dsl.Redis;

@Configuration
@EnableIntegration
public class ReminderStoreInboundConfig {

    @Bean
    public IntegrationFlow reminderStoreInboundFlow(
            RedisConnectionFactory redisConnectionFactory,
            ReminderStoreObserver observer) {

        return IntegrationFlow
            .from(Redis.storeInboundChannelAdapter(
                    redisConnectionFactory,
                    ReminderIndexWriter.DUE_KEY)
                    .collectionType(CollectionType.ZSET),
                endpoint -> endpoint
                    .poller(Pollers.fixedDelay(2000)
                        .maxMessagesPerPoll(1))
                    .id("reminderStorePoller"))
            .handle((payload, headers) -> {
                observer.observe(payload);
                return null;
            })
            .get();
    }
}
~~~

### 8.1. Imports and versions

The DSL factory **`Redis.storeInboundChannelAdapter(...)`** and **`Pollers.fixedDelay(...)`** are documented in the corresponding Spring Integration reference. **`CollectionType`** belongs to `RedisCollectionFactoryBean` in Spring Data Redis. When packages/APIs shift across versions, check your actual library rather than guessing nonexistent setters.

### 8.2. An observer should not repeatedly process the whole store

~~~java
import org.springframework.data.redis.support.collections.RedisStore;
import org.springframework.stereotype.Service;

@Service
public class ReminderStoreObserver {

    public void observe(Object payload) {
        if (!(payload instanceof RedisStore)) {
            throw new IllegalArgumentException(
                "Expected a RedisStore view");
        }

        // In the lab: observe that the source emitted a view into the flow.
        // Do not treat this poll as a claimed job.
    }
}
~~~

**Purpose of this first example:** demonstrate that the integration endpoint emits a **`RedisStore` view** and that the poller triggers. To select due reminders, move to a handler calling **`RedisZSet.rangeByScore(...)`** in section 10.

### 8.3. `maxMessagesPerPoll(1)` does not mean a one-job limit

In the example:

- The poller invokes the source and receives one **message containing a `RedisStore` view**.
- The handler may query **0, 10, or thousands** of members.
- Thus `maxMessagesPerPoll(1)` **does not limit how many members** the handler pulls.

To process bounded batches, apply limits inside the **range query or application batching**, not merely on the poller's `receive` count.

### 8.4. Do not use an unbounded QueueChannel to buffer views

If you place a `QueueChannel` after the source:

~~~text
Poll 1 -> RedisZSet view A -> QueueChannel
Poll 2 -> RedisZSet view B -> QueueChannel
Poll 3 -> RedisZSet view C -> QueueChannel
~~~

all three views still point to **the same Redis key**, and when consumed later they may all see the same live state rather than three independent snapshots. Buffering views does not create event history or per-poll backlogs.

## 9. Java annotations: RedisStoreMessageSource and @InboundChannelAdapter

Besides Java DSL, you can declare the `MessageSource` directly with annotations:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.support.collections.RedisCollectionFactoryBean.CollectionType;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.redis.inbound.RedisStoreMessageSource;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ReminderStoreAnnotationConfig {

    @Bean
    public MessageChannel reminderStoreViews() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
        channel = "reminderStoreViews",
        poller = @Poller(fixedDelay = "2000"))
    public RedisStoreMessageSource reminderStoreSource(
            RedisConnectionFactory redisConnectionFactory) {

        var source = new RedisStoreMessageSource(
            redisConnectionFactory,
            new LiteralExpression(ReminderIndexWriter.DUE_KEY));

        source.setCollectionType(CollectionType.ZSET);
        return source;
    }
}
~~~

**These two configurations are alternatives:** This snippet and the Java DSL in section 8 describe **the same scheduled store source**. Including both in one `ApplicationContext` creates **two pollers** on the same Redis key, easily invoking the business handler multiple times. Pick one approach per use case, or separate key/consumer ownership cleanly.

### 9.1. Why use LiteralExpression?

**`keyExpression`** is evaluated when the source receives data. When the key name is fixed, **`LiteralExpression`** makes intent explicit and avoids a value that looks like SpEL being parsed as an expression.

### 9.2. When to use a dynamic SpEL key-expression?

Use it when choosing a store key by controlled time/environment/tenant. However, because a polled source has no incoming user request payload, it cannot choose keys per item dynamically. A dynamic expression can re-evaluate between polls, abruptly switching sources if configuration state changes.

If a `keyExpression` derives from untrusted input, enforce an allowlist and tenancy validation; never let users pass arbitrary Redis key names to read internal stores.

### 9.3. Do not clear the entire collection in the annotated method

The annotated method returns a **`MessageSource`**. It is not the business handler executing jobs. Deleting all members each time the source is polled loses due/undue distinction, transient error handling, concurrency, and recovery.

## 10. Handling the RedisZSet view to read due members

To work with the typed store, the handler can accept **`RedisZSet`** and call **`rangeByScore`**. Example using a Spring Integration service activator:

~~~java
import java.util.Set;

import org.springframework.data.redis.support.collections.RedisZSet;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Service;

@Service
public class ReminderDueInspector {

    @ServiceActivator(inputChannel = "reminderStoreViews")
    public void inspect(RedisZSet<String> view) {
        double nowMillis = (double) System.currentTimeMillis();

        Set<String> due = view.rangeByScore(
            Double.NEGATIVE_INFINITY, nowMillis);

        if (due == null || due.isEmpty()) {
            return;
        }

        // Observation only in this initial example;
        // do not assume these jobs are claimed.
        for (String jobId : due) {
            System.out.println("Candidate due reminder: " + jobId);
        }
    }
}
~~~

This code reads from **`reminderStoreViews`** declared in section 9—do not attach the same handler simultaneously to the Java DSL flow in section 8. While learning, run **one configuration** at a time to observe and count callbacks.

### 10.1. Why choose ZSET for this problem?

**`rangeByScore(min, max)`** selects members whose scores fall in the interval. ZSETs fit reminder `dueAt`, rate-limit windows, or score-ordered datasets. However:

- **`rangeByScore` is a read operation**, not a claim.
- It can return many members, requiring batch limits when data grows.
- A job not yet removed/updated will reappear on the next poll.
- If a producer updates scores concurrently, results depend on query timing.

### 10.2. Querying reveals candidates, not delivery proof

~~~text
Poll 1: rangeByScore -> [reminder-1001, reminder-1002]
Poll 2: rangeByScore -> [reminder-1001, reminder-1002]
Poll 3: rangeByScore -> [reminder-1001, reminder-1002]
~~~

If the handler immediately sends an email inside the `for` loop without idempotency/checkpointing, the same recipient will receive multiple emails. `RedisStoreMessageSource` has no built-in memory of **“reminder-1001 already sent”**.

### 10.3. Avoid scanning a massive ZSET in full

A collection with one million members can cause:

- Increased Redis command/serialization latency.
- JVM memory pressure when materializing a large `Set`.
- Poller starvation, missing target cadence.
- Handlers reprocessing the same set.

Fetch only eligible members and bound batch sizes; you can use **`RedisTemplate.opsForZSet().rangeByScore(key, min, max, offset, count)`** or a version-compatible range API after designing proper claiming and recovery.

**Using `RedisTemplate` for bounded queries is a handler strategy** and does not alter the store inbound adapter's semantics.

## 11. Poller: fixedDelay, fixedRate, and maxMessagesPerPoll

The Spring Integration Poller controls **when `source.receive()` is called**.

| Setting | Meaning | Risk if misunderstood |
| --- | --- | --- |
| **`fixedDelay(2000)`** | Fixed pause between executions per trigger | Slow handlers lengthen real intervals between polls |
| **`fixedRate`** | Periodic schedule cadence | With slow jobs and executor concurrency, consider overlap |
| **`maxMessagesPerPoll(1)`** | Max messages received from source per poll | Does not limit Redis members inside one view |
| **`TaskScheduler`** | Thread pool triggering pollers | Saturated shared scheduler delays multiple flows |
| **`receiveTimeout`/`sendTimeout`** | Endpoint/channel-specific timeouts | Not business retry/backoff or ACK |
| **`transactional`/advice** | Advice wrapping the polling task | Does not create a distributed Redis + DB transaction |

### 11.1. Fixed delay is not a Redis ZSET TTL

The **2-second poller** is the inspection frequency. The **`dueAt` score** is the selection criterion. Redis ZSETs do not push members when scores reach `now`; due status only takes effect when application queries compare against current time.

### 11.2. One poller trigger can process multiple jobs

One `RedisStore` view can allow a handler to read 50 IDs in a single receive. `maxMessagesPerPoll(1)` does not cap it at 50. To process 10 jobs per batch:

1. Select at most 10 candidates in the query.
2. Apply claiming/locking/checkpointing per candidate.
3. Record success/failure individually per job.
4. Never delete an entire range merely because 9 out of 10 jobs succeeded.

### 11.3. The poller can still fire when the store is empty

For a view-emitting source, the source may produce a Spring Message even when the ZSET has no due members. Counting **adapter receive count** as **processed jobs count** will skew dashboards. Increment business success counters only after the handler confirms completion of a specific job.

### 11.4. Scheduler and threading model

With **`DirectChannel`**, the handler runs synchronously on the poller call path; slow handlers stall the poller task. With **`ExecutorChannel`**, the poller hands the view to an executor and returns immediately, running actual work later. Poller transaction synchronization can then **fire before the async handler finishes**, a severe hazard when using `afterCommit` to delete data.

To clean up after business outcomes, keep processing **synchronous inside a defined transaction boundary**, or separate it into a durable job state machine with explicit ACKs.

## 12. Snapshots, live views, and data races

A sound mental model:

~~~text
RedisStore view:
  "This is an object providing access to store X"

Not:
  "This is an immutable copy of all of store X at 10:00:00"
~~~

### 12.1. Two queries can return different results

~~~mermaid
sequenceDiagram
    participant H as Handler A
    participant R as Redis ZSET
    participant P as Producer
    H->>R: rangeByScore(0, now)
    R-->>H: [job-1, job-2]
    P->>R: ZADD job-3 dueAt=now
    H->>R: rangeByScore(0, now)
    R-->>H: [job-1, job-2, job-3]
~~~

If the handler needs **a deterministic set**, materialize the IDs first, persist batch/claim state, and enforce idempotency. Do not pass a raw `RedisStore` view over HTTP/Kafka/SFTP thinking it is a serializable snapshot; it is tied to the Redis client and future Redis access.

### 12.2. Contention when multiple pollers read the same key

Two replicas can read the same items simultaneously:

~~~text
Node A: rangeByScore -> job-1, job-2
Node B: rangeByScore -> job-1, job-2
~~~

If both send emails, each reminder goes out twice. The distinction between **view** and **claim** is decisive: a read-only query does not grant exclusive ownership to one worker.

### 12.3. Member/score changes during processing

A producer might **cancel** a reminder or reschedule `dueAt`. If a handler reads a candidate at `t0` and sends at `t1` without rechecking fresh state, it can deliver a canceled or rescheduled reminder.

Verify **status/version/dueAt** in the business source before executing final side effects, especially for time-sensitive events.

## 13. Transaction synchronization: before and after commit

Spring Integration supports **transaction synchronization** on pollers to trigger hooks at **`beforeCommit`**, **`afterCommit`**, or **`afterRollback`** of the transaction context.

The Spring Integration Redis store inbound documentation illustrates a **Redis ZSET view** with **`removeByScore(...)`** in an `afterCommit` expression. Logical flow:

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as RedisStore view
    participant H as Business handler
    participant TX as Transaction context
    participant R as Redis
    P->>S: receive view
    P->>TX: Begin transaction advice
    P->>H: Process candidates
    H-->>P: Success
    P->>TX: Commit
    TX->>R: afterCommit cleanup (if configured)
~~~

### 13.1. What does PseudoTransactionManager mean?

Spring Integration's **`PseudoTransactionManager`** can be used when there is no real database transaction manager, simply to enable **transaction synchronization callbacks**.

It **does not make Redis operations atomic**, cannot unsend an email, and does not combine Redis ZSET updates with JDBC/object storage into a distributed transaction.

### 13.2. Illustrative Java DSL poller transaction example

In Java DSL, a flow can configure a transactional poller with a synchronization factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.support.collections.RedisCollectionFactoryBean.CollectionType;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.redis.dsl.Redis;
import org.springframework.integration.transaction.PseudoTransactionManager;
import org.springframework.integration.transaction.TransactionSynchronizationFactory;

@Configuration
@EnableIntegration
public class ReminderStoreSyncFlow {

    @Bean
    public IntegrationFlow reminderStoreFlowWithSync(
            RedisConnectionFactory factory,
            TransactionSynchronizationFactory syncFactory,
            ReminderStoreObserver observer) {

        return IntegrationFlow.from(
            Redis.storeInboundChannelAdapter(
                    factory, ReminderIndexWriter.DUE_KEY)
                .collectionType(CollectionType.ZSET),
            endpoint -> endpoint.poller(
                Pollers.fixedDelay(2000)
                    .transactional(new PseudoTransactionManager())
                    .transactionSynchronizationFactory(syncFactory)))
            .handle((payload, headers) -> {
                observer.observe(payload);
                return null;
            })
            .get();
    }
}
~~~

**This is an alternative configuration** to the other poller configs; do not register multiple beans polling the same ZSET simultaneously while testing task logic. **`TransactionSynchronizationFactory` must be declared separately** and contain a processor with explicit callbacks; adding `.transactional(...)` alone does not remove members.

### 13.3. Post-commit cleanup expression

An educational mechanism example:

~~~text
afterCommit expression:
    payload.removeByScore(1, 3)
~~~

Here `payload` **must** be a compatible `RedisZSet` view; the expression deletes members with scores in `1..3`. This is an **API illustration**, not a production policy for due reminders.

**Why not copy this pattern straight to production?**

- `afterCommit` deletes **an entire range**, which can include members added after the handler read candidates.
- If 19 of 20 jobs in the range succeeded and 1 failed, deleting the whole range drops the 20th job.
- A handler using `ExecutorChannel` returns early, letting the transaction context commit before business work finishes.
- If Redis cleanup fails after DB commit, already-processed work reappears and requires idempotency.

**Recommendation:** Clean up by **claimed and completed job ID**, checking owner/version and guarding against duplicates. Use a durable state source to distinguish `PENDING`, `PROCESSING`, `DONE`, and `FAILED` rather than sweeping entire score ranges.

### 13.4. Synchronization callbacks do not replace Redis MULTI/EXEC

| Mechanism | Primary guarantee | What it does NOT guarantee |
| --- | --- | --- |
| Spring transaction synchronization | Runs callbacks before/after commit/rollback of the tx context | Automatic Redis rollback if Redis isn't in a real tx |
| `PseudoTransactionManager` | Provides callback synchronization hooks | Atomicity across JDBC + Redis + email |
| JDBC `@Transactional` | Atomicity of operations inside the DB transaction | Automatic rollback of Redis `ZADD`/`ZREM` or HTTP APIs |
| Redis `MULTI`/`EXEC` | Groups Redis commands per Redis semantics | Atomicity with external business code/databases |
| Redis Lua script | Atomicity of commands on one server/shard inside the script | End-to-end commit with object storage and database |

### 13.5. Failure window after DB commit

~~~text
Handler sends notification, DB commits
  -> process crashes before afterCommit Redis cleanup
  -> ZSET still holds job
  -> next poller reads it again
  -> notification could be sent again
~~~

Therefore you need **idempotent side effects**, a verifiable `DONE` state, and cleanup reconciliation. Never treat `afterCommit` cleanup as a durable broker ACK.

## 14. How does TransactionSynchronizationFactory work?

In Spring Integration versions supporting this Java API, a **`TransactionSynchronizationFactory`** creates a synchronization object per transaction/poll. **`ExpressionEvaluatingTransactionSynchronizationProcessor`** can evaluate **SpEL expressions** or send results to channels after commit/rollback.

Responsibility diagram:

~~~mermaid
flowchart TD
    POLL["Poller task"] --> ADVICE["Transaction advice"]
    ADVICE --> RECV["RedisStoreMessageSource.receive"]
    RECV --> HAND["Synchronous flow"]
    HAND --> DEC{"Transaction outcome"}
    DEC -->|"Commit"| AC["afterCommit callback"]
    DEC -->|"Rollback"| AR["afterRollback callback"]
    AC --> C["Optional cleanup / audit"]
    AR --> F["Optional failure record / alert"]
~~~

### 14.1. Callback data scope

`RedisStoreMessageSource` can bind the **`RedisStore` reference in an integration resource holder**, allowing the synchronization processor to access the store. This is a runtime callback mechanism, not a durable record persisted in Redis.

### 14.2. What can the callback do safely?

Relatively safe options:

- Record metrics/audits for a processed batch.
- Signal reconciliation for specific job IDs.
- Remove claimed IDs/versions when logic verifies ownership.
- Forward outcome details to a **dedicated channel** after commit.

Be cautious with:

- Deleting an entire `rangeByScore` without verifying individual items.
- Publishing to external systems without handling `UNKNOWN` publish results.
- Making network calls in `afterCommit` assuming the DB can roll back if they fail.
- Relying on `ThreadLocal` transaction context after the flow switches to an async thread.

### 14.3. What if there is no real transaction?

`PseudoTransactionManager` only exposes callbacks; **it does not create a durable transaction**. If business logic demands atomicity, use a real database transaction with an outbox or a durable claim/ACK workflow. You cannot “turn on transactions on the poller” to make any Redis collection an exactly-once message broker.

### 14.4. Error flows can alter transaction outcomes

If a handler throws an exception and an error flow absorbs it and returns normally, the transaction advice may treat the poll as successful depending on configuration—causing **`afterCommit` to run** even though business work failed. Tests must verify exception propagation and outcome paths rather than merely seeing an error log.

### 14.5. When is synchronization unnecessary?

If store inbound is only used to **read state on a schedule, compare metrics, or reconcile IDs** without modifying Redis during the poll, transaction synchronization may be unnecessary. Adding transaction machinery to a read-only flow does not improve reliability and complicates the code.

## 15. Validating key-expression, collection type, and serializers

The store source binds to the specified Redis key. The key can be a literal or an expression evaluated on receive.

### 15.1. Literal key

~~~java
new RedisStoreMessageSource(
    redisConnectionFactory,
    new LiteralExpression("reminders:{notify}:due"));
~~~

For fixed keys, this is simple, easy to debug, and prevents expressions from implicitly referencing unexpected beans/context.

### 15.2. Dynamic key-expression

A `key-expression` is evaluated **on every `source.receive()`**. If the expression changes between polls, an endpoint can alternate across keys:

~~~text
Poll 1 -> reminders:{notify}:due:current
Poll 2 -> reminders:{notify}:due:previous
Poll 3 -> reminders:{notify}:due:current
~~~

This can be intentional, yet risks missed items or duplicate reads if key switches lack checkpointing and provenance. Never base key names on raw user input or unverified tenant headers.

### 15.3. WRONGTYPE and serializer mismatch

If a key holds a Redis String while the source is configured as `ZSET`, range calls fail with `WRONGTYPE`. If a producer writes JDK-serialized bytes while the source defaults to `StringRedisTemplate`, members decode into garbage or break contracts.

Verification checklist:

1. Are the Redis instance, database, and key right?
2. Does **`TYPE key`** return `zset`/`list`/`set`/`hash` as expected?
3. Which serializers does the source's `RedisTemplate` use for key/value/hash?
4. Does the producer use the exact same serialization contract?
5. Is another component overwriting the key with a different Redis structure?

### 15.4. MAP and PROPERTIES require consistent hash serializers

For Redis hashes/maps, **field names and values** have dedicated serializers. Do not configure only the value serializer and ignore `hashKeySerializer`/`hashValueSerializer`. Never use native JDK serialization for data arriving from multiple untrusted services.

### 15.5. Redis key naming and Cluster hash tags

For example, **`reminders:{notify}:due`** uses the hash tag `notify`, useful if later designs execute multi-key atomic commands in Redis Cluster across keys in the same slot. However, **hash tags alone do not make polling/claiming across multiple application replicas atomic**; you still need an ownership algorithm.

## 16. From “due candidates” to “claimed job”: two distinct problems

Store inbound helps **discover eligible elements**, yet with multiple pollers/workers you need an explicit **claim** step before side effects.

~~~mermaid
flowchart TD
    Z["ZSET due index"] --> POLL["Store inbound poller"]
    POLL --> R["rangeByScore(..., now)"]
    R --> C{"Claim jobId succeeded?"}
    C -->|"No"| SKIP["Skip: owned by another worker"]
    C -->|"Yes"| V["Validate status/version"]
    V --> H["Business handler"]
    H --> S{"Outcome?"}
    S -->|"Success"| ACK["Persist DONE + cleanup index"]
    S -->|"Transient error"| RETRY["Durable retry / lease expiry"]
    S -->|"Permanent error"| DEAD["Final failed state"]
~~~

### 16.1. Read-check-write is not atomic

Broken pattern:

~~~text
Worker A: EXISTS job in ZSET -> true
Worker B: EXISTS job in ZSET -> true
Worker A: send reminder
Worker B: send reminder
Worker A: ZREM
Worker B: ZREM
~~~

**`ZREM` after sending** does not stop two workers from both sending. You need an **atomic claim** before side effects or an idempotency/status store with unique constraints/fencing.

### 16.2. Claiming via database state

When the database is the source of truth, one design:

~~~sql
-- Pseudo SQL: adapt to your actual database/schema/locking.
UPDATE reminder_jobs
SET status = 'PROCESSING',
    lease_owner = :worker,
    lease_until = :deadline,
    version = version + 1
WHERE job_id = :jobId
  AND status = 'PENDING'
  AND due_at <= CURRENT_TIMESTAMP
  AND version = :expectedVersion;
~~~

`affectedRows = 1` means one worker claimed it under current conditions. `affectedRows = 0` means another worker changed it or the job is no longer eligible. Always verify version/status in a transaction against the authoritative source.

### 16.3. Can ZREM be used to claim?

If you only need one worker to remove a member and do not need crash recovery, an atomic **`ZREM`** prevents two workers from both succeeding. However, if you **remove the member before business commit**, a crash loses the job from the index.

Thus:

- Removing to claim can prevent double claims in Redis.
- It is **not an ACK** proving completion.
- You still need processing state/leases and recovery.

### 16.4. ZPOPMIN does not check dueAt

**`ZPOPMIN`** pops the lowest-score element **even when that score is in the future**. If only due jobs may be claimed, check the cutoff inside a coordinated atomic operation, such as a Lua script with validation, or use a conditional database claim.

Never call `ZPOPMIN` and “push it back if not due yet” without accounting for unknown outcomes, ordering, and races.

### 16.5. Atomic claim with Lua: concept

The following logic picks at most one due job and moves it from the `due` ZSET to a `processing` ZSET within the same Redis server/hash slot.

~~~lua
-- KEYS[1] = due ZSET
-- KEYS[2] = processing ZSET
-- ARGV[1] = nowEpochMillis
-- ARGV[2] = leaseDeadlineEpochMillis

local candidates = redis.call(
    'ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 1)

if #candidates == 0 then
    return nil
end

local member = candidates[1]
local removed = redis.call('ZREM', KEYS[1], member)
if removed == 1 then
    redis.call('ZADD', KEYS[2], ARGV[2], member)
    return member
end
return nil
~~~

**Scope limits of this example:** The script is atomic on the target Redis shard, yet does not automatically:

- Attach an owner, fencing token, or attempt count.
- Preserve original `dueAt` history (store in a job registry if needed).
- Verify the member is not already `PROCESSING` from an earlier cycle.
- Guarantee script durability across every failover/RPO mode.
- Guarantee email/object storage/database side effects committed.

If a producer re-adds the same member to `due` while it is already `PROCESSING`, enforce duplicate/fencing contracts. Do not copy this bare script into production without completing the state machine.

### 16.6. Polling the view and claiming workers can be decoupled

`RedisStoreMessageSource` can:

1. Trigger store inspection on schedule.
2. Measure backlog/candidates.
3. Call a **claim service** backed by Redis Lua or conditional DB claims.
4. Dispatch only **claimed job IDs** to the worker flow.

This keeps the **inbound adapter in its proper store-polling role**, while the claim layer distributes exclusive ownership. Never send an entire `RedisStore` view to an executor and equate dispatch with claiming.

## 17. Retries and leases: recovering when a worker fails

A `PROCESSING` job may fail to finish due to a worker crash, connection drop, timeout, or external dependency outage. To retry across restarts, you need **durable attempt state** and **leases/reclaimers**.

### 17.1. Minimum state machine

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING: claim succeeded
    PROCESSING --> DONE: business committed
    PROCESSING --> RETRY_WAIT: transient error
    PROCESSING --> FAILED: permanent error / max attempts
    PROCESSING --> RETRY_WAIT: lease expired + reclaimer
    RETRY_WAIT --> PENDING: nextAttemptAt reached
    DONE --> [*]
    FAILED --> [*]
~~~

### 17.2. Why is an overly short lease dangerous?

~~~text
Worker A: claims reminder-1001; 5-second lease
Worker A: calls email provider, takes 8 seconds
Reclaimer: after 5 seconds assumes A died, lets B re-claim
Worker B: also calls email provider
~~~

If both A and B can send the same reminder, the business side effect duplicates. You need:

- Heartbeats/lease extensions for long-running work.
- Fencing tokens or versions so stale owners cannot write new state.
- Provider-side idempotency keys where supported.
- `DONE` state and unique `eventId` at commit time.
- A reclaimer with grace delays and a policy for `UNKNOWN` outcomes.

### 17.3. What is the scope of a retry budget?

Distinguish between:

- **In-JVM attempt**: `RetryTemplate` retrying briefly inside one handler invocation.
- **Durable delivery/claim attempt**: multiple claims after crashes or lease expirations.
- **Publish attempt**: producer rewriting data to Redis.
- **Business side-effect attempt**: a provider call may have succeeded even though the response timed out.

Never point to `RetryTemplate.maxAttempts(3)` alone to claim total emails sent across restarts are bounded.

### 17.4. Backoff and `nextRetryAt`

You can use a **Redis ZSET with `score = nextRetryAt`** for delayed jobs while a **database/job state table** tracks attempts/owner/errorCategory. A scheduler promotes due jobs subject to attempt caps and a final failed state.

**The store inbound poller does not update scores or requeue failed jobs automatically.** All state transitions belong to your handler/claim/reclaimer design.

### 17.5. Poison jobs

Jobs with bad schemas, missing tenants, invalid recipient emails, or unauthorized object keys will not heal on retry. Leaving them in the `due` ZSET without updating status causes **the poller to see them every 2 seconds forever**.

Classify them clearly:

| ErrorCategory | Retry? | Action |
| --- | --- | --- |
| `INVALID_SCHEMA` | No | Final `FAILED` + audit |
| `UNSUPPORTED_VERSION` | Usually not immediately | Alert, handle compatibility |
| `PERMISSION_DENIED` | No hot retries | Fix policy/config, investigate |
| `PROVIDER_TIMEOUT` | Bounded | Retry with backoff + idempotency |
| `DB_UNAVAILABLE` | Bounded | Backoff / circuit breaker |
| `UNKNOWN_PROVIDER_RESULT` | Needs reconciliation | Check status before resending |

### 17.6. When to use Redis Streams instead of ZSET + custom leases?

When requirements demand **per-event record IDs, consumer groups, pending entries, and reclaiming**, Redis Streams provide those primitives out of the box. ZSETs excel as **due-time/scheduling indexes**, not as default message logs.

One possible architecture:

~~~text
ZSET due index -> claim scheduler -> Redis Stream / durable broker
                                   -> consumer group -> business handler
~~~

Even then, the ZSET → Stream step requires **atomic handoff, duplicate protection, and recovery**; exactly-once does not emerge automatically just because both structures live in Redis.

## 18. Idempotency and business service transactions

In `ReminderService`, a `jobId` may be processed more than once when:

- Two pollers see the same candidate.
- A claim lease expires and a reclaimer hands it to another worker.
- A worker commits successfully but dies before cleanup.
- A producer schedules the same ID again.
- An operator replays a failed task.

### 18.1. Jobs table with unique keys

~~~text
reminder_jobs
    job_id         PRIMARY KEY
    business_key   UNIQUE (if required by contract)
    status         PENDING/PROCESSING/DONE/FAILED
    lease_owner
    lease_until
    version
    attempt_count
    result_id
    updated_at
~~~

A **unique constraint** on `jobId` or `business_key` guards against races between workers. Check-then-insert without a constraint fails under concurrency.

### 18.2. Two opposite crash windows

~~~text
Scenario A:
  Delete/ACK Redis job before sending or committing business work.
  -> Process crashes.
  -> Work can be lost.

Scenario B:
  Provider/DB committed.
  -> Process crashes before Redis cleanup / marking DONE.
  -> Job is reprocessed.
  -> Can duplicate if not idempotent.
~~~

Never claim `@Transactional` wraps Redis, an email provider, object storage, and JDBC into one atomic transaction. For external APIs, rely on idempotency keys, outboxes, reconciliation, and `UNKNOWN` state handling.

### 18.3. Fencing tokens / optimistic versions

If owner A's lease expires while A finishes late, B may already have claimed the job. A monotonically increasing **fencing token** per claim lets the target system or database reject stale owners.

However, fencing only works **if the system performing side effects enforces the token**. Logging a token that the provider ignores does not prevent duplicates.

### 18.4. Synchronizing the Redis index after business commit

Once a job is `DONE`:

1. Persist the business result and `DONE` status in the authoritative durable store.
2. Clean up the exact `jobId`/version from the ZSET per policy.
3. If Redis cleanup fails, the next poll sees `jobId` again, checks `DONE` in the DB, and skips it.
4. Periodic reconciliation sweeps stale index entries.

This prioritizes **never losing business state**, accepting candidate re-reads to finish index cleanup. It is much safer to operate than deleting broad score ranges and hoping no race occurred.

### 18.5. What if Redis is the sole data store?

When there is no DB/outbox/stream and the ZSET cannot be rebuilt, evaluate:

- Redis persistence/failover RPO/RTO.
- Atomic claiming and a processing store.
- Unique IDs and transaction ownership.
- Crash recovery, retries, and final failed states.
- Retention/eviction, memory pressure, backups/restores.

A polled store inbound adapter alone **does not satisfy all of these requirements**.

## 19. Endpoint lifecycle, Redis outages, and graceful shutdown

Store inbound is a **polling endpoint**, with lifecycle states:

~~~mermaid
flowchart TD
    S["Application startup"] --> E["Initialize Redis store source"]
    E --> P["Start poller"]
    P --> Q{"Redis available?"}
    Q -->|"Yes"| R["Receive RedisStore view"]
    R --> H["Query + business flow"]
    H --> P
    Q -->|"No"| ERR["Error / recovery strategy"]
    ERR --> P
    P -->|"Shutdown"| STOP["Stop scheduling polls"]
    STOP --> DRAIN["Finish / recover in-flight work"]
~~~

### 19.1. Auto-startup and phase

Spring Integration endpoints support start/stop lifecycle conventions. **`autoStartup`** and **`phase`** coordinate startup ordering across components.

However, a poller marked started **does not prove Redis is actually reachable**. Redis outages or bad ACLs may surface only on the first query. Readiness checks should verify Redis connectivity and actual operation health when required.

### 19.2. RedisConnectionFactory and client resources

`RedisConnectionFactory` creates connections per the Spring Data Redis client and configured topology. With Redis Cluster/Sentinel, test:

- Redis node reconnect/failover.
- Proper Redis key/slot routing.
- Client timeouts and retries so pollers do not block indefinitely.
- Shared hash slots for multi-key operations where required.
- Permissions across distinct ZSET/HASH namespaces.

**Never instantiate a new Redis client or connection per `RedisStore` view** inside a handler when the adapter/source already manages connections via `RedisTemplate`. Keep dependencies Spring-managed to avoid resource leaks.

### 19.3. Graceful shutdown

When stopping the application:

1. Stop polling/claiming new jobs.
2. Let active business handlers finish within a bounded timeout.
3. With leases, allow the scheduler/reclaimer to recover unfinished jobs upon restart.
4. Flush essential metrics/logs.
5. Close client resources via the Spring lifecycle.
6. After restart, reconcile expired `PROCESSING` leases and stale index entries.

**A clean stop does not prove every reminder was sent.** With claim state, inspect each job's actual status.

### 19.4. Poller crashes and transaction sync

If the process crashes:

- Before querying, the job remains in the ZSET for the next poll.
- After querying but before claiming, the job remains eligible and multiple workers may see it again.
- After claiming but before processing, lease/reclaimer recovers the job.
- After business commit but before cleanup, the index retains the member and creates a duplicate candidate.

Shutdown and restart correctness must therefore be tested across **all four windows**, not just a happy-path smoke test.

### 19.5. Scheduler clock drift

When scores represent `dueAt`, clock skew across nodes can trigger jobs early or late. Standardize on a consistent database/Redis/application clock policy, monitor clock skew, and allow for jitter within SLA. Never treat `fixedDelay(2000)` as a hard guarantee that jobs run within exactly 2 seconds of `dueAt`.

## 20. Security: Redis keys, SpEL, serializers, and business data

### 20.1. Redis ACLs and least privilege

A source that only reads a ZSET can be restricted to read permissions on that key. A claim service needs write permissions for `ZREM`/`ZADD` or Lua scripts per design. Separate roles:

| Actor | Conceptual least privilege |
| --- | --- |
| Reminder writer | Write ZSET members in permitted namespaces |
| Store observer | Read ZSET/metadata without deleting data |
| Claim service | Read and claim eligible jobs |
| Reclaimer | Inspect/transition processing state per lease |
| Operator | Investigate/replay per granted permissions, audited |

ACL syntax depends on Redis version and commands/scripts used. Never grant broad dangerous privileges to workers just to silence `NOAUTH`/`NOPERM` errors.

### 20.2. Key-expression is not an arbitrary Redis read API

If an application lets users pass arbitrary key names into SpEL/`key-expression`, they can force pollers to read **stores outside their tenant** or wrong data structures.

Enforce:

- Allowlists of permitted keys/namespaces.
- Tenant identity from authenticated sources.
- Never pass raw user-provided SpEL expressions into the Spring parser.
- Separate Redis users/instances when strong isolation is needed.

### 20.3. Redis ZSET members can carry malicious data

A producer-written **`jobId`** is not automatically trustworthy. Validate:

- ID length/format and schema version in business state.
- Job tenant/owner.
- `PENDING` status, `dueAt`, and current revision.
- Access permissions for recipient/template/destination.
- Rate limits to stop a producer from flooding millions of due jobs.

Never assume a member appearing in **`reminders:due`** authorizes the sender to email any tenant.

### 20.4. Avoid untrusted deserialization

When using `RedisTemplate` with a JDK serializer, understand the risks when other systems can write to Redis. Never enable broad polymorphic/trust-all deserialization on arbitrary objects.

Prefer **String IDs** in ZSETs and validated JSON/typed DTOs from the business source. For `MAP`/`PROPERTIES`, enforce clear serialization/schemas for complex values rather than letting a Redis hash execute arbitrary Java objects.

### 20.5. Paths and secrets

Never log raw payloads containing recipients, tokens, or user info; never embed Redis passwords in source code. Never pass a `RedisStore` live view or native Redis client inside HTTP message bodies, Kafka payloads, or serialization as if it were a DTO.

## 21. Monitoring: poll rate differs from business completion rate

A good dashboard distinguishes **polls**, **queries**, **candidates**, **claims**, and **business successes**.

| Signal | Meaning | What NOT to infer |
| --- | --- | --- |
| Poller executions | Trigger count | New job count |
| Source messages emitted | `RedisStore` views emitted | Processed member count |
| Redis query latency | Time for Redis range/size call | Email/provider delivery success |
| Due candidate count | Jobs due per query | Exclusively claimed jobs |
| Claim success/failure | Ownership outcomes | Business committed |
| Processing/in-flight count | Jobs currently running | Jobs `DONE` |
| Business completion rate | Finished jobs | Index cleanup succeeded |
| Cleanup failure | Stale ZSET post-commit | Business transaction rolled back |
| Lease expired/reclaimed | Jobs needing recovery | Previous worker skipped side effects |
| Duplicate skipped | Idempotency working | Producer never sent duplicates |

### 21.1. Illustrative metric naming

~~~text
redis_store_poller_executions_total{store="reminders-due"}
redis_store_source_emitted_total{store="reminders-due"}
redis_store_query_duration_seconds{store="reminders-due"}
reminder_due_candidates_total
reminder_claim_success_total
reminder_claim_conflict_total
reminder_completed_total
reminder_retry_exhausted_total{reason="PROVIDER_TIMEOUT"}
reminder_reclaimed_total
reminder_index_cleanup_failed_total
~~~

These are **instrumentation suggestions**, not all automatically emitted by the framework. In Micrometer/Observation, never use **`jobId`, `tenantId`, or `email`** as high-cardinality metric labels; keep those in protected logs/traces.

### 21.2. “Store size = 0” is not enough

If a handler claims immediately with `ZREM` and sends emails via an internal queue, the due ZSET may be empty while jobs sit in flight; if a worker crashes, those jobs can be lost without a processing store.

In a reliable job state model:

~~~text
Due ZSET count       = 0
Processing job count = 100
Business DONE count  = 0
~~~

Never display “all completed” based solely on `ZCARD` of the due ZSET.

### 21.3. SLA-based alerting

Key alert conditions:

- Oldest overdue job breaches SLA.
- Poller stops running or Redis queries fail repeatedly.
- Query duration spikes after ZSET cardinality grows.
- Unusual surge in claim conflicts from overlapping replicas.
- Growing backlog of expired `PROCESSING` leases.
- Retry-exhausted/`FAILED` jobs cross threshold.
- Rising cleanup failures (DB `DONE` while ZSET member remains).
- Redis memory/eviction/failover or ACL errors.

### 21.4. Logging a job safely

~~~text
endpoint=reminderStoreInbound
storeKeyAlias=reminders-due
collectionType=ZSET
jobId=reminder-1001
dueAtEpochMillis=1795402800000
claimState=ACQUIRED
jobStatus=PROCESSING
attempt=2
errorCategory=NONE
~~~

**Never log a full `RedisStore` object**—it is not an immutable DTO and may expose connection/context internals or invoke costly methods in debug formatting. Log key aliases, `jobId`, and validated state.

## 22. End-to-end test matrix with real Redis

Unit testing the business handler **does not prove** `RedisStoreMessageSource` creates the right view, evaluates `keyExpression` properly, fires the poller, or decodes values with the right serializer. Run integration tests against a real Redis server in an isolated environment.

| Test case | Setup | What to verify |
| --- | --- | --- |
| **Source emits view** | Valid poller and ZSET Redis key | Handler receives `RedisZSet`/`RedisStore` view, not a `String` `jobId` |
| **Empty store** | Nonexistent key or empty ZSET | Flow does not crash or report processed jobs |
| **Due range** | Add overdue and future jobs | `rangeByScore` returns only eligible candidates |
| **Live view vs snapshot** | Poll then producer adds member before query | Handler sees new change; test does not assume snapshot |
| **No destructive pop** | Poller receives view and handler only reads | ZSET member remains present after poll |
| **Repeated poll** | Leave due member uncleaned | Same candidate reappears across polls |
| **`maxMessagesPerPoll`** | Multiple members in ZSET | Single source message still yields multiple candidates |
| **Unsupported `CollectionType`** | Source `ZSET` but key holds String | `WRONGTYPE`/error observed |
| **Serializer mismatch** | Producer writes JDK bytes, source uses String serializer | Failure/garbled data detected |
| **SET view** | Source `CollectionType.SET` on Redis SET | Receives `RedisSet` view without assuming order |
| **MAP/PROPERTIES view** | Hash with fields | Reads expected fields/serializers and key |
| **Two poller replicas** | Both scan due ZSET | Read overlap occurs; claim service grants only one worker |
| **Claim race** | Two workers race on same `jobId` | Exactly one conditional claim succeeds |
| **Lua cross-slot** | ZSET keys in different hash slots in Cluster test | Cross-slot error detected, job not silently lost |
| **Crash before claim** | Kill handler after query, before claim | Job remains eligible for subsequent processing |
| **Crash after claim** | Kill after claim, before commit | Processing state persists; lease/reclaimer recovers |
| **Crash after commit** | Kill after external/DB commit before cleanup | Redis stale, yet idempotency prevents duplicate side effects |
| **Transaction sync success** | Synchronous business success | `afterCommit` callback runs per config |
| **Transaction sync failure** | Handler throws unhandled exception | Rollback/`afterCommit` behavior matches intent |
| **`ErrorChannel` swallow** | Error flow logs and returns | Error log not mistaken for business rollback |
| **Async handoff** | `ExecutorChannel` returns before business completes | Verify cleanup does not run prematurely |
| **Key-expression changes** | Change key config between polls | Source reads right key; no cross-tenant leak |
| **Redis restart** | Restart test Redis between polls | Connection recovery, metrics, state reconciliation |
| **Stop/start poller** | Stop endpoint then `ZADD` | On restart, source reads current store |
| **Poison member** | Invalid `jobId` format/status | Final failed state or alert, no hot loop |
| **Expired lease** | Worker runs longer than lease | Reclaim enforces fencing/idempotency; does not overwrite `DONE` |
| **Large ZSET** | Tens of thousands of members | Batch limits and stable latency; no unbounded materialization |
| **Security** | Redis user lacks permission or wrong tenant key | Clear error; no ACL bypass |
| **Wrong Redis topology** | Publisher/reader on different database indexes | Test catches store key/state mismatch |

### 22.1. Testing that a poll does not delete from the store

Isolated test sequence:

1. Create Redis ZSET **`test:reminders:due`** and add `job-1`.
2. Start Spring Integration flow with `RedisStoreMessageSource(CollectionType.ZSET)`.
3. Capture the first emitted Spring Message and assert payload is a **`RedisZSet` view**.
4. Call `rangeByScore` to read `job-1`.
5. Verify **`ZCARD`** is still 1 if the handler does not explicitly remove it.

This test distinguishes store inbound from destructive-`POP` Redis queue inbound.

### 22.2. Testing the poller with CountDownLatch

A test handler can use a latch to confirm the callback fired:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class RedisStoreCapturingSink {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<Object> payload =
        new AtomicReference<>();

    public void accept(Object view) {
        payload.set(view);
        latch.countDown();
    }

    public Object awaitView() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("RedisStore view not received");
        }
        return payload.get();
    }
}
~~~

**This helper is not a complete Spring context test.** Wire it into a test `IntegrationFlow`, start the poller, use an isolated test Redis, and ensure no duplicate pollers target the same key. Because the source can emit a view even with zero due members, **the latch only proves the poller invoked the handler**, not that a new job existed.

### 22.3. Testing transaction synchronization beyond counting callbacks

For post-commit cleanup callbacks, tests must verify:

1. The handler synchronously processes the exact set of job IDs.
2. The transaction context genuinely commits or rolls back as intended.
3. The callback executes in the right phase.
4. Redis state after the callback matches **only the processed IDs**.
5. A member added concurrently during processing **is not accidentally deleted**.
6. If `afterCommit` cleanup fails, the next poll **does not duplicate side effects**.

A test that merely asserts “`afterCommit` ran” does not prove Redis ZSET cleanup is safe under concurrent producers.

### 22.4. Testing the service without Redis

Unit tests for `ReminderHandler` can mock a **claimed `jobId`** and DB job state. Verify:

- Valid `PENDING` → `PROCESSING` → `DONE`.
- Unsupported schema/tenant → rejected.
- `DONE` `jobId` → side effect skipped.
- Provider timeout → `UNKNOWN` or retry per contract.
- Stale version/wrong owner → state not overwritten.
- Two workers conditionally claiming the same ID → only one succeeds.

Separating domain unit tests from Redis store polling exposes business bugs without depending on scheduler timing.

### 22.5. Never test against production Redis

Never run `DEL`/`FLUSHDB`, force `WRONGTYPE`, alter ACLs, or restart Redis serving live traffic. Use dedicated test namespaces/instances, least-privilege credentials, and controlled test cleanup.

## 23. Other collection types: LIST, SET, MAP, and PROPERTIES

Although ZSET is the primary example here, the **Redis store inbound adapter does not only read Sorted Sets**.

### 23.1. LIST: inspecting the collection, not BRPOP

~~~text
Redis LIST: import:{catalog}:candidates
  [file-1, file-2, file-3]

Poller -> RedisList view
Handler -> inspect collection / pick eligible items
~~~

If a handler iterates all items via a list view, the next poll will read the same items again. **There is no built-in consumer acknowledgment.** To consume FIFO work via destructive pop, use Redis queue inbound; for crash protection, consider Redis Streams or a processing-list contract.

### 23.2. SET: set of IDs to reconcile

~~~text
Redis SET: catalog:{refresh}:stale-product-ids
  {P-1, P-2, P-3}
~~~

A handler can read IDs to reconcile against a database. However, **Sets guarantee no iteration order**, and multiple pollers can pick the same `productId`. When removing members after a refresh, guard against racing with a producer re-marking the same ID stale during the refresh.

### 23.3. MAP: state lookup

~~~text
Redis HASH: catalog:{config}:flags
  newSearch = true
  resultLimit = 100
~~~

A `MAP` view can support scheduled configuration checks. However, a handler iterating fields while a producer updates them may observe mixed state; if a **consistent multi-field snapshot** is needed, design explicit versioning/atomic writes or read a versioned structure.

### 23.4. PROPERTIES: simple properties

`PROPERTIES` is a collection view type supported by Spring Data Redis; it can be used for simple application-managed properties. It **is not equivalent to a Java `application.properties` file** that hot-reloads Spring beans whenever Redis changes.

For runtime configuration updates, enforce ownership rules, schema/defaults, validation, and consistency—never mutate Spring bean config implicitly by polling a Redis store.

### 23.5. Each store type needs a distinct query/removal contract

| Store | Application query | Risk of improper cleanup |
| --- | --- | --- |
| `LIST` | View/iteration/index | Deleting wrong index under concurrent push/pop |
| `SET` | Membership/iteration | Deleting a member just re-flagged by producer |
| `ZSET` | Range by score/rank | Deleting entire range containing unprocessed jobs |
| `MAP` | Field get/entries | Overwriting/deleting a field just updated |
| `PROPERTIES` | Property lookup | Losing config or racing with writer |

Do not copy **`removeByScore`** from `ZSET` onto `SET`/`MAP`/`LIST` assuming all collections share the same API or guarantees.

## 24. Troubleshooting: poller runs yet data isn't processed properly

When a Redis store inbound flow produces no business output, trace **boundary by boundary** instead of randomly tweaking intervals:

~~~mermaid
flowchart TD
    A["Poller trigger"] --> B{"Source received view?"}
    B -->|"No"| E1["Endpoint/lifecycle/config"]
    B -->|"Yes"| C{"Right key/type/serializer?"}
    C -->|"No"| E2["Redis WRONGTYPE / RedisTemplate"]
    C -->|"Yes"| D{"Query returned candidates?"}
    D -->|"No"| E3["Score/cutoff/clock or empty store"]
    D -->|"Yes"| E{"Claim succeeded?"}
    E -->|"No"| E4["Replica conflict / stale state"]
    E -->|"Yes"| F{"Business success?"}
    F -->|"No"| E5["Provider/DB/validation"]
    F -->|"Yes"| G["DONE + cleanup/reconcile"]
~~~

### 24.1. Poller logs steadily, yet handler sees no jobs

The source may be emitting views, while:

- ZSET scores lie **in the future**.
- Worker compares **seconds** while producer wrote **milliseconds**.
- Redis key points to the wrong environment/database.
- Handler type mismatch—reading `RedisList` instead of `RedisZSet`.
- Serializer mismatch on members.
- Business filter skips `DONE`/`CANCELLED` jobs.
- Client clock skew or `dueAt` hasn't truly arrived yet.

**Increasing `maxMessagesPerPoll` will not fix a handler querying the wrong score range.**

### 24.2. Handler re-runs the same IDs every two seconds

This is expected behavior when:

- `rangeByScore` only reads.
- Members were never removed/marked `DONE`.
- Redis cleanup failed.
- Two pollers read the same ZSET.
- The source emits a `RedisStore` view on every poll.

The fix is **idempotency, claiming, checkpointing, and conditional cleanup**, not swapping `fixedDelay` for `fixedRate`.

### 24.3. Hitting WRONGTYPE

For instance, the source configures `CollectionType.ZSET` while the real key was overwritten with a Redis String via `SET`:

~~~bash
redis-cli TYPE reminders:{notify}:due
~~~

Running `TYPE` in an authorized environment identifies the actual Redis structure. Never `DEL` a production key just to silence `WRONGTYPE`; it may hold another service's critical data. Fix the key namespace/producer or run a proper migration.

### 24.4. Handler receives an object other than RedisZSet

Check:

- Which `CollectionType` is configured?
- Which endpoint is actually sending to the input channel?
- Are multiple sources feeding the same channel?
- Is a transformer altering the payload before the handler?
- Which Spring Data Redis/Integration version is active?

Avoid unchecked casts or swallowing `ClassCastException`. Payload types are part of your integration contract.

### 24.5. Cleanup runs but drops jobs

Deleting **range `0..now`** after processing a small batch can erase **unprocessed** jobs sharing similar scores. That is a data-loss bug, not a scheduling bug. Stop unsafe range cleanup, reconcile against the database, and switch to **removing only committed job IDs**.

### 24.6. Store is empty while receive metrics keep climbing

The source can emit views even when the key has zero members. Never report **source receive count** as job count. Track due candidates, claim successes, business successes, and cleanups instead.

### 24.7. Slow poller

Inspect Redis query latency, member count, response materialization, handler latency, executor saturation, transaction callbacks, and scheduler pool sizing. Do not lower the poll interval to 100ms when each query takes 2 seconds and downstream lacks capacity.

### 24.8. Redis connection UNKNOWN result

If a claim/delete command fails due to a network drop around the response, the application cannot tell whether Redis executed it. **Do not assume failure means not executed.** Inspect state by `jobId`/owner/version and retry idempotently per policy.

## 25. Real-world architectural scenarios

### 25.1. Case A – Reminder due index backed by an authoritative database

An appointment notification system:

~~~mermaid
flowchart LR
    API["Create reminder API"] --> DB[("Reminder DB")]
    DB --> IDX["ZSET due index"]
    IDX --> POLL["Redis store inbound<br/>poller"]
    POLL --> CL["Conditional DB claim"]
    CL --> SEND["Reminder provider"]
    SEND --> DONE["Mark DONE / cleanup"]
    DB --> REC["Reconciliation job"]
    REC --> IDX
~~~

**Suitable** when:

- DB is the source of truth.
- ZSET serves as an index accelerating candidate selection.
- Claiming uses conditional DB updates/owner leases.
- Provider supports idempotency or status reconciliation.
- If the index is lost, reconciliation rebuilds it from DB.

**Unsuitable** if the team assumes the poller alone guarantees each reminder fires once without claiming/leases/checkpointing.

### 25.2. Case B – Scanning a Redis SET of products needing refresh

A catalog service maintains a `SET` of `productId`s to reconcile:

~~~text
Redis SET catalog:{refresh}:stale
    -> Redis store inbound poller (CollectionType.SET)
    -> Read IDs
    -> Validate current productVersion from DB
    -> Refresh search index
    -> Conditional cleanup / reconciliation
~~~

Risk: while the handler refreshes **`P-1001`**, a producer may mark `P-1001` stale again. Unconditionally removing the member afterward drops the newer signal. One improvement is storing **versions/tokens** rather than bare SET members, or using durable task records.

### 25.3. Case C – Dynamic configuration from a Redis MAP

An application checks flags stored in a Redis Hash:

~~~text
Redis HASH config:search:flags
    -> CollectionType.MAP
    -> Poller
    -> Validate schema/tenant
    -> Compare with last applied version
    -> Apply safe runtime configuration
~~~

Do not blindly load arbitrary fields as Spring bean settings or let any Redis writer alter runtime security configuration. Enforce **versioning, allowlists, consistent state**, and rollback policies.

### 25.4. Case D – SFTP import → Redis ZSET reconciliation

A file inbound adapter syncs CSVs from SFTP; a parser writes job IDs and due scores:

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter<br/>poller"] --> PAR["CSV parser"]
    PAR --> DB[("Import DB + outbox")]
    DB --> Z["Redis ZSET<br/>due index"]
    Z --> SI["Redis store inbound<br/>poller"]
    SI --> V["Claim / validate"]
    V --> H["Row business handler"]
    H --> DB
~~~

**Two pollers serve two different sources:** the SFTP poller finds new files; the Redis store poller inspects the current collection/index. Do not mark the import complete solely because Redis `ZADD` succeeded; track row-level state and downstream outcomes.

### 25.5. Case E – Redis ZSET → Kafka/AMQP

If a handler scans a ZSET and publishes each member to Kafka or RabbitMQ:

~~~text
Redis store inbound -> select candidates
    -> claim
    -> Kafka/AMQP outbound adapter
    -> target broker confirm/ACK publish
    -> mark dispatched + cleanup
~~~

Failure windows:

- Claim succeeds then publish fails → needs retry.
- Publish succeeds yet response is `UNKNOWN` → retry can duplicate.
- Marked dispatched before broker confirmation → potential event loss.
- Broad score-range cleanup when only part of the batch published → drops remaining jobs.

You need stable `eventId`s, broker-specific confirms/returns/producer ACKs, durable state, and idempotent consumers. **`MessageChannel.send` success does not prove Kafka/RabbitMQ persisted the message or downstream consumers processed it.**

### 25.6. Case F – Periodic dashboard/cache checks

If the goal is simply **reading member counts and alerting**, Redis store inbound is a great fit:

~~~text
Poller -> RedisStore view -> read size/status -> alert if threshold
~~~

Do not over-engineer a read-only flow with complex retry/ACK machinery. Define view/query cost, cadence, metric cardinality, and read-only Redis access. This use case leverages the true **collection observation** nature of store inbound.

## 26. Common misconceptions

**“Redis store inbound is just Redis queue inbound renamed.”** No. Store inbound is a **polling source emitting a `RedisStore` view**; queue inbound is a message-driven endpoint typically popping individual items from a Redis List.

**“Choosing `CollectionType.LIST` fetches one List item per poll.”** Not by default. A List view is returned; reading or removing elements is up to the handler.

**“Store inbound uses Redis `PUBLISH`/`SUBSCRIBE`.”** No. Pub/Sub inbound is a separate adapter receiving channel/pattern notifications.

**“No Spring Integration Poller is needed because Redis already holds data.”** `RedisStoreMessageSource` is a polled `MessageSource`; it needs a poller or an active caller invoking `receive()`.

**“One poll = one job.”** One message containing a `RedisStore` view can yield many members or zero candidates.

**“`maxMessagesPerPoll(1)` limits to one Redis ZSET member.”** It limits messages received from the `MessageSource`, not elements queried from the view.

**“`RedisStore` is an immutable snapshot.”** The view can access live Redis data when handler methods run, after producers have mutated the store.

**“Putting `RedisStore` views into a `QueueChannel` creates event history.”** Buffered views can still point to the same Redis key; buffering does not create per-poll snapshots.

**“A ZSET pushes messages to handlers when `dueAt` arrives.”** ZSETs emit no score-based notifications; a poller or scheduler must query.

**“`rangeByScore` claims jobs.”** It only reads candidates; multiple workers can read identical IDs.

**“`ZREM` after side effects prevents all duplicates.”** Two workers can execute side effects before one succeeds in deleting.

**“`ZPOPMIN` only pops due jobs.”** `ZPOPMIN` pops the lowest-score member even if its score is in the future.

**“Deleting a ZSET score range after commit is always safe.”** That range can include newly added or failed members.

**“`afterCommit` cleanup is an atomic transaction with Redis.”** Callbacks synchronize timing; they do not make Redis and the database a distributed transaction.

**“`PseudoTransactionManager` records durable transactions.”** It enables transaction synchronization callbacks when no real transaction manager exists; it does not protect Redis or external APIs.

**“Enabling `@Transactional` automatically rolls back Redis `ZREM` on JDBC rollback.”** No, unless an explicit compatible transaction mechanism is wired; never assume a JDBC transaction spans Redis operations.

**“`ExecutorChannel` preserves `afterCommit` timing.”** An async handler may still be running after the poller callback/transaction finishes.

**“Spring `MessageHeaders.ID` is the business `jobId`.”** Spring's message ID can change whenever a Message is recreated. `jobId`/`eventId` needs a stable contract.

**“ZSET score is an ACK status.”** Scores are just numeric values per contract; `dueAt`/priority provides no ACK.

**“`SET`/`MAP`/`PROPERTIES` share the same score-removal API as `ZSET`.”** Redis collections have different operations and semantics.

**“Seeing a `RedisStore` view means Redis data was serialized into a Java DTO.”** The view is a store handle; the handler must query/convert data.

**“When the store is empty, the adapter definitely won't emit a message.”** The source may still emit a `RedisStore` view; test real behavior and count candidates for business metrics.

**“`RedisConnectionFactory` and `RedisTemplate` always share the same serializer.”** Source construction determines the default template; custom templates may differ from producers.

**“Setting both `redis-template` and `connection-factory` on the same source is harmless.”** Never mix them when the API defines them as mutually exclusive.

**“`key-expression` can come freely from user input.”** That risks reading wrong keys/tenants or introducing unsafe expressions.

**“`CollectionType.ZSET` automatically converts a Redis String key into a ZSET.”** Operations against the wrong structure return `WRONGTYPE`; migrations must be deliberate.

**“Three replicas scanning the same store divide members exclusively.”** Each replica gets a view of the same key and reads the same candidates; claiming/locking/idempotency is required.

**“Using a Lua script means email side effects commit with Redis.”** Lua is atomic on the target Redis shard, not across SMTP/HTTP/JDBC.

**“Lease expiration proves the old worker stopped.”** The old worker may keep running; use fencing/idempotency when reclaiming.

**“Moving a job to processing means it succeeded.”** `PROCESSING` is only the claim state; `DONE` must be confirmed after the business outcome.

**“Redis Cluster multi-key operations always work across any slots.”** Cross-slot commands require matching hash slots, e.g., via shared hash tags.

**“Counting polls is enough to report completed jobs.”** Poll counts, candidate counts, claim counts, and business successes must be tracked separately.

**“Adding more pollers speeds up processing regardless of downstream.”** It can merely increase query load, claim conflicts, duplicates, and transaction races.

**“Passing happy-path tests proves at-least-once.”** You need fault injection at query, claim, commit, cleanup, lease expiry, and failover boundaries.

**“Redis Streams are equivalent to a scored ZSET.”** Streams have record IDs, pending lists/consumer groups/ACKs; ZSETs lack those semantics out of the box.

## 27. Production design checklist

| Category | Questions to answer |
| --- | --- |
| **Right endpoint?** | Do you want to poll a collection view, pop List items, or receive Pub/Sub notifications? |
| **CollectionType** | `LIST`, `SET`, `ZSET`, `PROPERTIES`, or `MAP`? Does the Redis key have the right type? |
| **Key** | Literal or `key-expression`? Who is allowed to pick the key? |
| **Serializer** | Do key/value/hash serializers match between source and producer? |
| **Source payload** | Does the handler expect a `RedisStore` view or mistakenly an item DTO? |
| **Poller** | `fixedDelay`/`fixedRate`, `maxMessagesPerPoll`, scheduler pool, clock drift? |
| **Snapshot semantics** | Need live state, materialized IDs, or a claimed batch? |
| **Query** | Are `rangeByScore` cutoffs/limits exact? Are scores seconds or milliseconds? |
| **Claim** | How do two replicas avoid processing the same job? |
| **Transaction** | What boundaries separate DB transactions and Redis cleanup? |
| **Synchronization** | Do `afterCommit`/`afterRollback` behave per handler outcome? |
| **Cleanup** | Deleting only committed IDs or sweeping a range that may contain other jobs? |
| **Idempotency** | Unique `jobId`/business key, provider idempotency, `DONE` state? |
| **Retry** | How do in-process attempts differ from durable attempts? |
| **Lease/reclaim** | Who reclaims stuck `PROCESSING` jobs, with fencing/heartbeats? |
| **Poison jobs** | Where do permanent failures go, who owns them, and how are retention/audits handled? |
| **Concurrency** | How many copies of pollers/handlers/executors are running? |
| **Redis HA** | Do AOF/RDB/replication/failover meet RPO/RTO? |
| **Redis Cluster** | Do multi-key Lua/commands share the same hash slot? |
| **Security** | ACLs, TLS, key namespaces, tenant checks, SpEL inputs? |
| **Capacity** | ZSET size, query latency, memory limits, batch size, poll interval? |
| **Observability** | Separate polls, candidates, claims, `DONE`, cleanups, lease expirations? |
| **Testing** | Real Redis, live view, repeated polls, crash windows, and unknown outcomes? |
| **Fallback** | If Redis index is lost/stale, is there a source of truth to reconcile? |
| **API version** | Have Java DSL/annotations/transaction synchronization compiled against the current BOM? |

### 27.1. Quick decision rule

**Redis store inbound** fits when:

- You want to **inspect a Redis collection on a schedule**, without needing per-change notifications.
- There is a clear contract for collection type, queries, and elements.
- Idempotency/checkpointing is in place whenever executing side effects.
- An authoritative source/recovery path exists for high-assurance data.

**Redis queue inbound** fits when **popping individual List items**, understanding the post-pop loss window. **Redis Pub/Sub inbound** serves best-effort notifications to online subscribers. **Redis Streams** fits better when you need an event log, pending entries, and replay with consumer groups.

### 27.2. Do not add transaction synchronization if only observing

If the sole goal is observing a ZSET/SET and emitting metrics, keep the flow simple and **read-only**. Transaction synchronization helps coordinate outcome callbacks, but add it only when you clearly know:

- Which real transaction exists.
- Which payload/resources callbacks touch.
- Which Redis mutations callbacks run.
- How recovery works if a post-commit callback fails.

### 27.3. Reliability progression path

~~~text
Stage 1:
  Poll RedisStore view -> query -> observe/reconcile

Stage 2:
  Poll -> query bounded candidates -> idempotent handler
       -> mark DONE -> clean up by ID

Stage 3:
  Poll -> atomic claim -> durable processing state
       -> lease/reclaim -> retries -> final failed state
       -> fencing/idempotency -> audit/monitoring

Stage 4:
  Evaluate whether Redis Streams / AMQP / Kafka / DB job table
  fits better than maintaining custom claim and cleanup protocols.
~~~

Never jump straight to custom Lua/lease machinery for a read-only dashboard; equally, never leave a read-only `rangeByScore` in place as if it provided message delivery guarantees for payments.

## 28. Self-check questions

1. How is the Redis store inbound channel adapter triggered? Why is a Spring Integration Poller required?
2. Does `RedisStoreMessageSource` return **one Redis member** or **a `RedisStore` view**? How does this difference affect the business handler?
3. How does Redis store inbound differ from message-driven Redis queue inbound?
4. How does Redis store inbound differ from Redis Pub/Sub inbound in data source and trigger timing?
5. Name the five supported `CollectionType` values and one use case for each.
6. Does a Redis List view automatically `BRPOP` an item and ACK it for the handler?
7. Why is `RedisZSet.rangeByScore` not considered a job claim command?
8. Should a ZSET member with score greater than `nowEpochMillis` be processed immediately when using scores as `dueAt`?
9. Does `ZPOPMIN` guarantee popping only due members? If not, what condition must be added?
10. Why does each poller execution not necessarily correspond to one new job?
11. Does `maxMessagesPerPoll(1)` cap how many members a handler reads from a `RedisStore` view?
12. How does a `RedisStore` view differ from an immutable snapshot of a Redis collection?
13. If a `QueueChannel` holds three `RedisStore` views of the same key, do they become three independent snapshot versions?
14. Can two pollers calling `rangeByScore` see the same `jobId`? How do you guarantee only one worker claims it?
15. In Java DSL, is `CollectionType.ZSET` configured on the source or on the handler?
16. Can `RedisStoreMessageSource` be declared with `@InboundChannelAdapter` and `@Poller` instead of Java DSL?
17. Why shouldn't two pollers run simultaneously on the same key in a lab measuring a single business handler?
18. What is the difference between a literal key and a `key-expression`? Why do dynamic keys need tenancy control?
19. How do `RedisConnectionFactory` and `RedisTemplate` differ in responsibilities and serializers?
20. If the default source uses `StringRedisTemplate` while the producer writes JDK-serialized members, what risks arise?
21. What does `WRONGTYPE` mean when the source configures `ZSET` yet the Redis key holds a String?
22. Should `MAP`/`PROPERTIES` use the same `removeByScore` as `ZSET`? Why or why not?
23. Does a Redis `SET` guarantee member iteration order? What is a cleanup race when a producer re-adds the same ID?
24. If ZSET scores are Unix epoch milliseconds, how must local times be converted to avoid firing early or late?
25. Should a due reminder that is `CANCELLED` in the database still be sent?
26. If a handler only calls `rangeByScore` and logs, will the same `jobId` reappear in subsequent polls?
27. What support does `PseudoTransactionManager` provide, and what atomicity guarantees does it lack?
28. Which callback phases can `TransactionSynchronizationFactory` orchestrate?
29. Why does an `afterCommit` expression deleting an entire score range risk dropping unprocessed or newly added jobs?
30. If a handler uses `ExecutorChannel`, can `afterCommit` run before the async worker completes?
31. Do Redis `MULTI`/`EXEC` or Lua commit an email provider/JDBC inside the same transaction?
32. If a job is `DONE` in the database yet `afterCommit` Redis cleanup fails, how should the next poll handle it?
33. Which status/version conditions must a conditional DB claim update check to prevent races?
34. When multiple workers share a due ZSET, when are owner/lease/fencing tokens needed?
35. Does lease expiration prove the previous worker completely stopped?
36. How must a target system check a fencing token for it to be effective?
37. When ZSET is only a due index, where should the source of truth live and how is a lost Redis index rebuilt?
38. If Redis is the sole data store and fails over, what RPO/RTO and persistence requirements must be evaluated?
39. When using a two-key Lua claim script in Redis Cluster, what hash slot requirement must the keys meet?
40. Why is storing short `jobId` members safer and easier than storing full emails/PII inside ZSET members?
41. In an SFTP import → ZSET workflow, why can't you mark the import complete solely because Redis `ZADD` succeeded?
42. When bridging Redis ZSET → Kafka/AMQP, how do you distinguish broker publish results from downstream consumer completion?
43. Which metrics must be kept separate: poll count, candidate count, claim success, business `DONE`, and cleanup failure?
44. Does unit testing the handler prove `RedisStoreMessageSource` was polled with the right key/type?
45. What integration test proves Redis store inbound **does not auto-delete members**?
46. Why must you test crashes after claim before commit, and after commit before cleanup?
47. If after a deploy `due candidate count` rises while `job success` stays at 0, in what order do you investigate?
48. How should Redis permissions be configured for a read-only store inbound?
49. When should you switch from ZSET + custom claiming to a Redis Streams consumer group or an ACK-capable broker?
50. Sketch a minimal flow using `RedisStoreMessageSource` to **observe only** a ZSET without causing side effects.

## 29. References and version scope

Consult the **Spring Integration Redis Support** documentation and Spring Data Redis Javadocs before adopting code in production:

- [Spring Integration – Redis Support, Redis Store Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/redis.html): Java DSL, Java annotations, XML, `CollectionType`, default serializers, and transaction synchronization.
- [Spring Integration – RedisStoreMessageSource API](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/redis/inbound/RedisStoreMessageSource.html): source returning `RedisStore` view, constructors taking `RedisConnectionFactory` or `RedisTemplate`, `keyExpression`.
- [Spring Data Redis – RedisStore interface](https://docs.spring.io/spring-data/redis/docs/3.5.x/api/org/springframework/data/redis/support/collections/RedisStore.html): abstraction for Redis-backed collection views.
- [Spring Data Redis – RedisZSet API](https://docs.spring.io/spring-data/redis/docs/3.5.x/api/org/springframework/data/redis/support/collections/RedisZSet.html): `rangeByScore`, `removeByScore`, and ZSET operations.

Examples using `RedisStoreMessageSource`, `Redis.storeInboundChannelAdapter`, `Pollers`, and `PseudoTransactionManager` follow **the API model described in the corresponding documentation**. In practice, verify the Spring Boot–Spring Integration–Spring Data Redis BOM/versions, compile, and run integration tests against real Redis. This lesson is conceptual and practical reference material and **does not claim to have executed a build or project-specific Content QA**.

## Summary

The **Redis store inbound adapter** is a **polled inbound channel adapter**: a Spring Integration Poller triggers `RedisStoreMessageSource`, the source returns a **Spring Message containing a `RedisStore` view** bound to a Redis key, and `MessageChannel` delivers that view to transformers/routers/service activators. It supports collection types **LIST, SET, ZSET, PROPERTIES, and MAP**. The vital distinction is that **a store view does not mean a popped item, an immutable snapshot, or an ACKed job**.

In the **due-reminder ZSET** example, the poller periodically emits a view; the handler calls `rangeByScore` to find time-based **candidates**. **Querying, claiming, business processing, marking `DONE`, and Redis cleanup** are distinct actions. When multiple replicas scan concurrently, enforce atomic claiming/conditional DB updates, idempotency, and leases/fencing for long-running work; otherwise the same member will be processed repeatedly. **`maxMessagesPerPoll`** bounds only source receives, not Redis collection member counts.

**Transaction synchronization** lets you attach callbacks to `beforeCommit`/`afterCommit`/`afterRollback`, yet does not turn Redis + JDBC + external services into a distributed transaction. Deleting **an entire score range** after commit risks losing jobs under concurrent producers or partial batch failures. Production designs should clean up by **confirmed `jobId`/version**, maintain durable state/reconciliation, and test crashes, restarts, and races.

When integrating Redis alongside File, SFTP, HTTP, JMS, AMQP, Kafka, and databases in **SPRING_INTEGRATION_ADAPTERS**, always separate **source polled**, **candidate read**, **ownership claimed**, **result durably persisted**, and **business side effect completed**. Choose Redis store inbound for **scheduled collection observation/querying**; when you need message logs, consumer groups, pending records, or broker acknowledgments, consider Redis Streams or a more suitable durable messaging system.
