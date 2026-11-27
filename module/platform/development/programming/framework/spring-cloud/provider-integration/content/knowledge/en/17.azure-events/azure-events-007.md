# Publishing and Receiving Event Grid Events via SDK or Starter Capabilities

Azure Event Grid is a publish/subscribe event routing service. Applications publish events to a topic or domain; Event Grid applies event subscription filters and forwards matching events to event handlers such as HTTP webhooks, Service Bus queues/topics, Event Hubs, or Storage Queues. When integrating with Spring Boot, you can use the **Azure SDK for Java** directly or the **Spring Cloud Azure Event Grid starter** to publish events. On the receiving side, the application integrates with the registered target endpoint; the Event Grid Java SDK does not provide a receiver client to pull events from a topic.

This lesson focuses on Event Grid topics/domains and push delivery using the publisher SDK/starter. Event Grid namespaces with pull delivery have a separate consumption model and API; do not use the webhook/Service Bus examples below as configuration for a namespace pull consumer.

This lesson belongs to the **Azure Events** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with AWS, Azure, and Google Cloud managed services through the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on publishing `EventGridEvent`/`CloudEvent`, using the starter in Spring Boot, receiving via webhook or Service Bus, endpoint validation, retries, dead-lettering, and secure operations.

## 1. Learning Objectives

After this lesson, you will be able to:

- Describe the publisher → topic/domain → event subscription → event handler flow.
- Distinguish Event Grid from Event Hubs and Service Bus to choose the right service.
- Choose `EventGridEvent`, `CloudEvent`, or a custom schema according to the topic's input schema.
- Build a publisher client with the Azure SDK for Java and use the Spring Cloud Azure Event Grid starter.
- Configure Microsoft Entra ID, Managed Identity, and the EventGrid Data Sender role.
- Receive events via an HTTP webhook in Spring Boot or route events to Service Bus for consumer processing.
- Perform subscription validation properly for Event Grid schema and CloudEvents 1.0.
- Deserialize events, handle duplicates, return HTTP acknowledgments, and persist work durably.
- Configure retries/dead-lettering, monitor delivery failures, and run integration tests.

## 2. Event Publishing and Receiving Flow

~~~mermaid
flowchart LR
    P["Spring Boot publisher"] --> SDK["EventGridPublisherClient"]
    SDK --> T["Event Grid topic / domain"]
    T --> F["Event subscription + filters"]
    F --> W["HTTP webhook"]
    F --> Q["Service Bus queue"]
    F --> H["Event Hubs"]
    W --> C1["Spring Boot webhook handler"]
    Q --> C2["Spring Boot Service Bus consumer"]
    H --> C3["EventProcessorClient"]
~~~

Each component has a distinct responsibility:

| Component | Responsibility |
|---|---|
| Publisher | Builds events per contract and sends them to the endpoint |
| Topic/domain | Receives events from publishers; a domain can contain multiple topics |
| Event subscription | Selects events to receive using filters and configures the destination |
| Event handler | Receives events via webhook or a supported target service |
| Consumer application | Deserializes, validates, deduplicates, and executes business logic |
| Dead-letter destination | Stores events that could not be delivered for investigation/replay |

**Event Grid is an event router and delivery service.** A topic/domain is not an event store for consumers to re-read history at will. Events are delivered to subscription endpoints; if you need a durable queue, use Service Bus; if you need a stream with offset-based replay, use Event Hubs; if you need long-term retention, use storage/archives.

## 3. Choosing a Schema Before Creating a Publisher

A topic or domain is configured with an input schema. Publishers must send the matching event type.

| Topic/Domain Input Schema | Java Type with SDK | Characteristics |
|---|---|---|
| Event Grid schema | `EventGridEvent` | Azure's envelope: `id`, `subject`, `eventType`, `eventTime`, `dataVersion`, `data` |
| CloudEvents 1.0 | `com.azure.core.models.CloudEvent` | Standardized envelope with `source`, `type`, `id`, `time`, `data` |
| Custom schema | `BinaryData` | Application defines its own JSON structure |

You cannot send an `EventGridEvent` to a topic expecting CloudEvents or vice versa. If a publisher uses the wrong generic type/schema, Event Grid returns Bad Request and rejects the event.

You can check the input schema using the Azure CLI:

~~~bash
az eventgrid topic show \
  --name <topic-name> \
  --resource-group <resource-group> \
  --query inputSchema
~~~

Choose CloudEvents when sharing event contracts across multiple platforms or cloud providers. Event Grid schema is convenient when integrating Azure services and ecosystems that already use this envelope. Custom schemas should only be used when you have a tightly governed proprietary contract.

## 4. Dependencies and BOM for Spring Boot

### 4.1. Spring Cloud Azure Event Grid Starter

The starter lets Spring Boot auto-configure a publisher client based on endpoint and credentials:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>SPRING_CLOUD_AZURE_BOM_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-eventgrid</artifactId>
    </dependency>
</dependencies>
~~~

Choose `SPRING_CLOUD_AZURE_BOM_VERSION` matching your project's Spring Boot/Spring Cloud versions. In current documentation, Microsoft publishes BOM lines corresponding to Spring Boot 4.x, 3.5.x, and 2.x; always check the version mapping table before upgrading. Use one consistent BOM to avoid mixing incompatible Azure SDK and Spring Cloud Azure versions.

### 4.2. Direct Azure SDK for Java

If you need to construct publisher clients manually or use specific `CloudEvent`/custom schemas, add the SDK:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-eventgrid</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

You can manage versions with the Azure SDK BOM (`com.azure:azure-sdk-bom`) or use the SDK versions already managed by the Spring Cloud Azure BOM. Do not manually pin a version of `azure-messaging-eventgrid` different from the starter's transitive version without checking the dependency tree.

### 4.3. Dependency for a Service Bus Consumer

If an event subscription delivers events to a Service Bus queue and Spring Boot consumes them with the Spring Cloud Stream binder, add:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-stream-binder-servicebus</artifactId>
</dependency>
~~~

This is the **Service Bus consumer** dependency. The Event Grid starter handles publishing; the Service Bus binder handles receiving messages from the queue. Both can run in the same application or be split into separate services.

## 5. Identity and Access Permissions

### 5.1. Publisher Using Microsoft Entra ID

Prefer Managed Identity or workload identity so publishers do not hold access keys in configuration:

- Local development: logged-in developer credentials granted permissions on the dev topic.
- App Service/VM: system-assigned or user-assigned Managed Identity.
- AKS: Microsoft Entra Workload Identity.
- CI/CD: scoped workload identity federation.

The event-publishing principal needs the **EventGrid Data Sender** role on the topic/domain or appropriate scope. Resource management Contributor/Owner roles must not be granted to a runtime just to publish events.

### 5.2. Event Handler Permissions Are a Separate Path

A publisher having permission to send to a topic does not grant the consumer automatic access to databases, Service Bus, or webhooks. Each destination has its own security boundary:

| Flow | Identity / Permissions to Check |
|---|---|
| Spring Boot → Event Grid topic | Publisher identity has EventGrid Data Sender |
| Event Grid → Service Bus queue | Event Grid subscription's managed identity has Azure Service Bus Data Sender |
| Spring Boot consumer → Service Bus | Consumer identity has Azure Service Bus Data Receiver |
| Event Grid → webhook | TLS, endpoint authentication/authorization, validation handshake, and network policies |
| Consumer → database/API | Consumer application identity and permissions on target systems |

If using access keys or SAS in a lab, pull them from a secret manager/environment variable, restrict scope and expiration, and rotate on staff changes or suspected exposure. Never commit keys, tokens, or connection strings to Git.

## 6. Configuring Spring Boot with the Event Grid Starter

Example endpoint and Managed Identity configuration:

~~~yaml
spring:
  cloud:
    azure:
      eventgrid:
        endpoint: ${AZURE_EVENTGRID_ENDPOINT}
        event-schema: EVENT_GRID_EVENT
        credential:
          managed-identity-enabled: true
~~~

`AZURE_EVENTGRID_ENDPOINT` is the topic/domain endpoint. For user-assigned identity, configure client ID following the credential guide of your Spring Cloud Azure version. In local development, use an appropriate credential chain; do not assume Managed Identity exists on a developer workstation.

If a lab environment uses an access key, the starter also supports key configuration per your version's documentation. Store keys in a secret store and avoid placing real values in `application.yml`.

The starter supports configuring the schema via `spring.cloud.azure.eventgrid.event-schema`. Values include `EVENT_GRID_EVENT` (default), `CLOUD_EVENT`, and `CUSTOM_EVENT`. Choose the value matching the topic/domain input schema; the auto-configured client uses `EventGridEvent`, `CloudEvent`, or `BinaryData` accordingly. Never change only the generic type in code while forgetting to update `event-schema` in config.

## 7. Publishing EventGridEvent with the Starter

### 7.1. Injecting the Publisher Client

With the starter and a topic using Event Grid schema, inject the publisher client into a Spring service:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.messaging.eventgrid.EventGridEvent;
import com.azure.messaging.eventgrid.EventGridPublisherClient;
import java.time.OffsetDateTime;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {
    private final EventGridPublisherClient<EventGridEvent> publisher;

    OrderEventPublisher(
            EventGridPublisherClient<EventGridEvent> publisher) {
        this.publisher = publisher;
    }

    public void publishOrderCreated(OrderCreatedPayload payload) {
        EventGridEvent event = new EventGridEvent(
                "/orders/" + payload.orderId(),
                "com.example.orders.created",
                BinaryData.fromObject(payload),
                "1.0")
                .setId(payload.eventId())
                .setEventTime(OffsetDateTime.now());

        publisher.sendEvent(event);
    }
}

record OrderCreatedPayload(
        String eventId,
        String orderId,
        String customerId,
        long totalAmount,
        String currency) {}
~~~

The starter manages client creation; the business service just constructs events and calls `sendEvent`. In real applications, event IDs should originate from the outbox/business transaction and stay identical across retries rather than generating a new ID per send attempt.

### 7.2. Sending in Batches

The SDK supports sending multiple events in one request:

~~~java
import java.util.List;

public void publishBatch(List<EventGridEvent> events) {
    if (events.isEmpty()) {
        return;
    }
    publisher.sendEvents(events);
}
~~~

Batching reduces request overhead when the publisher has many events. Check payload/batch limits for your topic type and event size; split batches when exceeding limits. Never buffer events unboundedly in memory when producers outpace the service.

### 7.3. Sending Does Not Equal Completed Processing

When `sendEvent` returns successfully, the publisher received a success response from Event Grid. That does not prove the event subscription delivered to the endpoint or that the consumer completed business processing. Track delivery metrics and consumer outcomes separately.

If the application updates a database and then publishes an event, consider a transactional outbox to avoid cases where the DB commits yet publishing fails. Publish timeouts can produce indeterminate outcomes; keep event IDs stable and design idempotent consumers.

## 8. Publishing CloudEvents with the Azure SDK

CloudEvents uses `com.azure.core.models.CloudEvent`. Example creating an async publisher client with a Microsoft Entra credential:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.core.models.CloudEvent;
import com.azure.core.models.CloudEventDataFormat;
import com.azure.core.util.BinaryData;
import com.azure.messaging.eventgrid.EventGridPublisherAsyncClient;
import com.azure.messaging.eventgrid.EventGridPublisherClientBuilder;
import java.util.Map;

class CloudEventPublisher {
    private final EventGridPublisherAsyncClient<CloudEvent> publisher;

    CloudEventPublisher(String endpoint, TokenCredential credential) {
        this.publisher = new EventGridPublisherClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildCloudEventPublisherAsyncClient();
    }

    void publish(String eventId, String orderId) {
        CloudEvent event = new CloudEvent(
                "urn:example:orders-service",
                "com.example.orders.created",
                BinaryData.fromObject(Map.of(
                        "orderId", orderId,
                        "status", "CREATED")),
                CloudEventDataFormat.JSON,
                "application/json")
                .setId(eventId);

        publisher.sendEvent(event).block();
    }
}
~~~

`DefaultAzureCredential` can be created via `new DefaultAzureCredentialBuilder().build()` and passed into the constructor. In Spring Boot, register the credential and publisher client as reusable beans tied to the application lifecycle; never create a new client per request. In reactive flows, never call `block()` on an event loop—compose the `Mono` returned by the async client instead.

Do not use this publisher if the topic expects Event Grid schema. The topic/domain schema must match the `CloudEvent` type.

## 9. Custom Event Schemas

When a topic is configured with a custom schema, the SDK uses `BinaryData` as the generic type:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.messaging.eventgrid.EventGridPublisherClient;
import java.util.Map;

class CustomEventPublisher {
    private final EventGridPublisherClient<BinaryData> publisher;

    CustomEventPublisher(
            EventGridPublisherClient<BinaryData> publisher) {
        this.publisher = publisher;
    }

    void publish(String orderId) {
        Map<String, Object> event = Map.of(
                "id", "order-" + orderId,
                "subject", "/orders/" + orderId,
                "eventType", "OrderCreated",
                "dataVersion", "1.0",
                "data", Map.of("orderId", orderId));

        publisher.sendEvent(BinaryData.fromObject(event));
    }
}
~~~

Custom schemas require producers and consumers to align on fields, versioning, and validation. When multiple services share events, CloudEvents or Event Grid schema generally interoperate more easily than bespoke custom envelopes.

## 10. Receiving Events: Choosing an Event Handler

Event Grid has no receiver client in the Java SDK. How events are received depends on the event subscription's destination endpoint:

| Destination | How Spring Boot Receives |
|---|---|
| HTTP webhook | `@RestController` accepting POST and authenticating the endpoint |
| Service Bus queue/topic | Azure Service Bus SDK or Spring Cloud Stream Service Bus binder |
| Event Hubs | `EventProcessorClient` or Spring Cloud Stream Event Hubs binder |
| Storage Queue | Azure Storage Queue SDK or appropriate binder |
| Azure Function/Logic App | Platform-managed triggers/connectors |

Choose a webhook when you want an HTTP endpoint responding directly to Event Grid. Choose Service Bus when you need a durable queue, competing consumers, DLQs, and decoupling delivery from business processing duration. Event Grid can deliver events to Service Bus, after which consumers process independently.

## 11. Receiving Event Grid Schema via a Spring Boot Webhook

### 11.1. Subscription Validation

When creating an event subscription pointing to a webhook, Event Grid must verify the endpoint before delivering normal events. With **Event Grid schema**, Event Grid sends an event with type:

`Microsoft.EventGrid.SubscriptionValidationEvent`

The payload contains `data.validationCode`. The endpoint must return HTTP 200 with JSON:

~~~json
{
  "validationResponse": "<validationCode>"
}
~~~

This is a handshake proving the endpoint accepts the subscription. It does not replace authentication/authorization for requests sent to the webhook.

### 11.2. Controller Receiving Events and Returning Validation Responses

The Azure SDK's `EventGridEvent.fromString` can deserialize either a single event or a JSON array into a list of events:

~~~java
import com.azure.messaging.eventgrid.EventGridEvent;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/event-grid")
class EventGridWebhookController {
    private final EventInbox eventInbox;

    EventGridWebhookController(EventInbox eventInbox) {
        this.eventInbox = eventInbox;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> receive(@RequestBody String body) {
        List<EventGridEvent> events = EventGridEvent.fromString(body);

        if (events.size() == 1
                && "Microsoft.EventGrid.SubscriptionValidationEvent"
                    .equals(events.get(0).getEventType())) {

            if (events.get(0).getData() == null) {
                return ResponseEntity.badRequest().build();
            }
            Map<?, ?> data = events.get(0).getData().toObject(Map.class);
            Object validationCode = data.get("validationCode");

            if (validationCode == null) {
                return ResponseEntity.badRequest().build();
            }

            return ResponseEntity.ok(
                    Map.of("validationResponse", validationCode));
        }

        for (EventGridEvent event : events) {
            // Persist to durable inbox and deduplicate by event.getId().
            eventInbox.persistIfAbsent(
                    event.getId(),
                    event.getEventType(),
                    event.getData() == null
                            ? new byte[0]
                            : event.getData().toBytes());
        }

        // Only ACK after durably persisting the work.
        return ResponseEntity.accepted().build();
    }
}
~~~

`EventInbox` is an application service you implement backed by a durable database/queue with a unique constraint on event ID. Never merely push events onto an in-memory queue and return 202; the process can die after ACKing and lose the work. If persisting to the inbox fails, let the exception translate into an appropriate error response so Event Grid retries delivery.

In production, verify the expected topic/source and event types, limit body size, validate schemas, and authenticate the endpoint. Never log full payloads if they contain sensitive data.

### 11.3. Handling Multiple Events in One Request

Event Grid typically sends payloads as an array, even when delivering a single event. The controller should process every element in the body. The validation event is sent separately during subscription validation; once verified, business events are delivered.

Never assume the order of events within an array reflects global system order. Consumers must use event IDs, aggregate versions, and idempotency to protect state.

## 12. Receiving CloudEvents 1.0 via a Webhook

CloudEvents 1.0 uses a different webhook abuse-protection mechanism than Event Grid schema. Instead of sending `SubscriptionValidationEvent`, Event Grid sends an HTTP OPTIONS preflight with the `WebHook-Request-Origin` header. The endpoint consents to receive events by returning `WebHook-Allowed-Origin` and `WebHook-Allowed-Rate` headers.

~~~java
import com.azure.core.models.CloudEvent;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/cloudevents")
class CloudEventWebhookController {
    private final CloudEventInbox inbox;
    private final String allowedOrigin;

    CloudEventWebhookController(
            CloudEventInbox inbox,
            @org.springframework.beans.factory.annotation.Value(
                    "${app.eventgrid.webhook.allowed-origin}") String allowedOrigin) {
        this.inbox = inbox;
        this.allowedOrigin = allowedOrigin;
    }

    @RequestMapping(method = RequestMethod.OPTIONS)
    ResponseEntity<Void> validate(
            @RequestHeader("WebHook-Request-Origin") String requestedOrigin) {

        if (!allowedOrigin.equals(requestedOrigin)) {
            return ResponseEntity.status(403).build();
        }

        return ResponseEntity.ok()
                .header("WebHook-Allowed-Origin", requestedOrigin)
                .header("WebHook-Allowed-Rate", "600")
                .allow(HttpMethod.POST)
                .build();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Void> receive(
            @RequestBody String body,
            @RequestHeader(value = HttpHeaders.ORIGIN, required = false)
                    String origin) {

        if (!allowedOrigin.equals(origin)) {
            return ResponseEntity.status(403).build();
        }

        List<CloudEvent> events = CloudEvent.fromString(body);

        for (CloudEvent event : events) {
            inbox.persistIfAbsent(
                    event.getId(),
                    event.getType(),
                    event.getData() == null
                            ? new byte[0]
                            : event.getData().toBytes());
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

`WebHook-Allowed-Rate` is the number of requests per minute the endpoint accepts under the webhook contract; choose a value based on real capacity rather than copying the illustrative number into production. Event Grid sends `Origin` on delivery requests after the handshake; the endpoint should validate the agreed origin.

Example configuration of the allowed sender origin in the webhook application:

~~~yaml
app:
  eventgrid:
    webhook:
      allowed-origin: eventgrid.azure.net
~~~

Replace the illustrative value with the actual origin your endpoint agreed to during the handshake. When supporting multiple senders, maintain an allow-list rather than accepting every origin.

The CloudEvents abuse-protection handshake **is not authentication**. You still need webhook authentication/authorization, network restrictions, TLS, and event source verification.

## 13. Receiving Events via a Service Bus Queue

If you want to decouple event delivery timing from business processing duration, configure the event subscription destination as a **Service Bus queue**. Event Grid delivers events into the queue; the Spring Boot consumer receives them via the Service Bus binder.

### 13.1. Binding Configuration

Example function binding configuration:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
      servicebus:
        namespace: ${AZURE_SERVICEBUS_NAMESPACE}
    function:
      definition: consume
    stream:
      bindings:
        consume-in-0:
          destination: ${AZURE_EVENTGRID_QUEUE_NAME}
~~~

Dependencies require `spring-cloud-azure-stream-binder-servicebus` and a compatible BOM. The consumer identity needs Azure Service Bus Data Receiver on the queue. The Event Grid subscription identity needs Azure Service Bus Data Sender to write events into the queue.

### 13.2. Consumer Function Processing Payloads

The queue receives the JSON events delivered by Event Grid. Example with Event Grid schema:

~~~java
import com.azure.messaging.eventgrid.EventGridEvent;
import java.util.List;
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class EventGridQueueConsumer {
    @Bean
    Consumer<Message<String>> consume(EventInbox eventInbox) {
        return message -> {
            List<EventGridEvent> events =
                    EventGridEvent.fromString(message.getPayload());

            for (EventGridEvent event : events) {
                eventInbox.persistIfAbsent(
                        event.getId(),
                        event.getEventType(),
                        event.getData() == null
                                ? new byte[0]
                                : event.getData().toBytes());
            }
        };
    }
}
~~~

In production applications, choose settlement/auto-complete behavior appropriate for your Service Bus binder version. Only complete the message after the database transaction or durable work has completed. When using an inbox, persist the event ID and side effects in the same transaction; on transient failures, let Service Bus redeliver the message per policy.

### 13.3. Distinguishing Event Grid Retries from Service Bus Retries

Once Event Grid delivers successfully into the Service Bus queue, Event Grid considers delivery to the destination complete. Subsequent retries belong to Service Bus and the consumer. When using a webhook directly, Event Grid tracks the webhook's HTTP responses. The two retry layers have separate configurations and DLQs; monitor both.

## 14. Delivery Semantics, Duplicates, and Ordering

Event Grid delivers events with **at-least-once** semantics: an event may be redelivered if the endpoint times out, returns an error, or a response is lost. Event Grid does not guarantee global event delivery order.

Consumers need to:
- Use stable event IDs to deduplicate.
- Enforce a unique constraint in the inbox/processed-event table.
- Write the dedup record and business changes in the same transaction.
- Use aggregate versions when business state must follow a strict order.
- Return a success response only after accepting durable processing responsibility.
- Never send emails, charge payments, or call non-idempotent APIs without an idempotency key on the target system.

Event Grid does not replace Event Hubs when you need partitioned/offset-based event logs, or Service Bus when you need lock/complete, sessions, and queue DLQ semantics.

## 15. Retries, HTTP Responses, and Dead-Lettering

Event Grid uses HTTP responses to determine whether delivery succeeded or needs retrying. For webhooks, responses 200, 201, 202, 203, and 204 are treated as successful ACKs. Other responses are treated as failures; retry behavior depends on the status code and endpoint type.

| Response | Operational Meaning |
|---|---|
| 200/201/202/203/204 | Endpoint accepted the event; Event Grid marks delivery successful |
| 5xx | Server-side error, typically eligible for retry |
| 408/timeout | Event Grid may retry |
| 400 | Invalid request error; webhooks are not retried under normal policy |
| 401/403 | Authentication/authorization error; webhooks are not retried under normal policy |
| 413 | Payload too large; not retried under normal policy |

By default, dead-lettering is not automatically enabled on every event subscription. Configure a dead-letter destination (typically Blob Storage) if you do not want events dropped after retries exhaust or configuration errors occur. Set TTL and max delivery attempts according to SLOs and recovery capability.

When receiving events:
- Return 202 after persisting to a durable inbox/queue.
- Return 5xx for transient errors where the application cannot yet accept processing responsibility.
- Never return 400 merely because a downstream database is temporarily unavailable.
- For permanently invalid events, consider quarantining and ACKing once quarantine persistence succeeds, or configure dead-lettering appropriately.
- Never ACK before an event is durably persisted.

The dead-letter destination also needs permissions, encryption, lifecycle rules, alerts, and a replay runbook. If dead-letter storage does not exist or is inaccessible, events can still be lost per service policy.

## 16. Transactional Outbox When Publishing Events

If business logic writes to a database and then calls Event Grid in the same request, the two actions are not atomic. Possible failures:
- Database commit succeeds, yet publishing fails.
- Publishing succeeds, yet the database rolls back.
- Publishing succeeds, yet the response is lost and the publisher retries, causing duplicates.

A transactional outbox writes the event to publish in the same transaction as business data:

~~~mermaid
flowchart TD
    API["Spring Boot API"] --> TX["Database transaction"]
    TX --> ORDER["Update order"]
    TX --> OUTBOX["Insert outbox event"]
    OUTBOX --> WORKER["Outbox publisher"]
    WORKER --> EG["Event Grid topic"]
    EG --> SUB["Event subscription"]
    SUB --> CONSUMER["Idempotent consumer"]
~~~

A worker reads the outbox, sends the event, and marks it published. If the worker crashes after sending but before marking, the event may be resent; consumers still need to deduplicate by event ID. An outbox prevents forgetting to publish after commit, yet does not create exactly-once across the database and Event Grid.

## 17. Monitoring and Operations

Monitor the publisher, Event Grid subscription, and consumer:

| Group | Metrics to Track |
|---|---|
| Publisher | Send successes/failures, latency, throttling, 401/403, payload size |
| Event subscription | Delivery successes/failures, attempts, matched/unmatched events, filter behavior |
| Webhook | Request counts, 2xx/4xx/5xx, latency, validation failures |
| Service Bus destination | Active message count, oldest message age, DLQ count, lock/settlement failures |
| Consumer | Processing duration, duplicates suppressed, inbox backlog, business failures |
| Dead-letter | Event count, event age, failure reasons, and replay rate |
| Security | Identities, RBAC changes, secret rotation, unauthorized requests |

Use correlation IDs, event IDs, and subscription names to stitch publisher logs to consumer logs. Never log access keys, SAS tokens, `Authorization` headers, or payloads containing sensitive data.

Alert when delivery failures climb, webhooks return 401/403/5xx, DLQs receive new events, Service Bus backlogs grow, or consumers stop progressing. Every alert needs an owner, dashboard, and runbook to verify endpoints, identities, RBAC, networking, and schemas.

## 18. Integration Testing

Create dedicated test topics, event subscriptions, Service Bus queues, and dead-letter storage. Never use production endpoints to test validation or intentionally return errors.

| Scenario | How to Test | Expected Result |
|---|---|---|
| Publish EventGridEvent | Send event using starter/SDK | Topic accepts matching schema |
| Publish CloudEvent | Use CloudEvent publisher | CloudEvents topic accepts matching envelope |
| Schema mismatch | Send EventGridEvent to a CloudEvents topic | Publisher receives Bad Request |
| Batch publish | Send multiple events in one request | Event subscription receives all events |
| Event Grid validation | Create webhook subscription with Event Grid schema | Endpoint returns valid `validationResponse` |
| CloudEvents preflight | Send OPTIONS with `WebHook-Request-Origin` | Endpoint returns `Allowed-Origin` and `Allowed-Rate` |
| Duplicate delivery | Resend same event ID or simulate retry | Inbox prevents repeated side effects |
| Webhook timeout | Make handler slower than deadline | Event Grid retries per policy |
| HTTP 5xx | Return transient error in tests | Event is retried or dead-lettered |
| HTTP 400/403 | Return configuration error | Verify dead-lettering and do not assume retry |
| Service Bus destination | Event subscription delivers to queue | Consumer binder receives the event |
| Consumer failure | Make test database temporarily unavailable | Message is not completed prematurely |
| Dead-letter | Intentionally fail destination in test scenario | Event is written to dead-letter storage |
| Filtering | Send different event types/subjects | Only events matching filters are delivered |
| Cross-environment access | Use dev identity to publish to prod topic | Denied by RBAC |

Unit tests check event contracts, schema validation, and idempotency. Only cloud integration tests verify real Entra ID, RBAC, subscription validation, delivery retries, dead-lettering, and Service Bus destinations.

## 19. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Publisher 401/403 | Wrong credential or missing EventGrid Data Sender | Verify runtime principal and role scope |
| Publisher 400 | Generic client does not match input schema | Check topic `inputSchema` |
| Publish succeeds, consumer sees nothing | Missing subscription, unmatched filter, or wrong destination | Check subscription and delivery metrics |
| Webhook subscription creation fails | Validation handshake did not complete | Check response body/status, OPTIONS, and WAF |
| Webhook receives duplicates | At-least-once delivery or lost response | Inbox/dedup by event ID |
| Webhook returns 202 yet loses work | ACKed before durable persistence | Persist to inbox/queue before responding |
| Events dropped when endpoint returns 400/403 | Status codes not retried under webhook policy | Fix auth/schema and configure dead-lettering |
| Service Bus consumer receives nothing | Wrong queue/binder or missing Data Receiver | Check destination, identity, and role |
| Event Grid fails to write to Service Bus | Event Grid identity missing Data Sender | Assign role to the subscription's identity |
| Events arrive out of order | Event Grid does not guarantee global ordering | Use aggregate versions and state-transition guards |

## 20. Pre-Production Checklist

- **Schema:** Topic/domain input schema confirmed; publisher generic type matches.
- **Dependencies:** Spring Cloud Azure BOM compatible with Spring Boot; no mixed SDK versions.
- **Publisher:** Client reused via lifecycle, timeouts/retries monitored, stable event IDs.
- **Identity:** Publisher has EventGrid Data Sender; no hardcoded keys/SAS.
- **Subscription:** Filters, endpoint, retry policy, and dead-lettering explicitly configured.
- **Receiver:** Webhook has validation/authentication; or Service Bus queue has matching consumer identity and roles.
- **Acknowledgement:** Only return 2xx after accepting durable processing responsibility.
- **Reliability:** Consumer idempotent, duplicate-safe, makes no event-order assumptions.
- **Dead-letter:** Storage has permissions, encryption, lifecycle, alerts, and replay procedure.
- **Observability:** Delivery failures, webhook status, queue backlog, DLQ, and business processing monitored.
- **Testing:** Tested schema mismatch, validation, duplicates, timeouts, retries, DLQ, and RBAC denial.
- **Cost:** Event volume, deliveries, retries/fan-out, dead-letter storage, networking, and monitoring budgeted.

## 21. Summary

An Azure Event Grid publisher sends events to a topic/domain using `EventGridPublisherClient`; the Spring Cloud Azure Event Grid starter can auto-configure the publisher for Spring Boot. The Event Grid Java SDK has no receiver client. Events are received at configured event handlers: HTTP webhooks, Service Bus, Event Hubs, Storage Queues, or other supported services.

When publishing events, choose the right `EventGridEvent`, `CloudEvent`, or custom schema and use Microsoft Entra ID with the EventGrid Data Sender role whenever possible. When receiving events, complete the validation handshake, persist work durably before ACKing, handle duplicates, and configure dead-lettering. Event Grid delivers at-least-once and does not guarantee ordering; consumers require idempotency and correlation so the system recovers safely.

## References

- [Azure Event Grid client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/messaging-eventgrid-readme?view=azure-java-stable)
- [CloudEvent class in Azure SDK for Java](https://learn.microsoft.com/en-us/java/api/com.azure.core.models.cloudevent?view=azure-java-stable)
- [Use Azure Event Grid in Spring Boot](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-initializer-java-app-with-event-grid)
- [Spring Cloud Azure developer guide](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
- [Spring Cloud Azure configuration properties](https://microsoft.github.io/spring-cloud-azure/current/reference/html/appendix.html)
- [Validate webhook endpoints with Event Grid schema](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-event-grid-events-schema)
- [Endpoint validation with CloudEvents schema](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-cloud-events-schema)
- [Event Grid delivery and retry](https://learn.microsoft.com/en-us/azure/event-grid/delivery-and-retry)
- [Set dead-letter location and retry policy](https://learn.microsoft.com/en-us/azure/event-grid/manage-event-delivery)
