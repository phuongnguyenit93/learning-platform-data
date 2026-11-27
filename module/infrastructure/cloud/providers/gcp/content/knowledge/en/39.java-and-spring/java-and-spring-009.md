# Integrating Spring Boot with Pub/Sub via Messaging Adapters

In the `CLOUD_PROVIDERS_GCP` module, learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability alongside cost. In the **Java and Spring on GCP** chapter, this lesson guides you through publishing and consuming events in a Spring Boot application using **Google Cloud Pub/Sub** via **Spring Integration messaging adapters**.

We build an `orders-api` application: an HTTP request publishes an `OrderCreated` event to the `orders-created` topic; a consumer receives it via the `orders-worker-sub` subscription, runs business processing, and decides whether to `ack` or `nack`. The goal is not just sending a message, but also understanding data contracts, retries, deduplication, IAM, testing, observability, and choosing the right runtime environment.

## 1. Pub/Sub and Spring Integration Model

Pub/Sub delivers messages asynchronously following a publish/subscribe pattern. A **topic** is where producers publish; a **subscription** holds the stream of messages delivered to consumers. Two independent subscriptions on the same topic each receive a copy of the event stream; consumers sharing one subscription divide message processing for that subscription.

Spring Integration provides `Message`, `MessageChannel`, `@MessagingGateway`, `@ServiceActivator`, and Enterprise Integration Patterns. Channel adapters act as the bridge between Spring messages and Pub/Sub.

| Component | Function |
| --- | --- |
| `Message<T>` | Payload and headers of a message inside Spring. |
| `MessageChannel` | Internal channel between components; e.g., `DirectChannel`. |
| `@MessagingGateway` | Maps a Java method to sending a message onto a channel. |
| `PubSubMessageHandler` | Outbound adapter: receives messages from a channel and publishes to a Pub/Sub topic. |
| `PubSubInboundChannelAdapter` | Inbound adapter: uses Streaming Pull to read a Pub/Sub subscription and push messages to a channel. |
| `@ServiceActivator` | Processes incoming messages from a channel. |
| `PubSubTemplate` | Publish/subscribe abstraction configured by Spring Framework on Google Cloud. |
| `PubSubAdmin` | Manages topic and subscription resources during bootstrap. |

~~~mermaid
flowchart LR
  HTTP[POST /orders/id/events] --> REST[OrderController]
  REST --> GW[OrderEventGateway]
  GW --> OUT[ordersOutboundChannel]
  OUT --> ADOUT[PubSubMessageHandler]
  ADOUT --> TOPIC[(orders-created topic)]
  TOPIC --> SUB[(orders-worker-sub)]
  SUB --> ADIN[PubSubInboundChannelAdapter]
  ADIN --> IN[ordersInboundChannel]
  IN --> PROC[OrderProcessor]
  PROC -->|ack/nack| SUB
~~~

Topics and subscriptions are Google Cloud Pub/Sub resources; `MessageChannel` exists only inside the Spring Boot process. Messages are published to a topic; consumers subscribe to a subscription rather than pulling directly from a topic.

### 1.1. When to Choose Adapters?

| Option | Suitable scenario |
| --- | --- |
| Direct `PubSubTemplate` | Small logic needing simple publish/subscribe API calls inside services. |
| Spring Integration channel adapters | Applications with message flows, gateways, filters, transformers, and service activators wanting Enterprise Integration Patterns. |
| Spring Cloud Stream Pub/Sub Binder | Architecture built on Spring Cloud Stream functions/bindings wanting minimal middleware boilerplate. |

This example focuses on **Spring Integration adapters**; there is no need to add the Stream Binder for the same flow.

## 2. Preparing Google Cloud and IAM

You need JDK 17 or newer, a Spring Boot version compatible with Spring Framework on Google Cloud, the Google Cloud CLI, a project with active billing, and Pub/Sub management permissions to create initial resources.

### 2.1. Enable the API and Create a Topic and Pull Subscription

~~~bash
gcloud config set project PROJECT_ID
gcloud services enable pubsub.googleapis.com --project=PROJECT_ID

gcloud pubsub topics create orders-created --project=PROJECT_ID

gcloud pubsub subscriptions create orders-worker-sub \
  --topic=orders-created \
  --ack-deadline=30 \
  --project=PROJECT_ID
~~~

This is a **pull subscription**. `PubSubInboundChannelAdapter` uses Streaming Pull, so no push endpoint is needed. `--ack-deadline=30` sets the initial deadline; the Pub/Sub Java client automatically extends the ack deadline during processing. Do not assume every unacked message will be redelivered after exactly 30 seconds.

When producer and consumer reside in different projects, adapters accept full resource names such as `projects/PROJECT_ID/topics/TOPIC` or `projects/PROJECT_ID/subscriptions/SUBSCRIPTION`; in that case, IAM permissions must be granted on the corresponding project and resource.

### 2.2. Grant Least-Privilege Permissions

Create an illustrative runtime service account:

~~~bash
gcloud iam service-accounts create orders-messaging \
  --display-name="Orders messaging runtime" \
  --project=PROJECT_ID
~~~

Grant publish permission on the topic and subscribe permission on the subscription:

~~~bash
gcloud pubsub topics add-iam-policy-binding orders-created \
  --member="serviceAccount:orders-messaging@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=PROJECT_ID

gcloud pubsub subscriptions add-iam-policy-binding orders-worker-sub \
  --member="serviceAccount:orders-messaging@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber" \
  --project=PROJECT_ID
~~~

This lesson combines producer and consumer in one process for ease of running. In production, separate publisher and subscriber service accounts when the two workloads are independent. A message-processing service does not need Pub/Sub Admin just to read a subscription.

For local development against the real service, run `gcloud auth application-default login` and ensure the principal holds the corresponding Pub/Sub permissions. On Cloud Run, Compute Engine, or GKE, use workload-attached service accounts or Workload Identity Federation. Avoid long-lived service account JSON keys in source code, container images, or CI secrets.

## 3. Dependencies and Spring Boot Configuration

### 3.1. Choosing Library Versions

Spring Framework on Google Cloud uses a BOM to manage versions. For Spring Boot **3.5.x**, the **7.x** line of Spring Framework on Google Cloud is compatible per the project's matrix. Spring Boot 4.x projects have a different compatible branch; always check the compatibility matrix before bumping versions.

Partial `build.gradle` example for a Spring Boot 3.5.x application:

~~~groovy
dependencies {
    implementation platform("com.google.cloud:spring-cloud-gcp-dependencies:7.5.2")
    implementation "com.google.cloud:spring-cloud-gcp-starter-pubsub"
    implementation "org.springframework.integration:spring-integration-core"
    implementation "org.springframework.boot:spring-boot-starter-web"
}
~~~

BOM `7.5.2` is an illustrative version from the project guide; verify the version tested by your organization for real deployments. With Maven, import `com.google.cloud:spring-cloud-gcp-dependencies` in `dependencyManagement` and declare the dependencies above. Avoid mixing legacy `org.springframework.cloud:spring-cloud-gcp-...` coordinates with modern `com.google.cloud:spring-cloud-gcp-...` coordinates.

### 3.2. Configuring Project, Topic, and Subscription

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: orders-api
  cloud:
    gcp:
      project-id: PROJECT_ID
      pubsub:
        enabled: true

app:
  pubsub:
    topic: orders-created
    subscription: orders-worker-sub
~~~

Replace `PROJECT_ID` with your lab project; during deployment it can be overridden with `SPRING_CLOUD_GCP_PROJECT_ID`. The Pub/Sub starter provides `PubSubTemplate` configured with the project and Application Default Credentials (ADC). The keys `app.pubsub.topic` and `app.pubsub.subscription` are application settings to avoid hardcoding resource names in code.

## 4. Outbound Adapter: Sending OrderCreated Events

### 4.1. Defining the Event Contract

`OrderCreated.java`:

~~~java
package com.example.orders;

public record OrderCreated(
    String eventId,
    String orderId,
    String occurredAt,
    int schemaVersion
) {}
~~~

Example JSON:

~~~json
{
  "eventId": "event-6e4158",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-19T09:00:00Z",
  "schemaVersion": 1
}
~~~

`eventId` is the logical identifier of the event, used when implementing idempotency. Pub/Sub assigns its own `messageId` per publish attempt. If a producer retries by republishing the same event, the message ID may differ, so keep `eventId` stable per business transaction.

### 4.2. Messaging Gateway

`OrderEventGateway.java`:

~~~java
package com.example.orders;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "ordersOutboundChannel")
public interface OrderEventGateway {
    void publish(String json);
}
~~~

Spring Integration generates a gateway implementation and sends the `json` argument to the specified channel. Controllers invoke `gateway.publish(...)` like a normal Java method.

### 4.3. Configuring Inbound and Outbound Channels

`PubSubAdapters.java`:

~~~java
package com.example.orders;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler;
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@IntegrationComponentScan(basePackageClasses = OrderEventGateway.class)
public class PubSubAdapters {
    private static final Logger log =
        LoggerFactory.getLogger(PubSubAdapters.class);

    @Bean
    public MessageChannel ordersOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel ordersInboundChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "ordersOutboundChannel")
    public MessageHandler ordersPublisher(
            PubSubTemplate pubSubTemplate, Environment environment) {

        String topic = environment.getRequiredProperty("app.pubsub.topic");
        PubSubMessageHandler adapter =
            new PubSubMessageHandler(pubSubTemplate, topic);

        // Lab: return only after Pub/Sub confirms the publish.
        adapter.setSync(true);
        adapter.setPublishTimeout(10_000L);
        adapter.setSuccessCallback((messageId, original) ->
            log.info("publish confirmed messageId={}", messageId));
        adapter.setFailureCallback((error, original) ->
            log.error("publish failed", error));
        return adapter;
    }

    @Bean
    public PubSubInboundChannelAdapter ordersSubscriber(
            @Qualifier("ordersInboundChannel") MessageChannel input,
            PubSubTemplate pubSubTemplate,
            Environment environment) {

        String subscription =
            environment.getRequiredProperty("app.pubsub.subscription");
        PubSubInboundChannelAdapter adapter =
            new PubSubInboundChannelAdapter(pubSubTemplate, subscription);
        adapter.setOutputChannel(input);
        adapter.setAckMode(AckMode.MANUAL);
        return adapter;
    }

    @Bean
    @ServiceActivator(inputChannel = "ordersInboundChannel")
    public MessageHandler ordersReceiver(
            ObjectMapper mapper, OrderProcessor processor) {

        return springMessage -> {
            BasicAcknowledgeablePubsubMessage original =
                springMessage.getHeaders().get(
                    GcpPubSubHeaders.ORIGINAL_MESSAGE,
                    BasicAcknowledgeablePubsubMessage.class);

            if (original == null) {
                throw new IllegalStateException("Missing Pub/Sub ack header");
            }

            try {
                byte[] payload = (byte[]) springMessage.getPayload();
                OrderCreated event =
                    mapper.readValue(payload, OrderCreated.class);

                processor.handle(event);
                original.ack().whenComplete((done, error) -> {
                    if (error != null) {
                        log.error("Pub/Sub ack failed", error);
                    }
                });
            } catch (Exception error) {
                log.error("Processing failed; requesting redelivery", error);
                original.nack().whenComplete((done, nackError) -> {
                    if (nackError != null) {
                        log.error("Pub/Sub nack failed", nackError);
                    }
                });
            }
        };
    }
}
~~~

`DirectChannel` invokes the handler on the dispatching thread, which works well when you want processing to finish before acking. If switching to an `ExecutorChannel` or async pipeline, ensure the adapter/consumer never acks before business work is actually complete.

In `ordersPublisher`, `PubSubMessageHandler` publishes asynchronously by default; `setSync(true)` combined with a 10-second timeout makes gateway calls wait for publish confirmation. In production, if publishing asynchronously, use success/failure callbacks or a transactional outbox to track events not yet confirmed by Pub/Sub.

On the inbound side, `BasicAcknowledgeablePubsubMessage.ack()` and `nack()` return `CompletableFuture<Void>`. The code monitors ack/nack failures to avoid mistaking method invocation for successful acknowledgement.

### 4.4. Business Handler

`OrderProcessor.java`:

~~~java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderProcessor {
    private static final Logger log =
        LoggerFactory.getLogger(OrderProcessor.class);

    public void handle(OrderCreated event) {
        if (event.schemaVersion() != 1) {
            throw new IllegalArgumentException("Unsupported event version");
        }

        // Illustrative only: production must commit DB/idempotency before acking.
        log.info("handled eventId={} orderId={}",
            event.eventId(), event.orderId());
    }
}
~~~

This handler is intentionally simple for learning the messaging flow. When using a database, add a unique constraint on `eventId` or equivalent business key, apply mutations in a single transaction, and ack only after commit.

### 4.5. HTTP Controller to Test the Publisher

`OrderController.java`:

~~~java
package com.example.orders;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderEventGateway gateway;
    private final ObjectMapper mapper;

    public OrderController(OrderEventGateway gateway, ObjectMapper mapper) {
        this.gateway = gateway;
        this.mapper = mapper;
    }

    @PostMapping("/{orderId}/events")
    public ResponseEntity<Map<String, String>> publish(
            @PathVariable String orderId) throws JsonProcessingException {

        OrderCreated event = new OrderCreated(
            UUID.randomUUID().toString(),
            orderId,
            Instant.now().toString(),
            1
        );

        gateway.publish(mapper.writeValueAsString(event));

        return ResponseEntity.accepted()
            .body(Map.of("eventId", event.eventId()));
    }
}
~~~

With the synchronous publisher in this example, `202 Accepted` is returned after Pub/Sub confirms the publish. **The HTTP response does not prove the consumer has finished processing.** If switching to async publishing, `202` may return before Pub/Sub accepts the message; ensure publish durability guarantees match your system commitments.

### 4.6. Spring Boot Entry Point

`OrdersApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Place classes in the same package or subpackages of `com.example.orders` so component scanning discovers controllers, services, and adapter configurations.

## 5. ACK, NACK, and Success Conditions

With `PubSubInboundChannelAdapter`, the three acknowledgement modes behave differently:

| Ack mode | When handler succeeds | When exception escapes adapter |
| --- | --- | --- |
| `AUTO` (default) | Adapter acks | Adapter nacks for redelivery |
| `AUTO_ACK` | Adapter acks | Does not auto-ack/nack; waits for deadline |
| `MANUAL` | Application must ack/nack explicitly | Application must still decide ack/nack |

In `MANUAL` mode, calling `ack()` after commit defines the boundary of message processing responsibility. `nack()` can trigger immediate or near-immediate redelivery; if neither ack nor nack is called, Pub/Sub redelivers once the deadline expires and lease extensions end.

**Watch out for error channels:** With `AUTO`, if a Spring Integration error handler catches the exception and returns normally, the adapter may treat the flow as successful and ack the message. For `AUTO` mode to nack, the exception must propagate back to the adapter. `MANUAL` mode makes decisions explicit right inside the consumer, while requiring complete handling of every error path.

Never ack before committing to the database. If the app crashes between commit and ack, the message returns; that is why consumers must be idempotent. If it crashes before commit, Pub/Sub can redeliver the message for processing.

## 6. End-to-End Testing on Google Cloud

1. Ensure the topic/subscription exist, the application principal holds granted IAM roles, and `application.yml` points to the right project.
2. Start the app with Gradle or Maven. On a workstation, run `gcloud auth application-default login` beforehand.
3. Publish via HTTP:

~~~bash
./gradlew bootRun

curl -X POST "http://localhost:8080/orders/ORD-1001/events"
~~~

On Windows, use `gradlew.bat bootRun`. Observe `publish confirmed messageId=...` and `handled eventId=... orderId=...` in consumer logs.

You can also publish directly via the CLI to test the consumer independently of the controller:

~~~bash
gcloud pubsub topics publish orders-created \
  --message='{"eventId":"lab-1002","orderId":"ORD-1002","occurredAt":"2026-11-19T09:00:00Z","schemaVersion":1}' \
  --project=PROJECT_ID
~~~

Temporarily modify `OrderProcessor.handle` to throw an exception when `orderId` equals `ORD-FAIL`, send a failing event, and observe `nack` followed by redelivery. Restore the handler afterward. Pub/Sub events can be redelivered multiple times, so logs alone do not prove an event was processed only once.

## 7. Testing with the Pub/Sub Emulator

The Pub/Sub emulator lets you test publishing and subscribing without touching production resources. Start it via the Google Cloud CLI:

~~~bash
gcloud components install pubsub-emulator

gcloud beta emulators pubsub start \
  --project=local-pubsub \
  --host-port=127.0.0.1:8085
~~~

Add a Spring profile config file `application-local.yml`:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-pubsub
      pubsub:
        emulator-host: 127.0.0.1:8085
~~~

Activate the `local` profile when running against the emulator. The emulator does not enforce real IAM; resources and messages in a local session do not reflect production Pub/Sub reliability, quotas, or policies. Important: **`gcloud pubsub topics/subscriptions` does not create resources in the emulator**. The `gcloud pubsub` commands in Section 2 target the real service only.

Before starting the inbound adapter, create the topic and subscription in the emulator via `PubSubAdmin` in a separate bootstrap program or test fixture:

~~~java
// PubSubAdmin is already connected to project local-pubsub and the emulator.
pubSubAdmin.createTopic("orders-created");
pubSubAdmin.createSubscription("orders-worker-sub", "orders-created");
~~~

Do not blindly run those two creation calls inside an `ApplicationRunner` within the consumer app itself: the inbound adapter lifecycle may start before the runner, causing the subscriber to connect before the subscription exists. Integration tests should bootstrap resources before the consumer context starts.

## 8. Idempotency, Retries, and Dead-Letter Topics

### 8.1. Handling Duplicate Messages

Pub/Sub provides **at-least-once delivery** by default. Messages can be redelivered due to ack deadlines, network blips, client restarts, or crashes. If a consumer charges payments or writes to a database, reprocessing must not cause duplicate side effects.

Production implementation pattern:

1. Producer assigns a stable `eventId` to the same logical event.
2. Consumer opens a database transaction.
3. Insert `eventId` into a `processed_events` table with a unique constraint; if already present, treat as already processed.
4. Apply business mutations in the **same transaction**.
5. Commit successfully, then ack Pub/Sub.

If the consumer crashes after commit but before ack, the message may return and the unique constraint blocks duplicate side effects. Never rely on an in-memory `Set` across multiple replicas; restarts wipe it and races occur across instances.

### 8.2. Distinguishing Transient Errors from Permanent Errors

| Error | Recommended handling |
| --- | --- |
| Database timeout or downstream 503 | Retry with backoff; monitor delivery attempts and cap concurrency. |
| Quota 429 | Slow down, curb fan-out, and tune flow control. |
| Malformed JSON schema, unsupported event version | Route to DLQ after appropriate delivery attempts and inspect offline. |
| Duplicate already-committed event | Ack and skip repeating side effects. |
| Permission denied / missing subscription | Fix configuration/IAM; retrying the message will not fix system errors. |

### 8.3. Configuring a DLQ on a Subscription

~~~bash
gcloud pubsub topics create orders-dlq --project=PROJECT_ID

gcloud pubsub subscriptions create orders-dlq-sub \
  --topic=orders-dlq \
  --project=PROJECT_ID

gcloud pubsub subscriptions update orders-worker-sub \
  --dead-letter-topic=orders-dlq \
  --max-delivery-attempts=5 \
  --project=PROJECT_ID
~~~

The dead-letter topic belongs to the **source subscription** configuration. For forwarding to work, the project's Pub/Sub service agent (`service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com`) needs publish permission on the DLQ topic and subscribe/ack permissions on the source subscription. Pub/Sub documentation specifies the exact roles and setup instructions.

`max-delivery-attempts` is an approximate target; Pub/Sub may make slightly fewer or more delivery attempts. Maintain a subscription on the DLQ topic, a runbook, alerts, sensitive data handling, and a controlled replay procedure. Never replay schema-invalid messages automatically in an infinite loop.

## 9. Pub/Sub Headers, Schemas, and Ordering

The outbound adapter maps Spring `Message` headers to Pub/Sub attributes (string values), excluding certain internal headers; the inbound adapter maps attributes back to message headers.

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

Message<String> message = MessageBuilder
    .withPayload(json)
    .setHeader("eventType", "OrderCreated")
    .setHeader("schemaVersion", "1")
    .setHeader("correlationId", requestId)
    .build();

ordersOutboundChannel.send(message);
~~~

This illustrates sending headers given a `MessageChannel` reference and JSON payload. Never put access tokens, passwords, cookies, card numbers, or unnecessary personal data into payloads or headers. In production, use versioned schema contracts and maintain backward/forward compatibility so producers and consumers can deploy independently.

If ordering by `orderId` is required, Pub/Sub supports ordering keys. The Spring adapter uses `GcpPubSubHeaders.ORDERING_KEY`, and the publisher must enable `spring.cloud.gcp.pubsub.publisher.enable-message-ordering=true`. The subscription must also enable message ordering upon creation. Message ordering applies **per key**, does not enforce global topic-wide ordering, and affects retries and concurrency.

## 10. Choosing the Right Runtime Environment

**GKE / Compute Engine:** Streaming Pull suits continuously running applications or workers. Use Workload Identity Federation for GKE or a VM service account; configure subscriber flow control, concurrency, and graceful shutdown. If database writes are slow, limit outstanding messages to avoid exhausting the connection pool.

**Cloud Run:** Inbound Streaming Pull is a background task. If a Cloud Run service receives CPU only while handling HTTP requests, background subscribers can be throttled or paused. Evaluate instance-based billing, minimum instances, and instance lifecycles when running Streaming Pull on Cloud Run. For request-driven architectures, a **Pub/Sub push subscription** calling a Cloud Run HTTP endpoint is usually a better fit—though that uses the HTTP push model rather than the inbound Streaming Pull adapter shown here.

Running producer and consumer in one process is convenient for labs. In production, split them into two deployments to scale independently by HTTP traffic versus subscription backlog, and to separate IAM identities, quotas, and failure domains.

## 11. Observability and Operations

When deployed, monitor both the client and Pub/Sub:

| Signal | Meaning |
| --- | --- |
| `subscription/num_undelivered_messages` | Backlog; how far behind the consumer is. |
| `subscription/oldest_unacked_message_age` | Age of the oldest unacked message, reflecting processing lag. |
| Publish latency/failure | Publisher permissions, quotas, networking, and timeouts. |
| Consumer processing time/error | Health of business logic, database, and downstreams. |
| Ack/nack and redelivery | Repeated errors, deadline expirations, or failed processing. |
| `subscription/dead_letter_message_count` | Count of messages forwarded to the DLQ. |

Log `eventId`, `messageId` if appropriate, subscription, schema version, processing status, and sanitized errors. Use OpenTelemetry to create producer/consumer spans and propagate trace context via Pub/Sub attributes when end-to-end distributed tracing is needed. Context propagation via message metadata is not guaranteed unless configured by the application.

Set alerts on backlog, message age, DLQ counts, and failure rates; maintain a runbook for stuck subscriptions. Monitor billing across message volume, retention, egress, and log/metric ingestion—not just application CPU.

## 12. Troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Inbound adapter cannot find subscription | Wrong project, wrong subscription name, or subscription missing. | Check project ID, `app.pubsub.subscription`, and Pub/Sub Console. |
| Publish fails with `PERMISSION_DENIED` | Runtime lacks Pub/Sub Publisher on the topic. | Check principal and grant role on the exact topic. |
| Pull fails with `PERMISSION_DENIED` | Runtime lacks Pub/Sub Subscriber on the subscription. | Check IAM and runtime identity. |
| Gateway bean not created | Component scan for `@MessagingGateway` not enabled. | Check `@IntegrationComponentScan` and packages. |
| Payload throws `ClassCastException` | Inbound defaults to `byte[]`, handler casts to `String`. | Decode UTF-8 or configure a payload converter. |
| Consumer sees continuous redelivery | Nacks, parse errors, downstream failures, deadlines, or failed acks. | Check exceptions, subscriber metrics, and DLQ. |
| Messages vanish despite processing errors | Using `AUTO` and an error handler swallowed the exception. | Propagate errors or switch to `MANUAL` ack/nack. |
| Duplicate records created | At-least-once delivery without idempotency. | Add unique constraint on `eventId`, transaction, and ack after commit. |
| DLQ receives no messages | Service agent lacks forwarding permissions or misconfiguration. | Check service agent publisher/subscriber roles. |
| Emulator runs yet app hits real Pub/Sub | `local` profile not active or `emulator-host` not set. | Check profile/endpoint; bootstrap local resources before starting. |
| Streaming Pull erratic on Cloud Run | CPU throttled outside requests or scale-to-zero. | Adjust CPU allocation/min instances or switch to HTTP push. |

## 13. Completion Checklist

- [ ] Selected compatible Spring Boot and Spring Framework on Google Cloud BOM versions.
- [ ] Created topic and pull subscription in the target project.
- [ ] Attached a runtime identity with resource-scoped Pub/Sub Publisher and Subscriber roles.
- [ ] Spring Boot includes `PubSubTemplate`, application config, and Spring Integration dependency.
- [ ] Gateway sends JSON through outbound channel and `PubSubMessageHandler`.
- [ ] Inbound adapter uses Streaming Pull to push `byte[]` into the inbound channel.
- [ ] `ServiceActivator` parses the event and runs business logic before acking.
- [ ] `MANUAL` mode handles both ack and nack paths and observes ack/nack errors.
- [ ] Tested publishing via HTTP and CLI; verified message processing.
- [ ] Idempotency and DLQ strategy are in place before handling real data.
- [ ] Emulator tested under a dedicated profile without mixing local and cloud resources.
- [ ] Monitoring tracks backlog, oldest unacked age, publish failures, retries, and DLQ counts.
- [ ] Selected Streaming Pull or push model suited to Cloud Run/GKE/VM.

## References

- [Google Cloud: Using Pub/Sub in Spring applications](https://docs.cloud.google.com/pubsub/docs/spring) — distinguishing starters, Spring Integration adapters, and Stream Binder.
- [Spring Framework on Google Cloud: Spring Integration](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/spring-integration.html) — inbound/outbound adapters, ack modes, headers, and error handling.
- [Spring Framework on Google Cloud: Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/pubsub.html) — configuration, PubSubTemplate, and PubSubAdmin.
- [Spring Framework on Google Cloud: Getting Started](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/getting-started.html) — BOM and compatibility matrix.
- [Spring Guide: Messaging with Google Cloud Pub/Sub](https://github.com/spring-guides/gs-messaging-gcp-pubsub) — Spring Integration channel adapters example.
- [Pub/Sub: Dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics) — DLQ, service agent IAM, and delivery attempts.
- [Pub/Sub: Testing apps locally with the emulator](https://docs.cloud.google.com/pubsub/docs/emulator) — running the emulator, limitations, and connecting.
- [Pub/Sub: Subscriber overview](https://docs.cloud.google.com/pubsub/docs/subscriber) — Streaming Pull, ack deadlines, and redelivery.
- [Pub/Sub: Monitoring](https://docs.cloud.google.com/pubsub/docs/monitoring) — backlog, oldest unacked age, and operations.
