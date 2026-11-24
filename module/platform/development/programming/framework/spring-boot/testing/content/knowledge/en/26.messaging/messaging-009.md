# Retries, Redelivery, Dead-Lettering, and Verifying Errors Are Not Lost in Messaging

## 1. Real-world problem: where can a message processing failure go?

A consumer receiving messages from a broker (RabbitMQ, Kafka, or another system) can fail due to flaky networks, database locks, invalid JSON, incompatible schemas, or violated business rules. If you only write `catch (Exception ex) { log.warn(...); }` and let the listener return normally, the container may **ACK** the message even though the work never finished. The broker then assumes the message was handled and never sends it again. A swallowed error will not be retried, will not enter a dead-letter queue (DLQ), and becomes very hard to trace.

Conversely, if you requeue every exception infinitely by default, a **poison message** (a message that always fails due to invalid data) can be redelivered continuously, causing log storms, starving consumer resources, and blocking valid messages.

A sound design does not merely "enable retries"; it **proves the final state**:

- Processing succeeds → broker ACKed, business side effect accurate.
- Transient error → bounded retries then processing succeeds.
- Permanent error → after allowed attempts, the message moves to the **DLQ**, with payload and origin metadata available for investigation.
- NACK with `requeue=true` → broker **redelivers** the message; the consumer must tolerate repeated processing.
- Duplicate message → **idempotency** prevents repeating business effects.
- Publishing out to the broker → requires **publisher confirms/returns**, durable queue topology, and proper reconciliation to avoid losing messages on the producer side.
- The DLQ is monitored, alerted on, access-controlled, and has a **controlled replay** workflow. Never treat "message entered DLQ" as "business work completed".

**Lesson objectives:**

1. Distinguish **retry**, **broker redelivery**, **dead-lettering**, **replay**, **ACK/NACK/REJECT**, and **idempotency**.
2. Understand Spring AMQP `@RabbitListener`, `AcknowledgeMode.AUTO/MANUAL`, `RetryInterceptorBuilder`, and `RejectAndDontRequeueRecoverer`.
3. Explain why retrying within the same delivery differs from broker redelivery and why `redelivered` is not an attempt counter.
4. Configure RabbitMQ **main queue + dead-letter exchange (DLX) + DLQ**; inspect `x-death` and original payload.
5. Use Java 17 + **Spring Boot 3.3.5** + Testcontainers RabbitMQ + JUnit Jupiter to run **5 integration tests** on a real broker.
6. Verify transient errors are attempted **at most 3 times** and succeed without entering the DLQ.
7. Verify poison messages fail three times and are routed by the broker to the DLQ instead of vanishing.
8. Verify manual `basicNack(requeue=true)` triggers redelivery and ACKs on the next delivery.
9. Verify sending a duplicate ID records the business effect only once in the example.
10. Recognize the limits of an in-memory tracker and how to build **outbox/inbox, durable idempotency, monitoring, publisher confirms, and Kafka DLT** for production.

**Context:** Parent topic is **Messaging**. Runnable examples focus on **RabbitMQ + Spring AMQP** so ACK, NACK, redelivery, and dead-lettering are clearly visible. The Kafka section explains equivalents without pretending both brokers share the same API. No HTTP server or production database is required; tests use only a disposable RabbitMQ container.

**Pinned versions:** Java 17, Spring Boot **3.3.5**, Spring AMQP 3.1.x, Testcontainers, and JUnit Jupiter. Newer APIs may differ; in particular check Spring Boot 4.x packages/dependencies when upgrading.

## 2. From producer to consumer: distinct states

~~~text
Producer
   |
   | publish (exchange + routing key)
   |  └─ if publisher confirm/return enabled, publish feedback occurs
   v
RabbitMQ exchange
   |
   | routed successfully
   v
Main queue --deliver--> Consumer @RabbitListener
   |                       |
   |                       +-- succeeds --> ACK --> removed from main queue
   |                       |
   |                       +-- transient error
   |                       |       |
   |                       |       +-- in-process retry (attempt 1,2,3)
   |                       |                      |
   |                       |                      +-- succeeds --> ACK
   |                       |
   |                       +-- permanent error / exhausted
   |                               |
   |                               +-- REJECT/NACK requeue=false
   |                                            |
   v                                            v
Dead-letter exchange  <---------------- broker dead-letter
   |
   | routing key "failed"
   v
Dead-letter queue (DLQ)
   |
   +-- retained for observation/investigation, fix, controlled replay
~~~

**Retry** means **re-attempting processing**. It can occur **inside the listener container** on the very same delivery (`RetryOperationsInterceptor`) or via scheduling/broker mechanisms. The word "retry" alone does not specify how many times the message crossed the broker.

**Redelivery** means **the broker delivers a message again** when it has not been ACKed and is requeued (e.g., consumer NACK `requeue=true` or channel/connection closed with unacked messages). RabbitMQ exposes a `redelivered` flag, yet this flag is not an attempt counter and does not prove side effects never ran. The same message can be processed multiple times before one ACK succeeds.

**Dead-lettering** is the broker mechanism that sends a message from a source queue through a **dead-letter exchange (DLX)** when rejected/nacked with `requeue=false`, TTL expires, queue length limit is exceeded, or quorum queue delivery limit is reached (depending on queue type/config). A DLX is an **exchange**, whereas a DLQ is a **queue** bound to receive from that exchange. Failing messages do not automatically get a DLQ: **you must create the right topology and routing**.

**Replay** is taking a failed message after investigation and feeding it back into the system (preserving or rotating IDs per business contract). Never build an automatic infinite loop DLQ→main queue for poison messages. Replay requires policy, auditability, limits, and idempotency.

**"Errors are not lost" has two sides:** the unfinished payload must sit somewhere findable (main queue/retry queue/DLQ/ledger), and the **root cause of failure** must be traceable. RabbitMQ `x-death` holds dead-letter metadata, yet **does not automatically contain Java stack traces**. To preserve exception details, use structured logs/metrics/tracing or a recoverer/failed-message record storing permitted error details.

## 3. ACK, NACK, and requeue: understand before enabling retries

| RabbitMQ situation | Action | What the broker understands |
|---|---|---|
| AUTO ACK mode, method returns normally | Container sends `basicAck` | Message processed, remove from queue |
| AUTO mode, method throws exception | Container handles exception per policy | May reject/requeue or dead-letter |
| `defaultRequeueRejected=true` (common default) | Reject with `requeue=true` | May be redelivered continuously |
| `defaultRequeueRejected=false` | Reject/NACK `requeue=false` | Removed from main queue and sent to DLX **if configured** |
| `AmqpRejectAndDontRequeueException` | Explicitly forbids requeue | Routed to DLX if routing exists |
| `ImmediateRequeueAmqpException` | Requests requeue regardless of default | Can cause broker redelivery |
| MANUAL mode: `basicAck(tag,false)` | Consumer explicitly confirms | Removes message from queue |
| MANUAL mode: `basicNack(tag,false,true)` | NACK, `requeue=true` | Returns to main queue, may redeliver |
| MANUAL mode: `basicReject(tag,false)` | Reject, `requeue=false` | Dead-lettered if valid DLX exists |
| **Catch exception and return normally** | AUTO container assumes success | **Risk of losing work** if unfinished |

**Spring listener container `AUTO` ACK mode is not the same as RabbitMQ protocol `autoAck=true`.** With `AcknowledgeMode.AUTO`, Spring sends ACK **after the listener finishes successfully**, and decides to reject if the listener fails. With `AcknowledgeMode.NONE`, the broker treats the message as ACKed immediately upon delivery ("autoack" in RabbitMQ terms). Never confuse the two.

**Anti-pattern** example:

~~~java
@RabbitListener(queues = "orders.work")
void consume(String body) {
    try {
        process(body);
    } catch (Exception ex) {
        log.error("Failed: {}", body, ex);
        // Does not rethrow: container may ACK.
    }
}
~~~

This is an illustrative snippet, not a standalone runnable file. Logging is good, yet **logging alone is not a retry/failure-retention policy**. If `process` fails, the caller should throw (so the container handles it) or explicitly persist a failed record and ACK within a **guaranteed compensating transaction**, never swallowing errors unconditionally.

### 3.1. When should you not requeue?

Errors from temporary misconfiguration, unresponsive downstream dependencies, or 503 responses can be retried. By contrast, unparseable JSON, schema violations, or invalid business states usually do not heal by calling the exact same code immediately. For poison messages, bounded retries followed by DLQ and alerting are far safer than infinite `requeue=true`.

Do not set `defaultRequeueRejected=false` **without configuring a DLX/failed record** and claim errors are preserved: when the broker cannot dead-letter, the message can be dropped. That is why tests must **actually receive the message from the DLQ**, not merely verify that the listener threw an exception.

### 3.2. In-process retry is not broker redelivery

~~~text
One RabbitMQ delivery (redelivered=false)
   -> Spring listener attempt 1: IllegalStateException
   -> Spring listener attempt 2: IllegalStateException
   -> Spring listener attempt 3: SUCCESS
   -> basicAck (one broker delivery)

NACK requeue=true of a delivery:
   -> broker delivers message (delivery #1, redelivered=false)
   -> consumer basicNack(requeue=true)
   -> broker delivers message again (delivery #2, redelivered=true)
   -> consumer basicAck
~~~

In the first diagram, attempts equal **3**, yet `x-death` does not increment because the message never dead-lettered, and the broker did not necessarily deliver it three times. In the second diagram, the broker performs **2 deliveries**, without needing Spring `RetryOperationsInterceptor` at all.

### 3.3. Stateless and stateful retry

**Stateless retry** runs multiple attempts within **the same listener invocation/delivery**, convenient when no outer transaction must roll back between attempts. The demo uses 3 attempts and a tiny backoff for fast tests.

**Stateful retry** tracks retry state keyed by message identity across separate deliveries; better suited when an outer transaction wraps the listener and must roll back properly on every delivery. Stateful retry needs a **reliable message ID** or `MessageKeyGenerator`; a missing ID can trigger fatal policy/consumer stops depending on config. Never switch from stateless to stateful just by changing one word without testing message identity, transactions, requeue, and recovery.

**Spring Retry `maxAttempts(3)`** includes **the initial attempt plus two retries**. Do not interpret it as 3 retries on top of the initial attempt and write assertions expecting 4.

## 4. Dead-letter exchange, DLQ, and `x-death`

A minimal RabbitMQ topology:

~~~text
main queue = learning.work.q
  x-dead-letter-exchange    = learning.dead.x
  x-dead-letter-routing-key = failed

direct exchange = learning.dead.x
  binding failed -> learning.dead.q

dead-letter queue = learning.dead.q
  No default @RabbitListener: operators/tests read intentionally
~~~

When a message is rejected with `requeue=false`, RabbitMQ reads the exchange/routing key configured on the **source queue**, forwards the message to the DLX, and routes it to the DLQ. If the exchange name is misspelled, the binding is missing, or the DLQ itself is unavailable, you cannot assume messages are always preserved. Production should verify topology via declarations, broker metrics, and end-to-end tests.

**`x-death` attached by the broker on dead-lettering** typically contains `queue`, `reason`, `count`, `time`, and exchange/routing metadata. `reason` can be `rejected` for `basicReject`/`basicNack` without requeue. `count` reflects how many times the broker dead-lettered the message for that tuple, **not how many times the Java method retried inside the container**.

**Never forge `x-death` to trick logic.** It is broker metadata; tests should inspect real messages flowing through the broker. With RabbitMQ 4.x, broker handling of certain client-supplied headers changed; never treat client headers as equivalent to broker-generated `x-death`.

### 4.1. DLQs do not keep stack traces by default

The sample uses `RejectAndDontRequeueRecoverer`: once retries are exhausted, the recoverer throws `AmqpRejectAndDontRequeueException`; the container rejects and **RabbitMQ DLX** routes the message to the DLQ. The message keeps its original payload plus dead-letter metadata, yet **does not automatically embed the Java `IllegalStateException` cause**.

To preserve root causes, you have several options:
- Structured logs/error events with `messageId`, correlation ID, exception type, and trace ID, without printing secrets.
- A persistent failed-message table or event carrying key/id, error code, attempt count, and timestamp, with explicit transaction consistency.
- Spring AMQP `RepublishMessageRecoverer`, which republishes to an error exchange and can attach exception headers. **Differs from broker DLX**: if the recoverer succeeds and returns, the original message may be **ACKed**; if republishing fails or lacks publisher confirms, never assume the failed payload is safe.
- Metrics/alerts and dashboards for DLQ depth, oldest message age, and DLX routing failures.

**Never auto-replay every error.** For poison data, investigate the root cause first; without fixing the schema/consumer, replaying just recreates the failure loop.

## 5. Testing strategy: verify state, not just `verify(exception)`

| Scenario | What must be verified |
|---|---|
| Healthy | 1 attempt, 1 business effect, empty DLQ |
| Transient fails twice | 3 attempts, eventually succeeds, empty DLQ |
| Poison always fails | 3 attempts, 0 business effects, **DLQ holds original payload + `x-death`** |
| Broker redelivery | 2 broker deliveries, `redelivered` flag on 2nd delivery, consumer ACK |
| Duplicate publish | 2 delivery/attempt observations, **only 1 business effect** |
| Unroutable producer | Publisher return/confirm alerts, never equate `convertAndSend` with reaching queue |
| Consumer killed before ACK | Broker can redeliver, must be idempotent |
| DLQ unreachable | Tests/monitoring must detect; never claim no-loss |
| Retry budget exceeded | Dead-letter/failed record/alert, no infinite requeue |
| Replaying already-handled message | No repeated side effects, audited |

Mocking a listener's `process()` method with Mockito alone does not prove RabbitMQ ACK/NACK/DLX work. Hence the runnable example uses a **real `RabbitMQContainer`** via Testcontainers. Tests also use an **in-memory** `DeliveryTracker` counting attempts and effects for observability; the tracker is a lesson measurement tool, **not a durable ledger**. Production must use DB unique constraints/inbox/outbox and matching commit/ack policies.

### 5.1. Avoid fixed `Thread.sleep` for async tests

`@RabbitListener` runs on a separate thread. Publishing and immediately asserting attempt counts is flaky because the consumer may not have received the message yet. The example uses **Awaitility** (`await().atMost(Duration.ofSeconds(15)).untilAsserted(...)`) to wait for observable state with a deadline. `Thread.sleep(1000)` is always either too short or wasteful; on slow CI it fails randomly.

For the DLQ specifically, `RabbitTemplate.receive(queue, timeoutMillis)` polls the broker until a message arrives or the timeout expires; that actively inspects messages reaching the DLQ. `receive` **removes and ACKs the message from the DLQ in the test**. In production, never run a monitoring job that consumes the DLQ just to "count errors"; use RabbitMQ management/metrics for non-destructive observation.

## 6. Runnable project: Java 17 + Spring Boot 3.3.5 + RabbitMQ Testcontainers

The example has **two inbound queues** to separate two mechanisms:
- `learning.work.q`: Spring **AUTO ack + stateless retry 3 attempts + DLX**.
- `learning.redelivery.q`: Spring **MANUAL ack**, NACK requeue on first delivery, ACK on the broker's second delivery.
- `learning.dead.q`: DLQ receiving rejected messages from the work queue; **no auto-consuming listener**.
- `learning.dead.x`: direct DLX binding routing key `failed` to the DLQ.

The publisher sends strings formatted as `jobId|kind` to the work queue. `kind` accepts:
- `ok`: processes immediately.
- `transient`: fails the first two times, then succeeds on the third.
- `poison`: fails every attempt and moves to the DLQ.

In the example, "business effect" is simply a thread-safe counter. It is a learning aid to assert idempotency; surviving crashes/restarts requires replacing it with a DB transaction/unique key.

### 6.1. File structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/messaging/MessagingDemoApplication.java
src/main/java/demo/messaging/MessagingTopology.java
src/main/java/demo/messaging/RabbitListenerConfiguration.java
src/main/java/demo/messaging/DeliveryTracker.java
src/main/java/demo/messaging/WorkListener.java
src/main/java/demo/messaging/RedeliveryListener.java
src/main/java/demo/messaging/WorkPublisher.java
src/test/java/demo/messaging/MessagingReliabilityTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'rabbit-retry-dlq-test'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

- **starter-amqp**: Spring AMQP, `RabbitTemplate`, `@RabbitListener`, listener container factories, and Spring Retry integrations.
- **starter-test**: JUnit Jupiter, Spring Test, and Awaitility for waiting on async assertions.
- **spring-boot-testcontainers**: `@ServiceConnection` for typed `RabbitMQContainer` in Boot 3.3.x.
- **Testcontainers JUnit + RabbitMQ module**: runs real RabbitMQ in Docker and manages container lifecycle.
- Dependency versions are managed by the Spring Boot BOM. The lesson needs no web starter or database client.

**Execution requirements:** Java 17, compatible Gradle, running Docker daemon/container runtime supported by Testcontainers, permission to pull `rabbitmq:3.13-management-alpine`, and working network/port mapping. Never use production RabbitMQ and never hard-code `localhost:5672` because Testcontainers maps host ports dynamically.

### 6.2. Main application

**src/main/java/demo/messaging/MessagingDemoApplication.java**

~~~java
package demo.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessagingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingDemoApplication.class, args);
    }
}
~~~

The app needs no HTTP server. Spring Boot Rabbit auto-configuration supplies the connection factory, `RabbitTemplate`, `RabbitAdmin`, and listener infrastructure via the starter. Tests wire the container's RabbitMQ endpoint into auto-configuration via `@ServiceConnection`.

### 6.3. Queue, DLX, DLQ: real broker declarations

**src/main/java/demo/messaging/MessagingTopology.java**

~~~java
package demo.messaging;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MessagingTopology {

    public static final String WORK_QUEUE =
            "learning.work.q";
    public static final String REDELIVERY_QUEUE =
            "learning.redelivery.q";
    public static final String DEAD_EXCHANGE =
            "learning.dead.x";
    public static final String DEAD_QUEUE =
            "learning.dead.q";
    public static final String DEAD_ROUTING_KEY = "failed";

    @Bean
    Declarables messagingDeclarables() {
        DirectExchange dlx =
                new DirectExchange(DEAD_EXCHANGE, true, false);

        Queue dlq = QueueBuilder.durable(DEAD_QUEUE).build();

        Binding deadBinding =
                BindingBuilder.bind(dlq)
                        .to(dlx)
                        .with(DEAD_ROUTING_KEY);

        Queue workQueue = QueueBuilder.durable(WORK_QUEUE)
                .deadLetterExchange(DEAD_EXCHANGE)
                .deadLetterRoutingKey(DEAD_ROUTING_KEY)
                .build();

        Queue redeliveryQueue =
                QueueBuilder.durable(REDELIVERY_QUEUE).build();

        return new Declarables(
                dlx, dlq, deadBinding,
                workQueue, redeliveryQueue);
    }
}
~~~

**How it works:**

1. `DirectExchange` named `learning.dead.x` receives dead-lettered messages from the work queue.
2. DLQ `learning.dead.q` is bound with routing key `failed`.
3. The work queue carries `x-dead-letter-exchange` and `x-dead-letter-routing-key`. When the consumer rejects without requeue, the broker routes the message to the DLQ.
4. The redelivery queue is a separate queue without retry advice and needs no DLX for the NACK→ACK test.
5. `Declarables` are declared on the broker by Spring's `RabbitAdmin`. When publishing directly with `RabbitTemplate.convertAndSend(queueName, payload)`, `RabbitTemplate` uses the **default exchange** with the queue name as the routing key; RabbitMQ auto-binds the default exchange to every queue by name. No custom exchange is needed for publishers in this example.

**In production:** durable queues with persistent messages are important yet do not alone guarantee "zero message loss". You may need quorum queues, replication, publisher confirms, returns, broker policies, routing monitoring, and recovery. RabbitMQ recommends configuring DLX via **broker policies** instead of hard-coding x-arguments when flexible topology changes are needed; the code uses x-arguments for easy reproducibility with Testcontainers.

### 6.4. Container factories: one with retry, one with manual ack

**src/main/java/demo/messaging/RabbitListenerConfiguration.java**

~~~java
package demo.messaging;

import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitListenerConfiguration {

    @Bean("workFactory")
    SimpleRabbitListenerContainerFactory workFactory(
            ConnectionFactory connectionFactory,
            SimpleRabbitListenerContainerFactoryConfigurer configurer) {

        var factory = new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(1);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)
                        .backOffOptions(25L, 1.0, 25L)
                        .recoverer(
                                new RejectAndDontRequeueRecoverer())
                        .build());

        return factory;
    }

    @Bean("manualAckFactory")
    SimpleRabbitListenerContainerFactory manualAckFactory(
            ConnectionFactory connectionFactory,
            SimpleRabbitListenerContainerFactoryConfigurer configurer) {

        var factory = new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(1);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setPrefetchCount(1);

        return factory;
    }
}
~~~

**Decisions not to skip:**

- `workFactory` uses **AUTO ack**: if the listener succeeds after retrying, it ACKs; if retries exhaust, `RejectAndDontRequeueRecoverer` forbids requeuing.
- `.maxAttempts(3)` = **first attempt + 2 retries**. `.backOffOptions(25,1.0,25)` keeps tests fast; production usually needs longer backoff, jitter, and retryable/fatal exception classification.
- `.setDefaultRequeueRejected(false)` makes the fallback safer if an exception bypasses the advice unexpectedly. It does not create a DLQ; broker dead-lettering still depends on the topology above.
- `manualAckFactory` has no retry advice; the listener is responsible for **acking/nacking every path**. `prefetch=1` makes the educational scenario deterministic, not optimal for high throughput.
- Both factories use Boot's `SimpleRabbitListenerContainerFactoryConfigurer` to retain connection/observability settings. Do not construct a `new ConnectionFactory` pointing to `localhost` that bypasses the service connection.

**Important note on retry strategies:** Stateless retry should not be used indiscriminately when an outer transaction wraps the callback and must roll back between attempts. When business logic pairs DB transactions with broker acks, align transaction boundaries, outbox/inbox, and retry strategies; consider stateful retry where appropriate.

### 6.5. Thread-safe tracker for assertions (not a durable store)

**src/main/java/demo/messaging/DeliveryTracker.java**

~~~java
package demo.messaging;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class DeliveryTracker {

    private final ConcurrentMap<String, AtomicInteger> attempts =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> effects =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> brokerDeliveries =
            new ConcurrentHashMap<>();

    private final Set<String> completed =
            ConcurrentHashMap.newKeySet();

    private final Set<String> seenRedelivery =
            ConcurrentHashMap.newKeySet();

    public int recordAttempt(String id) {
        return attempts
                .computeIfAbsent(id, key -> new AtomicInteger())
                .incrementAndGet();
    }

    public int attempts(String id) {
        AtomicInteger counter = attempts.get(id);
        return counter == null ? 0 : counter.get();
    }

    public boolean isCompleted(String id) {
        return completed.contains(id);
    }

    public void completeOnce(String id) {
        effects.computeIfAbsent(id, key -> new AtomicInteger())
                .compareAndSet(0, 1);
        completed.add(id);
    }

    public int effects(String id) {
        AtomicInteger counter = effects.get(id);
        return counter == null ? 0 : counter.get();
    }

    public int recordBrokerDelivery(String id) {
        return brokerDeliveries
                .computeIfAbsent(id, key -> new AtomicInteger())
                .incrementAndGet();
    }

    public int brokerDeliveries(String id) {
        AtomicInteger counter = brokerDeliveries.get(id);
        return counter == null ? 0 : counter.get();
    }

    public void markRedelivered(String id) {
        seenRedelivery.add(id);
    }

    public boolean sawRedelivered(String id) {
        return seenRedelivery.contains(id);
    }
}
~~~

`ConcurrentHashMap` and `AtomicInteger` avoid data races while listeners run on background threads and the test thread reads state. `recordAttempt` counts Java listener invocations; `recordBrokerDelivery` counts RabbitMQ deliveries to the manual-ack consumer.

**Never ship this tracker to production and call it permanent idempotency.** It loses state on process restart, cannot coordinate multiple consumer instances, and `completed`/`effects` are not committed transactionally with business writes. Production needs a **persistent inbox/idempotency table** with a unique constraint on message ID, or inherently idempotent operations inside an appropriate transaction.

### 6.6. Work listener: transient succeeds, poison goes to DLQ

**src/main/java/demo/messaging/WorkListener.java**

~~~java
package demo.messaging;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class WorkListener {

    private final DeliveryTracker tracker;

    public WorkListener(DeliveryTracker tracker) {
        this.tracker = tracker;
    }

    @RabbitListener(
            queues = MessagingTopology.WORK_QUEUE,
            containerFactory = "workFactory")
    public void consume(String payload) {
        String[] fields = payload.split("\\|", 2);
        if (fields.length != 2
                || fields[0].isBlank()
                || fields[1].isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid message format");
        }

        String id = fields[0];
        String kind = fields[1];
        int attempt = tracker.recordAttempt(id);

        // Already processed this ID earlier: do not repeat business effect.
        if (tracker.isCompleted(id)) {
            return;
        }

        if ("poison".equals(kind)) {
            throw new IllegalArgumentException(
                    "Permanent poison payload id=" + id);
        }

        if ("transient".equals(kind) && attempt < 3) {
            throw new IllegalStateException(
                    "Simulated temporary dependency failure");
        }

        if (!"ok".equals(kind)
                && !"transient".equals(kind)) {
            throw new IllegalArgumentException(
                    "Unsupported kind=" + kind);
        }

        tracker.completeOnce(id);
    }
}
~~~

**Note:** `completeOnce` is only a test counter. When the consumer sees a duplicate `id`, the method returns normally and the AUTO container ACKs the duplicate; this is idempotent within one JVM instance. Two different payloads sharing an ID must not silently count as the same business action unless the contract allows it — define message IDs and versioning carefully. In real systems, deduplication keys must be strong and guarded by unique constraints/transactions.

**Why throw exceptions instead of catching and ignoring?** So the retry advice sees the failure. For `"transient"`, calls 1 and 2 throw, and call 3 succeeds. For `"poison"`, all three attempts throw, the recoverer demands REJECT without requeue, and the broker routes to the DLQ. That lets tests verify both distinct outcomes.

**Never use `attempt` in the tracker as a production retry counter.** In tests it lives in one process and never resets until restart. Production retry policies may rely on `Spring RetryContext`, message headers, persisted attempts, or broker delivery limits depending on the mechanism.

### 6.7. Manual-ack listener: explicitly NACK so the broker redelivers

**src/main/java/demo/messaging/RedeliveryListener.java**

~~~java
package demo.messaging;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class RedeliveryListener {

    private final DeliveryTracker tracker;

    public RedeliveryListener(DeliveryTracker tracker) {
        this.tracker = tracker;
    }

    @RabbitListener(
            queues = MessagingTopology.REDELIVERY_QUEUE,
            containerFactory = "manualAckFactory")
    public void consume(Message message, Channel channel)
            throws IOException {

        String id = new String(
                message.getBody(), StandardCharsets.UTF_8);

        long deliveryTag = message.getMessageProperties()
                .getDeliveryTag();

        int count = tracker.recordBrokerDelivery(id);

        if (count == 1) {
            // Return to broker for redelivery; not Spring Retry.
            channel.basicNack(deliveryTag, false, true);
            return;
        }

        // Second time: ACK first, then mark for the test.
        channel.basicAck(deliveryTag, false);

        if (Boolean.TRUE.equals(
                message.getMessageProperties().isRedelivered())) {
            tracker.markRedelivered(id);
        }
    }
}
~~~

`basicNack(deliveryTag, false, true)` means:
- `deliveryTag`: tag of the **delivery on the current channel**, not a business ID.
- `multiple=false`: applies only to this delivery, not batch-acking/nacking prior tags.
- `requeue=true`: returns the message to RabbitMQ so it can be delivered again.

`basicAck(deliveryTag, false)` confirms success. With one queue, one consumer, prefetch 1, and a disposable container, the test expects the second delivery to carry `redelivered=true`. This flag is **best-effort per protocol** and can also reflect connection/channel recovery in real systems. Never use `redelivered` as a unique identifier or an exactly-once guarantee.

**Risks of MANUAL ack:** If code forgets to ACK/NACK, messages sit unacked until the channel closes; if it NACKs with `requeue=true` every time, messages loop. Production needs `try/catch` for all errors, deadlines/backoff, metrics, and a policy for un-ackable paths. Limiting requeues to once via `tracker` is purely illustrative; it is not bounded production retry because the tracker disappears on restart.

### 6.8. Publisher using default exchange and queue-name routing key

**src/main/java/demo/messaging/WorkPublisher.java**

~~~java
package demo.messaging;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class WorkPublisher {

    private final RabbitTemplate template;

    public WorkPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void sendWork(String id, String kind) {
        template.convertAndSend(
                MessagingTopology.WORK_QUEUE,
                id + "|" + kind);
    }

    public void sendForRedelivery(String id) {
        template.convertAndSend(
                MessagingTopology.REDELIVERY_QUEUE, id);
    }
}
~~~

The publisher sends plain text Strings via `RabbitTemplate`'s default converter. In the example, `id|kind` assumes no `|` in `id`. Payloads and queue names are learning fixtures; real systems use JSON/Avro/Protobuf with schema versions, validation, and explicit correlation IDs.

**Important:** `convertAndSend` returning normally **does not prove the message was durably routed to the right queue**, especially when verifying producer-side loss prevention. To address no-loss guarantees, enable publisher confirms, mandatory returns, or an outbox, and verify broker topology and error paths. The runnable tests below focus on **consumer outcomes** and broker DLQ rather than claiming to test all network/cluster failures.

## 7. Five integration tests running against real RabbitMQ

A test suite must verify **both broker state** and **processing state**. Do not only run `verify(listener, times(3))` with Mockito: that cannot tell whether the message entered the DLQ. Here we have a real `RabbitMQContainer`, `RabbitTemplate` sending messages and reading the DLQ, and Awaitility waiting for listener completion.

**src/test/java/demo/messaging/MessagingReliabilityTest.java**

~~~java
package demo.messaging;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class MessagingReliabilityTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    "rabbitmq:3.13-management-alpine");

    @Autowired
    WorkPublisher publisher;

    @Autowired
    DeliveryTracker tracker;

    @Autowired
    RabbitTemplate template;

    @Autowired
    AmqpAdmin admin;

    private int queuedCount(String queue) {
        Properties properties = admin.getQueueProperties(queue);
        assertNotNull(properties, "Missing queue: " + queue);

        return ((Number) properties.get(
                RabbitAdmin.QUEUE_MESSAGE_COUNT)).intValue();
    }

    @Test
    void healthyMessageIsProcessedOnceWithoutDeadLetter() {
        String id = "healthy-326";

        publisher.sendWork(id, "ok");

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    assertTrue(tracker.isCompleted(id));
                    assertEquals(1, tracker.attempts(id));
                    assertEquals(1, tracker.effects(id));
                });

        assertEquals(0, queuedCount(MessagingTopology.DEAD_QUEUE));
    }

    @Test
    void transientFailureRetriesThreeAttemptsThenSucceeds() {
        String id = "transient-326";

        publisher.sendWork(id, "transient");

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    assertTrue(tracker.isCompleted(id));
                    assertEquals(3, tracker.attempts(id));
                    assertEquals(1, tracker.effects(id));
                });

        assertEquals(0, queuedCount(MessagingTopology.DEAD_QUEUE));
    }

    @Test
    void poisonFailureIsDeadLetteredWithOriginalPayload() {
        String id = "poison-326";
        String original = id + "|poison";

        publisher.sendWork(id, "poison");

        Message dead = template.receive(
                MessagingTopology.DEAD_QUEUE, 15_000);

        assertNotNull(
                dead,
                "Failed payload must reach DLQ, not disappear");

        assertEquals(
                original,
                new String(dead.getBody(), StandardCharsets.UTF_8));

        List<Map<String, ?>> deaths =
                dead.getMessageProperties().getXDeathHeader();

        assertNotNull(deaths);
        assertFalse(deaths.isEmpty());
        assertEquals("rejected", deaths.get(0).get("reason"));
        assertEquals(
                MessagingTopology.WORK_QUEUE,
                deaths.get(0).get("queue"));

        assertEquals(3, tracker.attempts(id));
        assertFalse(tracker.isCompleted(id));
        assertEquals(0, tracker.effects(id));
    }

    @Test
    void brokerNackRequeuesAndSetsRedeliveredFlag() {
        String id = "redelivery-326";

        publisher.sendForRedelivery(id);

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    assertEquals(2, tracker.brokerDeliveries(id));
                    assertTrue(tracker.sawRedelivered(id));
                });

        assertEquals(
                0, queuedCount(MessagingTopology.REDELIVERY_QUEUE));
    }

    @Test
    void duplicateMessageDoesNotRepeatBusinessEffect() {
        String id = "duplicate-326";

        publisher.sendWork(id, "ok");
        publisher.sendWork(id, "ok");

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    assertEquals(2, tracker.attempts(id));
                    assertTrue(tracker.isCompleted(id));
                    assertEquals(1, tracker.effects(id));
                });

        assertEquals(0, queuedCount(MessagingTopology.DEAD_QUEUE));
    }
}
~~~

**Exactly 5 JUnit Jupiter `@Test` methods.** `queuedCount` is a helper, not a test. No `@TestMethodOrder`, `Thread.sleep`, or order-dependent test data. Each test uses a distinct message ID, the RabbitMQ container belongs solely to this class, and the poison test **intentionally reads/removes the message from the DLQ** to assert its contents. If pointed at a production DLQ, never let tests consume live failing messages.

### 7.1. Healthy test: ACK and no DLQ entry

Message `healthy-326|ok` is published to the work queue. Listener `recordAttempt` increments to 1, business counter increments to 1, and returns normally; the container AUTO ACKs. The test awaits `isCompleted=true`, `attempts=1`, `effects=1`, and checks DLQ depth is 0.

**Do not assert only `isCompleted=true`**: that would miss a listener accidentally running twice or repeating business effects. In the example, both attempt count and effect count are checked to verify exact behavior.

### 7.2. Transient test: three attempts, single broker delivery

Message `transient-326|transient`: attempts 1 and 2 throw `IllegalStateException` simulating a temporary dependency failure; retry advice retries; attempt 3 succeeds. **Max attempts 3** includes the initial call. The test awaits completion, asserts `attempts=3`, `effects=1`, and an empty DLQ.

**Do not conclude RabbitMQ delivered the message three times just because the method ran three times.** In this **stateless retry** configuration, the same delivery is retried inside the advice, so the broker's `redelivered` flag need not be true and `x-death` does not increment.

### 7.3. Poison test: proof errors are not silently lost

Message `poison-326|poison` throws on all three attempts. Once retries exhaust, `RejectAndDontRequeueRecoverer` forbids requeue; RabbitMQ dead-letters via the DLX to the DLQ. The test uses `RabbitTemplate.receive(DLQ, timeout)` to fetch the **real broker-routed message**, then asserts:

1. **Payload bytes** decode as UTF-8 to the original string.
2. **`x-death`** was attached by the broker and is non-empty.
3. `x-death.reason` is `rejected`.
4. `x-death.queue` matches the source work queue.
5. Counter shows **3 listener attempts**.
6. Business effect is **0**, and the message is not marked completed.

**This is stronger evidence than "the listener threw an exception"** because it verifies broker state. Still, it **does not prove the whole system can never lose messages**. If exchanges/bindings are missing, the broker shuts down, or the DLQ is non-durable, a design lacking confirms/monitoring can still lose messages in other scenarios. Tests should expand to outage/routing/callback failures per real SLOs.

### 7.4. Manual redelivery test: NACK then ACK

The redelivery listener receives `redelivery-326` on delivery 1 and calls `basicNack(tag,false,true)`. The broker requeues and delivers it a second time; the listener ACKs. The tracker records **2 broker deliveries** and `redelivered=true` on the second delivery. The test uses no Spring retry advice on this queue, so it genuinely exercises **broker redelivery**.

**Note:** RabbitMQ's `redelivered` flag is best-effort per protocol: it indicates the delivery may have been delivered previously, not whether side effects ran, and does not provide an attempt count. Idempotency remains mandatory in real processing.

### 7.5. Duplicate publish test: idempotency is a separate concern

The publisher sends the same `duplicate-326|ok` twice. The listener records both attempts, yet `tracker.isCompleted` prevents the second delivery from incrementing the business effect. The test asserts `attempts=2`, `effects=1`.

**Do not call this exactly-once delivery.** RabbitMQ received **two messages**; code merely enforced one **business effect** in the test environment. Production can run multiple consumer replicas, crash between DB commit and ACK, or redeliver after network failures. To test end-to-end, use a persistent deduplication/inbox ID with a unique constraint and proper transactions; test crashes/restarts and concurrent deliveries.

## 8. Running tests and environment conditions

If the project already has a Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you just created `settings.gradle`, `build.gradle`, and source files **without a Gradle Wrapper yet**, `./gradlew` does not exist yet; use a compatible Gradle installation to generate the wrapper or run `gradle test`.

Run just this class:

~~~bash
./gradlew test --tests demo.messaging.MessagingReliabilityTest
~~~

Tests require a running Docker daemon with permission to create containers and pull `rabbitmq:3.13-management-alpine`. Do not set an overly short fixed container startup timeout on CI machines pulling the image for the first time. The **15-second** Awaitility timeout in the tests **bounds message processing after the container/context are ready**, not Docker pull/startup.

**Expected from source:** JUnit Jupiter discovers 5 test methods; healthy/transient/poison/redelivery/duplicate are all designed to PASS when RabbitMQ and container runtime work as described. These are **expectations derived from source code**, not claims that the tests were run on the reader's machine.

Gradle reports normally appear at:

~~~text
build/reports/tests/test/index.html
~~~

**About log noise:** The poison test intentionally throws exceptions three times, so Spring AMQP may log `WARN`/`ERROR` messages about retry exhaustion. Those logs do not mean the overall test failed; check the DLQ assertions and Gradle results. Conversely, a test with `ERROR` logs and no broker-state assertions could still "pass falsely".

### 8.1. Why is `@ServiceConnection` important?

Spring Boot 3.3 recognizes a **typed `RabbitMQContainer`** via `@ServiceConnection` in `spring-boot-testcontainers`, creating **`RabbitConnectionDetails`** with the container's actual host/port/credentials. Rabbit auto-configuration uses those details to build the connection factory.

Never hard-code host port 5672 in tests; Testcontainers selects a dynamic mapped port. If a test manually builds a custom `ConnectionFactory` pointing to localhost, clients can bypass the service connection. A test passing because it accidentally connected to a RabbitMQ running outside Docker **does not prove** the Testcontainers topology works.

### 8.2. Why not use Mockito for broker-level assertions?

Mockito can verify `verify(service, times(3)).process(id)` or stub exceptions, yet it does not run RabbitMQ routing, ACK, DLQ, or `x-death`. Use unit tests for **business error classification/retry policy**, and integration tests with `RabbitMQContainer` to verify real broker mechanics.

`@RabbitListenerTest` with `RabbitListenerTestHarness` helps spy/capture listener invocations when test-level introspection is wanted, yet it also **does not replace broker topology verification** when the goal is dead-lettering. Avoid equating "spy called 3 times" with "failed message safely retained".

## 9. "Errors are not lost": boundary-by-boundary checklist

### 9.1. Producer → broker

- **Publisher confirms:** Enable broker confirmation of published messages (e.g., Spring Boot Rabbit `spring.rabbitmq.publisher-confirm-type=correlated`). Handle broker ACK/NACK and timeout callbacks per policy. `convertAndSend` returning is insufficient.
- **Publisher returns / mandatory:** Enable `spring.rabbitmq.publisher-returns=true` and `spring.rabbitmq.template.mandatory=true` to detect messages sent to an exchange that **failed to route to any queue**. Confirms and returns answer different questions.
- **Durability:** Durable exchanges/queues, persistent messages, and broker HA/quorum policies per SLO. Never use non-durable queues and claim messages survive broker restarts.
- **Outbox:** When business operations both commit to a DB and publish, use transactional outbox/CDC or an equivalent sync mechanism so you never commit DB without publishing or publish before DB rollback.
- **Message ID:** Unique, stable, traceable across every retry/replay; avoid reusing IDs across distinct actions. Correlation IDs are not necessarily idempotency keys.
- **Monitoring:** Record counters for publish failures, returned messages, and confirm timeouts; attach alerts. Retries cannot fix an unroutable message indefinitely when topology is wrong.

**Illustrative** configuration snippet when extending a RabbitMQ producer:

~~~properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
~~~

Adding those lines alone **is not enough**: the application must also attach confirm/return callbacks or wait for confirms, handle failures, and trigger retries/outbox. Never treat `RabbitTemplate` publisher confirms as a "fire-and-forget success detector" without observing outcomes.

### 9.2. Broker → consumer

- **ACK only after business work completes**, never immediately upon parsing or launching an unfinished async task.
- With `AcknowledgeMode.AUTO`, throw exceptions on processing failure or use clear error/recoverer policies; never catch-and-return.
- Retry only **transient** errors; **fatal/permanent** errors should dead-letter early via a classifier. In the example, every exception is tried 3 times for simplicity, whereas production should classify them.
- **Bounded attempts** and backoff/jitter to avoid retry storms; avoid infinite unpaused requeues.
- DLX/DLQ declared, routing key exact, with retention and alarms. `defaultRequeueRejected=false` without a DLX can drop messages.
- With manual ack, every path must ACK/NACK or have an error policy so deliveries do not hang unacked.
- **Poison tests:** Assert the real message exists in the DLQ with matching body and metadata, not just exceptions/logs.
- **Duplicate tests:** At minimum verify repeated delivery does not double business effects. For higher confidence, test multiple replicas and crash points.

### 9.3. Consumer → database / external side effect

**At-least-once delivery + idempotent processing** is usually the practical choice. There is no default atomic transaction spanning a RabbitMQ ACK and an independent database. Example:

~~~text
1. Consumer receives message X.
2. Database COMMITS business work for X.
3. Consumer dies BEFORE broker receives ACK.
4. RabbitMQ redelivers message X.
5. Without persistent idempotency, the business effect runs a second time.
~~~

A common solution uses an **inbox table**:

~~~sql
CREATE TABLE processed_message (
    message_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

This is a suggested schema, not part of the runnable RabbitMQ project. Inside a DB transaction, the consumer attempts `INSERT processed_message(message_id,processed_at)`, executes business writes, and commits. A duplicate key indicates the ID was already processed, so skip the business effect per contract. After the transaction commits, the consumer ACKs. Design synchronization/inbox locking for concurrent deliveries and avoid marking "processed" before the business transaction succeeds.

**For external API side effects** (money transfers, emails, remote calls) that a database cannot roll back, use downstream idempotency keys or compensation/reconciliation. Never imagine a JDBC transaction can roll back an already-succeeded HTTP call.

### 9.4. DLQ → operations / replay

An unmonitored DLQ can hold errors until TTL expires or the queue fills up. Ensure:
- Alerts on **DLQ depth**, oldest message age, growth rate, and error types.
- Dashboards/structured logging with `messageId`, trace ID, error type, and attempt count. Never store raw PII/secrets in error headers.
- Quarantine controls, retention, and access control for messages containing sensitive data.
- Replay tooling with review/approval, dry runs, rate limiting, deduplication, and audit trails.
- When failures stem from schema deployment mismatches, fix the consumer version before replaying; never endlessly replay permanent failures back to the main queue.
- Careful TTL policies; certain TTL+DLX delay-retry topologies can create **death loops** without max-attempt cutoffs.

**Caution:** DLQ messages fetched via `RabbitTemplate.receive` are ACKed and removed from the DLQ. In the example that is an intentional test action. Production observability tools must never consume and delete DLQ messages just to gather statistics.

## 10. Backoff retries and retry queues vs. instant redelivery

A transient outage might need 2–30 seconds or several minutes to recover. Calling `basicNack(requeue=true)` immediately in a tight loop can spin thousands of times per second. There are three primary architectures (plus variations):

| Approach | Strengths | Risks |
|---|---|---|
| **In-process bounded retry** | Clean config, good for brief transient blips | Ties up consumer thread; requires rollback design with transactions |
| **Broker redelivery (`nack requeue=true`)** | Broker redelivers, handy when a worker dies | No built-in delay/budget; can hot-loop |
| **Delayed retry queue / TTL + DLX** | Spaces out attempts, frees consumer thread | Complex routing, `x-death` counting, poison loops |
| **Republish to retry exchange** | Explicit headers, scheduling, routing | Must ensure publish/ack atomicity or reconciliation |
| **Kafka retry topics / DLT** | Fits Kafka record model | Different from AMQP ACK, offsets, partitions/ordering |

Choose backoff suited to the failure class; when a downstream dependency is broadly failing, circuit breakers/rate limits/bulkheads may be needed. Retries should not amplify load against an already degraded dependency.

In Spring AMQP, `RetryInterceptorBuilder.stateless()` in the example uses `.backOffOptions(25,1.0,25)` for fast tests; never copy 25 ms blindly into production. If processing involves database transactions that must roll back between attempts, look at **stateful retry** with message IDs and container transaction semantics rather than treating stateless retry as universal.

## 11. RabbitMQ vs. Kafka: same goals, different APIs

You cannot apply `@RabbitListener`/`basicNack` directly to Kafka. In Spring Kafka:
- Listeners typically use `@KafkaListener` with consumer group/offset management.
- Failure handling uses **`DefaultErrorHandler`**, which can retry/seek with backoff policies.
- **`DeadLetterPublishingRecoverer`** can publish failed records to a **DLT topic** once retries exhaust.
- **`@RetryableTopic`** supports non-blocking retry topics and DLT per compatible Spring Kafka config.
- Offset commits, retry sequencing, partition ordering, and transactional producers/consumers differ from RabbitMQ queue ACKs.
- Kafka brokers retain logs; a "DLT" is a topic holding failed records, not a RabbitMQ DLQ/DLX.
- Tests should assert **records on the DLT topic**, keys/values/headers/correlation/partition/offset policies, not merely mock handler exceptions.

Equivalent diagrams:

~~~text
RabbitMQ:
main queue -> listener retry -> reject requeue=false
          -> DLX -> DLQ -> review/replay

Kafka:
main topic -> @KafkaListener / DefaultErrorHandler
           -> retry/seek or retry topic(s)
           -> DeadLetterPublishingRecoverer -> DLT topic
           -> review/replay
~~~

**Kafka-specific caveats:** Ordering guarantees within a partition can be affected by non-blocking retry topics; offset commits are not equivalent to RabbitMQ `basicAck`. Across multi-partition topics, never assert global ordering indiscriminately. For Kafka, use `EmbeddedKafka` or Kafka Testcontainers as appropriate; to verify real broker DLT behavior and persistence, broker integration tests are usually best.

Spring Kafka docs provide dedicated APIs for exception classification, backoff, delivery attempts, and DLT routing. Never "rename dead queue to dead topic" and reuse RabbitMQ tests as-is.

## 12. Negative tests and failure injection: proof against losing errors

Small mutations like these test whether your suite catches real failure-loss risks:

| Mutation/change | Expected failing test or gap to cover |
|---|---|
| Remove `RejectAndDontRequeueRecoverer` and swallow exceptions | Poison test finds no message in DLQ |
| Set `defaultRequeueRejected` to true while removing recoverer | Poison message requeues infinitely, test times out |
| Remove `deadLetterExchange` from work queue | Poison message never reaches DLQ |
| Change binding routing key from `failed` to `unknown` | DLQ receives no message |
| Catch `IllegalArgumentException` and return | Poison message is ACKed and lost from main queue |
| Change `maxAttempts(3)` to 2 | 3-attempt transient test fails or lands in DLQ |
| Remove `basicNack(...,true)` and ACK on first delivery | Redelivery test fails |
| Change `basicNack(...,true)` to `false` | Message is dropped/dead-lettered if configured, not redelivered |
| Remove `isCompleted` deduplication logic | Duplicate effects exceed 1 |
| Use a static `AtomicInteger` without separating IDs | Tests become order-dependent or noisy |
| Assert DLQ using only `"error"` log lines | Can falsely pass even when payload vanished |
| Inspect DLQ with `receive` in a production monitor | Monitor itself consumes and deletes failing messages |
| Make external HTTP call before DB commit then ACK | Crash/retry can duplicate remote side effects |
| Ignore publisher returns | Unroutable publishes can be mistaken for success |

**Conditional tests to add for production:**

1. **Producer confirmation:** Publish to an exchange with an unbound routing key, verify mandatory return and confirm; never settle for a green `convertAndSend`.
2. **Broker restart:** Send a persistent message to a durable/quorum queue, restart the broker cleanly, and verify the message is still readable. Requires real durable storage and container-control CI.
3. **Consumer crash after DB commit before ACK:** Kill the consumer process, let the broker redeliver, and assert the business effect happened once. The example's in-memory tracker resets, so this test must use a persistent DB.
4. **Broken DLX binding:** Break the binding in a disposable environment to verify monitoring/safeguards alert on dead-letter delivery failures.
5. **Poison payloads:** Test malformed payloads, unknown schema versions, bad headers, and content-type conversion failures occurring before the listener runs; verify error handler policy.
6. **Retry backoff:** Use a test clock/scheduler or broker timed retries instead of unreliable `Thread.sleep`.
7. **Concurrent duplicates:** Two consumers receive the same ID across two messages; database unique constraints/inbox must guarantee one side effect.
8. **Replay:** Re-publish a reviewed valid message back to the main queue; check audit, idempotency, and DLQ depth decreasing/not growing.
9. **Publisher→DB atomicity:** Outbox record commits before publishing; inject failure between the two steps; relay republishes without duplicating effects.
10. **DLQ retention:** TTL, size limits, quorum delivery-limit, and queue-full policies; verify operational handling when retention expires.

**No-loss claims must state their scope.** The 5 runnable tests prove behavior on a RabbitMQ container with the described topology, listeners, and fault scenarios. They do not prove immunity to all races, failovers, network partitions, or storage corruption.

## 13. Troubleshooting table

| Symptom | Common cause | Solution / test check |
|---|---|---|
| Failing message vanishes, DLQ empty | Listener catches-and-returns → ACK | Do not swallow exceptions; assert DLQ payload |
| Failing message vanishes on reject | Missing DLX, binding, or wrong routing key | Declare topology, assert queue metadata |
| Poison message causes log storm | Infinite `requeue=true` | Bounded retries, backoff, reject→DLQ |
| Always retries only once | Advice attached to wrong factory | Check `containerFactory` name and interceptor |
| Expected 3 attempts, observed 4 | Confused `maxAttempts` with retry count | `maxAttempts=3` includes the initial attempt |
| Broker deliveries=1 yet attempts=3 | Stateless retry within same delivery | Distinguish attempts from redeliveries |
| `redelivered=false` during internal retries | No broker requeue happened | Expected semantics; don't assert wrong flag |
| Manual listener never gets second delivery | Forgot `basicNack(..., true)` or ACKed early | Check `deliveryTag` and `requeue` flag |
| Message stuck unacked | Manual mode forgot ACK/NACK | Check every branch and consumer channel |
| DLQ has message without stack trace | `x-death` holds only broker metadata | Structured logs/error records/recoverer |
| `x-death` count differs from Java attempts | Retry advice doesn't dead-letter every attempt | Don't use `x-death` as an in-process retry counter |
| Tests fail randomly on CI | Asserted before async listener processed | Awaitility, unique message IDs, isolated broker |
| `@RabbitListener` does not subscribe | Wrong factory bean name, missing queue/declaration | Check `@RabbitListener`, `RabbitAdmin`, startup logs |
| `Could not connect to localhost:5672` | `ConnectionFactory` bypassed container endpoint | `@ServiceConnection` + Boot auto-config |
| `Queue declaration failed` | Queue already exists with different arguments | Disposable Docker/containers or broker policy migrations |
| Payload fails to convert to String | Mismatched content type/converter | Send String via `RabbitTemplate`, check converter |
| Dead-letter routed to wrong queue | DLX/binding key mismatch | Check `x-death.queue` and DLQ binding |
| Retries repeat business effects | Crash after DB commit before ACK, no dedup | Persistent inbox/idempotency table |
| RabbitMQ restart loses data | Non-durable queues/transient messages or cluster config | Durable/persistent/quorum + restart tests |
| Unroutable publish treated as OK | Mandatory returns unhandled | Publisher returns + confirms + alerts |
| Growing DLQ goes unnoticed | No queue depth/oldest age metrics | Alerts/dashboards/replay procedures |
| Only looking at logged exceptions | Logs can rotate or lose context | Broker state assertions and trace IDs |
| Kafka DLT test uses RabbitMQ matchers | Different broker semantics | Kafka error handler/DLT topic integration |

### 13.1. Pre-merge checklist for messaging changes

1. **Topologies:** Queues/exchanges/DLX/DLQ declared properly without typos in routing keys.
2. **Ack mode:** Know whether you are in `AUTO`, `MANUAL`, or `NONE`; never confuse `AUTO` with broker autoack.
3. **Failure policy:** Separate transient vs. fatal errors; finite max attempts and backoff.
4. **Exhaustion:** After retries, proper recoverer runs; message goes to DLQ or persistent failure ledger rather than wrong ACK.
5. **Evidence:** Tests assert broker DLQ payload, `x-death`, processing counts, and zero unwanted business effects.
6. **Redelivery:** Test a NACK/requeue or crash scenario; never equate retry attempts with broker delivery counts.
7. **Idempotency:** Duplicate messages never repeat business effects; production uses persistent deduplication.
8. **Publisher:** Confirms, returns, mandatory, and outbox designed per reliability needs.
9. **Operations:** Metrics, alarms, retention, replay tooling, access control, and auditing.
10. **Isolation:** Dedicated Docker test broker, isolated message IDs, Awaitility instead of fixed sleeps.
11. **Security:** Never leak PII/tokens/secrets in exceptions, `x-death`, or public logs.
12. **Compatibility:** Spring Boot 3.3.5/Spring AMQP 3.1.x APIs, RabbitMQ broker version, and factory configs verified.
13. **Rollback:** DB transactions and Rabbit ACKs are not treated as one atomic transaction unless explicitly designed.
14. **Timeout:** Poison tests have finite deadlines and clear failures rather than waiting indefinitely.
15. **Evidence over optimism:** "Tests passed" must rest on broker/business state assertions, not method invocation counts alone.

## 14. Self-practice exercises

**Exercise 1 — Retry count:** Change `.maxAttempts(3)` to `.maxAttempts(2)`. Does the transient message still succeed? Which test catches it?

**Exercise 2 — Broken DLQ:** Remove the DLX from the work queue on a **disposable** H2/RabbitMQ setup and send a poison message. Why does `RejectAndDontRequeueRecoverer` not guarantee the message is preserved? Propose a startup topology test.

**Exercise 3 — Normal return:** Catch and swallow `IllegalArgumentException` inside `WorkListener`, then re-run the poison test. What happens to the broker ACK and the DLQ?

**Exercise 4 — Redelivery:** Replace `basicNack(tag,false,true)` with `basicAck(tag,false)` on the first delivery. Compare attempts and the `redelivered` flag.

**Exercise 5 — Idempotency:** Replace the in-memory completed set with a `processed_message` table having a `PRIMARY KEY` and business effects in the same DB transaction. Write a concurrent duplicates test.

**Exercise 6 — Crash window:** Design failure injection between DB commit and Rabbit ACK. Why does at-least-once delivery need deduplication even when the listener itself has no retries?

**Exercise 7 — Headers:** Add `messageId`, correlation ID, and `schemaVersion` to each Rabbit message; verify they are preserved in the DLQ. Never log secrets.

**Exercise 8 — Error taxonomy:** Distinguish `IllegalArgumentException` (fatal) from `IOException` (transient); attach a retry classifier and verify fatal errors dead-letter without burning 3 attempts if policy requires.

**Exercise 9 — Publisher loss:** Enable correlated publisher confirms and mandatory returns. Send to an exchange/routing key with no binding on a disposable broker and verify the return callback.

**Exercise 10 — Replay:** Read a failed payload from the DLQ, fix the failure condition, republish with the defined ID/correlation policy, record an audit entry, and verify business effects do not duplicate.

**Exercise 11 — Delay:** Design a TTL + DLX retry queue with an attempt cap; explain how to avoid a poison loop as `x-death` grows.

**Exercise 12 — Kafka:** Port the model to Spring Kafka `DefaultErrorHandler` + `DeadLetterPublishingRecoverer`; test the DLT topic with Kafka Testcontainers without using RabbitMQ `x-death` semantics.

**Exercise 13 — Observability:** Design a dashboard for messages processed, retries, DLQ depth, oldest message age, returned publications, and consumer lag. Which trends trigger alerts?

**Exercise 14 — Migration:** When upgrading Boot 3.3 to a new major version, re-verify retry advice interfaces, container factories, Testcontainers `@ServiceConnection`, and RabbitMQ broker DLX handling.

## 15. Official References

- [Spring AMQP 3.1 — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/3.1/amqp/resilience-recovering-from-errors-and-broker-failures.html): stateless/stateful retry, recoverers, and consumer error handling.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): `defaultRequeueRejected`, fatal conversion errors, AMQP listener exception semantics.
- [Spring AMQP 3.1 API — MessageProperties](https://docs.spring.io/spring-amqp/docs/3.1.x/api/org/springframework/amqp/core/MessageProperties.html): `getDeliveryTag`, `isRedelivered`, `getXDeathHeader`.
- [Spring AMQP 3.1 API — RetryInterceptorBuilder](https://docs.spring.io/spring-amqp/docs/3.1.x/api/org/springframework/amqp/rabbit/config/RetryInterceptorBuilder.html): `stateless`, `stateful`, `maxAttempts`, `backOffOptions`.
- [Spring AMQP — Rabbit Listener Container Acknowledgments](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `AUTO`/`MANUAL`/`NONE` acknowledge modes.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-letter reasons, queue policies, and routing to DLQ.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): `basicAck`/`basicNack`/`basicReject`, publisher confirms.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection`, `RabbitConnectionDetails`, and typed `RabbitMQContainer`.
- [Testcontainers for Java — RabbitMQ](https://java.testcontainers.org/modules/rabbitmq/): `RabbitMQContainer` and Docker runtime.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, DLT.
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): `@RetryableTopic`, retry topics, and DLT.

**Remember:** **Retry** is re-attempting processing, **redelivery** is the broker delivering a message again, and **dead-lettering** is routing unprocessable messages via a DLX to a DLQ; the three mechanisms are not synonymous. With RabbitMQ and Spring Boot, bound retries, avoid infinite requeues, ACK on success, and reject without requeue to dead-letter once attempts exhaust. A good test verifies **real payload in the DLQ + `x-death` + attempts + business effects**, not merely logged exceptions. Achieving production reliability additionally requires **publisher confirms/returns, durable topology, persistent idempotency/outbox, metrics, and controlled replay**. No single retry annotation guarantees "zero lost errors" across every failure boundary.
