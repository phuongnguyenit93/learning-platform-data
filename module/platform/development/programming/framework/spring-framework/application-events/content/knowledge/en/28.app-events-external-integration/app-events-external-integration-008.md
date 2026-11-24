# Broker-Level Retries: Kafka, RabbitMQ, and Spring Application Events

When a Spring application emits an event for another system to handle, failures can occur such as dropped connections, temporary consumer downtime, downstream HTTP `503` responses, database deadlocks, or invalid message data. **Broker-level retries** use the **message broker infrastructure and consumer container** to re-execute **message delivery/consumption** under controlled rules, rather than keeping a retry loop inside the thread handling the request.

Within the **Spring Framework Application Events** topic, you must distinguish right from the start:

- `ApplicationEventPublisher.publishEvent(...)` and `@EventListener` are mechanisms for **application events inside the Spring ApplicationContext**, typically within a single JVM. **This Spring event bus has no built-in retry topics, dead-letter queues (DLQs), offsets, acknowledgments, or durable storage.**
- `@KafkaListener` in **Spring for Apache Kafka** and `@RabbitListener` in **Spring AMQP** receive messages via a **broker**. Retries are governed by containers, error handlers, acknowledgments, retry topics/queues, broker policies, and/or application-level recovery.
- To bridge from an in-transaction domain event to Kafka/RabbitMQ without dropping messages when the process crashes, you typically need a dedicated **Transactional Outbox** or a delivery mechanism with equivalent guarantees.

Lesson objectives: understand **bounded retries** at the broker, distinguish **blocking** vs. **non-blocking retries**, use Spring Kafka `@RetryableTopic`/DLT and Spring AMQP DLX/TTL, design idempotency, handle poison messages, calculate backoff, monitor backlogs, and test both success and failure paths.

## 1. Why are in-JVM retries insufficient for external integration?

Suppose an order has committed and the application wants to notify the invoicing service:

```text
HTTP request
    |
    +-- OrderService: UPDATE order; COMMIT
    |
    +-- publishEvent(OrderApproved)
            |
            +-- @EventListener
                    |
                    +-- call invoicing API
                         +-- failed -> retry 3 times in RAM
```

If the error lasts only one second and the process stays alive, a local retry may help. However, if the application dies right after commit or while waiting for the next attempt, **there is no guaranteed durable message remaining** for another consumer to pick up. `@TransactionalEventListener(AFTER_COMMIT)` does not create a message persistence mechanism either.

Broker architecture:

```text
OrderService
     |
     +-- COMMIT business data + outbox row (if atomicity is required)
                |
                v
       Outbox publisher / producer
                |
                v
          Kafka / RabbitMQ
                |
                +-- durable topic / queue
                |
                v
            Consumer
                |
                +-- success -> acknowledge/advance offset
                |
                +-- transient failure
                |      -> retry with backoff/bounds
                |
                +-- permanent failure / attempts exhausted
                       -> DLT/DLQ/quarantine
```

**Broker retries do not mean exactly-once side effects.** A consumer can finish updating its database and crash before acking/committing the offset, causing **redelivery**. Therefore, business handlers need to be **idempotent** or use an appropriate inbox/deduplication mechanism.

### Core terminology

| Term | Meaning |
| --- | --- |
| **Message / record** | Data placed into a topic/queue; typically has key, headers, payload, metadata |
| **Delivery attempt** | One instance of a consumer receiving and attempting to process a message |
| **Ack / Nack / Reject** | Consumer/broker signal on delivery or processing outcome; semantics vary by protocol |
| **Kafka offset** | Record position within a topic partition; committed offsets track consumer group progress |
| **Requeue** | Returning a RabbitMQ message to the queue to be redelivered |
| **Retry topic/queue** | Temporary destination storing failed messages for scheduled/backoff reprocessing |
| **DLT / DLQ** | Dead Letter Topic / Dead Letter Queue: destination for messages unprocessable under the current policy |
| **Poison message** | A message that repeatedly fails consumers due to payload/schema/logic errors that waiting cannot fix |
| **Idempotency key** | Stable identifier for a logical operation/event across multiple attempts |
| **Backoff / jitter** | Delay interval and random variance to prevent retry storms |

A record has “reached the broker” only when there is **publish confirmation evidence** per producer config. Calling `KafkaTemplate.send(...)` without observing completion/errors is insufficient to conclude the broker stored the record successfully.

## 2. Choosing a retry tier: blocking or non-blocking?

### 2.1. Blocking retry

**Blocking retry** holds the consumer/partition on the failing record until attempts are exhausted (or recovery runs). In Spring Kafka, `DefaultErrorHandler` with a `BackOff` is a typical choice.

```text
Kafka topic / partition P0:
    record A -> attempt 1 fail
               wait 1 s
               attempt 2 fail
               wait 1 s
               attempt 3 success
    record B -> processed only afterward per container strategy
```

Advantages:

- Usually easier to preserve processing order on the same partition since records are not moved to another topic.
- No need to design/deploy multiple retry topics.
- Suits short outages, small attempt counts, and strict ordering requirements.

Disadvantages:

- A failing record can cause **head-of-line blocking**, lowering partition/consumer throughput.
- Long backoffs can interact with `max.poll.interval.ms` and assignment/rebalances; use appropriate container pausing mechanisms for longer waits.
- Poison messages cause stalls if configured with infinite retries.

Do not interpret “blocking” as the Kafka broker itself sleeping for 1 second. Here the consumer’s error handler/listener container **coordinates redelivery** and backoff; the broker remains the topic store.

### 2.2. Non-blocking retry via retry topics

Spring Kafka provides `@RetryableTopic` to support a **non-blocking retry topology**:

```text
notifications.commands  (main topic)
      |
      +-- success -> done
      |
      +-- failure -> notifications.commands-retry-1000
                          |
                          +-- due time -> consumer retry
                          |
                          +-- failure -> notifications.commands-retry-2000
                                              |
                                              +-- due time -> consumer retry
                                              |
                                              +-- failure/budget exhausted
                                                     -> notifications.commands-dlt
```

Topic names are **illustrative examples**: actual suffixes depend on policy, backoff intervals, and version/configuration; do not hardcode framework-generated names into business logic without verification.

Benefit: the main consumer can move on to other records while the failing record is routed to a retry topic. Trade-offs:

- **No strict global ordering guarantee** between retried record A and a subsequent record B with the same key succeeding on the main topic first.
- Must operate additional topics/consumers, retention, partitions, storage, and metrics.
- Forwarding to retry/DLT and committing offsets have failure boundaries; you must understand acknowledgments, confirms, and recovery.
- Delays based on due timestamps/topic consumers have **bounded precision**, not a hard real-time deadline.

**Important limitation of Spring Kafka 3.3:** non-blocking retries **do not support batch listeners** and **cannot be combined with Kafka container transactions**. Do not apply `@RetryableTopic` blindly to pipelines already using those modes. For workloads requiring strict ordering, consider short blocking retries, aggregate-level workflows, or dedicated partition/sequence strategies.

### 2.3. Quick comparison

| Property | Blocking consumer retry | Retry topic/queue |
| --- | --- | --- |
| Where it waits | Consumer/container, optionally pausing polls | Message moves to separate waiting infrastructure |
| Main pipeline | Can be blocked by failing records | Can continue processing other records |
| Ordering | Easier to preserve per partition | Processing order can invert |
| Number of topics/queues | Fewer | Usually increases |
| Long retries (minutes/hours) | Not ideal if holding the consumer | Usually better suited |
| Durable across restarts | Depends on broker offset/ack and recovery | Broker retains retry messages if configured properly |
| Exhaustion handling | Recoverer/DLT/DLQ | DLT/DLQ and remediation workflow |
| Idempotency | Still needed | **Still needed** |

## 3. Designing a retry policy: which errors, how many times, how long to wait?

Before picking an annotation or broker policy, answer:

1. **Transient or permanent?** Timeouts, 503s, and temporary DB unavailability can be retried. Invalid schemas, permanent business rule violations, and missing permissions normally should not.
2. **Does max attempts include the initial try?** For example, **3 attempts** = initial try + **2 retries**. Never use ambiguous phrasing like “retry three times”.
3. **Backoff and jitter:** 1 s, 2 s, 4 s or capped exponential; add jitter when many consumers hit an outage simultaneously.
4. **Per-attempt timeout** and **overall event deadline**: a network call without a timeout can hang a consumer indefinitely.
5. **Where do final failures go?** DLT/DLQ, terminal state, alerts, replay procedure.
6. **Who is authorized to replay?** Never automatically push poison messages back onto the main topic infinitely.
7. **Can duplicate processing occur?** Downstream side effects must be idempotent.
8. **Is ordering by `orderId` required?** If so, retry topics can break sequence.

Example of **3 attempts** with 1 s and 2 s backoffs:

```text
attempt 1 (main topic) -> fail
wait about 1 s
attempt 2 (retry topic) -> fail
wait about 2 s
attempt 3 (retry topic) -> success OR DLT
```

Wait intervals are configuration targets, not strict empirical SLAs. Total processing time also includes queue lag, consumer startup, rebalances, networking, and each attempt’s execution time.

### Avoid retrying the wrong errors

Suggested table, to be tailored per downstream contract:

| Scenario | Policy |
| --- | --- |
| HTTP 503, temporary connection reset | Retry with backoff/timeout |
| HTTP 429 | Retry honoring `Retry-After` and bounds; do not retry immediately |
| Invalid deserialization/JSON | Usually DLT/quarantine early; do not retry pointlessly |
| 403 unauthorized | Usually fail, alert on misconfiguration; do not retry continuously |
| Database deadlock | Consider retrying **the whole new transaction** when safe |
| Deterministic programming bug | Fail/alert, do not retry infinitely |
| Gateway completed work but response lost | Retry safely only with an idempotency key or reconciliation |
| Consumer restarted before ack | Prepare for redelivery even if the prior attempt had side effects |

A policy that retries a permanent error thirty times does not make the system “more resilient”; it just prolongs the failure and inflates the backlog.

## 4. Spring Kafka: two common error-handling approaches

### 4.1. DefaultErrorHandler: blocking retries on the listener container

Spring for Apache Kafka provides `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`.

**Configuration snippet for illustration**, not a standalone program:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1000L, 2L));

    // Two backoff attempts after the initial attempt: at most three deliveries.
    handler.addNotRetryableExceptions(
            IllegalArgumentException.class);

    return handler;
}
```

Requires imports from `org.springframework.kafka.listener`, `org.springframework.kafka.core`, `org.springframework.util.backoff.FixedBackOff`, plus a Spring context with a properly serialized `KafkaTemplate` and a container factory wired with this handler.

Specifically:

- `FixedBackOff(1000L, 2L)` means **two retries** after the initial attempt, not three retries.
- `DeadLetterPublishingRecoverer` forwards the final record to the dead-letter destination per configuration.
- With the default resolver in Spring Kafka 3.3, the DLT usually uses the `-dlt` suffix and **the same partition**; the DLT topic needs enough partitions if preserving partition numbers.
- If DLT publishing fails and the recoverer does not report/observe the error properly, records risk being lost when marked recovered. Check producer send results, recoverer config, timeouts, and failure-path tests.
- `DefaultErrorHandler` is a container-level facility; do not combine it haphazardly with `@RetryableTopic` such that retry policies stack and attempt counts exceed expectations.

### 4.2. @RetryableTopic: non-blocking retry topics

With Spring Kafka 3.3, add `@RetryableTopic` to `@KafkaListener` to create a retry/DLT topology:

```java
@RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 1000, multiplier = 2.0),
        include = TransientGatewayException.class)
@KafkaListener(
        topics = "notifications.commands",
        groupId = "notification-group")
public void onMessage(String eventId) {
    notificationService.deliver(eventId);
}

@DltHandler
public void onDeadLetter(String eventId) {
    deadLetterService.recordFailure(eventId);
}
```

This is **illustrative integration code**; it requires `org.springframework.kafka.annotation`, `org.springframework.retry.annotation.Backoff`, a Spring-managed bean, and corresponding service types.

- `attempts = "3"` caps total processing at **three attempts**, including the main attempt.
- `include` specifies retryable exceptions; exceptions outside the policy can go straight to the DLT.
- `@DltHandler` defines DLT record handling inside the **same listener class**; it does not magically “fix” poison data.
- The framework uses retry topics and consumers for delays; **it does not preserve main-topic ordering**.
- Requires environment-appropriate topics, permissions, group IDs, serializers, container factories, and producer settings.
- Topic auto-creation may need to be disabled in production if broker ACLs/governance require explicit provisioning.

**Spring Kafka version matters:** read the docs for your exact version, and do not mix `@RetryableTopic` attributes and core retry mechanisms from different versions. Spring Kafka 3.3 belongs to the Spring Framework 6.2 ecosystem; Spring Kafka 4.x may alter API details and configuration.

## 5. Java 17+ hands-on with real Kafka: retry success and DLT

This complete example runs on **Spring Boot 3.4.6 / Spring Kafka 3.3.x**, **JDK 17+**, Maven, and an Apache Kafka broker at `localhost:9092`. No HTTP endpoints are needed.

The app publishes two distinct messages:

- `evt-transient` fails transiently twice, then succeeds on the third attempt.
- `evt-invalid` throws a data error outside `include`, so it routes to the DLT without futile retries.

The program uses `CountDownLatch` to wait for **terminal outcomes**, rather than using `Thread.sleep` to guess when the broker finished. Finally, it prints one summary line with attempts/delivered/DLT. This is an **integration demo requiring a Kafka broker**, not a pure Spring Context event bus.

### 5.1. Structure

```text
spring-kafka-broker-retry-demo/
├── pom.xml
└── src/main/
    ├── java/example/BrokerRetryDemo.java
    └── resources/application.properties
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.6</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>spring-kafka-broker-retry-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.kafka</groupId>
            <artifactId>spring-kafka</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.retry</groupId>
            <artifactId>spring-retry</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The actual Spring Kafka version is selected by Spring Boot 3.4.6 dependency management. If a project pins its own versions, verify compatibility across Boot, Framework, Kafka client, and Spring Kafka.

### 5.3. src/main/resources/application.properties

```properties
spring.application.name=broker-retry-demo
spring.main.web-application-type=none

spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer

spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer

logging.level.org.apache.kafka=WARN
logging.level.org.springframework.kafka=WARN
```

The demo uses String payloads only to focus on retry semantics. Production should use an event envelope with `eventId`, `schemaVersion`, `occurredAt`, and entity IDs, along with explicit serializer/schema registry policies if switching to JSON/Avro/Protobuf.

### 5.4. src/main/java/example/BrokerRetryDemo.java

```java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableKafka
public class BrokerRetryDemo {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(BrokerRetryDemo.class, args);
        SpringApplication.exit(context);
    }

    static final class TransientGatewayException
            extends RuntimeException {
        TransientGatewayException(String message) {
            super(message);
        }
    }

    @Component
    static class Outcome {
        private final Map<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();
        private final AtomicInteger delivered = new AtomicInteger();
        private final AtomicInteger deadLettered = new AtomicInteger();
        private final CountDownLatch done = new CountDownLatch(2);

        int nextAttempt(String id) {
            return attempts.computeIfAbsent(
                    id, ignored -> new AtomicInteger())
                    .incrementAndGet();
        }

        int count(String id) {
            AtomicInteger value = attempts.get(id);
            return value == null ? 0 : value.get();
        }

        void delivered() {
            delivered.incrementAndGet();
            done.countDown();
        }

        void deadLettered() {
            deadLettered.incrementAndGet();
            done.countDown();
        }
    }

    @Component
    static class NotificationConsumer {
        private final Outcome outcome;

        NotificationConsumer(Outcome outcome) {
            this.outcome = outcome;
        }

        @RetryableTopic(
                attempts = "3",
                backoff = @Backoff(
                        delay = 1000,
                        multiplier = 2.0),
                include = TransientGatewayException.class,
                autoCreateTopics = "true",
                numPartitions = "1",
                replicationFactor = "1")
        @KafkaListener(
                topics = "notifications.commands",
                groupId = "notifications-demo")
        public void receive(String eventId) {
            int attempt = outcome.nextAttempt(eventId);

            if ("evt-transient".equals(eventId) && attempt < 3) {
                throw new TransientGatewayException(
                        "gateway unavailable");
            }

            if ("evt-invalid".equals(eventId)) {
                throw new IllegalArgumentException(
                        "invalid payload");
            }

            if ("evt-transient".equals(eventId)) {
                outcome.delivered();
            }
        }

        @DltHandler
        public void onDeadLetter(String eventId) {
            if ("evt-invalid".equals(eventId)) {
                outcome.deadLettered();
            }
        }
    }

    @Bean
    ApplicationRunner sendDemo(
            KafkaTemplate<String, String> template,
            Outcome outcome) {

        return args -> {
            template.send(
                    "notifications.commands",
                    "evt-transient",
                    "evt-transient")
                    .get(10, TimeUnit.SECONDS);

            template.send(
                    "notifications.commands",
                    "evt-invalid",
                    "evt-invalid")
                    .get(10, TimeUnit.SECONDS);

            if (!outcome.done.await(60, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Kafka retries/DLT did not complete");
            }

            System.out.println(
                    "summary: transientAttempts="
                    + outcome.count("evt-transient")
                    + " invalidAttempts="
                    + outcome.count("evt-invalid")
                    + " delivered="
                    + outcome.delivered.get()
                    + " dlt="
                    + outcome.deadLettered.get());
        };
    }
}
```

**Run the broker** in one terminal with Docker (for local demo only; not a production HA/secure config):

```bash
docker run --rm --name broker-retry-local -p 9092:9092 apache/kafka:3.8.1
```

This JVM Kafka image has official standalone instructions on default port `9092`. Verify Docker is running and the broker is ready before running Maven. In another terminal, from the project directory:

```bash
mvn -q spring-boot:run
```

When the broker is available, topics can be created, and the consumer completes within the timeout, the **program’s summary line** looks like:

```text
summary: transientAttempts=3 invalidAttempts=1 delivered=1 dlt=1
```

Spring Boot/Kafka may print extra logs. **Processing order inside the listener is not guaranteed** because multiple retry/DLT consumers exist. What to check is the terminal state and attempt count per logical event in a clean-topic/clean-group run.

**Hands-on limitations:**

1. This example uses **real Kafka**, so it will not run without a broker, Docker/Maven/JDK, or appropriate ACLs. Do not treat a successful `mvn compile` as proof of end-to-end retry verification.
2. `@RetryableTopic` creates or uses main/retry/DLT topics according to config and version. Production should provision topics via IaC/admin tools, rather than relying on auto-creation where prohibited.
3. `Outcome` is an **in-memory recorder for demo use only**, not an inbox/idempotency table. Data does not survive restarts and is not synchronized across multiple consumers.
4. On a topic with leftover messages from a previous run or a shared consumer group, demo counters may reflect more than just the two messages created. Use a clean Kafka instance/topic group for hands-on runs and reset between runs.
5. `onDeadLetter` only increments a counter. Production must persist full error details into a failure store/quarantine, emit alerts, and provide a controlled replay workflow.
6. `evt-invalid` goes to the DLT after the first attempt because its exception is outside the retry list. `evt-transient` succeeds on its third attempt after two hops through retry topics.
7. Kafka producer sends await completion in the demo; **producer completion does not prove consumer business side effects completed**, which is why the terminal latch is still required.
8. Backoff delays of 1 s/2 s are not millisecond-exact SLAs: queue lag, polling, scheduling, and load affect actual delivery times.

For more deterministic testing, you can use `spring-kafka-test` and `@EmbeddedKafka` in JUnit 5 to run an embedded broker, wait on a latch, and assert attempts; never use `Thread.sleep(...)` to guess when an event finished. To test true durability across restarts, run a persistent broker and test restarting the consumer/process separately.

## 6. Kafka offsets, acks, and forwarding failures: guarantee boundaries

Kafka is an append-only log; consumer groups track offsets. A record **is not deleted from the topic when a consumer acks**; it stays retained per the Kafka topic’s retention/compaction policy. This differs from RabbitMQ, where an ack normally confirms processing of a delivery so the broker does not redeliver that message.

Some scenarios:

```text
Consumer reads record at offset 100
  |
  +-- performs side effect successfully
  |
  +-- crashes before offset is committed
  |
  v
Restart -> offset 100 can be redelivered
           -> side effect can run a second time
```

In a non-blocking retry flow:

```text
Main record failure
    |
    +-- framework forwards to retry topic
    |
    +-- main consumer can advance to next record
    |
    +-- retry consumer processes when due
```

Between **successful forwarding** and **committing the main consumer’s position**, failure windows exist unless a dedicated transaction/guarantee mechanism is in place. Do not infer that enabling `@RetryableTopic` gives end-to-end atomicity across databases, Kafka topics, and external APIs. If the recoverer fails to publish to the DLT, the policy must ensure **records are never silently dropped**.

### Blocking retries and Kafka transactions

When using Kafka container transactions, error-handling strategies differ:

- For non-transactional record listeners, `DefaultErrorHandler` can manage backoff/recovery.
- For transactional containers, one option is `DefaultAfterRollbackProcessor` to process records after a transaction rolls back.
- Spring Kafka 3.3 **does not allow combining non-blocking retry topics with container transactions**. Choose another design if atomic Kafka consume/produce transactions are required.
- A Kafka transaction **does not create a shared transaction with databases and external services**. Evaluate each resource and failure window individually.

Do not combine `@RetryableTopic` with transactional error-handler configurations simply because both relate to retries.

### Per-aggregate ordering

Example consumer receiving on a single partition:

```text
Order-42 status version=1 -> error, goes to retry topic
Order-42 status version=2 -> main consumer processes successfully
Order-42 version=1 -> retry completes after version=2
```

Read models can be reverted to an older version if updates lack sequence checks. Ways to handle this:

- Use an **aggregate version** and ignore events with a lower version than the already-applied state.
- Keep blocking retries for flows requiring strict ordering.
- Partition logical processing by key, partition, and explicit concurrency policies.
- Design handlers with **commutative/idempotent semantics** where possible.
- Use dedicated workflows when ordering is a non-negotiable business invariant.

Kafka partition ordering applies **only within one partition of the same topic**; moving a message to a retry topic changes the scope of that ordering guarantee.

## 7. Spring AMQP/RabbitMQ: requeue, DLX, TTL, and DLQ

With RabbitMQ, listeners use Spring AMQP’s `@RabbitListener`, and the container handles exceptions/acks/rejections according to configuration.

### 7.1. Immediate requeue can create a hot loop

Illustrative code:

```java
@RabbitListener(queues = "notifications.main")
public void receive(String payload) {
    notificationService.deliver(payload);
}
```

If a listener repeatedly throws an exception, a requeue configuration can make the broker redeliver the message **very rapidly**. If the queue contains a poison message, CPU/logs can spike and healthy messages get starved.

Spring AMQP lets you configure `defaultRequeueRejected=false` or throw `AmqpRejectAndDontRequeueException` to reject a message **without requeuing**. The broker can route the message through a **Dead Letter Exchange (DLX)** if the queue is configured. Without an appropriate DLX, rejected messages can be **discarded**.

```java
@RabbitListener(queues = "notifications.main")
public void receive(String payload) {
    try {
        notificationService.deliver(payload);
    } catch (InvalidPayloadException ex) {
        throw new AmqpRejectAndDontRequeueException(
                "permanent invalid payload", ex);
    }
}
```

This is **illustrative integration code**, requiring Spring AMQP, application classes/imports, and a valid container factory. Throwing exceptions applies under **container-managed acknowledgment**; when using manual acknowledgments, follow `basicAck`/`basicNack` and the error-handling contract explicitly rather than mixing the two models haphazardly.

### 7.2. Retry topology using TTL + DLX

A common architecture:

```text
Exchange notifications.exchange
   |
   +-- routing key notification.main
           |
           v
       notifications.main.queue
           |
           +-- consumer fail / reject(requeue=false)
           |
           v
      retry DLX / retry queue
      notifications.retry.30s
      (TTL = 30 s, dead-letter routes back to main)
           |
           +-- TTL expires
           |
           v
      notifications.exchange
           |
           v
      notifications.main.queue

      After exceeding budget or permanent error:
           |
           v
      notifications.dead.queue  (DLQ, manual review)
```

**The diagram illustrates topology only.** To make it safe, you must configure all bindings, routing keys, queue policies, TTLs, and max-attempt checks. Creating a DLX loop from main to retry and back to main **without a counter/budget** can cause infinite retries.

RabbitMQ provides metadata such as `x-death` for dead-letter transitions. However, **never assume** the `x-death` count always equals “the number of times the handler ran”; semantics vary with dead-letter reason, queue, version, and how consumers republish. Do not let clients forge `x-death` to manipulate reliability, as it is a broker-managed header.

In Spring AMQP 3.2, `MessageProperties.getRetryCount()` and `incrementRetryCount()` exist to support managed retry/republish flows. With DLX-based retries, the framework can map `x-death.count` into a retry count in applicable scenarios. If republishing from application code, update the retry count **intentionally** per contract. Every project must test against its actual broker version.

### 7.3. Quorum queues and delivery limits

RabbitMQ **quorum queues** have built-in poison-message handling and a **delivery limit**; the default delivery limit is 20 since RabbitMQ 4.0 (different from 3.x). Once exceeded, messages are dead-lettered or dropped depending on DLX configuration.

**Version-specific details matter:** RabbitMQ 4.3 documentation distinguishes `delivery-count` from `acquired-count`, and some `nack/requeue` modes do not increment `delivery-count` the way you might expect. Therefore, do not design budgets by looking only at the `redelivered` flag or assuming every requeue increments the broker count.

RabbitMQ 4.3 also supports **delayed retries on quorum queues** with policy controls; this is a **different** mechanism from traditional TTL/DLX retries. Choose one consistent strategy for your version and avoid accidentally stacking multiple retry layers that multiply attempt counts.

RabbitMQ DLX has different reliability modes, including `at-least-once` dead-lettering for quorum queues when configured appropriately. Do not assume every DLX moves messages durably in all situations. Monitor broker confirms, capacity, and target queues.

### 7.4. Distinguishing local consumer retries from broker retries

Spring AMQP also has `RetryOperationsInterceptor`/Spring Retry, allowing multiple attempts **within the same listener invocation**. That differs from storing a message in a **retry queue** for the broker to redeliver minutes later.

| AMQP mechanism | How it works | Characteristics |
| --- | --- | --- |
| Listener interceptor retry | Re-invokes logic on the consumer thread with backoff | Short, can block the consumer |
| Direct requeue | Message returns to the queue immediately | Prone to hot loops if unbounded |
| TTL + DLX | Message waits in retry queue then returns to main | Requires topology/attempt budget |
| Quorum delayed retry (supported versions) | Broker holds message until retry due time | Depends on policies/quorum/version |
| DLQ/recoverer | Routes failed messages to separate handling | Needs monitoring, inspection, controlled replay |

Do not document “RabbitMQ automatically retries three times” if you are actually using an in-JVM Spring interceptor. Identify clearly who **owns the retry schedule and attempt state**.

## 8. Outbox: from ApplicationEventPublisher to broker with no gap

A source event in Spring may be published before the business transaction has committed. If a listener sends to Kafka immediately:

```text
BEGIN T1
  UPDATE order status=APPROVED
  publishEvent(OrderApproved)
       -> Kafka send succeeds
  T1 ROLLBACK
```

External consumers may see `OrderApproved` even though the database ultimately did not approve the order. Conversely, if publishing happens after commit and the process dies before sending, **the database committed yet the broker has no message**.

When the requirement is “every committed business change must produce a message for consumers”, use a **Transactional Outbox**:

```text
Transaction T1:
    UPDATE orders SET status='APPROVED'
    INSERT INTO outbox_events(
        event_id, event_type, aggregate_id,
        payload, status='PENDING', created_at)
    COMMIT T1
            |
            v
Outbox worker:
    read PENDING, claim atomically
    publish to broker, confirm send
    mark SENT or retry with backoff
            |
            v
Kafka/RabbitMQ:
    consumer process / broker-level retry / DLT/DLQ
```

Key points to preserve:

- The outbox record and business data are written **in the same database transaction**.
- The outbox dispatcher must maintain **state/retries**, able to resume after restarts.
- A successful publish followed by a crash before marking `SENT` can **send duplicates**: downstream idempotency is mandatory.
- If the use case requires per-aggregate ordering, sequence/version and partition keys must be chosen intentionally.
- **Outbox retries** (producer sending to broker) and **broker retries** (consumer processing failures) are **two distinct queues of responsibility**. They need separate metrics and deadlines.
- `@TransactionalEventListener(AFTER_COMMIT)` can be an optimization hint to “wake” the worker, but must not be the **sole** way pending messages are discovered when reliability is required; the worker still needs durable state polling/scanning.

An event envelope entering the broker might look like:

```json
{
  "eventId": "evt-85f",
  "eventType": "OrderApproved",
  "schemaVersion": 1,
  "aggregateId": "order-42",
  "aggregateVersion": 7,
  "occurredAt": "2026-01-10T00:00:00Z"
}
```

Values are illustrative; do not store full JPA entities/PII in events by default. The `eventId` must remain stable **across retry topics, DLTs, and replays** to identify the same logical event.

## 9. Idempotent consumers: preventing retries from creating duplicate side effects

A timeout does not necessarily mean the external system did not process the request:

```text
consumer -> Payment Gateway: charge(eventId=evt-85f)
gateway: charge succeeds
consumer: response lost, treated as timeout
broker retry: same message processed again
consumer -> gateway: charge(eventId=evt-85f) again
```

Without an idempotency contract, there is a risk of double charging. Retrying is safe only when side effects have a mechanism ensuring safety.

### 9.1. Using a stable idempotency key

With downstream APIs that support it, send the same `Idempotency-Key` on every attempt:

```text
Idempotency-Key: evt-85f
```

Never generate a new key per attempt. Some APIs retain idempotency keys only for a limited window; reconcile your **retry and replay durations** against that window.

### 9.2. Inbox table for database side effects

A practical design:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Within a single DB transaction, the handler can attempt to insert the marker with a unique constraint and then update business tables in the **same transaction**. If the marker already exists, skip the duplicate per policy. Doing `SELECT EXISTS(...)` followed separately by `INSERT` can race with multiple workers; the unique key and transaction boundary provide the critical protection.

External non-DB side effects (email, payments, webhooks) require **downstream API idempotency** or reconciliation workflows; a local inbox cannot undo a request already processed by an external service before a local transaction rolls back.

## 10. DLT/DLQ is not an “auto-deleting trash bin”

A DLT/DLQ is a place to **quarantine failing messages** to avoid blocking the main pipeline—not a statement that “the system handled it successfully”.

A solid workflow:

1. Record event ID, source topic/queue, consumer, attempt count, error type, timestamp, and trace/correlation ID.
2. Avoid writing sensitive secrets/PII into error headers/logs without genuine need and proper permissions.
3. Emit metrics/alerts for DLT volume, oldest age, and backlog growth rate.
4. Triage messages into those fixable by redeploy/config/migration vs. those needing manual intervention.
5. Provide **approved replays** using the same `eventId` and a bounded new attempt budget (or an explicit revision), avoiding DLT-to-main infinite loops.
6. Audit who replayed, why, and the post-replay outcome; retain necessary failure history per retention policies.
7. Set appropriate topic/queue retention: too short on a DLT loses evidence before investigation; infinite retention increases data exposure risks.

In systems with strict ordering, replaying an old record after newer records have processed can also expose ordering issues. Handlers need aggregate version guards or controlled rebuild replays.

### Explicit failure states

```text
NEW -> PROCESSING -> SUCCEEDED
          |
          +-- TRANSIENT_FAILED -> RETRY_SCHEDULED
          |                            |
          |                            +-- PROCESSING
          |
          +-- EXHAUSTED -> DLT_PENDING_REVIEW
                                |
                                +-- REPLAY_APPROVED -> PROCESSING
                                |
                                +-- QUARANTINED / COMPENSATED
```

Never equate “DLT received the record” with “payment succeeded”. These are **two distinct business states**.

## 11. Observability: tracking deliveries, attempts, and lag

A system with retry topics/queues can return HTTP 200 very quickly while its backlog grows steadily. Measure **end-to-end** instead of request latency alone.

| Signal | Explanation |
| --- | --- |
| Producer send failures/confirm latency | Did the outbox worker get the message onto the broker? |
| Consumer processing success/failure | Did the handler process the message? |
| Attempts per logical event | Receive/process attempts for one event, not confused with new events |
| Retry queue/topic lag | Messages waiting for retry and overdue retries |
| Oldest pending age | Longest-waiting event since creation |
| DLT/DLQ rate | Messages exhausting budgets or classified permanent |
| DLQ replay success rate | Are replays resolving errors or looping? |
| Kafka consumer group lag | Offset gap between consumer and topic log |
| RabbitMQ ready/unacked/requeue | Queue and delivery state on the broker |
| Broker publish/republish errors | Errors on retry/DLT forwarding paths |
| Downstream timeout/error rate | Root cause of retry storms |
| Idempotency duplicate suppression | Redeliveries safely skipped |

Metric labels should have bounded cardinality: `topic`, `consumerGroup`, `errorCategory`, `outcome`. Never put `eventId`, email, or order ID into low-cardinality metric tags. IDs belong in protected logs/traces and audit records.

Spring Framework `@EventListener` does not automatically create observations for every listener; Spring Kafka/AMQP have their own observability infrastructure depending on version and configuration. Do not assume enabling Actuator alone gives complete retry-topic and DLQ SLO dashboards.

### Example dashboard

```text
Kafka notifications:
  - main consumer lag:        120 records
  - retry topics lag:          45 records
  - DLT unreviewed:             3 records
  - p95 event completion:      8.4 seconds
  - retries exhausted/hour:     2
```

Numbers are **illustrative data**. A rapidly growing retry backlog alongside a rising downstream 503 rate signals an outage; reduce concurrency/rate, increase backoff, trip a circuit breaker, or pause replays instead of increasing retries infinitely.

## 12. Capacity planning and retry storms

Suppose a consumer receives `1,000` logical events per minute while downstream is completely down. With `maxAttempts=3`, no circuit breaker, and every event exhausting attempts, the system can generate up to **3,000 processing attempts/minute** (if infrastructure can sustain it) instead of 1,000 calls.

Factors to examine:

- `maxAttempts` and `maxElapsedTime`: total budget for one logical event.
- `backoff`/`jitter`: spreads load so downstream can recover.
- `consumer concurrency`, `prefetch` (RabbitMQ), Kafka partitions: concurrent work capacity.
- `queue length/storage limits`: retry messages consume disk/retention and can be dropped when limits are exceeded.
- `rejection`/`dead-letter` behavior: never silently drop messages under overload.
- `circuit breaker/bulkhead`: cut futile calls to an unhealthy dependency.
- `consumer lag/SLA`: after an outage, how long will it take to drain the backlog?
- `hot partitions`: one overly hot aggregate key can saturate a partition even while the rest of the cluster is idle.

A solid retry policy typically has **two bounds**: max attempts and max lifetime for the work. Do not keep retrying a message for days when the action is no longer meaningful (e.g., an expired OTP code), unless retained separately for investigation.

## 13. Properly testing broker retries

Do not write only handler unit tests and assume the entire system is resilient. Required test layers:

### 13.1. Business handler unit tests

- Transient errors are classified accurately.
- Permanent errors are not retried.
- Side effects are idempotent on duplicate `eventId`.
- Aggregate version guards prevent stale events from overwriting newer state.
- Payload schemas/migrations work on historical events.

### 13.2. Spring Kafka integration tests

Use `spring-kafka-test`, `@EmbeddedKafka`, or a containerized/test-environment broker:

1. Publish a message once.
2. Consumer throws transient exceptions initially; assert exact attempts and *approximate* backoff intervals.
3. Consumer succeeds after N attempts; assert side effect happens **once**.
4. Permanent errors go straight to DLT; assert DLT payload, headers, metadata.
5. On max attempts exhausted, assert no infinite retries.
6. Stop and restart the consumer; verify offsets/acks and redelivery.
7. Simulate a crash after the side effect but before offset commit; verify idempotency.
8. If per-key order matters, publish version 1 then 2 and check behavior when version 1 retries.
9. When forwarding to retry/DLT fails due to ACL/missing topic, assert messages are not silently lost.
10. Test container transactions **separately from** non-blocking `@RetryableTopic` if your architecture requires them.

Do not assert exact millisecond backoff timings in async tests. Use reasonable deadlines, latches/`Awaitility` (if available), terminal states, and approximate timing checks.

### 13.3. Spring AMQP/RabbitMQ integration tests

You can use Testcontainers RabbitMQ to verify against a real broker:

- Does `defaultRequeueRejected=true` with a persistently failing handler cause a redelivery storm?
- Does `AmqpRejectAndDontRequeueException` route properly to DLX/DLQ?
- Do TTL retry queues return messages to main after the expected interval?
- Does the budget on `x-death`/`retry_count` match the **actual broker version**?
- When the target DLX is missing, are messages lost under the dead-letter strategy?
- Does quorum `delivery-limit` behave as expected with the `nack`/`reject` mode used?
- Are publisher confirms and acks coordinated safely?
- Does manual ack on error avoid prematurely acking before side effects?

Do not confuse “testing consumer code” with “testing broker topology”. To prove message durability, test queues/topics/broker restarts or failure windows; mocking `RabbitTemplate` is not enough.

### 13.4. Chaos and load tests

- Downstream returns 503 for 5 minutes, then recovers.
- Broker temporarily disconnects between consumer acknowledgment and producer forwarding.
- Message hits DLT when ACL forbids publishing.
- Consumer crashes after DB commit but before Kafka offset commit.
- Retry topic fills up or retention is shorter than retry delay.
- RabbitMQ quorum leader failover or queue policy changes.
- A poison message occupies a partition, driving up main lag.
- Operator replays DLT while new consumers are active.

Evaluate **not only request p95**, but also final event completion time, backlog recovery latency, lost/duplicate side effect counts, and diagnosability.

## 14. Common mistakes and how to avoid them

**1. Thinking in-process `@EventListener` has Kafka/RabbitMQ retries.**  
No. You need a bridge/publisher to a broker and a separate consumer.

**2. Using `@TransactionalEventListener(AFTER_COMMIT)` as a durable delivery guarantee.**  
The callback runs in the right phase, but the process can die before sending. If events cannot be lost, consider an outbox.

**3. Using non-blocking retry topics for data requiring strict per-key order.**  
A failing record detours through retry topics while newer records process ahead of it. Use version guards or a different strategy.

**4. Using `@RetryableTopic` with batch listeners or Kafka container transactions in Spring Kafka 3.3.**  
Unsupported per the documentation. Choose `DefaultErrorHandler` or another transaction-aware recovery mechanism.

**5. Unlimited requeue with RabbitMQ.**  
Poison messages run in a tight hot loop and cause congestion. Use DLX/TTL/broker policies/attempt counters properly.

**6. Trusting `x-death.count` as always equal to listener execution count.**  
False across many topologies and versions; test headers and broker behavior directly.

**7. Configuring a broker delivery limit without a DLQ.**  
Messages exceeding the limit can be dropped, losing business data; configure dead-letter topology and alerts.

**8. “Retry succeeded” even though DLT publishing failed.**  
If the recoverer/producer fails to surface errors or acks prematurely, messages can be lost. Test recovery failures.

**9. Generating a new `eventId` for a logical event on every retry.**  
Breaks deduplication and correlation, risking duplicated side effects. Keep IDs stable across main/retry/DLT/replay.

**10. Relying on Kafka offsets to assert once-only side effects.**  
Offset commits and DB/payment side effects have a failure window; design idempotency.

**11. Setting infinite attempts to “never lose a message”.**  
Causes head-of-line blocking, triggers retry storms, and delays poison-message investigation.

**12. A DLT that only logs and discards.**  
No place for review/replay, missing runbooks and retention; loses recoverability.

**13. Retrying before knowing whether an error is transient or permanent.**  
400/invalid schema errors rarely self-heal; classify and quarantine early.

**14. Not monitoring retry topic/queue lag.**  
Main consumers look healthy while end-to-end event completion SLAs are failing.

**15. Neglecting security/access controls on the DLT.**  
DLTs can hold sensitive payloads or error headers; apply ACLs, encryption, retention, and masking.

**16. Stacking two retry layers uncontrolled.**  
Three attempts inside a service combined with three container attempts yield **nine calls** for one event; define one clear total retry budget.

## 15. Production readiness checklist

Before enabling broker-level retries, confirm:

1. **Event contract:** are topic/queue, event ID, schema version, aggregate key/version, and headers stable?
2. **Source atomicity:** are DB updates and message emission backed by an outbox/proper transaction?
3. **Producer confirmation:** are send failures observed and retries bounded?
4. **Consumer errors:** is transient/permanent exception classification tested?
5. **Max attempts:** total attempts vs. retries after first attempt; how many layers participate?
6. **Backoff:** delay, multiplier, jitter, max delay, queue lag, and deadline?
7. **Broker semantics:** specific Kafka offset/partition or RabbitMQ ack/requeue/DLX behavior?
8. **Compatibility:** do Spring Kafka/AMQP and broker versions support the chosen features?
9. **Ordering:** can events for the same aggregate reorder via retry topics?
10. **Idempotency:** can a crash between side effect and ack/offset commit create duplicates?
11. **DLT/DLQ:** are retention, ACLs, alerts, routing, replay approval, and audits clear?
12. **Capacity:** poison messages, outages, broker storage, partitions/prefetch, and retry storms?
13. **Observability:** attempts, terminal successes, failures, lag, oldest message age, DLQ backlog?
14. **Operations:** if the broker is down or a topic is missing, are recovery/runbooks in place without false acks?
15. **Testing:** have integration/chaos tests run against a real broker simulating restarts and failure windows?

## 16. Self-assessment questions

**1. Does `ApplicationEventPublisher.publishEvent(...)` automatically persist messages to Kafka or RabbitMQ?**  
No. In-JVM Spring application events differ from broker messaging. You need a dedicated producer/bridge.

**2. How many processing executions does Kafka `@RetryableTopic(attempts = "3")` correspond to?**  
At most **three attempts**, including the initial try. If all three hit retryable errors, the record can move to the DLT per policy.

**3. Why can retry topics break ordering?**  
A failing record is moved to another topic to wait for backoff, while a newer record on the main topic can be processed ahead of it.

**4. How many retries does `DefaultErrorHandler(new FixedBackOff(1000, 2))` perform?**  
Two retries after the initial processing attempt, typically yielding at most three attempts before recovery.

**5. Is RabbitMQ `requeue=true` a safe backoff policy?**  
No. It can immediately redeliver, creating a hot loop. Use DLX/TTL/delayed retries and a budget.

**6. Does DLT mean the business operation succeeded?**  
No. DLT means the message is in an error state requiring review/replay or another resolution decision.

**7. Why are idempotent consumers needed if the broker guarantees durable delivery?**  
Because a consumer can complete a side effect and crash before ack/offset commit; the broker will redeliver.

**8. When a committed business DB change must appear as a message on the broker, what should you use?**  
A common pattern is **Transactional Outbox**: write the outbox in the business transaction, and have a worker send to the broker and retry.

**9. Does Spring Kafka 3.3 support `@RetryableTopic` with batch listeners and container transactions?**  
No, per the non-blocking retry documentation for that version.

**10. When should you choose blocking retries over retry topics?**  
When errors are usually brief, per-partition ordering must be preserved, and temporarily blocking the consumer is acceptable; max attempts/backoff and recovery must still be configured.

## 17. Official documentation

- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Kafka 3.3 — Non-blocking Retries (@RetryableTopic)](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic.html)
- [Spring Kafka 3.3 — Retry Topic Configuration](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic/retry-config.html)
- [Spring Kafka 3.3 — Error Handlers and DeadLetterPublishingRecoverer](https://docs.spring.io/spring-kafka/reference/3.3/kafka/annotation-error-handling.html)
- [Spring Kafka 3.3 — @RetryableTopic Javadoc](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/annotation/RetryableTopic.html)
- [Spring AMQP 3.2 — Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/3.2/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [Spring AMQP 3.2 — Listener Error Handling](https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/async-annotation-driven/error-handling.html)
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [RabbitMQ — Quorum Queues, delivery-limit and delayed retry](https://www.rabbitmq.com/docs/quorum-queues)
- [Apache Kafka 3.8 — Docker Quick Start](https://kafka.apache.org/38/getting-started/docker/)

