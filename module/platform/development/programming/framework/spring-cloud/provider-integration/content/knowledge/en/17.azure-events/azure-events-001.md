# Distinguishing Event Hubs, Event Grid, and Service Bus

Azure provides multiple event and messaging services, but they solve different problems. **Event Hubs** is suited for large streams of event data that need continuous ingestion and processing; **Event Grid** is suited for event routing when something has happened; **Service Bus** is suited for business messaging that requires queues, topics, subscriptions, acknowledgment handling, and message orchestration capabilities. Choosing the wrong service can make it difficult for an application to guarantee ordering, handle duplicate messages, control costs, or avoid having to build foundational features yourself that already exist in another service.

This lesson belongs to the **Azure Events** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. Its goal is to help learners integrate Spring Boot with Azure managed services through the Azure SDK and appropriate Spring Cloud Azure libraries; understand how to configure identities and permissions, send/receive data, protect secrets, handle errors, run integration tests, and compare Azure choices with AWS and Google Cloud.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the difference in purpose between **event streaming**, **event routing**, and **enterprise messaging**.
- Choose Event Hubs, Event Grid, or Service Bus based on data type, delivery semantics, ordering, replay, routing, and transaction needs.
- Understand partitions, consumer groups, offsets, checkpoints, event subscriptions, queues, topics, subscriptions, and dead-letter queues.
- Design Spring Boot producers/consumers with the Azure SDK, managed identity, and RBAC.
- Handle duplicates, retries, poison events, backpressure, checkpoints, and partial failures.
- Design tests on dedicated namespaces/topics/queues, and monitor metrics, quotas, and costs.
- Recognize when multiple services need to be combined into an event-driven architecture.

## 2. Distinguishing Events, Messages, and Streams

These three terms are often used interchangeably, but they can be understood by their purpose:

- An **Event** describes something that has happened: `OrderCreated`, `InvoiceUploaded`, `CustomerAddressChanged`. An event is usually immutable in meaning: it records a fact in the past.
- A **Command** asks a component to do something: `ReserveInventory`, `SendInvoice`, `CancelOrder`. A command usually has a single place responsible for processing it and a business outcome to track.
- A **Message** is the unit of data transmitted between components. A message can carry an event, a command, or work data.
- An **Event stream** is a continuous sequence of events that can be recorded and read by multiple consumers by position/offset. Consumers may need to re-read history to rebuild state or run a new computation.

Example in an order system:

| Data | Meaning | Common Delivery Need |
|---|---|---|
| `OrderCreated` | An order was just created | Broadcast to multiple consumers: inventory, billing, analytics |
| `ReserveInventory` | Request to reserve stock | One worker processes the command and reports the result |
| Clickstream / telemetry | Large, continuous event stream | High-throughput ingestion, multiple consumers reading independently |
| `BlobCreated` | A new object appeared | Route a notification to the appropriate handler |
| `PaymentAuthorized` | Payment was confirmed | Deliver a business message with retries, DLQ, and audit |

An event can be sent through multiple types of services depending on requirements. The payload name does not determine the service; **delivery, retention, routing, ordering, and how consumers process it** are what determine the choice.

## 3. At a Glance: Three Services Solving Three Problems

| Service | Primary Role | Mental Model |
|---|---|---|
| **Azure Event Hubs** | Platform for ingesting and processing large-scale event streams | An event stream split into partitions; multiple consumer groups read independently |
| **Azure Event Grid** | Event router based on source, type, and conditions | When an event occurs, deliver a notification to the matching endpoint/subscriber |
| **Azure Service Bus** | Enterprise messaging broker | A queue or topic holds messages for consumers to process and settle |

| Criterion | Event Hubs | Event Grid | Service Bus |
|---|---|---|---|
| Purpose | Streaming / telemetry / event ingestion | Event routing / notification | Enterprise messaging / workflow |
| Primary unit | Event in a partition | Event routed to an event subscription | Message in a queue or topic subscription |
| Consumption model | Consumers read by offset/checkpoint | Push delivery or pull depending on resource/tier capabilities | Peek-Lock or Receive-and-Delete |
| Replay | Can re-read within retention using offset/checkpoint | Not a long-term event log for arbitrary replay; requires a separate store | Not a stream log; messages are completed/deleted per lifecycle |
| Ordering | Ordered within a single partition | No global ordering guarantee; not designed as an ordered log | Can use sessions for ordered processing per group |
| Fan-out | Independent consumer groups reading the stream | Routing to multiple event subscriptions | Topic fan-out to multiple subscriptions |
| Dead-letter | Application handles checkpoints/errors; not a Service Bus-style broker DLQ | Dead-lettering can be configured for failed deliveries | Built-in DLQ for queues/topic subscriptions |
| Filtering | Consumers filter the stream themselves or via processor | Event subscription filters by event type/subject/advanced filters | Subscription filters/rules on a topic |
| Business transactions | Not a command transaction broker | Not a workflow transaction broker | Supports transactions within Service Bus supported scope |
| Best suited for | High-volume, continuous data, analytics, telemetry | Reacting to events from many sources | Commands, tasks, integration messages requiring delivery control |

**Do not translate mechanically:** Event Hubs is not a queue just because consumers receive events; Event Grid is not an event store; a Service Bus topic is not a stream log that can be re-read indefinitely. Each service has its own state management and cost model.

## 4. Azure Event Hubs: Ingesting and Processing Event Streams

### 4.1. When to Use Event Hubs?

Event Hubs is suitable when a system needs to ingest a large volume of continuous data from many producers: device telemetry, application logs, clickstreams, generated transaction data, events from operational systems, or data that needs to be forwarded to an analytics pipeline.

Key characteristics:

- A namespace contains one or more event hubs.
- Each event hub is divided into **partitions** to distribute data and processing load.
- Producers can send events with a partition key or let the service distribute them using an appropriate mechanism.
- A consumer group provides an independent reading view for an application/consumer group.
- Consumers track their **offset** and save **checkpoints** to resume from the last processed position.
- Events have retention based on configuration/tier; consumers can re-read within the active retention window.
- Event Hubs supports Azure Blob Storage/ADLS Capture to write the stream to storage for batch/analytics processing as configured.
- Provides a Kafka-compatible protocol endpoint for many scenarios, though not all Kafka features are strictly equivalent.

~~~mermaid
flowchart LR
    P1["IoT / application producer"] --> H["Event Hubs namespace"]
    P2["Services / logs"] --> H
    H --> A["Partition 0"]
    H --> B["Partition 1"]
    H --> C["Partition 2"]
    A --> CG1["Consumer group: analytics"]
    B --> CG1
    C --> CG1
    A --> CG2["Consumer group: fraud detection"]
    B --> CG2
    C --> CG2
    H -. "Capture (if enabled)" .-> ST["Blob Storage / ADLS"]
~~~

A consumer group does not mean every instance receives all events. Instances within the same consumer group typically share partition ownership; different consumer groups can read the same stream independently, each with its own offsets/checkpoints.

### 4.2. Partitions, Ordering, and Partition Keys

Event Hubs guarantees ordering per **partition** within the scope of how that partition is written and read; there is no global ordering across all partitions. If related events must be processed in order, the producer must use a stable partition key (for example `customerId` or `orderId`) to route events with the same key to the same partition. Changing the partition count or how keys are chosen can affect distribution and observed order; do not treat a partition key as a transaction key.

Partition count is an important design decision:
- Too few partitions can limit concurrency and throughput.
- Too many partitions can increase cost/complexity and affect consumer strategy.
- A key with disproportionately high traffic can create a **hot partition**, while other partitions sit idle.
- The number of consumers processing in parallel within a consumer group is bounded by the number of partitions owned and processor configuration.

Do not choose the partition count solely based on the number of Spring Boot instances. Forecast event rate, event size, required throughput, number of consumer groups, latency, and scalability.

### 4.3. Consumer Groups, Offsets, and Checkpoints

An **offset** identifies an event's position within a partition. A **checkpoint** is the durable progress state saved by a consumer, typically using Blob Storage as a checkpoint store when using the Event Processor. Checkpointing too frequently can increase I/O and cost; checkpointing too infrequently causes many events to be re-read and reprocessed after a failure.

The Event Processor Client helps manage partition ownership, load balancing, and the checkpoint store. When an instance dies, another instance can take over partitions after rebalancing; the application must tolerate **reprocessing a slice of events since the latest checkpoint**. Therefore, consumers should be idempotent and have a mechanism to record processed events when side effects matter.

### 4.4. Event Hubs Does Not Replace a Business Queue

Event Hubs retains events for the retention period and consumers read by offset. It does not use a "lock a single message, process it, then complete it" model like Service Bus Peek-Lock. If you need workflows with a built-in DLQ, message settlement, sessions, or broker transactions, evaluate Service Bus.

## 5. Azure Event Grid: Routing Events When Something Happens

### 5.1. When to Use Event Grid?

Event Grid is suitable for connecting event-producing sources with handlers without forcing the producer to know about every consumer. For example:
- When a blob is created, invoke a function to process the image.
- When a cloud resource changes, send an event to automation or a webhook.
- When a business system emits `OrderApproved`, route it to the handlers that need to react.
- When events arrive from partners or Azure services, distribute them to the appropriate endpoints.

Conceptual components:
- **Event source/topic:** where events are emitted or collected.
- **Event subscription:** registers to receive events, applies filters, and defines the target endpoint.
- **Handler/destination:** Azure Function, webhook, queue, Event Hubs, or another supported endpoint.
- **Filter:** filters by event type, subject prefix/suffix, or supported data conditions.
- **Delivery policy:** retries, event time-to-live, and dead-lettering when configured.

~~~mermaid
flowchart LR
    S1["Blob Storage"] --> EG["Event Grid"]
    S2["Azure resource"] --> EG
    S3["Custom topic / app"] --> EG
    EG --> F["Filter: event type / subject"]
    F --> H1["Function: image processor"]
    F --> Q["Service Bus queue"]
    F --> W["Webhook: order handler"]
~~~

Event Grid reduces coupling between publishers and subscribers: producers emit events according to a contract; subscriptions decide which events go where. Producers still need to manage event schemas, publish permissions, retry capability, and publish failures.

### 5.2. Push, Pull, and Delivery

Event Grid supports multiple resource/delivery models depending on the topic type and tier. **Push delivery** sends events to a registered endpoint; some resource types support **pull delivery** so subscribers can actively receive/acknowledge events under the service's model. You must choose the right Event Grid resource type and supported features, rather than assuming every topic has the same semantics.

With push delivery, the endpoint must follow the required protocol, return a success response, and handle validation when registering a subscription. Events may be redelivered if the endpoint fails to acknowledge success or times out; global ordering is not guaranteed. Therefore, handlers need to:
- Process events by stable ID and idempotency.
- Return a success response only after durably accepting responsibility for processing.
- Offload long-running tasks to a queue or outbox/worker instead of keeping HTTP webhooks open for too long.
- Configure a dead-letter destination and alerts for prolonged delivery failures.
- Verify the subscription validation handshake and authentication appropriate for the endpoint type.

You should not handle an HTTP event and return 2xx before persisting the work to be done if the process could crash afterward and lose the side effect. One option is to write the event to a database/outbox or durable queue and then return success.

### 5.3. Event Schema and CloudEvents

Event Grid can work with the **Event Grid schema** or **CloudEvents 1.0** depending on the resource/integration. An event typically contains:
- `id`: event identifier.
- `source`: emitting source.
- `type`: event type.
- `subject`: related entity/object.
- `time`: timestamp when it occurred.
- `data`: business payload or metadata.
- Schema version/content type according to the protocol.

CloudEvents helps standardize the envelope across multiple systems; however, the payload inside `data` still needs schema versioning, backward compatibility, and processing rules. Do not put secrets, access tokens, or unnecessary personal data into events because events can be distributed to many consumers and stored in many places.

### 5.4. Retry and Dead-Lettering

Event Grid has retry/dead-letter policies depending on the resource type and configuration. When an endpoint does not respond with success, the event can be redelivered according to the retry schedule; when delivery attempts are exhausted or TTL expires, the event can be dead-lettered if a destination is configured and operational. Leaving dead-lettering disabled means failed events will not automatically be saved to a safe place.

Dead-letter storage must have permissions, a lifecycle, alerts, and a replay procedure. When replaying, keep the original event ID or record a new replay ID linked to the original event to avoid duplicate processing.

## 6. Azure Service Bus: Enterprise Messaging and Workflows

### 6.1. When to Use Service Bus?

Service Bus is appropriate when a system needs to send **commands or business messages** to workers for reliable processing:
- Processing orders, payments, invoices, or background tasks.
- Queues to decouple producers from consumers and absorb traffic spikes.
- Topics/subscriptions to fan out the same message to multiple logical consumers.
- Sessions to group ordered messages by a business key.
- Dead-letter queues to isolate unprocessable messages.
- Scheduled/deferred messages and transactions within the supported scope.

Service Bus provides delivery and settlement semantics suited for enterprise messaging. It is not an event log for multiple consumers to freely re-read the entire history by offset like Event Hubs.

### 6.2. Queues and Topics/Subscriptions

~~~mermaid
flowchart LR
    P["Spring Boot producer"] --> T["Service Bus topic: order-events"]
    T --> S1["Subscription: billing"]
    T --> S2["Subscription: warehouse"]
    T --> S3["Subscription: notification"]
    S1 --> C1["Billing worker"]
    S2 --> C2["Warehouse worker"]
    S3 --> C3["Notification worker"]
    C1 -. "Dedicated DLQ" .-> D1["Dead-letter"]
    C2 -. "Dedicated DLQ" .-> D2["Dead-letter"]
~~~

- **Queue:** a stream of work distributed to one consumer in the receiving group; messages are settled to delete or return them.
- **Topic:** publishers send one copy of a message to the topic; Service Bus distributes logical copies to matching **subscriptions**.
- **Subscription:** can define filters/rules to receive only a subset of messages; each subscription has its own state and DLQ.
- **Session:** groups messages by SessionId for ordered processing within the session and supports per-session state/locking within the service's scope.

Topics/subscriptions are useful when multiple components need the same event but have independent processing lifecycles. If you only need a job processed by one worker, a queue is usually simpler.

### 6.3. Peek-Lock and Receive-and-Delete

**Peek-Lock** is the standard model for safe processing:
1. The consumer receives a message and temporarily locks it.
2. The consumer performs business processing.
3. On success, it calls **Complete** to settle the message.
4. On failure, it can **Abandon** for redelivery, or let the lock expire.
5. Messages exceeding delivery thresholds or explicitly dead-lettered can move to the DLQ.

If the consumer commits to the database but the Complete call is lost, the broker may redeliver the message. Consumers must be idempotent; a broker lock does not replace a database transaction.

**Receive-and-Delete** deletes the message as soon as the broker delivers it to the consumer. It reduces some round-trips, but if the consumer crashes before processing, the message can be lost to the application flow. Use it only when those semantics are acceptable.

### 6.4. Sessions, Duplicate Detection, and Transactions

- **Sessions** support grouping messages with the same SessionId and processing them sequentially within the group; they do not create global ordering across all sessions.
- **Duplicate detection** drops messages with a duplicate MessageId within the configured scope and window. This is not an end-to-end exactly-once guarantee: consumer side effects, databases, and external systems still require idempotency.
- **Transactions** support certain Service Bus operations within the documented broker scope; they do not automatically create atomic distributed transactions with SQL databases, S3, HTTP APIs, or other providers.
- **DLQ** holds unprocessable messages for investigation and controlled replay. A DLQ does not automatically fix poison messages or invalid schemas.

Service Bus has tiers (for example Basic, Standard, Premium) with different features and capacity/pricing models. Not every feature—such as topics, sessions, transactions, duplicate detection, or networking—is available in every tier; always check the current feature matrix and SKU before designing.

## 7. Choosing a Service by Scenario

| Requirement | Preferred Choice | Reason |
|---|---|---|
| Ingest millions of continuous telemetry events | **Event Hubs** | Partitions, throughput, and consumer groups for stream processing |
| Multiple consumers need to re-read data within retention | **Event Hubs** | Independent offsets/checkpoints and consumer groups |
| Invoke an image processor as soon as a blob is created | **Event Grid** | Event routing from resources to handlers |
| Trigger automation when an Azure resource changes | **Event Grid** | Event subscriptions and filtering by source/type |
| Send an invoice-processing command requiring Complete/Abandon/DLQ | **Service Bus** | Queues and settlement semantics |
| Distribute commands to multiple independent consumer groups | **Service Bus topic/subscription** | Fan-out, filtering, and per-subscription DLQs |
| Need message ordering per order ID | **Service Bus sessions** or Event Hubs partition key depending on the problem | Sessions for workflow messages; partitions for streams |
| Need to re-read the entire stream for analytics | **Event Hubs** | Retention and consumer offsets |
| Only need a notification when something happens, without long-term business message storage | **Event Grid** | Event routing, event-handling endpoints |
| Need broker transactions or scheduled/deferred commands | **Service Bus** | Enterprise messaging capabilities |

### 7.1. Decision Tree

~~~mermaid
flowchart TD
    A["What kind of data are you transmitting?"] --> B{"Continuous stream, high throughput, offset-based replay needed?"}
    B -->|Yes| EH["Event Hubs"]
    B -->|No| C{"An event occurred and needs routing to handlers?"}
    C -->|Yes| EG["Event Grid"]
    C -->|No| D{"Need queues/commands, settlement, DLQ, sessions, or transactions?"}
    D -->|Yes| SB["Service Bus"]
    D -->|No| X["Re-evaluate contract, delivery, and retention"]
~~~

If the answer is "all three are needed," you do not have to pick just one. For example, Event Hubs ingests telemetry, Event Grid notifies that a blob was created, and Service Bus coordinates a report-generation command. Each service requires its own event contract, permissions, monitoring, and failure handling.

## 8. Designing a Shared Event Contract for Spring Boot

A good event should describe **what happened**, independent of internal database structure:
- `eventId`: unique and stable ID for a business event.
- `eventType`: versioned event type, e.g. `com.example.orders.created.v1`.
- `source`: service/producer.
- `subject`: related entity, e.g. `orders/12345`.
- `occurredAt`: business occurrence timestamp, not necessarily when the broker received it.
- `correlationId` and `traceparent`: link steps across a distributed flow.
- `schemaVersion`: payload version.
- `data`: fields needed by consumers, avoiding bloated payloads.

Example payload:

~~~json
{
  "eventId": "evt-7f3a8e",
  "eventType": "com.example.orders.created.v1",
  "source": "orders-service",
  "subject": "orders/12345",
  "occurredAt": "2026-11-24T09:30:00Z",
  "correlationId": "req-91ac",
  "schemaVersion": 1,
  "data": {
    "orderId": "12345",
    "customerRef": "cust-204",
    "currency": "VND",
    "total": 450000
  }
}
~~~

The data above is a fictional example. Do not put passwords, access tokens, connection strings, or payment card details into messages. If consumers need large data, consider storing the object in storage and sending a reference with restricted access; do not use events to carry large files exceeding broker limits.

### 8.1. Schema Evolution

When the payload changes:
- Add optional fields with defaults or fallback rules so older consumers keep working.
- Do not change the meaning of an existing field without bumping the version.
- Do not remove fields while older consumers are still active.
- Test backward and forward compatibility of producers/consumers according to your rollout strategy.
- Maintain a schema registry or contract tests when multiple teams develop together.
- Plan for older messages still sitting in retention/queues after the application is upgraded.

Event Hubs stream retention may contain events from a previous version; Service Bus queues/topics may also hold pending messages; Event Grid may retry older events. Consumers need to know how to handle payloads by version in all three cases.

## 9. Integrating Spring Boot with the Azure SDK

### 9.1. Choosing Libraries and Versions

You can use:
- **Azure SDK for Java** directly when you need fine-grained control over producers/consumers, checkpoints, processors, retries, or advanced settings.
- **Spring Cloud Azure** to leverage Spring Boot auto-configuration, credential integration, Spring Messaging, and listener abstractions when the version supports the required service.
- **Spring Cloud Stream** with the corresponding binder when your architecture wants binder abstractions and you clearly understand the semantics the binder supports.

Choose the **Spring Cloud Azure BOM compatible with your Spring Boot version**. Artifact names, packages, properties, and annotations change across library generations. Do not copy configuration from another major version without checking the compatibility matrix. For critical features like sessions, manual settlement, checkpoints, or processor ownership, verify whether the abstraction exposes the APIs you need or whether you should use the native SDK.

### 9.2. Identity and Configuration

On Azure, prefer **Microsoft Entra ID** and workload identities:
- Local development can use logged-in and controlled developer credentials.
- App Service/Functions/VMs can use Managed Identity.
- AKS can use Workload Identity.
- CI/CD can use workload identity federation / appropriate service connections.

Do not hardcode SAS keys or connection strings into the repository. If SAS is used, scope it by resource, permission, and expiration; store it in a secret manager, rotate it, and audit it. With Entra ID, assign the proper roles:
- Event Hubs: **Azure Event Hubs Data Sender** or **Azure Event Hubs Data Receiver** per producer/consumer.
- Service Bus: **Azure Service Bus Data Sender** or **Azure Service Bus Data Receiver**.
- Event Grid: the appropriate publish role, e.g. **EventGrid Data Sender** for publishers at the proper scope; handlers need their own authentication/authorization mechanism per endpoint.

Namespace/resource management roles do not implicitly grant data-plane permissions. Verify the runtime principal and the assigned scope.

Example configuration without secrets:

~~~yaml
app:
  azure:
    event-hubs:
      namespace: orders-dev.servicebus.windows.net
      name: order-telemetry
    service-bus:
      namespace: orders-dev-messaging.servicebus.windows.net
      queue: orders-dev
    event-grid:
      endpoint: https://orders-dev-events.example.region-1.eventgrid.azure.net/api/events
~~~

The `app.azure.*` keys are custom application configuration, not default global Spring Cloud Azure properties. The endpoints are illustrative values; retrieve real endpoints from deployed resources. Never put keys or tokens into YAML files.

## 10. Event Hubs Producer Example with the Azure SDK

The example below sends an event to Event Hubs using **DefaultAzureCredential**. The runtime identity must have the **Azure Event Hubs Data Sender** role on the namespace or appropriate scope.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;

public class TelemetryPublisher {
    public void publish(
            String fullyQualifiedNamespace,
            String eventHubName,
            String jsonPayload) {

        EventHubProducerClient producer = new EventHubClientBuilder()
                .credential(
                        fullyQualifiedNamespace,
                        eventHubName,
                        new DefaultAzureCredentialBuilder().build())
                .buildProducerClient();

        try {
            EventDataBatch batch = producer.createBatch();
            if (!batch.tryAdd(new EventData(jsonPayload))) {
                throw new IllegalArgumentException(
                        "Event exceeds the available batch size");
            }
            producer.send(batch);
        } finally {
            producer.close();
        }
    }
}
~~~

The illustrative code requires compatible Azure Identity and Azure Messaging Event Hubs dependencies. In production applications, create the producer client as a **reusable Spring bean** instead of creating and closing the client per request; add timeouts, retry policies, telemetry, and error handling. If a batch does not have enough room for an event, split batches or reject the payload per policy; do not increase size indefinitely.

### 10.1. Consumers and Checkpoints

For stream processing, use **EventProcessorClient** to manage partition ownership and checkpoints through an appropriate checkpoint store (typically Blob Storage). Consumer groups should have dedicated names per logical application; replicas of the same consumer group share partitions, while analytics and fraud detection use separate consumer groups.

Processing flow:
1. Receive events along with partition context.
2. Validate schema and event ID.
3. Perform idempotent side effects or store results durably.
4. Checkpoint after safe processing according to your chosen batch/interval.
5. If an instance dies before checkpointing, events since the last checkpoint may be reprocessed.

Do not checkpoint before durable side effects, or processing may be lost. Checkpointing too often increases cost and I/O; checkpointing too rarely increases the number of events to replay. If there are side effects to a database, use appropriate deduplication/outbox patterns.

## 11. Service Bus Message Sending Example with the Azure SDK

Service Bus is suited for commands or work requiring settlement. Producer example using managed identity:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;

public class OrderCommandPublisher {
    public void send(
            String namespace,
            String queueName,
            String eventId,
            String payload) {

        ServiceBusSenderClient sender = new ServiceBusClientBuilder()
                .credential(
                        namespace,
                        new DefaultAzureCredentialBuilder().build())
                .sender()
                .queueName(queueName)
                .buildClient();

        try {
            ServiceBusMessage message = new ServiceBusMessage(payload)
                    .setMessageId(eventId)
                    .setContentType("application/json")
                    .setSubject("ReserveInventory");
            sender.sendMessage(message);
        } finally {
            sender.close();
        }
    }
}
~~~

In a Spring Boot application, create a reusable sender client managed by the bean lifecycle rather than initializing it on every call. A stable `MessageId` supports duplicate detection if the namespace/queue is configured with that feature; consumers must still be idempotent because deduplication has scope/time limits and does not cover side effects outside the broker.

### 11.1. Consumers and Settlement

You can use **ServiceBusProcessorClient** to receive messages asynchronously. The handler only calls Complete after business processing and database commit succeed; on transient failures, it can abandon so the broker redelivers according to policy. For unrecoverable data errors, dead-letter with a reason/description stripped of sensitive data.

~~~java
import com.azure.messaging.servicebus.ServiceBusReceivedMessageContext;

void handleMessage(ServiceBusReceivedMessageContext context) {
    String body = context.getMessage().getBody().toString();

    // Validate and process idempotently inside the database transaction.
    processOrderCommand(body);

    // Only settle as complete after the transaction has committed.
    context.complete();
}
~~~

This snippet is a **handler outline**, meant to be invoked from the processor client callback with the processor configured in Peek-Lock/manual settlement mode appropriate for the SDK version. If a framework listener automatically completes after the callback, do not call manual settlement redundantly. Do not catch and swallow exceptions; if the transaction fails, let the policy handle retry/abandon or dead-lettering.

## 12. Event Grid and Spring Boot Webhooks

Event Grid commonly pushes events to HTTP endpoints. The handler needs to:
- Complete the subscription validation handshake according to the event type/schema.
- Verify endpoint authentication; do not treat an obscure URL as a security mechanism.
- Parse the configured Event Grid schema or CloudEvents 1.0 accurately.
- Use the event ID to prevent duplicates.
- Persist work durably or publish to a queue before returning success if processing takes time.
- Limit request body size, validate schemas, and do not trust event data as already-authorized data.

An illustrative Spring MVC endpoint for **CloudEvents JSON** (DTOs must be adjusted to your actual schema and Jackson configuration):

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record CloudEventRequest(
        String specversion,
        String id,
        String source,
        String type,
        Instant time,
        String subject,
        Object data) {}

@RestController
@RequestMapping("/events")
class OrderEventController {

    @PostMapping
    ResponseEntity<Void> receive(
            @RequestBody List<CloudEventRequest> events) {

        for (CloudEventRequest event : events) {
            if (event.id() == null || event.type() == null) {
                return ResponseEntity.badRequest().build();
            }
            // Persist to inbox/queue with unique event ID.
            acceptForAsyncProcessing(event);
        }
        return ResponseEntity.ok().build();
    }

    private void acceptForAsyncProcessing(CloudEventRequest event) {
        // Store durably and deduplicate before acknowledging delivery.
    }
}
~~~

This is an illustrative skeleton, not a complete production webhook. You must implement subscription validation per the chosen protocol; authenticate the source/endpoint, enforce schema limits, handle duplicates, use transactions when saving to an inbox, and return responses per the delivery contract. If the handler cannot persist durably, return an appropriate error so Event Grid can retry according to policy.

## 13. Combining All Three Services in One Architecture

An e-commerce system can use all three:
- **Event Grid** receives `BlobCreated` notifications and routes them to a file-checking function or puts a reference onto Service Bus.
- **Service Bus** receives `GenerateInvoice` commands, processed by workers with lock/complete, retries, and DLQ.
- **Event Hubs** receives telemetry from applications, gateways, and workers to analyze throughput, latency, and user behavior.

~~~mermaid
flowchart TD
    B["Blob Storage: invoice uploaded"] --> EG["Event Grid"]
    EG --> Q["Service Bus queue: validate invoice"]
    Q --> W["Spring Boot invoice worker"]
    W --> DB["Managed database"]
    APP["Spring Boot services"] --> EH["Event Hubs: telemetry stream"]
    W --> EH
    EH --> AN["Stream analytics / data platform"]
    Q -. "Poison messages" .-> DLQ["Service Bus DLQ"]
~~~

Do not blindly replicate every business event into all three services. Each stream/flow needs an owner, purpose, retention, schema, permissions, cost center, and error-handling procedure. When Event Grid routes into Service Bus, producers/handlers must clearly define which events are forwarded and how to avoid duplicate submissions.

## 14. Security, Networking, and Authorization

### 14.1. RBAC and Identity

Use Managed Identity or Workload Identity whenever possible:
- Event Hubs producer: **Azure Event Hubs Data Sender**.
- Event Hubs consumer: **Azure Event Hubs Data Receiver**.
- Service Bus producer: **Azure Service Bus Data Sender**.
- Service Bus consumer: **Azure Service Bus Data Receiver**.
- Event Grid publisher: **EventGrid Data Sender** or the corresponding data role per resource.
- Webhook/handler: authenticate separately using a supported mechanism, such as Microsoft Entra/managed identity for compatible destinations, or appropriate endpoint authentication.

Roles assigned at the namespace level can cover multiple entities; assign at a smaller scope when the service and role support it. Do not grant Contributor/Owner just to send or receive messages. Resource management permissions differ from data-plane permissions; verify the actual runtime principal rather than local credentials.

### 14.2. SAS, Connection Strings, and Secrets

SAS/connection strings may be needed in certain scenarios, but you must:
- Scope to the namespace/entity, Send/Listen/Manage rights, and expiration.
- Never use **Manage** permissions for workloads that only need Send or Listen.
- Store in Azure Key Vault or an appropriate secret manager; rotate and revoke when compromise is suspected.
- Never log connection strings, SAS tokens, or sensitive raw message payloads.
- Prefer Entra ID when supported by the SDK, service, and deployment environment.

### 14.3. Networking

Event Hubs, Service Bus, and Event Grid offer network controls depending on the resource/tier, such as firewalls, private endpoints/private links, or supported network connections. Verify DNS, routing, TLS, ingress/egress, and endpoint reachability from the runtime. A private endpoint does not grant permissions by itself; RBAC and authentication must still be configured properly.

## 15. Reliability: Retries, Duplicates, Ordering, and Dead-Lettering

| Aspect | Event Hubs | Event Grid | Service Bus |
|---|---|---|---|
| Retry | Consumers manage retry/checkpointing; producer SDK has retry policies | Delivery retries per resource policy | Redelivery on abandon/lock expiry; retries in consumer |
| Duplicates | Consumers may re-read from the last checkpoint | Events may be delivered multiple times | Messages may be redelivered; duplicate detection is optional |
| Ordering | Within one partition per stream semantics | No global ordering guarantee | Sessions support ordering within a session |
| Replay | Re-read by offset within retention | Requires a separate store for long-term history replay | Not a replay log; message lifecycle via settlement |
| Poison events | Application logging/quarantine/checkpoint policy | Dead-lettering if configured | Built-in DLQ |
| Backpressure | Consumer throughput, partition ownership, checkpoints | Endpoint response, delivery retries, pull model if supported | Prefetch, max concurrent calls, lock duration, queue depth |

Principles:
- Generate stable business **eventId/messageId** values rather than relying only on delivery IDs.
- Make consumers idempotent using an inbox/processed-event table or conditional updates.
- Only checkpoint Event Hubs after durable side effects per your processing strategy.
- Only Complete Service Bus messages after the business transaction.
- Event Grid webhooks should persist durably before returning 2xx for work that will be processed later.
- Use bounded retries with backoff/jitter, deadlines, and error classification; do not retry 401/403/schema errors forever.
- Monitor DLQ/dead-letter storage and maintain an approved replay procedure.

## 16. Observability and Cost

### 16.1. Metrics to Monitor

**Event Hubs**
- Incoming messages/bytes and outgoing messages/bytes.
- Throttled requests, server errors, active connections.
- Consumer lag / processing delay by offset and event time.
- Checkpoint failures, partition ownership rebalances, Capture backlog/storage.
- Partition count and throughput/capacity utilization per tier.

**Event Grid**
- Delivery success/failure, delivery attempts, unmatched events.
- Dead-lettered events and destination capacity.
- Publish errors, latency, and endpoint availability.
- Event count per topic/subscription, filter matches, and retries.

**Service Bus**
- Active messages, dead-lettered messages, scheduled messages.
- Incoming/outgoing requests, server errors, throttled requests.
- Queue/topic/subscription size, oldest message age.
- Lock lost/abandoned/expired, delivery count, and DLQ growth.
- Messaging Units/CPU/memory for the corresponding tier.

Set alerts on **latency and backlog age**, not just message count. A queue with 100 messages where the oldest message has waited an hour can be more severe than a queue with 10,000 messages generated over a few seconds.

### 16.2. Cost and Capacity

- **Event Hubs:** pricing depends on tier/capacity model, throughput/capacity units, ingress/processing, and retention or Capture features as chosen.
- **Event Grid:** billed per operations/events/deliveries or specific resource/tier model; retries and fan-out can increase delivery volume.
- **Service Bus:** depends on tier, messaging operations, capacity/messaging units, and networking/geo-disaster recovery features per SKU.

There is no single fixed price that applies across all Regions and times. Read the official pricing table for your **SKU, Region, volume, payload size, retention, networking, and number of subscriptions/consumers**. Also factor in the cost of Blob Storage used for checkpoints or Capture, logs/monitoring, private endpoints, and data transfer.

## 17. Integration Testing

A test suite can be divided into layers:

1. **Contract/unit tests:** test event schemas, versions, validation, partition keys, message properties, and business idempotency using fixtures.
2. **Component tests:** test adapters/serialization/retry logic using mocks or test doubles; do not assume mocks prove Azure semantics.
3. **Cloud integration tests:** use dedicated test namespaces, topics, queues, subscriptions, and storage; verify real credentials, RBAC, endpoints, and delivery.
4. **Failure tests:** connection drops, endpoint timeouts, duplicates, consumer crashes before ACK/checkpoint, poison messages, lock expiry, quota/throttling.
5. **Recovery tests:** verify DLQ, replay, checkpoint resume, consumer rebalance, and cleanup.
6. **Security tests:** verify dev identities cannot publish/consume from production resources; secrets never appear in logs.

### 17.1. Test Matrix by Service

| Scenario | Event Hubs | Event Grid | Service Bus |
|---|---|---|---|
| Successful event delivery | Producer sends and consumer receives | Publish and endpoint receives | Send and receiver receives |
| Consumer/endpoint failure | Checkpoint does not advance wrongly; resume can replay | Retries and dead-lettering as configured | Abandon/lock expiry and redelivery |
| Duplicate event | Deduplicate by eventId in consumer | Idempotent handler | MessageId/dedup per config and DB dedup |
| Horizontal scaling | Partition ownership and rebalance | Multiple endpoints/workers per delivery model | Multiple receivers and lock contention |
| Ordering | Same partition key | Do not assume global order | SessionId and session receiver |
| Overload | Throughput, throttling, lag | Delivery failure/endpoint backpressure | Queue depth, locks, throttling, tier |
| Replay | Offset/retention/checkpoint | Separate event store or application-driven replay | Controlled replay via DLQ/resubmit |

Do not use production namespaces to test malformed messages, delete topics, or test quotas by intentionally generating load. Create test resources with bounded TTL/lifecycle and cost limits.

## 18. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Event Hubs is a queue where each event goes to one consumer | Multiple consumer groups can read independently; instances in the same group share partitions |
| Event Grid stores events for replay like an event store | Event Grid primarily routes and delivers; long-term storage/replay requires a separate store/stream |
| A Service Bus topic is a stream log | Topics distribute messages to subscriptions that have independent lifecycles/settlement |
| Event Grid guarantees event ordering | Do not design around global ordering; handlers need versions/state transitions |
| SQS/SB/PubSub or Event Grid deliver exactly once | Duplicates/redeliveries can still occur depending on semantics; business idempotency is required |
| Checkpointing Event Hubs before processing is faster and safe | Events can be skipped if processing fails after the checkpoint |
| Calling Service Bus Complete before committing to the DB is safe | Messages can be lost if the DB commit fails after Complete |
| Duplicate detection replaces idempotency | Broker dedup has scope/time limits; external side effects still need duplicate protection |
| Using Managed Identity means RBAC is unnecessary | The identity must still be assigned the appropriate data-plane role |
| Private endpoints guarantee every request is valid | Private networking does not replace authentication, authorization, or schema validation |
| One producer can only send one event type | It can send multiple event types, but needs clear contracts, routing, and permissions |
| All three services charge the same way per message | Each service has its own meters, tiers, throughput, and delivery models |

## 19. Selection and Implementation Checklist

Before deciding on a service, answer:

- **Purpose:** continuous stream, event routing, or command/work queue?
- **Volume:** events/second, payload size, bursts, retention, and required throughput?
- **Consumers:** one group of workers or multiple independent consumers? Are fan-out/filters needed?
- **Delivery:** at-least-once, replay, checkpoints, ACK/Complete, or pull/push?
- **Ordering:** global order, by partition key, or by session?
- **Failures:** how are duplicates, retries, poison events, DLQs, checkpoints, replay, and idempotency handled?
- **Security:** workload identity, RBAC data roles, SAS/secrets, private networking, and cross-environment isolation?
- **Operations:** metrics, alerts, backlogs, DLQs, consumer lag, quotas, and runbooks?
- **Cost:** tier, capacity, operations/deliveries, retention, Capture/storage, networking, and monitoring?
- **Spring compatibility:** matching BOM, starter/SDK, auto-configuration, client lifecycle, and settlement semantics for your version?

## 20. Summary

**Event Hubs** is the choice for high-throughput event streaming, partitions, consumer groups, and offset-based replay within retention. **Event Grid** is the choice for event routing, filtering, and notifications when an event occurs. **Service Bus** is the choice for enterprise messaging, queues/topics, settlement, sessions, retries, and dead-lettering. The three services can work together, but they do not replace one another.

When integrating Spring Boot, choose the service based on the **contract and how consumers must process data**, and only then select the starter/SDK. Protect each flow with managed identity and RBAC, design proper schemas/event IDs, idempotency, timely checkpoints or ACKs, monitor lag/backlog/DLQ, and test failures on dedicated resources. This approach helps your application leverage Azure's capabilities correctly and maintain correctness as the system scales or a component fails.
