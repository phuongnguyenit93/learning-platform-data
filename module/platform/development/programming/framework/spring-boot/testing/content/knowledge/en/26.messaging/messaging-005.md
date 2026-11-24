# Topics, Queues, Consumer Groups, and Test Data Isolation

## 1. Why are messaging tests often flaky or misleading?

A synchronous API usually has one call and one return value. Messaging is different: producers, brokers, partitions/queues, consumers, acknowledgments, offsets, retries, and dead-letter processing operate across multiple threads and points in time. If a test simply calls `send(...)` and immediately asserts a variable, it easily fails because the consumer has not finished processing yet. If a test reuses a topic, queue, or consumer group from a previous run, it may read stale data and falsely PASS, have another test's consumer steal messages, or skip events because offsets were already committed.

This lesson focuses on one clear goal: **understanding topics, queues, consumer groups, and designing isolated data and infrastructure for reliable messaging tests** in Spring Boot.

You will learn:

1. Distinguish Kafka **topic/partition/consumer group/offset** from RabbitMQ **exchange/queue/binding/competing consumers**.
2. Understand how many consumers can receive a message: **once within a group**, each **different group** reading independently, or each **different queue** receiving a copy if the exchange routes that way.
3. Distinguish broker acknowledgments, consumer processing, Kafka offset commits, RabbitMQ basicAck/NACK, and business side effects.
4. Create unique topics, unique group IDs, unique queues/exchanges, and unique event IDs per test or test class.
5. Use Testcontainers instead of production/shared environments; understand `@ServiceConnection`, `@DynamicPropertySource`, and Spring TestContext caching.
6. Wait for listener/container readiness and message receipt using time-bounded signals, without `Thread.sleep`.
7. Maintain isolation under parallel execution, replay and `auto-offset-reset`, partition ordering, redelivery, and duplicate messages.
8. Know when to use `@EmbeddedKafka`, Kafka Testcontainers, RabbitMQ Testcontainers, and when multi-node integration is required.
9. Use domain fixtures carrying `testRunId`/`correlationId` and assertions that guard against picking up the wrong message.
10. Build **two standalone Maven projects** with Java 17, Spring Boot 3.5.16, JUnit Jupiter, and containerized brokers via Testcontainers:
    - Kafka: Spring `@KafkaListener` with unique topic/group; test two consumers in the same group and one consumer in a different group.
    - RabbitMQ: Spring `@RabbitListener` with a dedicated queue; test a fanout exchange to two queues and prove each queue receives its own copy.

**Testing goal:** Not just "the message was sent", but verifying **who receives it**, **how many times**, **in which partition/queue**, **when it is acknowledged**, and **whether data from other tests can leak in**.

> The labs run real brokers on Docker/Testcontainers. Code has been reviewed for structure and API compatibility with Boot 3.5/Spring Kafka 3.3/Spring AMQP 3.2; Maven/Docker results must be verified by running in an environment with Docker. Never treat a test as PASS if Surefire reports SKIPPED.

## 2. Concept map: Kafka and RabbitMQ are not one-to-one equivalents

### 2.1. Kafka: append-only logs by topic and partition

Kafka appends messages to **partition logs** of a topic. A topic has one or more partitions, and each record has an offset **within its partition**; the offset is a read position, not a business message ID.

~~~text
Producer -> Kafka topic orders.created
                       |
           +-----------+-----------+
           |                       |
     Partition 0               Partition 1
     offset 0: A               offset 0: C
     offset 1: B               offset 1: D
           |                       |
           +-----------+-----------+
                       |
                 Consumer Group G1
                  c1 <-> p0
                  c2 <-> p1

                 Consumer Group G2
                  c3 <-> p0,p1
~~~

Within a stable group, each partition is normally assigned to **at most one consumer member of that group at a time**. The two consumers in G1 split the partitions; G2's consumer can read **the same records** independently because G2's offsets do not depend on G1.

Never assume a record on Kafka is processed exactly-once by default: a consumer may finish processing and crash before committing its offset, then read it again. Delivery/processing should usually be designed as **at-least-once with idempotency** unless using and properly verifying supported transactional semantics within a well-defined boundary.

### 2.2. RabbitMQ: exchanges route to queues

A producer in AMQP sends messages to an **exchange**. The exchange uses bindings and routing keys to place messages into one or more **queues**. Consumers receive messages from a queue, rather than directly "subscribing to a Kafka topic".

~~~text
                           fanout exchange
                          /               \
Producer -> event       /                 \
                      queue.shipping     queue.analytics
                           |                 |
                       consumer A         consumer B
                           |                 |
                      event copy         event copy
~~~

If **two consumers share the same queue**, they are competing consumers: a single delivery is normally sent to **one consumer** at a time; if it is unacked when a connection drops or it is nacked/requeued, the message may be redelivered, possibly to another consumer.

~~~text
Producer -> exchange -> queue.jobs
                           |
                       +---+---+
                       |       |
                  worker A   worker B

One message in queue.jobs is distributed to one worker;
A and B do not reliably both receive a copy.
~~~

To ensure each independent subscriber gets **its own copy** of an event, create **separate queues** and bind them to a fanout/topic exchange per the routing contract.

### 2.3. Comparison table

| Aspect | Kafka | RabbitMQ/AMQP |
| --- | --- | --- |
| Where producer writes | Topic (partitioned log) | Exchange with routing key |
| Consumer subscription | Topic/partitions via group | Queue |
| Independent broadcast | Different consumer groups read the log separately | Separate queues routed by the exchange |
| Workload sharing | Partition assignment within one group | Competing consumers on the same queue |
| Read position | Offset per topic-partition and group | Queue tracks pending/unacked deliveries |
| Message after consumption | Usually remains on log per retention | Usually removed from queue on ack |
| Replay | Seek/reset/new group + retained data | Must requeue/republish or use another store |
| Ordering | Within **one partition** (with retry/producer config caveats) | Queue order can shift across multiple consumers/requeues/priorities |
| Acknowledgment | Producer broker ack differs from consumer offset commit | Publisher confirm differs from consumer `basicAck` |
| Isolation identifier | Topic, `group.id`, key, `eventId` | Exchange, queue, routing key, `messageId` |
| Test startup | Metadata/topic readiness, group assignment | Queue/exchange/binding declaration, listener readiness |
| Testcontainers | `KafkaContainer`/`ConfluentKafkaContainer` | `RabbitMQContainer` |
| Spring listener | `@KafkaListener` | `@RabbitListener` |

**Do not call RabbitMQ a "topic" without clarifying whether you mean `TopicExchange` or a publish/subscribe pattern; it is not a Kafka topic.**

## 3. Kafka topics/partitions/groups: what must be verified properly

### 3.1. Topics retain data per retention policy

Kafka consumers read records from a log; they do not delete a record just because it was processed. Retention depends on time/size/compaction, not group commits. A shared test topic across CI runs may contain old records.

To prevent issues:
- Dedicated topic per class/test when strong isolation is needed.
- Include `testRunId` and `eventId` in payload/key/headers.
- Create a fresh group ID if you want to read from the beginning.
- Choose `auto-offset-reset=earliest` when a new group has no committed offsets yet and the test needs to read already-sent records.
- Do not use `earliest` as a way to wipe old backlogs: a shared topic still holds historical data.
- With multiple partitions, do not rely on global ordering across records.

### 3.2. Consumer groups and assignment

In group G:
- 2 partitions, 1 consumer → the consumer can receive both.
- 2 partitions, 2 consumers → each consumer is typically assigned one partition.
- 2 partitions, 3 consumers → one consumer is normally idle because there are fewer partitions than consumers.
- A single partition is not processed concurrently by two members **at the same time** within a stable group.
- When members join/leave, rebalances shift assignments; across rebalances, a record may be processed more than once depending on offset-commit/side-effect timing.

Do not assert "consumer A receives partition 0 specifically" if the assignment strategy does not guarantee it; tests should assert **each partition is assigned to one group member** and the union of results is complete.

### 3.3. Offsets and auto.offset.reset

`auto.offset.reset` only decides where to start when the group **has no valid committed offset** (or the offset is invalid/out of range):
- `earliest`: start from the earliest retained log record.
- `latest`: start at the end of the retained log; messages sent **before** a new consumer group initializes may be missed.
- `none`: fail if no valid offset exists.

If a group has already committed an offset, changing to `earliest` does not reset the group back to the start. To replay deliberately, use a new group, seek, or use Kafka admin offset resets properly.

### 3.4. Keys and partition ordering

Kafka producers take a key; the same key (with a stable partitioner/partition count) typically maps to the same partition. Ordering is guaranteed by offset **within a partition**; if records span multiple partitions, there is no total order across the topic.

Tests may specify an explicit partition in producer tests to make group distribution deterministic. However, production keying/partitioning must be tested separately if rules depend on ordering per customer/order ID.

### 3.5. Producer send ack is not consumer processed

~~~java
SendResult<String, String> result =
        template.send(topic, key, value).get(10, TimeUnit.SECONDS);
~~~

This snippet assumes `KafkaTemplate` and `TimeUnit` in scope. Future success proves the producer received the Kafka send result per `acks` and config, **not** that the consumer business handler ran, DB writes committed, or all subscribers received it.

Use a dedicated latch/probe/DB readback for consumer outcomes.

## 4. RabbitMQ exchanges, queues, and bindings

### 4.1. Direct, topic, and fanout exchanges

- **DirectExchange**: routing key matches the binding key exactly.
- **TopicExchange**: pattern-based routing; `*` matches one word, `#` matches zero or more words (words separated by dots).
- **FanoutExchange**: routes a copy to every bound queue, ignoring the routing key.
- **HeadersExchange**: routes by header conditions when required.

Example:

~~~text
TopicExchange: events.topic
  Binding shipping.q: "orders.created"
  Binding audit.q:    "orders.#"

Publish routingKey "orders.created":
  -> shipping.q
  -> audit.q

Publish routingKey "payments.captured":
  -> neither queue above
~~~

Do not confuse Kafka topic partitions with RabbitMQ `TopicExchange`; the names sound similar, yet consumption and retention work differently.

### 4.2. Default exchange

RabbitMQ has an unnamed default direct exchange `""`. Every queue is normally auto-bound with a routing key equal to its queue name, so in Spring:

~~~java
rabbitTemplate.convertAndSend("", queueName, payload);
~~~

sends to the queue named `queueName` via the default exchange. This is **not** a producer "sending directly to a queue" at the AMQP protocol level; routing still passes through the default exchange.

### 4.3. Competing consumers on the same queue

If `queue.jobs` has two `@RabbitListener` instances or listener `concurrency=2`, each ready message goes to one consumer delivery; the broker does not duplicate it to both. If a consumer fails and issues `basicNack(requeue=true)`, the message can be redelivered. Hence "the queue processes every message once" is **too strong** an assumption unless acks/transactions/idempotency are explicitly verified.

Use a unique `messageId`/idempotency key and business-side deduplication when repeated processing has side effects.

### 4.4. Two independent queues receiving a broadcast

With a fanout exchange:
- Every bound queue receives a copy of the event (provided the exchange/queues/bindings exist at publish time).
- Queue A's consumer ACKing does not affect Queue B's delivery.
- A slow Queue B keeps its own backlog.
- A new queue bound after an event was published **does not replay** old events: Rabbit classic queues differ from Kafka's retained log.

### 4.5. Queues, ack, nack, and dead-letter

- **Consumer ack**: confirms a delivery was processed so the broker can remove it from the queue.
- **Nack/reject + requeue**: puts the message back on the queue, potentially repeating.
- **Nack/reject without requeue**: message may be dropped or dead-lettered if the queue has a DLX configured.
- **Publisher confirm**: confirms to the publisher that the broker accepted the publish (per config), not that consumers processed it.
- **Mandatory return**: detects publishes that do not route to any queue when configured; publisher confirms can still succeed for unroutable messages if returns are not checked.

Reliability tests must verify ack/nack/DLX explicitly rather than only checking that `RabbitTemplate.convertAndSend` threw no exception.

## 5. Why do messaging tests contaminate each other so easily?

### 5.1. Sharing fixed topics or queues

Test A sends an event to `orders.created`; test B sends at the same time; consumer B might receive A's event or count both. Shared brokers between local runs and CI may even hold yesterday's records. Tests that only assert "at least one event" falsely PASS easily.

**Solution:** unique resource names per test class/run, e.g., `orders.test.<random-id>` or `orders.test.2026...`, `testRunId` on events, and clear cleanup/lifecycle.

### 5.2. Sharing a Kafka `group.id`

Two test processes sharing a `group.id` can join the same group and split partitions. When each process expects to receive all messages, one test misses records. A consumer group is a **logical consumption unit**, not an arbitrary name that can be shared harmlessly.

### 5.3. Reusing Rabbit queues across tests

Two listeners on the same queue **compete** for messages. Test A can accidentally steal Test B's messages. Use unique queue names for independent subscribers, or run isolated brokers/containers.

### 5.4. Poorly timed queue cleanup

Calling `purgeQueue` in Test A while Test B uses the same queue deletes Test B's messages. Deleting a shared queue or topic can break other consumer groups. Never clean up by purging/deleting shared team resources; namespace test resources and clean up only those owned by the test.

### 5.5. "Waiting 1 second" does not solve contamination

`Thread.sleep(1000)` merely delays; it does not distinguish message origin. A proper test needs:
- A distinct correlation ID or `eventId`.
- The right destination/topic/group.
- Bounded awaits and exact payload checks.
- Count/negative assertions when the contract requires them.
- Resource ownership/cleanup.

## 6. Levels of test data isolation

| Isolation level | Kafka | RabbitMQ | When to use |
| --- | --- | --- | --- |
| Broker/container per class | Dedicated `KafkaContainer` | Dedicated `RabbitMQContainer` | Reliable integration tests when Docker is available |
| Topic/queue per test class | Unique topic + group | Unique queue/exchange | Shared broker where each class is isolated |
| Resource per test method | `NewTopic` + fresh group | Declare fresh queue/exchange | Parallel methods or specialized tests |
| Event-level isolation | `eventId`/`testRunId`/header | `messageId`/`correlationId`/header | Filtering/correlating within tests |
| Consumer state isolation | Fresh consumer group/intentional offset reset | Independent queue + ack state | Replay, repeated tests |
| Application context isolation | Unique Spring properties / context lifecycle | Unique queue property / listener lifecycle | Multiple `@SpringBootTest` classes |
| Post-test cleanup | Delete test topics/ephemeral container | Delete test queues/exchanges/ephemeral container | Preventing leftover data |

**No single measure suffices for every case.** A unique `eventId` does not stop Consumer A from stealing Message B and ACKing it; unique queues/topics protect at the broker level. Conversely, a dedicated container does not replace correlation IDs when a test emits multiple messages in the same flow.

### 6.1. Isolation for Spring contexts

`@KafkaListener(topics="${lab.kafka.topic}", groupId="${lab.kafka.group}")` resolves placeholders when the context is created. If you want to change topics between test methods sharing a cached `ApplicationContext`, mutating a Java static variable at runtime **does not** automatically re-subscribe the listener. For topic-per-method, create listener containers/consumers programmatically or use separate contexts rather than trying to alter properties after context startup.

`@RabbitListener(queues="${lab.rabbit.queue}")` behaves similarly. Prefer resource-per-class as in these two labs, or declare/subscribe programmatically inside the test method for resource-per-test.

### 6.2. Unique IDs and assertions

A minimal payload might be:

~~~json
{
  "eventId": "test-abc-event-001",
  "testRunId": "run-abc",
  "orderId": "order-42",
  "type": "ORDER_CREATED",
  "version": 1
}
~~~

Event IDs should carry meaning to assert the exact message. The Kafka lab uses a simple String payload `eventId|CREATED`, and the Rabbit lab uses String messages to focus on routing semantics. Real systems usually use JSON/Avro/Protobuf with schema/version compatibility.

### 6.3. Naming resources

Resource names must obey broker rules:
- Kafka topic names typically allow letters, numbers, `. _ -`; length limits and character rules should be checked against the broker/version.
- Rabbit queue/exchange names also have restrictions/ownership; avoid system-reserved prefixes like `amq.`.
- Use a stable prefix like `it.orders.` + short random ID for easy debugging.
- Never embed real customer names, PII, or secrets into resource IDs.

## 7. Kafka lab: runnable Java 17 / Spring Boot 3.5.16

### 7.1. Scope

**First standalone project.** A real Kafka broker runs in Testcontainers. The Spring Boot context configures producer, listener, and `NewTopic`; a test checks message roundtrip. A plain Java JUnit class uses low-level Kafka clients to test **two members in the same group** and **an independent group** on a dedicated topic.

No need to download/start Kafka manually via shell outside Testcontainers. Requires Docker capable of running the Apache Kafka single-node image with sufficient resources (RAM/CPU/network).

### 7.2. File tree

~~~text
kafka-topic-isolation-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/kafkalab/
│   ├── KafkaLabApplication.java
│   ├── KafkaTopicConfiguration.java
│   ├── ReceivedOrders.java
│   └── OrderConsumer.java
└── src/test/java/com/example/kafkalab/
    ├── KafkaSpringTopicIsolationTest.java
    └── KafkaConsumerGroupSemanticsTest.java
~~~

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>kafka-topic-isolation-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.kafka</groupId>
      <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.kafka</groupId>
      <artifactId>spring-kafka-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>kafka</artifactId>
      <scope>test</scope>
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
~~~

The Boot 3.5 BOM manages compatible dependencies, including the Testcontainers 1.x module `org.testcontainers:kafka`. If a project upgrades to Testcontainers 2.x, module coordinates may change (e.g., `testcontainers-kafka`); check the BOM/imports for that version rather than blindly copying the same package.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
lab.kafka.topic=orders.local
lab.kafka.group=orders.local.consumer
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.listener.ack-mode=record
~~~

`localhost:9092` is a **fallback for running the app outside tests** when you intentionally run a local broker. In JUnit Testcontainers, `@ServiceConnection` provides `KafkaConnectionDetails` from the container so runtime bootstrap servers **do not** depend on this fixed port; dynamic properties override topic/group.

Consumer config `auto-offset-reset=earliest` only helps a fresh group with no offsets. It does not clear history from a shared topic/group. `ack-mode=record` commits offsets after the listener processes each record per Spring Kafka container semantics, though external DB/broker transactions still need dedicated design.

### 7.5. KafkaLabApplication.java

~~~java
package com.example.kafkalab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KafkaLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(KafkaLabApplication.class, args);
    }
}
~~~

Spring Boot auto-configures Kafka when `spring-kafka` is present and discovers `@KafkaListener` via annotation infrastructure. Do not add a custom consumer factory when Boot defaults suffice. When production needs SASL/SSL security, schema registry, or transactions, configure per the broker contract.

### 7.6. KafkaTopicConfiguration.java

~~~java
package com.example.kafkalab;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration(proxyBeanMethods = false)
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic(
            @Value("${lab.kafka.topic}") String topicName) {
        return TopicBuilder.name(topicName)
                .partitions(2)
                .replicas(1)
                .build();
    }
}
~~~

Spring Boot's `KafkaAdmin` picks up `NewTopic` beans to create topics if they do not exist. Two partitions suffice for demonstrating consumer-group sharing. Single-node Kafka Testcontainers uses replication factor 1; this is **not** a production HA recommendation.

Note: Topic creation is an infrastructure setup step, **not** a test of production topic retention/replay. In CI, check logs/admin metadata if the listener cannot receive an assignment.

### 7.7. ReceivedOrders.java

~~~java
package com.example.kafkalab;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.stereotype.Component;

@Component
public class ReceivedOrders {

    private final BlockingQueue<ConsumerRecord<String, String>> records =
            new LinkedBlockingQueue<>();

    void record(ConsumerRecord<String, String> event) {
        records.add(event);
    }

    public ConsumerRecord<String, String> await(
            Duration timeout) throws InterruptedException {
        return records.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

The probe is an **in-memory observation** so the test can await the listener, not an offset store or production consumer. Using `BlockingQueue.poll` with a deadline avoids calling `Thread.sleep`. With multiple test methods, filter/match `eventId`, isolate state, or clear the probe safely; this lab has only one integration method for this topic listener.

### 7.8. OrderConsumer.java

~~~java
package com.example.kafkalab;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private final ReceivedOrders probe;

    public OrderConsumer(ReceivedOrders probe) {
        this.probe = probe;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "${lab.kafka.topic}",
            groupId = "${lab.kafka.group}")
    public void onOrder(ConsumerRecord<String, String> record) {
        probe.record(record);
    }
}
~~~

Annotation property placeholders resolve when the Spring context creates the listener. Different group IDs maintain independent offsets. Storing the record in a queue is just a probe; production listeners must also validate schemas, perform idempotent writes/side effects, and handle failures/retries properly.

### 7.9. KafkaSpringTopicIsolationTest.java

`src/test/java/com/example/kafkalab/KafkaSpringTopicIsolationTest.java`:

~~~java
package com.example.kafkalab;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.utils.ContainerTestUtils;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class KafkaSpringTopicIsolationTest {

    private static final String RUN_ID =
            UUID.randomUUID().toString().replace("-", "");

    private static final String TOPIC =
            "it.orders." + RUN_ID;

    private static final String GROUP =
            "it.orders.consumer." + RUN_ID;

    @Container
    @ServiceConnection
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("lab.kafka.topic", () -> TOPIC);
        registry.add("lab.kafka.group", () -> GROUP);
    }

    @Autowired
    KafkaTemplate<String, String> producer;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    ReceivedOrders received;

    @Test
    void uniqueTopicAndGroupReceiveOnlyOurEvent()
            throws Exception {
        var listener = registry.getListenerContainer(
                "ordersListener");
        assertThat(listener).isNotNull();

        // Wait until the listener is assigned both 2 partitions
        // before the producer sends the message.
        ContainerTestUtils.waitForAssignment(listener, 2);

        String eventId = "event-" + RUN_ID;
        String payload = eventId + "|CREATED";

        var sendResult = producer.send(
                TOPIC, eventId, payload)
                .get(20, TimeUnit.SECONDS);

        assertThat(sendResult.getRecordMetadata().topic())
                .isEqualTo(TOPIC);

        ConsumerRecord<String, String> event =
                received.await(Duration.ofSeconds(15));

        assertThat(event).isNotNull();
        assertThat(event.topic()).isEqualTo(TOPIC);
        assertThat(event.key()).isEqualTo(eventId);
        assertThat(event.value()).isEqualTo(payload);
        assertThat(event.partition()).isBetween(0, 1);
        assertThat(event.offset()).isGreaterThanOrEqualTo(0L);
    }
}
~~~

**What is verified?**
- The Kafka broker is a **real container**, not a Mockito fake producer.
- Topic/group have random run-specific suffixes, so old consumer offsets from other tests are not read.
- `@ServiceConnection` supplies the right bootstrap servers; the Spring context does not hit a local/production broker.
- `@DynamicPropertySource` supplies the right names for `NewTopic`/`@KafkaListener`.
- `ContainerTestUtils.waitForAssignment` waits for consumer subscription/partition assignment, preventing races where the producer sends too early; this is a `spring-kafka-test` helper.
- `send(...).get` awaits the broker send result, and `received.await` awaits **listener** execution.
- Assertions check topic, key, payload, partition, and offset to reduce false positives.
- Does not assert global ordering across partitions.

**Caveat:** Only runs for real when Docker is present. `disabledWithoutDocker=true` skips the class if Docker is unavailable; CI integration jobs must report executed test counts and never treat skipped as PASS.

### 7.10. KafkaConsumerGroupSemanticsTest.java

This class uses **Apache Kafka clients directly** with a fresh topic per method: two consumers in the same group and one consumer in a different group. No Spring context is needed because the goal is broker group semantics, and the test creates the topic/clients/teardown inside method scope.

`src/test/java/com/example/kafkalab/KafkaConsumerGroupSemanticsTest.java`:

~~~java
package com.example.kafkalab;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers(disabledWithoutDocker = true)
class KafkaConsumerGroupSemanticsTest {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @Test
    void sameGroupSharesPartitionsDifferentGroupReplaysAll()
            throws Exception {

        String runId = UUID.randomUUID()
                .toString().replace("-", "");
        String topic = "it.groups." + runId;

        String sharedGroup = "it.shared." + runId;
        String independentGroup = "it.independent." + runId;

        try (AdminClient admin = AdminClient.create(Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers()))) {
            admin.createTopics(List.of(
                    new NewTopic(topic, 2, (short) 1)))
                    .all()
                    .get(30, TimeUnit.SECONDS);
        }

        try (KafkaConsumer<String, String> first =
                        consumer(sharedGroup);
             KafkaConsumer<String, String> second =
                        consumer(sharedGroup);
             KafkaConsumer<String, String> independent =
                        consumer(independentGroup);
             KafkaProducer<String, String> producer =
                        producer()) {

            first.subscribe(List.of(topic));
            second.subscribe(List.of(topic));
            independent.subscribe(List.of(topic));

            awaitAssignments(first, second, independent);

            List<String> expected = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                String id = "event-" + runId + "-" + i;
                expected.add(id);

                // Both partition 0 and 1 receive records.
                producer.send(new ProducerRecord<>(
                                topic,
                                i % 2,
                                "order-" + i,
                                id))
                        .get(15, TimeUnit.SECONDS);
            }

            List<String> sharedValues = new ArrayList<>();
            List<String> independentValues =
                    new ArrayList<>();

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(20);

            while (System.nanoTime() < deadline
                    && (sharedValues.size() < expected.size()
                        || independentValues.size()
                                < expected.size())) {

                collect(first.poll(Duration.ofMillis(150)),
                        sharedValues);
                collect(second.poll(Duration.ofMillis(150)),
                        sharedValues);
                collect(independent.poll(Duration.ofMillis(150)),
                        independentValues);
            }

            assertThat(first.assignment()).hasSize(1);
            assertThat(second.assignment()).hasSize(1);
            assertThat(independent.assignment()).hasSize(2);

            // Two consumers in the same group split 8 records;
            // combined total is 8, not 8 each.
            assertThat(sharedValues)
                    .containsExactlyInAnyOrderElementsOf(
                            expected);

            // Independent group reads all 8 retained records.
            assertThat(independentValues)
                    .containsExactlyInAnyOrderElementsOf(
                            expected);

            assertThat(new HashSet<>(sharedValues))
                    .hasSize(8);
        }
    }

    private KafkaConsumer<String, String> consumer(
            String groupId) {
        Map<String, Object> props = new HashMap<>();
        props.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers());
        props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false);
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        return new KafkaConsumer<>(props);
    }

    private KafkaProducer<String, String> producer() {
        Map<String, Object> props = new HashMap<>();
        props.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                kafka.getBootstrapServers());
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        return new KafkaProducer<>(props);
    }

    private static void collect(
            ConsumerRecords<String, String> batch,
            List<String> sink) {
        for (ConsumerRecord<String, String> record : batch) {
            sink.add(record.value());
        }
    }

    private static void awaitAssignments(
            KafkaConsumer<String, String> a,
            KafkaConsumer<String, String> b,
            KafkaConsumer<String, String> c) {

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(25);

        while (System.nanoTime() < deadline) {
            a.poll(Duration.ofMillis(150));
            b.poll(Duration.ofMillis(150));
            c.poll(Duration.ofMillis(150));

            if (a.assignment().size() == 1
                    && b.assignment().size() == 1
                    && c.assignment().size() == 2) {
                return;
            }
        }

        throw new IllegalStateException(
                "Kafka group assignment not ready");
    }
}
~~~

**Deep explanation:**

- `AdminClient` creates a unique topic with **two partitions** before consumers join.
- Two consumers share **the same group ID**. Kafka distributes partitions across members; the test does not assert which member gets partition 0.
- The third consumer belongs to a **different group ID**, gets assigned both partitions, and reads all retained records.
- Using a fresh group, `auto-offset-reset=earliest`, and a fresh topic keeps offsets completely isolated with no dependency on previous runs.
- `awaitAssignments` polls until group assignments stabilize in the expected shape with a 25-second deadline; it is not a fixed sleep.
- The producer sends 8 records explicitly to partitions 0 and 1 so it does not rely on key hash/partitioner behavior.
- Both members of the shared group are polled in a loop and their results unioned; the independent group is also polled until all 8 arrive.
- The test does not commit offsets because the goal is delivery/assignment within the current test session, not restart/resume behavior.
- `containsExactlyInAnyOrderElementsOf` avoids assuming **global ordering** across partitions.
- If the broker rebalances aggressively, a record might be reprocessed; this stable-assignment test does not prove exactly-once under failures. Failure/rebalance scenarios require separate tests.

**Test isolation perspective:** Unique topic *and* group inside the method are what prevent the test from reading old backlogs. Changing only the group ID on a shared topic that already has historical messages can still cause `earliest` to read messages not belonging to the test.

### 7.11. Running the Kafka lab

~~~bash
mvn -q clean test
mvn -q -Dtest=KafkaSpringTopicIsolationTest test
mvn -q -Dtest=KafkaConsumerGroupSemanticsTest test
~~~

When Docker is available and tests execute:
- The Kafka Spring test publishes/reads one event with a unique topic/group.
- The group semantics test creates an isolated topic and proves the shared group together receives 8 events while the independent group receives 8 events.
- Maven returns exit code 0 on success, with reports in `target/surefire-reports`.

There is no fixed stdout because Docker/image pulls, Kafka startup, group joins, and OS differ. **Do not equate an exit code 0 build where all tests were SKIPPED with an integration PASS.**

## 8. RabbitMQ lab: queue and exchange isolation

### 8.1. Scope

**Second standalone Maven project**, using `RabbitMQContainer`. The first test verifies a Spring `@RabbitListener` receives a message on a unique queue; the second test creates a fanout exchange and two independent queues, asserting each queue receives a copy.

There is no listener competition on the fanout queues; `RabbitTemplate.receiveAndConvert` pulls directly from each queue to show the routing result. The `@RabbitListener` queue is completely separate from the two fanout test queues.

### 8.2. File tree

~~~text
rabbit-queue-isolation-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/rabbitlab/
│   ├── RabbitLabApplication.java
│   ├── RabbitQueueConfiguration.java
│   ├── ReceivedMessages.java
│   └── OrderQueueListener.java
└── src/test/java/com/example/rabbitlab/
    └── RabbitMessagingIsolationTest.java
~~~

### 8.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>rabbit-queue-isolation-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>rabbitmq</artifactId>
      <scope>test</scope>
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
~~~

`RabbitMQContainer` needs a broker image; the example uses `rabbitmq:3.13-alpine`. Spring Boot 3.5 `RabbitConnectionDetails` supports a typed `RabbitMQContainer`. Since the management UI is not needed for these tests, there is no need to expose the management port externally.

### 8.4. application.properties

`src/main/resources/application.properties`:

~~~properties
lab.rabbit.queue=it.orders.local
spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.listener.simple.concurrency=1
spring.rabbitmq.listener.simple.max-concurrency=1
~~~

This is a fallback when manually running the app with local RabbitMQ. In Testcontainers, `@ServiceConnection` supplies the exact host/port/user/password from the container; the queue name is changed via a dynamic property.

### 8.5. RabbitLabApplication.java

~~~java
package com.example.rabbitlab;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class RabbitLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RabbitLabApplication.class, args);
    }
}
~~~

`@EnableRabbit` registers annotation-driven `@RabbitListener` support; Boot auto-configures the connection factory, `RabbitTemplate`, and default listener container factory. When promoting configs to production, review ack mode, retries, prefetch, concurrency, and DLQ separately.

### 8.6. RabbitQueueConfiguration.java

~~~java
package com.example.rabbitlab;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitQueueConfiguration {

    @Bean
    Queue ordersQueue(
            @Value("${lab.rabbit.queue}") String queueName) {
        return QueueBuilder.nonDurable(queueName).build();
    }
}
~~~

`RabbitAdmin` (via Spring Boot) can auto-declare this `Queue` bean when the listener/broker connection opens. A **non-durable** queue is strictly for integration tests; production queues need durability/arguments designed around SLAs.

If a queue already exists with different durability/arguments, the broker may return `PRECONDITION_FAILED`. Unique queue names avoid collisions with queues from previous runs.

### 8.7. ReceivedMessages.java

~~~java
package com.example.rabbitlab;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class ReceivedMessages {

    private final BlockingQueue<String> inbox =
            new LinkedBlockingQueue<>();

    void record(String payload) {
        inbox.add(payload);
    }

    public String await(Duration timeout)
            throws InterruptedException {
        return inbox.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

The probe uses an in-memory queue so the test can wait for the consumer to process. It does not replace an AMQP queue or persistent storage. No `Thread.sleep`, no static mutable global list.

### 8.8. OrderQueueListener.java

~~~java
package com.example.rabbitlab;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderQueueListener {

    private final ReceivedMessages probe;

    public OrderQueueListener(ReceivedMessages probe) {
        this.probe = probe;
    }

    @RabbitListener(queues = "${lab.rabbit.queue}")
    public void onMessage(String payload) {
        probe.record(payload);
    }
}
~~~

All Spring listener instances on the **same queue name** are competing consumers. This listener receives from a unique queue unrelated to the two fanout test queues below.

### 8.9. RabbitMessagingIsolationTest.java

`src/test/java/com/example/rabbitlab/RabbitMessagingIsolationTest.java`:

~~~java
package com.example.rabbitlab;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.FanoutExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class RabbitMessagingIsolationTest {

    private static final String RUN_ID =
            UUID.randomUUID().toString().replace("-", "");

    private static final String LISTENER_QUEUE =
            "it.orders.listener." + RUN_ID;

    @Container
    @ServiceConnection
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:3.13-alpine");

    @DynamicPropertySource
    static void rabbitProperties(
            DynamicPropertyRegistry registry) {
        registry.add("lab.rabbit.queue", () -> LISTENER_QUEUE);
    }

    @Autowired
    RabbitTemplate template;

    @Autowired
    AmqpAdmin admin;

    @Autowired
    ReceivedMessages received;

    @Test
    void listenerGetsMessageFromItsOwnUniqueQueue()
            throws Exception {

        String payload = "order-" + RUN_ID + "|CREATED";

        // Empty exchange name = default direct exchange.
        template.convertAndSend(
                "", LISTENER_QUEUE, payload);

        String delivered = received.await(
                Duration.ofSeconds(10));

        assertThat(delivered).isEqualTo(payload);
    }

    @Test
    void fanoutExchangeCopiesOneEventToEachBoundQueue() {
        String suffix = UUID.randomUUID()
                .toString().replace("-", "");

        String exchangeName = "it.fanout." + suffix;
        String shippingName = "it.shipping." + suffix;
        String analyticsName = "it.analytics." + suffix;

        FanoutExchange exchange =
                new FanoutExchange(exchangeName, false, false);

        Queue shipping =
                QueueBuilder.nonDurable(shippingName).build();
        Queue analytics =
                QueueBuilder.nonDurable(analyticsName).build();

        admin.declareExchange(exchange);
        admin.declareQueue(shipping);
        admin.declareQueue(analytics);
        admin.declareBinding(
                BindingBuilder.bind(shipping).to(exchange));
        admin.declareBinding(
                BindingBuilder.bind(analytics).to(exchange));

        try {
            String payload = "event-" + suffix + "|PAID";

            template.convertAndSend(
                    exchangeName, "", payload);

            Object shippingCopy =
                    template.receiveAndConvert(
                            shippingName, 5000);
            Object analyticsCopy =
                    template.receiveAndConvert(
                            analyticsName, 5000);

            assertThat(shippingCopy).isEqualTo(payload);
            assertThat(analyticsCopy).isEqualTo(payload);

            // After pulling and acking, both test queues are empty.
            assertThat(template.receiveAndConvert(
                    shippingName)).isNull();
            assertThat(template.receiveAndConvert(
                    analyticsName)).isNull();
        }
        finally {
            admin.deleteQueue(shippingName);
            admin.deleteQueue(analyticsName);
            admin.deleteExchange(exchangeName);
        }
    }
}
~~~

**What is verified?**
- The listener test has a per-run queue name so it does not consume data from other tests.
- `RabbitTemplate.convertAndSend("", queueName, payload)` routes through the default exchange using the queue name as the routing key.
- `@RabbitListener` receives and puts the payload into the probe; the test awaits with a bounded timeout.
- The fanout test declares its own exchange, two **distinct queues**, and two bindings; the same event routes to each queue.
- `receiveAndConvert(queueName, 5000)` is a blocking receive with a timeout; no sleep is used. Because there is no auto-consumer on the two fanout queues, the test pulls each copy directly.
- Once pulled/acked, the queues are empty (under default auto-ack semantics of `RabbitTemplate` synchronous receive). This differs from Kafka's retained log.
- `finally` deletes **only the two queues and exchange owned by the method**; it never purges or deletes shared queues.
- The test uses `@ServiceConnection` so it never hits a real RabbitMQ on localhost.

### 8.10. Running the RabbitMQ lab

~~~bash
mvn -q clean test
mvn -q -Dtest=RabbitMessagingIsolationTest test
~~~

When Docker is available and tests actually run:
- The listener test receives a single payload on its unique queue.
- The fanout test receives the same payload from **two independent queues**, then cleans up.
- Maven returns exit code 0 if assertions succeed; check `target/surefire-reports`.

Queue declaration must complete before publishing. In the lab, the listener queue is declared as a `Queue` bean by Spring Boot `RabbitAdmin`; the fanout queues/exchange/bindings are declared directly by the test method before sending the message.

## 9. Testing competing consumers on RabbitMQ

### 9.1. Two consumers on the same queue are not broadcast

Suppose two service instances share `@RabbitListener(queues="jobs.q")`. The queue has 100 jobs. RabbitMQ distributes jobs among consumers based on prefetch, ack/availability, and scheduling; you cannot reliably expect a 50/50 split. Conditions to assert:
- Total processed business task IDs = expected set.
- Under stable/proper auto-ack settings, no invalid IDs are processed.
- Do not require each consumer to receive the same message.
- Do not assume strictly fair distribution.
- Under manual ack/requeue/restarts, allow for redeliveries and verify idempotency.

### 9.2. Test plan for two listener instances

1. Use a **test-dedicated** queue.
2. Start two consumers on the same queue, each with an instance ID.
3. Wait until both consumers are registered and broker connections are usable.
4. Send multiple messages with distinct `eventId`s.
5. Collect results into a thread-safe probe/DB table.
6. Assert the union of IDs equals the expected set and no stray events appear.
7. If a test specifically demands "both workers participate", verify consumer readiness, prefetch, and supply sufficient load; do not treat one worker staying idle as a Rabbit routing bug.
8. Test requeue/nack/consumer crashes separately instead of mixing them into the happy path.

This is an **extension scenario**, not implemented in the section 8 lab; avoid claiming the fanout code proves competing consumers.

### 9.3. Publisher confirm, consumer ack, and idempotency

A message can be publisher-confirmed yet not processed by a consumer (still sitting in the queue). A consumer can write to the DB and crash before acking, causing the broker to redeliver. Hence tests should separate:
- Producer broker accepted.
- Queue routing accurate.
- Consumer method invoked.
- Side effect/DB transaction committed.
- Consumer ack/offset state satisfied.

For consumer replay, business operations should use unique constraints/idempotency keys to avoid duplicating payments/orders/emails.

## 10. Kafka replay and group offsets

### 10.1. Changing groups to replay retained records

A Kafka message in a topic can be read independently by groups G1 and G2. Once G1 commits the latest offset, restarting G1 usually does not show old records; a fresh group G2 with `earliest` can still see records remaining per retention. This is **not** like an acked RabbitMQ queue, where the copy disappears from the queue.

### 10.2. Auto-offset-reset does not delete committed offsets

If a group already has committed offsets, `auto-offset-reset=earliest` normally **does not reset** the group. Proper ways to test replay:
- Create a fresh group ID.
- Explicitly seek to the target position.
- Use admin offset resets when there are no active consumers.
- Create a fresh topic to avoid historical noise.
- Assert expected IDs instead of `count()>0`.

### 10.3. Do not reuse the same group ID in two test classes

Two parallel Spring tests with the same `group.id` and topic join one group and split partitions. Each test can lose part of its expected data. Create separate group IDs, or when intentionally testing group sharing, **deliberately** share a group like in the Kafka group semantics test.

### 10.4. Kafka retention and message cleanup

Kafka has no "remove message X after assertion" operation like RabbitMQ's `queue.basicAck`. You can delete the topic, shorten retention, truncate log/seek, or simply let an **ephemeral broker container** be destroyed. When topics must be shared on a long-lived test broker, delete only test-owned topics via `AdminClient` and await completion before reusing names.

### 10.5. At-least-once and duplicate tests

When a listener succeeds before committing its offset, a rebalance/restart can read the record again. A happy-path group assignment test does not prove exactly-once. To test idempotency:
- Send the same `eventId` twice.
- Consumer uses a deduplication store/unique constraint.
- Assert one business side effect for that `eventId`.
- Test offset/DB transaction boundaries separately.
- With Kafka transactions, understand `read_committed`, producer transactions, processing guarantees within **Kafka**, and DB side effects outside Kafka.

## 11. Retries, dead-lettering, and poison messages

### 11.1. Kafka error handling

Spring Kafka offers `DefaultErrorHandler` and `DeadLetterPublishingRecoverer` for retry/DLT routing. A failing message may be retried several times, sent to `orders.DLT`, or handled per recovery policy. Tests must specify:
- Retry budget/backoff.
- Not blocking the partition indefinitely.
- DLT topic name and payload/headers.
- Consumer group can continue after a poison record.
- Idempotency on retry.
- Dedicated DLT topic in integration tests.

Never assume `@KafkaListener` auto-commit behavior matches `@Transactional` JPA; offset commits and DB commits are two separate boundaries.

### 11.2. RabbitMQ NACK/requeue/DLX

In Rabbit:
- Listener exceptions can lead to requeue or reject depending on container settings.
- `basicNack(requeue=true)` can redeliver continuously.
- `basicReject(requeue=false)` can dead-letter if the queue has `x-dead-letter-exchange`; without a DLX, the message may be dropped.
- DLQ and routing must be declared **before publishing**.
- Policy/classic/quorum queue behavior can differ.

When testing DLQ, use **isolated queues/exchanges** for main and DLQ, bounded awaits on the DLQ, assert headers/`messageId` and rejection reasons, and clean up those resources afterwards. Never use a production DLX in CI.

### 11.3. Duplicates do not come only from the broker

Duplicates can arise from producer retries, HTTP client retries, outbox relay retries after broker ACK but before DB state update, consumer restarts, or worker logic emitting events multiple times. Use an `eventId`/idempotency key rather than relying on an "auto-generated messageId" that can change across retries.

### 11.4. Transactional outbox

If committing to the database and then publishing could lose an event on app crash, use a **transactional outbox**: write the business row and outbox row in the same DB transaction; a relay publishes from committed outbox rows; consumers stay idempotent. Testing this spans the DB + broker boundary, unlike a plain `KafkaTemplate.send().get()` test.

## 12. Readiness and async synchronization

### 12.1. Kafka listener assignment is a real step

The `@SpringBootTest` context may have created the listener bean before the Kafka consumer has received partitions. Sending a record with a fresh group and `auto-offset-reset=latest` at that moment can cause the test to miss the record. Spring Kafka test helper:

~~~java
ContainerTestUtils.waitForAssignment(
        registry.getListenerContainer("ordersListener"), 2);
~~~

This requires the Spring Kafka Test dependency and the real listener ID. Asserting assignment is only a **precondition**; you still must wait for handler receipt/side effects.

### 12.2. RabbitMQ listener readiness

The Rabbit listener container needs a broker connection, queue declarations, and consumer registration. If the queue exists and a message is published before the listener attaches, the broker can hold the message until the consumer connects—unlike a new Kafka group on `latest` missing records sent before joining. However, sending before the exchange/queue/binding exists can be unroutable or lost. Rabbit tests should ensure declarations precede publishing, then wait for message receipt with a bounded timeout.

### 12.3. Do not use Thread.sleep

Wrong:

~~~java
template.send(topic, key, payload);
Thread.sleep(1000);
assertThat(inbox.size()).isEqualTo(1);
~~~

Better:
- Wait for producer broker ACK separately (if part of the contract).
- Wait for consumer assignment/queue declaration when needed.
- Use `BlockingQueue.poll(timeout)` or Awaitility.
- Assert the exact `eventId` and payload.
- On timeout, print logs/metadata/consumer assignments instead of looping arbitrary sleeps.

### 12.4. Bounded awaits to prevent CI hangs

Set sensible budgets:
- Broker/container startup has Testcontainers wait/readiness.
- Producer send result `.get(15s)`.
- Consumer receive `poll(10s)`.
- Business DB readback has bounded eventually assertions if eventual consistency is the contract.
- Total JUnit time has an upper bound, avoiding preemptive timeouts that break transactional `ThreadLocal`s if a test uses `@Transactional`.

Pick timeouts grounded in broker startup/CI speed, without turning tests into 5-minute waits for misconfigured resources.

## 13. Topic/queue provisioning and cleanup

### 13.1. Kafka NewTopic vs. broker auto-create

In Spring Boot, `NewTopic` beans + `KafkaAdmin` declare topics with explicit partition counts and replication factors. Relying on Kafka `auto.create.topics.enable` can create topics with a different partition count than expected and cause false positives.

If a group-sharing test requires two partitions, create the topic with **2 partitions** explicitly and wait for metadata. Do not create the topic via an accidental publish before configuration is ready.

### 13.2. Rabbit admin declarations

Spring AMQP `RabbitAdmin`/`AmqpAdmin` creates queues/exchanges/bindings. A queue has fixed durability/auto-delete/exclusive semantics; re-declaring the same name with different arguments can return `PRECONDITION_FAILED`. Unique test names prevent collisions, though you must still understand queue options.

### 13.3. Cleaning up Rabbit with proper ownership

- Delete queues created by the test.
- Delete exchanges created by the test.
- Never delete system exchanges or shared production routes.
- Never purge shared queues when other tests may be using them.
- Clean up in `finally` so cleanup still attempts to run after assertion failures; ephemeral containers act as a safety net if the JVM is killed.
- If a listener is running on a queue, stop the listener container before deleting the queue if the test explicitly deletes it inside the same Spring context; the lab does not delete the listener queue between tests.

### 13.4. Cleaning up Kafka with proper ownership

- If each test class has its own `KafkaContainer`, shutting down the container at the end of the class is the simplest isolation.
- On a shared broker, delete test-owned topics via `AdminClient` and await completion; never delete another test's topic.
- Do not reset group offsets on shared consumer groups.
- Unique topic names reduce collisions, yet can accumulate thousands of topics on a shared broker; lifecycle cleanup/quotas are needed.

## 14. Pattern selection for test boundaries

| Goal | Test type | Setup |
| --- | --- | --- |
| Domain event serialization/validation | Pure JUnit | JSON/Avro fixtures, schema validator |
| Message-handling logic | Handler class unit test | Mock repository/gateway, verify business rules |
| Producer record key/headers | `KafkaTemplate` contract test | Embedded broker or Testcontainers |
| Kafka group/partition semantics | Testcontainers Kafka | Unique topic/group, real clients |
| Rabbit queue routing/fanout | Testcontainers RabbitMQ | Unique exchange/queues/bindings |
| Offset resume/rebalance | Integration/fault tests | Group restart/seek/assignment control |
| Retry/DLT | Broker integration tests | DLT resources/test failure handler |
| Durable outbox | DB + broker integration | DB transaction, relay, `eventId` |
| Auth/TLS/ACL | Security integration | Sandbox broker credentials/certs |
| Multi-broker failover/durability | Production-like cluster | Not just a single-node container |
| REST request triggers message | `@SpringBootTest` + broker | HTTP service + async listener, cleanup |

Test levels complement one another. You do not need Kafka Testcontainers for every domain calculation; nor does a unit test mocking `KafkaTemplate` verify broker routing.

## 15. Common mistakes and how to fix them

### 15.1. Kafka consumer receives no messages

Check whether the topic/partitions exist, whether the bootstrap server points to the Testcontainers endpoint, whether the listener completed assignment, whether the group ID is shared, whether `auto-offset-reset` is `latest`, whether offsets were already committed from an earlier test, and whether serializers/deserializers match.

Do not fix every failure by sleeping a few extra seconds: the consumer might be reading the wrong topic or group.

### 15.2. Kafka test sometimes sees only half the records

Two test classes may share the same `group.id` and unintentionally split partition assignments. Within the same group, **splitting** the workload is expected. If each test needs every record, use different groups or separate topics.

### 15.3. Kafka test reads records from a previous run

Shared topics retain logs; a fresh group + `earliest` reads from the beginning. Use unique topics/`testRunId`, or filter/seek intentionally. Never merely assert `count>=1`.

### 15.4. Kafka order assertions fail

If records span multiple partitions, there is no global total order. Assert ordering only within a single partition/proper key partitioning, or use `containsExactlyInAnyOrder` when business logic does not require ordering.

### 15.5. Kafka duplicates after consumer restart

Offset commits occur after business actions or fail to commit; records get redelivered. Design idempotent handlers and test retry/rebalance semantics rather than claiming exactly-once by default.

### 15.6. Kafka Producer future PASSES yet consumer times out

Broker ack does not prove the handler was called. Check listener assignment, topic/partition/group, error handler, deserializer, poison events, and test await logic. Never assert immediately after `send`.

### 15.7. RabbitMQ publisher sends yet no queue receives

It may have sent to the wrong exchange/routing key, the queue was unbound, or the message was unroutable. Declare queues/exchanges before publishing and use publisher confirms/returns when the routing contract is critical.

### 15.8. RabbitMQ two workers do not both receive a message

That is competing-consumer semantics on a single queue. If broadcast is required, create a separate queue per subscriber and bind them to a fanout/topic exchange.

### 15.9. RabbitMQ queue declaration `PRECONDITION_FAILED`

A queue already exists with different durability/exclusive/arguments. Use unique test queue resources, or align declarations with managed configuration. Never delete a shared queue just to make a test pass.

### 15.10. Rabbit message processed again

Consumer crash before ack, reject/requeue, retry, or connection drop can trigger redelivery. Inspect the `redelivered` flag when helpful, but never rely on it as the sole idempotency token; use an application-managed event ID.

### 15.11. Rabbit listener has a queue yet test races

The listener container may not have registered or the message was published before the binding existed. Existing queues hold messages, yet exchange routing must be valid. Declare before publishing and use bounded polls instead of sleeps.

### 15.12. `@SpringBootTest` fails context startup because broker is not started

Static `@Container` and `@ServiceConnection` need Testcontainers dependencies and proper annotations. Check container runtime, image, service connection factory, and context initialization. Never point tests at a production broker to "run faster".

### 15.13. Spring context cache points to a stopped container

A JUnit Testcontainers static container stops after the class; the Spring TestContext caches contexts across classes and can reuse stale connection details/clients. Use Spring-managed container beans per Boot docs, isolate contexts, or manage container lifecycles accordingly.

### 15.14. Docker tests SKIPPED yet build exits 0

`@Testcontainers(disabledWithoutDocker=true)` can skip classes when Docker is unavailable. CI integration jobs must require Docker and `skipped=0` in Surefire; never claim tests ran when they did not.

### 15.15. Running tests in parallel causes message stealing

Shared Kafka groups or Rabbit queues make tests compete. Use isolated topics/groups/queues, check correlation/`eventId`, and avoid global mutable probes.

### 15.16. DLT/DLQ collides with data from other tests

Default names like `orders.DLT` or `dead-letter.queue` shared across tests accumulate failing messages. Create isolated dead-letter resources, assert exact event IDs, and clean up.

### 15.17. `@DirtiesContext` used as broker cleanup

`@DirtiesContext` only invalidates the Spring `ApplicationContext` cache; it does not delete Kafka topics/offsets or Rabbit queues. Clean up real broker resources or rely on ephemeral containers per test ownership.

### 15.18. Kafka transaction treated as equivalent to a DB transaction

Kafka transactions cover Kafka records/offsets per API and config; they do not automatically encompass an external JDBC transaction. If an app writes to a DB and emits an event in one workflow requiring atomicity, consider transactional outbox and idempotency.

### 15.19. Rabbit consumer ack treated as business commit

Ack may happen after or before DB commit depending on container/handler config. A consumer crashing between DB commit and ack can cause duplicates. Test business side effects and ack/requeue policies independently.

### 15.20. Single container treated as production cluster

A single-node Kafka/RabbitMQ container verifies basic protocol/routing. It does not prove 3-node replication, rack-awareness, quorum failover, network partitions, or broker security policies. HA/SLA claims require matching test environments.

## 16. Security and repeatability checklist

- Never connect to production topics/queues in automated integration tests.
- Never use real credentials, real customer data, or payment details in test messages.
- Broker containers use dynamic ports; never hard-code endpoints.
- Pin approved image tags/digests when reproducibility is required.
- Namespace unique IDs per test to prevent collisions during parallel runs.
- Producer/consumer serializers, headers, and message schemas are versioned.
- Consumer group IDs belong to tests; never reuse production groups.
- Kafka topic partitions/retention are provisioned intentionally.
- Rabbit exchanges/queues/bindings are declared before publishing.
- Never use `Thread.sleep` for readiness/synchronization.
- Use bounded awaits and cleanup in `finally`.
- Keep logs sufficient for debugging while scrubbing secrets/PII.
- CI verifies tests actually executed, not just overall build status.
- In parallel/group tests, never assert a specific member assignment without a contract.
- Never claim exactly-once from happy-path tests alone.
- Include negative/duplicate/retry/DLT tests when business risk warrants them.
- Multi-consumer data must be read in line with group/queue semantics.

## 17. Practice exercises

1. Create a two-partition Kafka topic and two consumers in the same group: observe partition assignment and assert the union of records rather than requiring each consumer to read all.
2. Add a second group with `earliest`, verifying it reads the same retained records with independent offsets.
3. Change the new group from `earliest` to `latest`, sending messages before and after assignment; explain which events are missed and why.
4. Reuse an old group with committed offsets and explain why `earliest` does not replay everything.
5. Create a per-test-method topic using `AdminClient`, cleaning up only the topic owned by the method.
6. Use the same key for three Kafka records and verify partition stability while partition count stays constant.
7. Send records across two partitions, try asserting global order, and fix the assertion to be per-partition.
8. Simulate a Kafka consumer restart before offset commit, adding an idempotency key to the handler.
9. Use the RabbitMQ default exchange and a unique queue, send a message, and receive from the queue.
10. Attach two consumers to the same queue and explain why only one consumer receives each delivery.
11. Bind two queues to a fanout exchange and prove each queue receives its own copy.
12. Use topic exchange patterns `orders.*` and `orders.#`, testing routing keys that match differently.
13. Intentionally publish before creating bindings and observe unroutable behavior; add publisher returns/confirm handling.
14. Create a dedicated DLQ, reject a message without requeue, and inspect headers/payload in the DLQ.
15. Put `eventId`/`testRunId` in the payload and test filtering the exact event in a multi-message environment.
16. Run two Spring test classes in parallel with the same group/queue, then switch to unique resource names.
17. Stop Docker, run Maven tests, and distinguish `SKIPPED` from `PASS` in Surefire.
18. Convert a mocked Kafka producer test to Testcontainers and describe which newly covered risks are tested.
19. Use a fake handler unit test for validation/serialization and compare cost with broker integration.
20. Design an outbox row + broker integration and verify a duplicate event does not trigger two business side effects.

## 18. Pre-merge checklist

- [ ] Identified backend as Kafka or RabbitMQ/AMQP without mixing terminology?
- [ ] Kafka topic/partition/group/offset semantics understood correctly?
- [ ] Rabbit exchange/queue/binding/consumer semantics understood correctly?
- [ ] Used independent Kafka groups or independent Rabbit queues for broadcast?
- [ ] Used Kafka groups or Rabbit queue competition properly for workload sharing?
- [ ] Resource names isolated per class/test/run?
- [ ] Event IDs/correlation IDs asserted explicitly?
- [ ] Kafka group IDs not accidentally shared across tests?
- [ ] Kafka `auto-offset-reset` matches the position being tested?
- [ ] Topic partitions/replication and Rabbit bindings provisioned before send?
- [ ] Consumer assignment/queue declaration readiness verified?
- [ ] Producer broker ACK and consumer processed outcome verified separately?
- [ ] Bounded poll/await used instead of fixed `Thread.sleep`?
- [ ] No global Kafka ordering asserted across partitions?
- [ ] No exact 50/50 split asserted for Rabbit workers?
- [ ] `@DirtiesContext` not used in place of broker cleanup?
- [ ] Cleanup removes only test-owned resources, never disrupting shared topics/queues?
- [ ] Parallel tests genuinely isolated with no global mutable probes?
- [ ] Retry/DLT/DLQ/idempotency tests present per domain risk?
- [ ] Docker CI executes real brokers rather than skipping?
- [ ] Container lifecycle and Spring cached contexts aligned?
- [ ] No secrets/PII or messages sent to production?
- [ ] Boot/Testcontainers/kafka-client/AMQP versions compatible?
- [ ] Surefire reports checked and async errors include diagnostic logs?

**Conclusion:** Kafka consumer groups and RabbitMQ queues both support workload distribution, yet at different abstractions: **Kafka assigns partitions per group with independent offsets**; **RabbitMQ exchanges route copies to queues while consumers on the same queue compete for deliveries**. Reliable tests need resource ownership, isolated topics/groups/queues, traceable `eventId`s, readiness and bounded awaits, plus proper separation of broker acknowledgments from business processing. Never just send a message, sleep, or count any arbitrary event. By understanding topology and isolation accurately, you can make messaging integration tests faster, less flaky, and capable of catching real routing/consumer group/ack bugs.

## 19. Official References

- Spring Boot 3.5 — Apache Kafka messaging: https://docs.spring.io/spring-boot/3.5/reference/messaging/kafka.html
- Spring Boot 3.5 — AMQP / RabbitMQ: https://docs.spring.io/spring-boot/3.5/reference/messaging/amqp.html
- Spring Boot 3.5 — Testcontainers & service connections: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Kafka 3.3 — Testing: https://docs.spring.io/spring-kafka/reference/3.3/testing.html
- Spring Kafka 3.3 — @KafkaListener: https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/listener-annotation.html
- Spring Kafka 3.3 — Topic configuration: https://docs.spring.io/spring-kafka/reference/3.3/configuration/topic.html
- Spring Kafka 3.3 — Consumer offset commits: https://docs.spring.io/spring-kafka/reference/3.3/kafka/receiving-messages/message-listener-container.html
- Spring AMQP 3.2 — Annotation-driven Rabbit listeners: https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/async-annotation-driven.html
- Spring AMQP 3.2 — Sending messages: https://docs.spring.io/spring-amqp/reference/3.2/amqp/sending-messages.html
- Spring AMQP 3.2 — Listener acknowledgement modes: https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/async-consumer.html
- Testcontainers Java — Kafka module: https://java.testcontainers.org/modules/kafka/
- Testcontainers Java — RabbitMQ module: https://java.testcontainers.org/modules/rabbitmq/
- Testcontainers Java — JUnit 5: https://java.testcontainers.org/quickstart/junit_5_quickstart/
- Apache Kafka — Consumer concepts: https://kafka.apache.org/documentation/#consumerapi
- RabbitMQ — AMQP concepts (exchanges, bindings, queues): https://www.rabbitmq.com/tutorials/amqp-concepts
- RabbitMQ — Consumer acknowledgements & publisher confirms: https://www.rabbitmq.com/docs/confirms
- RabbitMQ — Consumer prefetch: https://www.rabbitmq.com/docs/consumer-prefetch
