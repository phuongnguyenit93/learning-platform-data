# Publishing Events from REST, Schedules, and Business Services

Not every event is created inside a Supplier function. In real-world applications, events can arise when a REST API receives a request, when a scheduled task comes due, or when a business service completes an operation. Spring Cloud Stream provides **StreamBridge** so these imperative components can send messages into configured streams without calling the specific APIs of Kafka, RabbitMQ, or Pulsar directly.

**StreamBridge** acts as a bridge between regular Java code and the messaging system. The calling component creates a payload or **Message<?>**, selects an output binding, and sends the message. The binder handles delivering the message to the corresponding destination. This organization lets controllers, schedulers, and services focus on business logic while binding configuration handles connecting to the broker.

## 1. What problem does StreamBridge solve?

Supplier is appropriate when the application proactively generates messages via polling or a continuous publishing source. However, a REST controller is not a Supplier; it is invoked when an HTTP request arrives. A time-based scheduler does not need to be turned into a Supplier function either. A business service often just wants to publish an event at a specific point in a workflow.

**StreamBridge** enables sending messages from those components:

~~~text
REST request -----------+
                        |
Scheduled task ---------+--> StreamBridge --> Output binding
                        |                         |
Business service ------+                         v
                                             Binder
                                                |
                                                v
                                           Kafka / RabbitMQ / Pulsar
~~~

For example, when a customer confirms an order, the application can publish **OrderConfirmed**. When it is time to aggregate inventory, the scheduler publishes **InventorySnapshotRequested**. When a service completes a payment, it publishes **PaymentCompleted**.

**StreamBridge** is a Spring Cloud Stream API. It is not KafkaTemplate, RabbitTemplate, or a Pulsar client; the application does not need to create each broker's producer directly if it only uses capabilities provided by the binder.

## 2. Declaring output bindings

For destinations known in advance, output bindings should be declared in **application.yml**. Example using the Kafka binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderConfirmed-out-0:
          destination: orders.confirmed
          content-type: application/json
        inventorySnapshot-out-0:
          destination: inventory.snapshot.requested
          content-type: application/json
        paymentCompleted-out-0:
          destination: payments.completed
          content-type: application/json
      kafka:
        binder:
          brokers: localhost:9092
~~~

In the configuration:

- **orderConfirmed-out-0**, **inventorySnapshot-out-0**, and **paymentCompleted-out-0** are the binding names that Java code passes to **StreamBridge**.
- **destination** is the logical stream name on the broker.
- **content-type** specifies the payload format for the message converter to process.
- **brokers** is configuration specific to the Kafka binder in this example.

Because the output binding name is explicitly declared, it does not depend on the name of the Java method calling **StreamBridge**. One binding can be used from multiple places in the application if those places publish the same message type under the same contract.

If using RabbitMQ or Pulsar, the binding and logical destination section can follow a similar organization. Replace the starter and connection settings with the corresponding binder, then verify how destinations map to exchanges/queues or topics/subscriptions. Do not copy Kafka broker settings to another binder.

## 3. Publishing events from a REST controller

A REST API typically receives a command from a client, validates the input, and then publishes an event for other services to process asynchronously. The example below illustrates an endpoint publishing an order confirmation event:

~~~java
import java.time.Instant;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

record OrderConfirmed(String orderId, Instant confirmedAt) {}

@RestController
class OrderEventController {

    private final StreamBridge streamBridge;

    OrderEventController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/api/orders/{orderId}/confirm")
    ResponseEntity<Void> confirm(@PathVariable String orderId) {
        if (orderId == null || orderId.isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        OrderConfirmed event =
                new OrderConfirmed(orderId, Instant.now());

        boolean sent = streamBridge.send("orderConfirmed-out-0", event);
        if (!sent) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .build();
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

When the endpoint is called, the controller creates an **OrderConfirmed** payload and sends it via the **orderConfirmed-out-0** binding. The binder maps that binding to the **orders.confirmed** destination. The client receives HTTP 202 when the send operation is accepted on the application side.

A **true** return value from **StreamBridge.send** indicates that sending to the output channel succeeded per the binding's mechanism. It does not prove the consumer received, processed, or committed the business action. Likewise, HTTP 202 should only be understood as the application having accepted the request for asynchronous processing per the API contract; do not describe it as confirmation that downstream business processing has completed.

In a real application, the controller usually calls a business service to check permissions, order state, and state transition rules. The example above focuses on where the event is published. If an operation simultaneously writes to a database and publishes a message, consistency between the two must be handled; the transactional outbox section below presents a more durable approach.

## 4. Sending a Message with headers

**StreamBridge** can send an object directly or send a **Message<?>**. When metadata such as event ID, event type, or correlation ID is needed, create the message using **MessageBuilder**:

~~~java
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderConfirmed> message = MessageBuilder
        .withPayload(new OrderConfirmed("ORD-1001", Instant.now()))
        .setHeader("eventId", UUID.randomUUID().toString())
        .setHeader("eventType", "OrderConfirmed")
        .setHeader("correlationId", "corr-8a21")
        .build();

boolean sent = streamBridge.send("orderConfirmed-out-0", message);
~~~

Headers support tracing and event interpretation at the consumer. Use consistent header names across producers and pass only necessary metadata. Do not put tokens, credentials, or large business payloads in headers.

If **content-type** is declared on the binding, Spring Cloud Stream can use the corresponding message converter to serialize the payload. When sending **Message<?>**, check headers and binding configuration to ensure the converter receives the right data type. With Avro or Protobuf using native serializers, configure the binder's serializer/deserializer according to the chosen format; **StreamBridge** does not automatically convert objects into every binary format merely by changing the content type.

## 5. Publishing events from a schedule

A periodic task can publish messages without an HTTP request. Enable scheduling and use **StreamBridge** in the scheduled component:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

record InventorySnapshotRequested(String requestId, Instant requestedAt) {}

@Configuration
@EnableScheduling
class SchedulingConfiguration {}

@Component
class InventorySnapshotScheduler {

    private final StreamBridge streamBridge;

    InventorySnapshotScheduler(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Scheduled(fixedDelay = 60000)
    void requestSnapshot() {
        InventorySnapshotRequested event =
                new InventorySnapshotRequested(
                        UUID.randomUUID().toString(),
                        Instant.now());

        boolean sent = streamBridge.send("inventorySnapshot-out-0", event);
        if (!sent) {
            // Log or increment metric so operations detect the failed send.
        }
    }
}
~~~

The **fixedDelay** property specifies the waiting period after the previous invocation finishes. The example uses a 60,000 ms interval. A cron expression can be used when the schedule needs to be tied to a specific time:

~~~java
@Scheduled(cron = "0 0 2 * * *")
void requestNightlySnapshot() {
    // Create the event and send via StreamBridge.
}
~~~

When deploying multiple instances of the application, each instance may run the same schedule and publish duplicate events. If publishing once per period is a strict requirement, a coordination mechanism such as a distributed lock, leader election, or storing run schedules in the database is needed. Consumers should still be idempotent because messages can be redelivered.

For critical tasks, do not just log when sending fails and move on. Persist the work state to be published, set a retry policy, and raise alerts if a scheduled run is not sent successfully.

## 6. Publishing events from a business service

A business service is typically where the application knows an event has actually occurred. For example, after confirming a successful payment, the service publishes **PaymentCompleted** for the invoicing or analytics service to continue processing:

~~~java
import java.time.Instant;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record PaymentCompleted(
        String paymentId,
        String orderId,
        long amountMinorUnits,
        Instant completedAt) {}

@Service
class PaymentApplicationService {

    private final StreamBridge streamBridge;
    private final PaymentGateway paymentGateway;

    PaymentApplicationService(
            StreamBridge streamBridge,
            PaymentGateway paymentGateway) {
        this.streamBridge = streamBridge;
        this.paymentGateway = paymentGateway;
    }

    void completePayment(String paymentId, String orderId) {
        PaymentResult result = paymentGateway.capture(paymentId);
        if (!result.success()) {
            throw new IllegalStateException("Payment was not completed");
        }

        PaymentCompleted event = new PaymentCompleted(
                paymentId,
                orderId,
                result.amountMinorUnits(),
                Instant.now());

        boolean sent = streamBridge.send("paymentCompleted-out-0", event);
        if (!sent) {
            throw new IllegalStateException(
                    "Could not publish PaymentCompleted");
        }
    }
}
~~~

Types **PaymentGateway** and **PaymentResult** represent application business components. The key point is that the event is only created after the payment operation succeeds. Consumers can use paymentId or eventId to identify the message and avoid recording a payment twice.

The example above shows a direct call flow for clarity, but careful consideration is required when the service simultaneously updates a database. If the payment succeeded or the business record committed while sending the message fails, the system can end up with the business operation completed but the event unpublished. If sending the message succeeds and then the database transaction rolls back, consumers may receive an event for a change that does not exist.

Do not assume that a **StreamBridge.send** call and a database transaction form an atomic transaction. For critical events tied to data changes, use a transactional outbox.

## 7. Transactional outbox when event publishing guarantees are needed

Transactional outbox solves the scenario where a business operation must both update data and publish an event. Within the same database transaction, the service writes the business change and an outbox record. A separate publisher reads unpublished records, sends them with **StreamBridge**, and marks them as published after sending succeeds.

~~~text
Business service
      |
      v
Database transaction
  - update business data
  - insert Outbox record
      |
      v
Commit
      |
      v
Outbox publisher / scheduled poller
      |
      v
StreamBridge.send(...)
      |
      v
Broker destination
      |
      v
Mark Outbox record as sent
~~~

Because business data and the outbox record are written in the same transaction, if the transaction rolls back then neither appears. If the application stops after commit but before publishing, the publisher can resend on startup. This prevents losing events due to the gap between commit and sending the message.

Publisher pseudocode:

~~~java
void publishPendingEvents() {
    List<OutboxEvent> events = outboxRepository.findPendingBatch(100);

    for (OutboxEvent event : events) {
        boolean sent = streamBridge.send(
                "paymentCompleted-out-0",
                event.toPaymentCompleted());

        if (sent) {
            outboxRepository.markPublished(event.id());
        } else {
            outboxRepository.recordAttempt(event.id());
        }
    }
}
~~~

This is pseudocode focused on the sequence. In real implementations, design locking or a record-claiming mechanism so multiple publishers do not unintentionally process the same batch, set retry limits, and store error details. If the publisher sends successfully but stops before marking the outbox, the message may be sent again. Therefore, an outbox typically provides at-least-once publishing; consumers must be idempotent based on eventId or a business key.

## 8. Declared bindings and dynamic destinations

There are two ways to use **StreamBridge**:

**Pre-declared bindings** fit when the destination is known and stable. For example, **orderConfirmed-out-0** is explicitly configured with destination **orders.confirmed**. This makes configuration review, permission granting, and monitoring easier.

**Dynamic destinations** fit when the target destination is decided at runtime. If no binding with the same name exists, **StreamBridge** can dynamically create an output binding for the passed destination:

~~~java
boolean sent = streamBridge.send("tenant-a.audit-events", auditEvent);
~~~

In this example, the passed name is used as a dynamic destination when no corresponding binding exists. Creating dynamic bindings depends on the binder's capabilities and application configuration. Restrict allowed destinations according to system rules; avoid taking an arbitrary name from an HTTP request and using it directly as a destination. If callers can choose a destination, map that choice through an application-controlled allow-list.

When destinations are known in advance, prefer declared bindings. Dynamic destinations create additional resources and binding state inside the application; you must manage the number of destinations, binding caches, broker permissions, and resource lifecycles. Do not use dynamic destinations to replace a business routing model that already has clear rules.

## 9. Handling send results and errors

**StreamBridge.send** returns a boolean indicating whether sending the message through the binding succeeded at call time. Check the result when the application needs to react to failures:

- For synchronous REST APIs, return an appropriate error if the message is not accepted for sending and the endpoint contract requires send confirmation.
- For schedulers, log with eventId, increment metrics, and place the work into a retry queue or status table.
- For critical business services, use an outbox so you do not rely on a single direct send.
- For all consumers, design safe duplicate handling and monitor binder retry/DLQ behavior.

A **true** result does not prove the broker durably stored the message under all configurations, that the consumer received it, or that downstream business logic finished. To know a message has been processed, you need application-level acknowledgments, business state, or separate response events.

Do not retry indefinitely directly on the HTTP thread or business processing thread; doing so can exhaust threads and increase load during broker outages. Retries need limits, backoff, and persistent state if work must recover after a process stops.

## 10. Testing components that use StreamBridge

You can use the Spring Cloud Stream test binder to verify messages sent to an output binding without running a real broker. Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.cloud.stream.binder.test.OutputDestination;

@SpringBootTest(properties = {
        "spring.cloud.stream.output-bindings=orderConfirmed-out-0",
        "spring.cloud.stream.bindings.orderConfirmed-out-0.destination=orders.confirmed",
        "spring.cloud.stream.bindings.orderConfirmed-out-0.content-type=application/json"
})
class OrderEventPublishingTest {

    @Autowired
    StreamBridge streamBridge;

    @Autowired
    OutputDestination output;

    @Test
    void publishesAnOrderConfirmedEvent() {
        OrderConfirmed event =
                new OrderConfirmed("ORD-TEST-1", Instant.parse("2026-01-01T00:00:00Z"));

        assertTrue(streamBridge.send("orderConfirmed-out-0", event));
        assertNotNull(output.receive(1000, "orderConfirmed-out-0"));
    }
}
~~~

The test binder verifies the send path at the application and output binding level. It does not replace integration testing with Kafka, RabbitMQ, or Pulsar. With a real broker, verify destination write permissions, serialization, header mapping, connection failures, retries, and behavior during temporary broker outages.

With transactional outbox, add tests verifying that business changes and outbox records commit or roll back together; that the publisher resends pending records after restart; and that consumers do not produce duplicate side effects when receiving the same eventId again.

## 11. Choosing the event publishing point in the architecture

| Publishing source | When to use | Things to watch out for |
|---|---|---|
| REST controller | HTTP request directly requests publishing a message | Authentication, validation, timeouts, and HTTP response semantics |
| Scheduled task | Events or jobs published on a schedule | Multiple instances may run duplicates; needs coordination and state persistence |
| Business service | Events arising from business outcomes | Synchronizing transactions and messages; consider outbox |
| Outbox publisher | Events must be durably published after data commits | Idempotency, batch claiming, retries, and publish status |

Publish events at the place that has enough information to determine the event actually happened. A controller can receive a request, but should not conclude a business action succeeded if the service has not finished validation. A scheduler can generate periodic processing requests, but needs a run ID to detect duplicates. A business service understands domain state, while an outbox ensures the event is stored together with data changes.

## 12. Pre-deployment checklist

- Output bindings have clear names and properly configured destinations.
- Payloads have a stable contract, eventId, and required metadata.
- Content type and serializer match the data format.
- REST endpoints distinguish an accepted request from completed business processing.
- Schedulers have mechanisms to prevent duplicate publishing when running multiple instances if business rules require it.
- Business services do not assume DB transactions and broker sends are atomic.
- Critical events use an outbox or an equivalently designed delivery mechanism.
- Publishers have bounded retries, error observability, and the ability to resume after restarts.
- Consumers are idempotent and have retry/DLQ monitoring.
- Tested with the test binder and integration-tested with the real binder/broker.

**StreamBridge** enables REST controllers, schedulers, and business services to send messages through the same Spring Cloud Stream binding model. Pre-declared bindings fit stable destinations; dynamic destinations are useful when the target is genuinely decided at runtime and properly controlled. For events tied to critical data changes, transactional outbox, bounded retries, and idempotent consumers make the event publishing flow recoverable and more reliable to operate.
