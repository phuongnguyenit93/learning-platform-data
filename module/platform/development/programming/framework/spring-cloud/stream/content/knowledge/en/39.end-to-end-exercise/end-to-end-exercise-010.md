# Integrating the Pulsar Binder with Appropriate Schemas and Subscriptions

In this exercise, you connect a Spring Cloud Stream application to Apache Pulsar, publish order events through a topic with a JSON schema, and consume events using a named subscription. You will configure each binding individually so producer and consumer share the same data contract, then select a subscription type matching how the application needs to scale.

The Spring Cloud Stream Binder for Apache Pulsar lets applications focus on domain functions. The binder maps Spring Cloud Stream bindings to topics and manages producer and consumer creation via Spring for Apache Pulsar. What still requires careful design is the message contract, subscription naming, and how multiple consumers share work.

## Objectives

After completing this exercise, you will be able to:

- Add the Pulsar Binder to a Spring Cloud Stream application.
- Map output and input bindings to the same fully qualified topic name.
- Enable native encoding and native decoding to use Pulsar schemas.
- Declare consistent schema types and Java message types on both producer and consumer.
- Configure a durable consumer group and subscription, selecting a subscription type suited to the processing model.
- Test the event flow and verify subscriptions on Pulsar.

## Exercise Context

Suppose an e-commerce system emits an **OrderCreated** event after an order is created. The fulfillment service needs to receive this event to update status and trigger downstream steps. The topic used in this exercise is:

    persistent://public/default/order-events

The fully qualified topic name includes persistence mode, tenant, namespace, and topic name. Writing the full name prevents topic mismatches when applications run across multiple tenants or namespaces.

Processing flow:

    HTTP request
        -> StreamBridge
        -> orderEvents-out-0
        -> Pulsar topic: order-events
        -> processOrderCreated-in-0
        -> Consumer<OrderCreated>

Producer and consumer share the same `OrderCreated` data type. The consumer belongs to group `order-fulfillment-v1`. Instances in the same group share a subscription, while other groups can receive independent copies of the event.

## 1. Adding the Pulsar Binder

Add the binder dependency to the Maven application:

    <dependency>
        <groupId>org.springframework.pulsar</groupId>
        <artifactId>spring-pulsar-spring-cloud-stream-binder</artifactId>
    </dependency>

The application also needs Spring Boot Web if you want to expose the HTTP endpoint in this example. To avoid version conflicts, use a mutually compatible BOM and release train across Spring Boot, Spring Cloud Stream, and Spring for Apache Pulsar; never manually pick a binder version from a different release line than the core libraries.

When only one binder is on the classpath, Spring Cloud Stream can select it automatically. If the application includes multiple binders, specify the binder on each binding per project configuration.

## 2. Declaring the Event Contract

Create the `OrderCreated` data type. Identifier fields support traceability and deduplication at the business layer, while `amountInCents` avoids floating-point errors when representing money.

    package com.example.orders;

    public record OrderCreated(
            String eventId,
            String orderId,
            String customerId,
            long amountInCents,
            String currency,
            String occurredAt
    ) {
    }

In this example, `occurredAt` is an ISO-8601 timestamp string such as `2026-11-24T09:30:00Z`. A production event contract should clearly specify formats, timezones, currency units, field semantics, and compatibility rules when adding or changing fields.

## 3. Writing the Consumer and Publisher

The consumer is declared using Spring Cloud Stream's functional model:

    package com.example.orders;

    import java.util.function.Consumer;

    import org.springframework.boot.SpringApplication;
    import org.springframework.boot.autoconfigure.SpringBootApplication;
    import org.springframework.context.annotation.Bean;

    @SpringBootApplication
    public class OrderEventApplication {

        public static void main(String[] args) {
            SpringApplication.run(OrderEventApplication.class, args);
        }

        @Bean
        Consumer<OrderCreated> processOrderCreated() {
            return event -> {
                System.out.printf(
                        "Received eventId=%s orderId=%s amount=%d %s%n",
                        event.eventId(),
                        event.orderId(),
                        event.amountInCents(),
                        event.currency()
                );

                // Call domain service to update the order.
                // The service should use eventId or orderId to guarantee idempotency.
            };
        }
    }

The publisher uses `StreamBridge` to send an `OrderCreated` object to the configured output binding:

    package com.example.orders;

    import org.springframework.cloud.stream.function.StreamBridge;
    import org.springframework.http.HttpStatus;
    import org.springframework.http.ResponseEntity;
    import org.springframework.web.bind.annotation.PostMapping;
    import org.springframework.web.bind.annotation.RequestBody;
    import org.springframework.web.bind.annotation.RequestMapping;
    import org.springframework.web.bind.annotation.RestController;

    @RestController
    @RequestMapping("/api/order-events")
    public class OrderEventController {

        private final StreamBridge streamBridge;

        public OrderEventController(StreamBridge streamBridge) {
            this.streamBridge = streamBridge;
        }

        @PostMapping
        public ResponseEntity<Void> publish(@RequestBody OrderCreated event) {
            boolean sent = streamBridge.send("orderEvents-out-0", event);
            if (!sent) {
                return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
            }
            return ResponseEntity.accepted().build();
        }
    }

`orderEvents-out-0` is the output binding name used by `StreamBridge`. `processOrderCreated-in-0` is derived from the `processOrderCreated` function bean name. If you rename the function or remap bindings, update the corresponding configuration keys.

## 4. Configuring Connection, Schema, and Subscription

Create `application.yml`:

    server:
      port: 8090

    spring:
      pulsar:
        client:
          service-url: pulsar://localhost:6650
        admin:
          service-url: http://localhost:8080
      cloud:
        function:
          definition: processOrderCreated
        stream:
          bindings:
            orderEvents-out-0:
              destination: persistent://public/default/order-events
              producer:
                use-native-encoding: true
            processOrderCreated-in-0:
              destination: persistent://public/default/order-events
              group: order-fulfillment-v1
              consumer:
                use-native-decoding: true
          pulsar:
            bindings:
              orderEvents-out-0:
                producer:
                  schema-type: JSON
                  message-type: com.example.orders.OrderCreated
              processOrderCreated-in-0:
                consumer:
                  schema-type: JSON
                  message-type: com.example.orders.OrderCreated
                  subscription:
                    name: order-fulfillment-v1
                    type: Shared
                    mode: Durable
                    initial-position: Earliest

Two groups of properties play distinct roles:

| Property | Role |
|---|---|
| `spring.cloud.stream.bindings.*.destination` | Selects the topic used by the binding |
| `spring.cloud.stream.bindings.*.group` | Sets a named consumer group on input bindings |
| `producer.use-native-encoding` | Lets the Pulsar client encode payloads per declared schema |
| `consumer.use-native-decoding` | Lets the Pulsar client decode payloads per declared schema |
| `spring.cloud.stream.pulsar.bindings.*.producer.schema-type` | Schema type of outgoing messages |
| `spring.cloud.stream.pulsar.bindings.*.consumer.schema-type` | Schema type of incoming messages |
| `producer/consumer.message-type` | Java type used to write or read schema data |
| `consumer.subscription.*` | Subscription name, type, mode, and initial position |

In this example, both `group` and `subscription.name` are set to `order-fulfillment-v1` so the Spring Cloud Stream group name matches the Pulsar subscription. A `Durable` subscription retains its cursor when consumers pause. `initial-position: Earliest` applies only when Pulsar first creates the subscription; it does not rewind an existing subscription.

`spring.pulsar.client.service-url` is the broker protocol URL. `spring.pulsar.admin.service-url` is the Pulsar Admin HTTP URL used by the binder when provisioning topics. These typically default to ports 6650 and 8080 in a standalone Pulsar environment. The sample app runs HTTP on port 8090 to avoid conflicting with Admin port 8080.

## 5. Understanding How Schemas Are Applied

Spring Cloud Stream has its own message conversion layer. Without native encoding/decoding enabled, the framework typically converts payloads through a message converter, sending `byte[]` to Pulsar with `Schema.BYTES`. Setting content type `application/json` in that case only tells Spring how to convert payloads—it does not mean the topic stores a Pulsar JSON schema.

When native encoding is enabled on the producer and native decoding on the consumer, Pulsar handles schema serialization and deserialization. Therefore, configuration must include all four settings:

1. Producer enables `use-native-encoding`.
2. Consumer enables `use-native-decoding`.
3. Producer and consumer declare compatible `schema-type` values.
4. `message-type` points to the exact Java class to write or read.

`JSON` fits when you want human-readable contracts and broad system interoperability. `AVRO` or `PROTOBUF` fits when teams need structured schema management and stricter contract evolution. Across `AVRO`, `PROTOBUF`, or `JSON`, producers and consumers must agree on the schema type and field interpretation. When schemas cover both keys and values, the binder also supports `message-key-type` and `message-value-type`.

Never change the data type of a field already used by consumers without checking the namespace's schema compatibility policy. When adding fields, provide defaults or handle absent values; deploy consumers capable of reading both old and new data before producers emit the new schema. Always verify the registered broker schema in an integration environment before releasing.

## 6. Choosing a Subscription Type

The subscription governs how Pulsar distributes messages across consumers registered under the same subscription name. Choose the type based on parallelism, ordering, and failover needs:

| Type | Distribution behavior | Suitable use cases |
|---|---|---|
| `Exclusive` | Single active consumer on the subscription | Single-threaded tasks or strict single-consumer requirement |
| `Failover` | One active consumer with standby backups | Need standby failover when primary consumer drops |
| `Shared` | Multiple consumers receive messages concurrently | Parallel processing, scaling instances with load |
| `Key_Shared` | Multiple consumers process concurrently; messages with the same key route consistently | Parallelism across orders while keeping per-`orderId` ordering |

This exercise picks `Shared` because the goal is balancing order processing across multiple instances. Under `Shared`, messages may be delivered to different consumers; global ordering is not preserved. If business logic requires every event of the same `orderId` to follow the same processing stream, consider `Key_Shared` and ensure producers set the Pulsar message key to `orderId`. Also check batching requirements and limitations for `Key_Shared` in your deployed Pulsar version.

A named subscription should represent a stable processing purpose, such as `order-fulfillment-v1`. Independent services needing copies of every event should use distinct subscription names. Competing instances of the same service should share the same subscription name.

## 7. Running and Testing the Event Flow

Start a standalone Pulsar broker exposing port 6650 and Admin HTTP 8080, then start the Spring Boot application. The binder can auto-provision basic topics if they do not exist; if the environment restricts auto-creation, pre-create the topic using admin tools and grant appropriate permissions.

Send a test event to the endpoint using PowerShell:

    $body = @{
        eventId = "evt-001"
        orderId = "ORD-001"
        customerId = "CUS-007"
        amountInCents = 125000
        currency = "VND"
        occurredAt = "2026-11-24T09:30:00Z"
    } | ConvertTo-Json

    Invoke-RestMethod -Method Post -Uri "http://localhost:8090/api/order-events" -ContentType "application/json" -Body $body

Expected outcome:

- HTTP returns `202 Accepted` once `StreamBridge` accepts sending the message to the output binding.
- Consumer logs print `eventId` as `evt-001`, `orderId` as `ORD-001`, and `amountInCents` as `125000`.
- Pulsar shows topic `order-events` with subscription `order-fulfillment-v1`.

Inspect topic stats with Pulsar Admin:

    bin/pulsar-admin topics stats persistent://public/default/order-events

In the output, verify the exact subscription name, connected consumer count, and backlog. Send another event and confirm the consumer receives it. Start a second application instance with the same group to verify `Shared` subscription load distribution across instances. Each message within the same subscription is delivered to one consumer at a time, while another subscription group can still receive its own independent copy.

HTTP `202` only confirms the binding accepted the send call; it does not prove downstream consumer business logic completed. In production, track processing outcomes, retries, dead-letter topics, and backlog state separately.

## 8. Troubleshooting Common Issues

| Symptom | Possible cause | How to check |
|---|---|---|
| App cannot connect to broker | Wrong service URL, DNS, port, or TLS config | Check `spring.pulsar.client.service-url` and port reachability |
| Cannot create topic | Wrong Admin URL or missing admin permissions | Check `spring.pulsar.admin.service-url`, tenant/namespace permissions, and provisioner logs |
| Producer sends but consumer does not read | Mismatched destination, function definition, or binding name | Compare `processOrderCreated-in-0` and `orderEvents-out-0` |
| Schema error or payload decode failure | `schema-type` or `message-type` mismatch | Compare `schema-type`, `message-type`, and the schema registered on the topic |
| Consumer reads raw `byte[]` | Native decoding disabled or binding misconfigured | Check `consumer.use-native-decoding` and Pulsar consumer settings |
| Second instance fails to join subscription | Subscription type rejects multiple consumers or name mismatch | Check `subscription.type` and `subscription.name` across all instances |
| Consumer starts without receiving old messages | Subscription already exists with an advanced cursor | Check backlog and remember `initial-position` only applies on subscription creation |
| Duplicate event processing | Retries, redelivery, or producer re-emitting same event | Use `eventId` as an idempotency key at the business layer |

Never handle duplicates by assuming the broker always delivers messages exactly once. Consumers should record processed `eventId`s within the same transaction boundary as business updates, or apply an equivalent idempotency mechanism.

## 9. Extension Exercises

1. Replace `JSON` with `AVRO`. Declare the schema, update `schema-type`, and verify both producer and consumer read the data.
2. Run two consumer instances with the same group and observe how the `Shared` subscription distributes messages.
3. Create a second consumer group named `order-audit-v1`. Verify the audit group receives an independent copy alongside fulfillment.
4. Switch to `Key_Shared`, send messages keyed by `orderId`, and verify events for the same order route consistently to the same consumer.
5. Add an optional field to `OrderCreated`. Verify consumers can read both old and new data before deploying the updated producer.
6. Configure retry and dead-letter topics for recoverable processing failures; monitor backlog and DLQ counts.

## Completion Criteria

- The application connects to Pulsar using valid broker and Admin URLs.
- Output and input bindings both point to topic `order-events`.
- Producer and consumer use native encoding/decoding with matching JSON schemas and message types.
- The consumer uses a stable group and subscription name, `Durable` mode, and `Shared` type for load balancing.
- Test events can be published and observed arriving with accurate fields at the consumer.
- You can explain why `Shared` fits load balancing and when to choose `Key_Shared`.

## References

- [Spring Cloud Stream Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Cloud Stream Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Boot Apache Pulsar Support](https://docs.spring.io/spring-boot/3.5/reference/messaging/pulsar.html)
- [Spring Boot Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
