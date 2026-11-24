# Separating Consumer Groups for Billing and Notification

In an order processing system, the same `OrderCreated` event often needs to trigger multiple independent business workflows. Billing creates an invoice or records accounts receivable; Notification sends an email or alert to the customer. Both workflows need to receive the same event, can run at different speeds, and must not steal records from one another.

Kafka solves this problem with consumer groups. Billing and Notification share the `orders` topic but have separate group IDs. Each group maintains its own offsets and reading progress, so both receive every record. If two listeners share the same group ID, Kafka distributes partitions between them to balance load; a record goes to either Billing or Notification depending on assignment, rather than being broadcast to both.

This hands-on lab builds a producer that publishes `OrderCreated`, two listeners consuming the same topic under two independent consumer groups, and then inspects offsets, partition assignments, and multi-instance scaling behavior.

## 1. Objectives and Architecture

After this lab, you will be able to:

- Create an `orders` topic with multiple partitions.
- Publish `OrderCreated` events using `KafkaTemplate`.
- Configure the Billing listener using the `billing-service` group.
- Configure the Notification listener using the `notification-service` group.
- Prove that both groups receive the same record.
- Scale multiple instances within a group to share load.
- Observe offsets and consumer assignments via the Kafka CLI.
- Understand retry, duplicates, and idempotency per consumer group.

Target architecture:

~~~mermaid
flowchart TD
    API[Order Service / Producer] -->|OrderCreated| T[(orders topic)]
    T --> P0[Partition 0]
    T --> P1[Partition 1]
    T --> P2[Partition 2]
    P0 --> B[Billing consumer group]
    P1 --> B
    P2 --> B
    P0 --> N[Notification consumer group]
    P1 --> N
    P2 --> N
    B --> DB[(Billing database)]
    N --> MAIL[Email / notification provider]
~~~

Both groups independently read the same topic log. On the same partition, Billing may be processing the record at offset 100 while Notification is still at offset 85. Kafka does not require the two groups to run at the same pace or have matching committed offsets.

Within each group, instances split partitions among themselves. Across the two groups, each group receives its own independent partition assignment and can read all partitions of the topic.

## 2. Preparing the Project

Use a Spring Boot application with Spring Kafka and a Kafka broker reachable from the application. With Maven, the main dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

If the project uses Spring Boot dependency management, do not specify a Spring Kafka version manually unless there is a specific compatibility reason. For integration tests with an embedded broker, add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The examples below use Java records and JSON serialization. Ensure the project uses aligned Spring Boot/Spring Kafka versions and the local broker is ready before running the lab.

## 3. Configuring Topic, Producer, and Consumer

Create `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      auto-offset-reset: earliest
      enable-auto-commit: false
      properties:
        spring.json.trusted.packages: com.example.messaging
        spring.json.value.default.type: com.example.messaging.OrderCreated
        spring.json.use.type.headers: false

app:
  kafka:
    topics:
      orders: orders
    groups:
      billing: billing-service
      notification: notification-service
    billing:
      concurrency: 2
    notification:
      concurrency: 1
~~~

Explanation:

- `bootstrap-servers` points to the Kafka broker.
- Producer uses `StringSerializer` for the key and `JsonSerializer` for the event.
- Consumer uses `StringDeserializer` and `JsonDeserializer`.
- Default type specifies the Java class to deserialize the payload into.
- `trusted.packages` restricts packages allowed for deserialization.
- `auto-offset-reset: earliest` applies when a group does not yet have a valid committed offset.
- Two distinct group IDs are the core mechanism enabling both streams to receive independently.
- Concurrency can be tuned according to partition count and processing capacity.

Because both listeners receive the same `OrderCreated` event type, they can share a `ConsumerFactory`. If Billing and Notification need different serializers, deserializers, or error handling, create dedicated container factories for each listener rather than letting shared configuration become unwieldy.

## 4. Creating the orders Topic

In a local environment, you can declare the topic with Spring Kafka:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;
import org.apache.kafka.clients.admin.NewTopic;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic(
            @Value("${app.kafka.topics.orders}") String topicName) {

        return TopicBuilder.name(topicName)
                .partitions(3)
                .replicas(1)
                .build();
    }
}
~~~

The topic has three partitions so distribution across consumers is easy to observe. Replication factor 1 suits a single local broker; production environments need a replication factor matching the cluster's fault-tolerance policy.

If topics are already managed by Terraform, Helm, a Kafka operator, or a separate infrastructure workflow, you can omit the `NewTopic` bean and provision topics externally. Do not let every application instance arbitrarily mutate production topology on startup.

Inspect the topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

The output should confirm the topic exists and has three partitions. Note the partition IDs to cross-check against listener logs.

## 5. Declaring the OrderCreated Event

Create the event shared by both consumers:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        String currency,
        Instant occurredAt
) {
}
~~~

Field meanings:

- `eventId` is the unique identifier of the event, used for idempotency and investigation.
- `orderId` is the business key of the order.
- `customerId` identifies the customer receiving the notification.
- `totalAmount` and `currency` provide data for Billing.
- `occurredAt` is the business timestamp when the event was created.

Using `orderId` as the Kafka key routes events for the same order to the same partition, thereby preserving order per key under the active partitioner.

Do not include sensitive payment credentials or authentication secrets in the event. If the two consumers require different data, define a minimal event contract and apply appropriate topic authorization.

## 6. Publishing Events with KafkaTemplate

Create the publisher:

~~~java
package com.example.messaging;

import java.util.concurrent.CompletableFuture;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;
    private final String ordersTopic;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate,
            @Value("${app.kafka.topics.orders}") String ordersTopic) {
        this.kafkaTemplate = kafkaTemplate;
        this.ordersTopic = ordersTopic;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
                ordersTopic,
                event.orderId(),
                event
        );
    }
}
~~~

The producer sends the event to the `orders` topic with `orderId` as the key. The future lets the caller observe the send result:

The example uses the Spring Kafka 3.x API where `send()` returns a `CompletableFuture`. If your project uses Spring Kafka 2.x, the future type and callback registration may use `ListenableFuture`; adjust to match your managed version.

~~~java
publisher.publish(event)
        .whenComplete((result, error) -> {
            if (error != null) {
                log.error("Cannot publish OrderCreated eventId={}",
                        event.eventId(), error);
                return;
            }

            var metadata = result.getRecordMetadata();

            log.info(
                    "Published eventId={} topic={} partition={} offset={}",
                    event.eventId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
~~~

Do not log "published successfully" immediately after calling `send()` without observing the future result. Once the broker acknowledges, metadata provides the partition and offset to cross-reference with consumers.

## 7. Creating the Billing Consumer Group

The Billing listener uses the `billing-service` group ID:

~~~java
package com.example.messaging.billing;

import com.example.messaging.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderListener {

    private final BillingService billingService;

    public BillingOrderListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
            id = "billing-orders-listener",
            topics = "${app.kafka.topics.orders}",
            groupId = "${app.kafka.groups.billing}",
            concurrency = "${app.kafka.billing.concurrency:2}"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.createInvoice(event);
    }
}
~~~

With group ID `billing-service`, Kafka tracks committed offsets separately for Billing. Billing can process events faster or slower without affecting Notification's offsets.

In the example, `BillingService` represents invoice creation business logic. In a real application, database operations need transactions and idempotency keyed by `eventId` or `orderId` to safely handle record redelivery.

## 8. Creating the Notification Consumer Group

The Notification listener also subscribes to the `orders` topic, but uses the `notification-service` group ID:

~~~java
package com.example.messaging.notification;

import com.example.messaging.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class NotificationOrderListener {

    private final NotificationService notificationService;

    public NotificationOrderListener(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @KafkaListener(
            id = "notification-orders-listener",
            topics = "${app.kafka.topics.orders}",
            groupId = "${app.kafka.groups.notification}",
            concurrency = "${app.kafka.notification.concurrency:1}"
    )
    public void onOrderCreated(OrderCreated event) {
        notificationService.sendOrderConfirmation(event);
    }
}
~~~

The crucial point is that both annotations share the same `topics` value but have different `groupId` values. Kafka tracks independent progress:

- `billing-service` reads every event from the topic according to its own offsets.
- `notification-service` also reads every event from the topic according to its own offsets.
- Billing does not steal records from Notification.
- Notification does not alter Billing's committed offsets.

If Notification slows down because an email provider has an outage, Billing can continue processing. Notification's lag rises independently under the `notification-service` group.

## 9. What Happens If Both Listeners Share the Same Group ID?

To see the difference, try changing both `groupId` values to the same value, `order-processors`.

Then both listeners join the same consumer group. Kafka treats them as member consumers of one group and distributes partitions among those members. Each record is processed by only one consumer in the group based on partition assignment.

Example:

| Partition | Assigned consumer in group order-processors |
|---|---|
| orders-0 | Billing listener |
| orders-1 | Notification listener |
| orders-2 | Billing listener |

Result: some events go through Billing, while others go through Notification. There is no guarantee both workflows receive every event. This is the competing consumers pattern for load sharing, not broadcast.

For both Billing and Notification to receive all events, you must keep separate group IDs:

~~~text
orders topic
  ├── billing-service      -> reads all partitions
  └── notification-service -> reads all partitions
~~~

You do not need to create two separate topics just so two services can receive the same event. One topic with multiple consumer groups is typically the right design when consumers require independent progress and processing goals.

## 10. Running the Lab and Sending Sample Events

Start the Kafka broker, then run the Spring Boot application. When the listeners start, both consumer groups join the `orders` topic and receive partition assignments.

Generate sample events by invoking the publisher from a REST endpoint, a `CommandLineRunner`, or a test fixture. Example using `CommandLineRunner` for local runs only:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SampleOrderRunnerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(SampleOrderRunnerConfiguration.class);

    @Bean
    CommandLineRunner publishSampleOrder(OrderEventPublisher publisher) {
        return args -> {
            var event = new OrderCreated(
                    UUID.randomUUID().toString(),
                    "ORD-1001",
                    "CUS-2001",
                    new BigDecimal("125000.00"),
                    "VND",
                    Instant.now()
            );

            publisher.publish(event)
                    .whenComplete((result, error) -> {
                        if (error != null) {
                            log.error("Publish failed", error);
                        }
                        else {
                            log.info("Sample order published at partition={} offset={}",
                                    result.getRecordMetadata().partition(),
                                    result.getRecordMetadata().offset());
                        }
                    });
        };
    }
}
~~~

Each run of the runner emits a new event. When testing multiple times, you can emit 10–20 events with different `orderId` values to observe partition distribution.

`CommandLineRunner` runs once per application instance. Only enable this example when running a single instance to seed sample data; when testing multi-instance scaling, disable the runner or use a dedicated endpoint/test producer so each pod does not emit extra events on startup.

Expected logs show the same `eventId` appearing in both Billing and Notification, though the log order between the two listeners may differ:

~~~text
Billing received eventId=evt-101 orderId=ORD-1001
Notification received eventId=evt-101 orderId=ORD-1001
~~~

There is no requirement for the two listeners to process simultaneously or finish at the same time. They have independent consumer threads, offsets, and speeds.

## 11. Verifying Both Consumer Groups via Kafka CLI

List groups:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list
~~~

Expect to see both groups:

~~~text
billing-service
notification-service
~~~

Describe Billing:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group billing-service
~~~

Describe Notification:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group notification-service
~~~

Each group shows rows for the `orders` topic covering the partitions managed by that group. Compare:

- GROUP: different group IDs.
- TOPIC: both are `orders`.
- PARTITION: both groups have assignments across all partitions, provided enough active consumers exist.
- CURRENT-OFFSET: independent commit progress.
- LOG-END-OFFSET: references the same topic log.
- LAG: can differ due to different processing speeds.
- CONSUMER-ID: instances belonging to the respective group.

If both groups have finished processing the same number of records, their committed offsets may be equal. When Notification slows down, `notification-service` lag grows while `billing-service` lag can remain 0.

## 12. Testing Multi-Instance Scaling

Suppose the `orders` topic has three partitions:

- Billing concurrency = 2.
- Notification concurrency = 1.
- Run two application instances.

Total consumers would be:

| Group | Concurrency per instance | Instances | Total consumers | Partitions |
|---|---:|---:|---:|---:|
| billing-service | 2 | 2 | 4 | 3 |
| notification-service | 1 | 2 | 2 | 3 |

In the Billing group, at most three consumers are assigned partitions; the fourth consumer remains idle. In the Notification group, two consumers share three partitions. The two groups are independent, so Billing's assignments do not affect Notification's assignments.

Try increasing the topic to six partitions in a lab environment or creating a new six-partition topic, then observe scaling behavior. Do not increase production partitions just to experiment, because doing so can affect key-to-partition mapping and ordering.

## 13. Demonstrating Independent Offsets

To illustrate offsets clearly, assume we examine a single partition with a log end offset of 20. Billing has processed up to next position 20, while Notification has only committed next position 12 because the email service is slow.

Illustrative state:

| Group | Log end offset | Committed offset | Illustrative lag |
|---|---:|---:|---:|
| billing-service | 20 | 20 | 0 |
| notification-service | 20 | 12 | 8 |

In the lab's three-partition topic, read the corresponding table per partition; do not sum offsets across partitions into a single topic-wide offset. Offsets in Kafka start at 0 and the committed offset usually represents the next position to read, so apply the tool's exact semantics when calculating lag.

When Notification recovers, it resumes from its own group's committed offset. Billing does not have to re-read events just because Notification is catching up on a backlog.

This is the core benefit of separate groups: each logical consumer can progress, retry, and operate independently.

## 14. Testing Slow or Stopped Notification

Pause the Notification listener or stop the application instance running that listener. Then continue publishing events.

Observe:

- Billing still receives and processes new events.
- The Notification group does not advance its offsets, or its lag increases.
- When Notification restarts, it resumes from the group's committed offset.
- Billing's offsets are not rewound because Notification restarted.

If Billing and Notification shared the same group ID, stopping one listener would trigger a rebalance and cause the remaining consumer to pick up the previous partitions. That would cause some events to be processed by the wrong business service.

With separate group IDs, a Notification failure does not cause Billing to take over Notification's partitions or vice versa. Both services still share the broker/topic, so a broker or topic outage can still affect both.

## 15. Independent Retry and DLT per Consumer Group

Billing and Notification can have different retry policies:

- Billing retries database errors with a short, bounded backoff.
- Notification retries email provider errors with a longer backoff.
- Each flow has its own DLT and operational runbook.

If using `@RetryableTopic`, design retry topics per listener/group and choose a naming strategy to avoid collisions between flows. Verify auxiliary topics are created properly, have appropriate retention, and have sufficient ACL permissions for producers/consumers.

An event can succeed in Billing while failing in Notification and entering Notification's DLT. Do not treat that event as globally failed when Billing's workflow already completed. Track processing state per consumer or per bounded context.

## 16. Idempotency for Each Consumer

A Kafka consumer can receive records again during a rebalance, a process crash before committing offsets, or a retry. Separate groups do not eliminate duplicates; they only isolate reading progress.

Each consumer should implement appropriate idempotency:

- Billing records `eventId` or `orderId` for created invoices so it never creates duplicate invoices.
- Notification records `notificationId` or `eventId` and notification type to avoid sending duplicate emails.
- Use unique constraints or atomic inserts to handle concurrent redeliveries.
- With external APIs, pass an idempotency key if the provider supports one.

Do not share a deduplication table between Billing and Notification in a way that lets one consumer mark an event as processed and block the other consumer from running its workflow. The idempotency key must be scoped to the logical consumer, such as `(consumer_name, event_id)`.

If you need to synchronize database writes and event publishing, consider the transactional outbox pattern. A Kafka transaction across Kafka records does not automatically roll back a database write or an already-sent email.

## 17. Integration Testing Both Groups

An integration test should verify that both groups receive the same event. You can use `@EmbeddedKafka` or Testcontainers and create a topic with at least one partition for a simple test.

Test steps:

1. Start the test broker and create the `orders` topic.
2. Start the Billing listener with group `billing-test`.
3. Start the Notification listener with group `notification-test`.
4. Wait until both listeners receive partition assignments.
5. Send an `OrderCreated` event with a fixed `eventId`.
6. Wait for Billing to receive the event and assert `eventId`.
7. Wait for Notification to receive the same `eventId`.
8. Send multiple events and assert each group receives the full count.
9. Pause one listener, keep sending events, and assert the other group keeps processing.
10. Restart the paused listener and assert it reads the backlog from its own offset.

In tests, use dedicated topics and group IDs per test run to avoid state leakage from other tests. Use a latch/queue with a timeout instead of a fixed `Thread.sleep`; sleeping only slows down tests and does not prove consumer assignment completed.

Do not merely assert that logs were printed. Record `eventId` into a test sink or mock service to confirm each group actually invoked the right business handler.

## 18. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Only Billing or Notification receives the event | Both listeners accidentally share the same group ID | Assign a distinct group ID to each logical consumer |
| A group does not appear in CLI | Listener not started, wrong group property, or not subscribed to the topic | Check listener registry, startup logs, and annotations |
| Consumer remains idle despite multiple instances | More consumers than partitions | Adjust concurrency or partitions after benchmarking |
| Notification reprocesses many old events | New group had no offset and `auto.offset.reset=earliest` | Define an explicit offset initialization policy |
| Billing lag is low while Notification lag is high | Notification is slow or downstream dependency is failing | Investigate the Notification group and its downstream independently |
| Duplicate invoices or duplicate emails created | Record redelivered and handler is not idempotent | Deduplicate by `eventId` scoped to the consumer |
| Both listeners receive the event but finish in different orders | Both groups have independent speeds and scheduling | Never rely on completion order across the two services |
| Changing concurrency triggers rebalance | Consumer membership changed | Monitor assignments and handle in-flight work safely |

## 19. Lab Completion Checklist

- [ ] Topic `orders` exists and has three partitions in the lab.
- [ ] Producer sends `OrderCreated` with `orderId` as the key.
- [ ] Billing listener uses group `billing-service`.
- [ ] Notification listener uses group `notification-service`.
- [ ] Both listeners subscribe to the `orders` topic.
- [ ] The same `eventId` appears in both business handlers.
- [ ] CLI shows two distinct consumer groups.
- [ ] Each group has assignments for the topic's partitions.
- [ ] Lag and committed offsets are tracked independently.
- [ ] Stopping Notification does not stop Billing from processing.
- [ ] Restarting Notification drains its backlog.
- [ ] Concurrency does not exceed the number of useful partitions.
- [ ] Retry/DLT are designed per business workflow.
- [ ] Billing and Notification have independent idempotency.
- [ ] Integration test verifies both groups receive the same event.

## 20. Extending After the Lab

Once the lab runs stably, you can extend it in the following directions:

- Add an Analytics consumer group to build reports without modifying the producer.
- Add an Audit consumer group to archive event history.
- Use schema versioning to evolve `OrderCreated` safely.
- Configure separate retry topics and DLTs for Billing and Notification.
- Add Micrometer metrics for lag, processing time, and failure rate.
- Use a transactional outbox to ensure order state and events are persisted durably together.
- Deploy consumers separately to scale Billing and Notification independently by load.

The single-topic, multiple-consumer-group model lets one event serve multiple bounded contexts while preserving independent processing progress. Billing and Notification share the `orders` topic but must have separate group IDs; instances of the same service share a group ID to split partitions. When finishing the lab, confirm the same `eventId` appears in both consumers, observe separate offsets/lag, and test stopping one flow to prove the other continues working.

