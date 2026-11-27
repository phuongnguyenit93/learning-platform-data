# Sending Events and Operating an Event Hubs Processor

Azure Event Hubs is not just an endpoint for emitting events. A production system must manage producer lifecycles, group events into appropriate batches, choose partition keys, authenticate identities, handle indeterminate send outcomes, run distributed consumers, persist checkpoints, and monitor lag. If producers create clients repeatedly, consumers checkpoint at the wrong time, or the application swallows exceptions, the system can incur higher costs, lose processing progress, or cause duplicate side effects.

In the **Azure Events** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, this lesson guides you through integrating Spring Boot with Azure Event Hubs using the Azure SDK for Java and appropriate Spring Cloud Azure libraries. The focus is on **sending events safely**, **operating EventProcessorClient**, configuring Managed Identity and Azure RBAC, managing checkpoints/ownership, handling errors, monitoring, and testing in an isolated environment.

## 1. Learning Objectives

After this lesson, you will be able to:

- Describe producer and consumer lifecycles when working with Event Hubs.
- Send single events or batches using the Azure SDK for Java.
- Choose partition keys and attach metadata such as event ID, schema version, and correlation ID.
- Manage reusable producer clients in Spring Boot and close resources properly.
- Configure EventProcessorClient with a consumer group, Blob checkpoint store, and workload identity.
- Understand how the processor starts/stops, claims ownership, processes events, updates checkpoints, and reports errors.
- Handle timeouts, throttling, duplicates, poison events, checkpoint failures, and graceful shutdowns.
- Assign Event Hubs Data Sender/Receiver and Storage Blob Data Contributor permissions following least privilege.
- Test producers/processors, monitor consumer lag, partition ownership, and operational costs.

## 2. Producer and Processor Architecture

An application can both publish and consume events, though the two roles should have distinct configurations and permissions. Producers send data to an event hub; processors read the stream within a consumer group, coordinate ownership across instances, and persist progress in a checkpoint store.

~~~mermaid
flowchart LR
    API["Spring Boot API"] --> PR["EventHubProducerClient"]
    PR --> EH["Azure Event Hubs"]
    EH --> P0["Partition 0"]
    EH --> P1["Partition 1"]
    EH --> P2["Partition 2"]
    P0 --> EP["EventProcessorClient"]
    P1 --> EP
    P2 --> EP
    EP --> DB["Business database"]
    EP <--> CP["Blob checkpoint store"]
    EP --> OBS["Logs / metrics / tracing"]
~~~

Each component has a distinct responsibility:

| Component | Responsibility | Lifecycle |
|---|---|---|
| Producer client | Builds batches, sends events, applies SDK retries/timeouts | Reused over the application's lifetime |
| Event Hub | Receives and retains events per partition within retention | Managed by Azure |
| Consumer group | Tracks an independent logical reading position for a workload | Exists per Event Hubs configuration |
| EventProcessorClient | Reads events, distributes partition ownership, and invokes handlers | Started when app is ready; stopped on shutdown |
| Blob checkpoint store | Stores processor ownership and checkpoints | Separate, long-lived resource |
| Business handler | Validates, executes business logic, deduplicates, and persists data | Managed by the application |
| Observability | Measures throughput, lag, errors, checkpoints, and worker health | Continuous operation |

**Event Hubs does not store business-processed state.** It retains events according to retention; the application must manage processing outcomes, idempotency, and checkpoints.

## 3. Preparing the Namespace, Event Hub, and Identity

Before writing code, clearly identify:

- **Namespace FQDN:** for example `orders-dev.servicebus.windows.net`.
- **Event hub name:** for example `order-events`.
- **Consumer group:** for example `order-projection`; each logical workload gets its own group.
- **Checkpoint container:** for example the `eventhub-checkpoints` container in an appropriate storage account.
- **Environment:** dev, test, staging, or production.
- **Region and tier/capacity:** matching throughput, retention, and operational requirements.
- **Runtime principal:** the Managed Identity or workload identity that Spring Boot actually uses.

Create event hubs and checkpoint containers via IaC or a controlled platform process. Do not let every Spring Boot startup auto-create production namespaces, event hubs, or containers; the runtime should only have permissions to use already-provisioned resources.

### 3.1. Permissions for Producers and Processors

| Role | Resource | Suggested Azure Role |
|---|---|---|
| Producer | Target event hub/namespace | **Azure Event Hubs Data Sender** |
| Consumer processor | Source event hub/namespace | **Azure Event Hubs Data Receiver** |
| Processor checkpoint | Blob container storing ownership/checkpoints | **Storage Blob Data Contributor** |
| Platform/IaC | Create namespace, hub, storage account, container, and role assignments | Management permissions at deployment scope, separated from runtime |

Assign roles at the narrowest scope allowed by the service and architecture. Namespace/resource management roles do not automatically substitute for data-plane permissions. Conversely, Data Sender does not need permission to create or delete event hubs.

The checkpoint store is an independent resource: a processor can read Event Hubs successfully yet fail to balance ownership or save checkpoints if Blob permissions are missing. The container should be pre-created with IaC; the workload needs appropriate blob read/write permissions.

### 3.2. Authenticating with Managed Identity

Prefer Microsoft Entra ID and workload identities where supported by the environment:
- Local development: logged-in developer credentials granted dev permissions.
- Azure App Service/VM: Managed Identity per service configuration.
- AKS: Workload Identity for Kubernetes workloads.
- CI/CD: workload identity federation or scoped service connections.

Never commit SAS tokens, connection strings, or secrets to a repository. If SAS must be used, restrict it by entity, Send/Listen permissions, and expiration; store it in a secret manager, rotate, and audit it. Never grant Manage rights to workloads that only need to send or receive events.

## 4. Choosing the Azure SDK and Spring Cloud Azure

There are two common integration approaches:

**Direct Azure SDK:** suitable when you need granular control over producer batches, EventProcessorClient, checkpoint stores, callbacks, retries, and lifecycles. This is the primary approach illustrated in this lesson.

**Spring Cloud Azure:** provides starters and auto-configuration to integrate Azure services in an idiomatic Spring Boot way. Artifact names, properties, annotations, and APIs can vary across major versions. Before using it:
- Select a Spring Cloud Azure BOM compatible with your Spring Boot version.
- Verify that the starter exposes required operations such as checkpointing, manual processing, partition context, and lifecycle control.
- Avoid creating manual clients that duplicate auto-configured beans.
- When fine-grained control over partition ownership/checkpointing is required, consider using EventProcessorClient directly as a Spring bean.

Java dependencies typically needed for the examples:
- `azure-messaging-eventhubs`
- `azure-messaging-eventhubs-checkpointstore-blob`
- `azure-storage-blob`
- `azure-identity`
- Spring Boot configuration and dependency injection

Use a BOM or dependency management to align Azure SDK versions; do not pick disjointed versions without checking compatibility.

## 5. Configuring Spring Boot per Environment

Example custom configuration:

~~~yaml
app:
  event-hubs:
    namespace: orders-dev.servicebus.windows.net
    event-hub-name: order-events
    consumer-group: order-projection
    checkpoint-container-url: https://ordersdevstore.blob.core.windows.net/eventhub-checkpoints
    partition-key-field: orderId
~~~

Keys under `app.event-hubs.*` are application-defined properties in this example, **not default properties common to all Spring Cloud Azure versions**. Bind them with `@ConfigurationProperties`, validate on startup, and supply values from deployment config.

Dev, test, staging, and production each need appropriate namespaces/hubs, consumer groups, and checkpoint containers. Never let a test profile accidentally point to production endpoints or checkpoints. Verify:
- Namespace and event hub name.
- Consumer group.
- Checkpoint storage account/container.
- Runtime principal and tenant.
- Region/environment manifest.
- Network endpoints, DNS, and private access.

Profiles only select configuration; RBAC is what enforces permissions. If a misconfiguration points to a production resource, the dev identity should still be denied at the target resource.

## 6. Sending Events with EventHubProducerClient

### 6.1. Creating a Reusable Producer Client

Azure SDK clients should be created once per application lifecycle and reused. Do not instantiate a new client per HTTP request, as that increases connection setup overhead, network resource usage, and latency.

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@ConfigurationProperties(prefix = "app.event-hubs")
record EventHubProperties(
        String namespace,
        String eventHubName,
        String consumerGroup,
        String checkpointContainerUrl) {}

@Configuration
@EnableConfigurationProperties(EventHubProperties.class)
class EventHubProducerConfiguration {

    @Bean
    DefaultAzureCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean(destroyMethod = "close")
    EventHubProducerClient eventHubProducerClient(
            EventHubProperties properties,
            DefaultAzureCredential credential) {
        return new EventHubClientBuilder()
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .buildProducerClient();
    }
}
~~~

This snippet assumes the namespace is an FQDN, the event hub already exists, and the runtime principal has **Azure Event Hubs Data Sender**. DefaultAzureCredential selects credentials based on the environment; verify effective credentials when running in the cloud. The bean uses `destroyMethod = "close"` to release the client when the Spring context shuts down.

### 6.2. Sending a Single Event

~~~java
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import org.springframework.stereotype.Service;

@Service
class TelemetryPublisher {
    private final EventHubProducerClient producer;

    TelemetryPublisher(EventHubProducerClient producer) {
        this.producer = producer;
    }

    void publish(String jsonPayload) {
        EventData event = new EventData(jsonPayload);
        producer.send(java.util.List.of(event));
    }
}
~~~

Completing `send` means the producer received acknowledgment per SDK/service semantics for the send operation; **it does not mean a consumer has read or processed the event**. If end-to-end tracking is needed, payloads must include an event ID/correlation ID and consumers must emit separate metrics or business outcomes.

Do not send arbitrary Java objects without defining serialization. Use versioned JSON/Avro/Protobuf schemas, enforce size limits, and validate content before sending.

### 6.3. Sending in Batches

Batching helps utilize request capacity and reduce overhead when sending many events. Event Hubs has batch/message size limits by tier and configuration; do not hardcode an arbitrary payload size.

~~~java
import com.azure.messaging.eventhubs.CreateBatchOptions;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import java.util.List;

class BatchedEventPublisher {
    private final EventHubProducerClient producer;

    BatchedEventPublisher(EventHubProducerClient producer) {
        this.producer = producer;
    }

    void publishBatch(List<String> payloads, String partitionKey) {
        CreateBatchOptions options =
                new CreateBatchOptions().setPartitionKey(partitionKey);
        EventDataBatch batch = producer.createBatch(options);

        for (String payload : payloads) {
            EventData event = new EventData(payload);
            if (!batch.tryAdd(event)) {
                if (batch.getCount() == 0) {
                    throw new IllegalArgumentException(
                            "A single event exceeds the batch size limit");
                }

                producer.send(batch);
                batch = producer.createBatch(options);

                if (!batch.tryAdd(event)) {
                    throw new IllegalArgumentException(
                            "A single event exceeds the batch size limit");
                }
            }
        }

        if (batch.getCount() > 0) {
            producer.send(batch);
        }
    }
}
~~~

This is a synchronous example illustrating how to split batches. In production you must:
- Check for empty batches before sending and ensure no unadded event is dropped.
- Bound the number of events/bytes in application buffers.
- Handle per-batch send failures and determine which events require retry.
- Avoid keeping an unbounded list on the heap when producers outpace the service.
- Use a reusable client and measure batch creation/send latency.
- When using a partition key, all events in the batch route by that key; skewed key distribution can create hot partitions.

Do not arbitrarily split an oversized event into multiple events if consumers have no contract to reassemble them. For large payloads, consider storing the content in Blob Storage and sending a reference with restricted access.

### 6.4. Attaching Metadata and Event IDs

An event should contain:
- `eventId`: unique business ID, stable across retries.
- `eventType` and `schemaVersion`: contract type and version.
- `aggregateId`/partition key: entity requiring ordering.
- `occurredAt`: business occurrence timestamp.
- `correlationId`/trace context: links processing steps.
- Minimal payload required by consumers.

Example payload:

~~~json
{
  "eventId": "evt-1001-01",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "order-1001",
  "occurredAt": "2026-11-24T10:00:00Z",
  "correlationId": "req-abc-123",
  "data": {
    "orderId": "order-1001",
    "currency": "VND",
    "total": 450000
  }
}
~~~

The event ID should be generated by business logic before the first send attempt and kept identical on retries. Never generate a new ID per attempt, or consumers cannot recognize duplicate submissions of the same intent. Do not put secrets, access tokens, passwords, or unnecessary sensitive data in payloads or properties.

### 6.5. Partition Keys and Ordering

Use a partition key matching the entity requiring ordered processing, such as `orderId`. Events for the same order are routed to the same partition by Event Hubs' mechanism; events for different orders can run in parallel. There is no global order across partitions.

Do not pick a skewed key like one huge tenant value if it creates a hot partition. If the business requires per-customer ordering yet one customer generates disproportionate traffic, design sharding/sequencing or accept parallelism limits. A partition key is not a transaction lock and does not automatically guarantee database commit order.

## 7. Sending Events Safely Under Failures

### 7.1. Producer Error Classification

| Error | Handling Approach |
|---|---|
| Authentication/authorization | Check credentials, tenant, Data Sender role, and scope; do not retry indefinitely |
| Wrong namespace/event hub | Verify FQDN, hub name, environment, and resource existence |
| DNS/network/TLS | Check private endpoint, DNS, firewall, routing, and certificates |
| Payload/batch too large | Reduce payload or split batches per contract; do not retry the same batch |
| Throttling/quota | Slow down, respect retry policy, apply backoff, and monitor metrics |
| Timeout during send | Outcome may be indeterminate; the event may already have been received |
| Transient service unavailable | Bounded retries if side effects are protected by event ID/idempotency |
| Invalid schema | Fix data; do not retry the same malformed payload |

The Azure SDK has its own retry policies per client/API and version. Before adding Spring Retry/Resilience4j, determine which cases the SDK already retries to avoid nested retries. Retries need exponential backoff, jitter, attempt limits, and an overall deadline.

### 7.2. A Timeout Does Not Prove the Event Was Not Received

If a producer sends an event and the response is lost, the application cannot be sure whether Event Hubs received the event. Retrying can produce duplicate events. How to handle this:
- Keep the exact same event ID across all retry attempts.
- Deduplicate at the consumer by event ID in a database or inbox table.
- Log sanitized attempt/request context for investigation.
- If the business requires DB commits and event publishing to stay consistent, use a transactional outbox rather than committing to the DB and calling send directly in the same request.
- Never claim exactly-once just because SDK send returned successfully.

### 7.3. Transactional Outbox

If updating an order in the database and publishing an event are two separate operations, the following can happen:
- DB commit succeeds, but publish fails.
- Event is published, yet the DB transaction rolls back.
- Publish succeeds, response is lost, publisher retries and creates duplicates.

A transactional outbox writes business state and the event to publish in the **same database transaction**. A separate worker reads the outbox and sends to Event Hubs; only after a successful send does it mark the row as published. If the worker crashes after sending but before marking, the event may be resent; consumers still require idempotency.

~~~mermaid
flowchart TD
    API["Spring Boot API"] --> TX["Database transaction"]
    TX --> O["Update order"]
    TX --> OB["Insert outbox event"]
    OB --> W["Outbox publisher"]
    W --> EH["Event Hubs"]
    EH --> C["Idempotent consumer"]
    W -. "Timeout / retry" .-> OB
~~~

An outbox does not create exactly-once across the database and Event Hubs; it ensures events are not dropped between business commits and emission, with potential duplicates handled by consumers.

## 8. Operating EventProcessorClient

### 8.1. What Does the Processor Do?

EventProcessorClient manages reading events in a consumer group and coordinating partition ownership via a checkpoint store. A processor instance:
1. Starts with a namespace, event hub, and consumer group.
2. Reads current ownership from the checkpoint store.
3. Claims ownership of one or more partitions through load balancing.
4. Reads events from the checkpoint, or initial position if no checkpoint exists.
5. Invokes the event processing callback.
6. Updates checkpoints when requested by the application.
7. Reports exceptions/transport/ownership issues to the error callback.
8. Stops when the application shuts down.

Multiple instances of the same workload use the **same consumer group and the same checkpoint store** to coordinate. Different logical applications needing independent progress must use different consumer groups. Never assign a separate consumer group per pod if you want pods to share partitions.

### 8.2. Blob Checkpoint Store

BlobCheckpointStore persists two types of state:
- **Ownership:** which processor instance currently owns a partition in the consumer group.
- **Checkpoint:** the latest processed position on a partition.

The container should be created via IaC before the processor starts. The runtime principal needs appropriate Blob data permissions. If the Blob endpoint is unreachable, the processor may fail to write checkpoints or balance ownership as expected; do not check only Event Hubs permissions.

The checkpoint store does not store all events. Events stay in Event Hubs per retention; if long-term archiving is needed, look into Event Hubs Capture or a pipeline archiving to Blob Storage/ADLS.

### 8.3. Creating the EventProcessorClient Bean

Spring Boot example using the Azure SDK directly:

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class EventProcessorConfiguration {

    @Bean(destroyMethod = "stop")
    EventProcessorClient eventProcessorClient(
            EventHubProperties properties,
            DefaultAzureCredential credential,
            BlobContainerAsyncClient checkpointContainer,
            OrderEventHandler handler) {

        return new EventProcessorClientBuilder()
                .consumerGroup(properties.consumerGroup())
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .checkpointStore(new BlobCheckpointStore(checkpointContainer))
                .processEvent(context -> {
                    handler.handle(context.getEventData());
                    // Only checkpoint after the handler completes durable processing.
                    context.updateCheckpoint();
                })
                .processError(error -> {
                    // Use a structured logger in production applications.
                    // Log exception, partition, and sanitized context.
                    System.err.println(
                            "Event processor error: " + error.getThrowable());
                })
                .buildEventProcessorClient();
    }
}
~~~

This example assumes `EventHubProperties`, `DefaultAzureCredential`, `BlobContainerAsyncClient`, and `OrderEventHandler` beans are configured. Callback APIs must be verified against your project's Azure SDK version. In production code, use a logger instead of `System.err`, add metrics, and avoid logging sensitive payloads.

### 8.4. Starting and Stopping with the Spring Lifecycle

EventProcessorClient should be started after the application context has initialized required beans and dependencies. You can use ApplicationRunner:

~~~java
import com.azure.messaging.eventhubs.EventProcessorClient;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
class EventProcessorStarter implements ApplicationRunner {
    private final EventProcessorClient processor;

    EventProcessorStarter(EventProcessorClient processor) {
        this.processor = processor;
    }

    @Override
    public void run(ApplicationArguments args) {
        processor.start();
    }
}
~~~

The bean declares `destroyMethod = "stop"` so Spring invokes stop when the context closes. Verify shutdown behavior and stop duration for your SDK version; avoid killing the process immediately mid-event.

Another option is a Spring lifecycle component to start/stop by phase. Whichever approach you pick, avoid:
- Calling start multiple times on the same bean.
- Creating a new processor client on every refresh request.
- Stopping the processor before pending commit operations finish.
- Closing the Blob client/checkpoint store too early.
- Swallowing shutdown errors, making the system appear to have stopped cleanly.

### 8.5. Graceful Shutdown

When a container receives SIGTERM during a rollout:
1. Stop accepting new work from other sources if needed.
2. Tell the processor to stop and relinquish ownership per the SDK mechanism.
3. Allow in-flight callbacks to finish within the shutdown grace period.
4. Ensure side effects commit before checkpointing.
5. Close clients and datasources according to lifecycle order.
6. If work cannot finish in time, let events be re-read from the last checkpoint and guard against duplicates with idempotency.

Do not checkpoint an event that is still mid-processing. If the orchestrator kills the process before the callback finishes, the event may replay; that behavior is necessary to prevent data loss.

## 9. Processing Events in the Processor

### 9.1. Validate, Process, Checkpoint

A handler should execute in this order:
1. Read body and metadata.
2. Validate schema version, event ID, event type, and partition context.
3. Record correlation/trace context.
4. Execute idempotent business logic inside a transaction.
5. If the event is invalid, store it in durable quarantine per policy.
6. Only checkpoint after processing or quarantine completes.

Example PostgreSQL DDL for a deduplication table:

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(200) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id varchar(200) PRIMARY KEY,
    status varchar(50) NOT NULL
);
~~~

Example service handler using a unique constraint to prevent two competing callbacks from processing the same event:

~~~java
import com.azure.messaging.eventhubs.EventData;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderEventHandler {
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    OrderEventHandler(
            JdbcTemplate jdbc,
            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public void handle(EventData event) {
        OrderCreated payload = parseAndValidate(event.getBodyAsString());
        if (payload.eventId() == null || payload.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }

        int inserted = jdbc.update(
                "INSERT INTO processed_event (consumer_name, event_id) " +
                "VALUES (?, ?) ON CONFLICT DO NOTHING",
                "order-projection",
                payload.eventId());
        if (inserted == 0) {
            return;
        }

        jdbc.update(
                "INSERT INTO order_projection (order_id, status) VALUES (?, ?)",
                payload.data().orderId(),
                payload.data().status());
    }

    private OrderCreated parseAndValidate(String body) {
        try {
            OrderCreated payload = objectMapper.readValue(body, OrderCreated.class);
            if (payload == null || payload.data() == null
                    || payload.data().orderId() == null
                    || payload.data().orderId().isBlank()) {
                throw new IllegalArgumentException("Missing order data");
            }
            return payload;
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Invalid event payload", exception);
        }
    }
}

record OrderCreated(String eventId, OrderCreatedData data) {}
record OrderCreatedData(String orderId, String status) {}
~~~

This is an illustrative skeleton; in real implementations, validate property nulls/types, use unique constraints to guard against race conditions instead of `exists` then `record`, and ensure the repository and processed-event table participate in the same transaction. Never leave placeholder exception handling in production handlers.

### 9.2. Duplicates and Idempotency

EventProcessorClient may re-read events from the latest checkpoint after a crash/rebalance. Consumers must tolerate at-least-once processing:
- Use a stable event ID generated by the producer.
- Enforce a unique constraint on event ID or `(consumerName, eventId)`.
- Write the processed-event record and projection changes in the same transaction.
- If the same ID arrives with a different payload, report a conflict for investigation.
- Retain deduplication records long enough relative to retention and replay windows.
- Do not use offsets as the sole business ID, because replays or other consumer groups may read events in different contexts.

### 9.3. Poison Events and Quarantine

Events with invalid schemas or invariant violations can cause callbacks to fail continuously. Event Hubs has no Service Bus-style built-in DLQ. Applications can:
- Save the event and required metadata to a dedicated quarantine store/queue.
- Record partition ID, offset, sequence number, event ID, and a sanitized failure reason.
- Only checkpoint past the event once quarantine persistence succeeds and policy permits skipping.
- If quarantine storage fails, do not checkpoint past the event; raise an error and intervene per runbook.
- Maintain a process to fix data/handlers and run a controlled replay.

Do not log raw payloads if they contain personal data or secrets. Quarantined data also requires encryption, RBAC, retention, and lifecycle policies.

## 10. Checkpointing at the Right Time

**A checkpoint represents processed progress**, not proof that an event reached the processor. The standard rule is to commit side effects first, then checkpoint.

| Order | Failure | Outcome |
|---|---|---|
| Checkpoint before DB commit | Process crashes between steps | May skip an event not yet written to DB |
| DB commit before checkpoint | Process crashes between steps | Event may be re-read |
| DB commit + dedup before checkpoint | Event is re-read | Dedup prevents duplicate side effects |
| Durable quarantine before checkpoint | Invalid-schema event | Can be skipped per policy so the stream continues |

Checkpointing every event reduces replay volume but increases checkpoint writes. Checkpointing per batch/interval reduces overhead but may re-read more already-processed events. Choose frequency based on throughput, Blob costs, replay capability, and idempotency.

If the callback processes events asynchronously, never checkpoint on the last event simply because it was received last. Ensure **every event prior to the checkpoint has completed or been durably quarantined**. Otherwise, a slow-processing event can be skipped once the checkpoint advances past it.

## 11. Error Handling and Retries

### 11.1. Producers and Processors Have Different Error Types

| Layer | Error Example | Response |
|---|---|---|
| Producer | 401/403 | Check token, tenant, Data Sender role, and scope |
| Producer | Wrong namespace/hub | Fix endpoint/name; do not retry indefinitely |
| Producer | Payload/batch too large | Shrink/split payload per contract |
| Producer | Throttling/temporary service error | Bounded retries with backoff/jitter |
| Processor | Blob checkpoint access denied | Check Storage Blob Data Contributor, scope, and identity |
| Processor | Event Hubs receive denied | Check Event Hubs Data Receiver |
| Processor | Network/DNS/AMQP failure | Check private endpoint, DNS, firewall, TLS, and retries |
| Handler | Database timeout | Distinguish indeterminate commits, transactions, and idempotency |
| Handler | Schema/validation failure | Quarantine or halt per policy; do not retry forever |
| Checkpoint | Blob write failure | Do not assume checkpoint saved; monitor replay and ownership |

### 11.2. The Error Callback Is Not for Business Handling

`processError` receives processor/partition processing errors and is where exceptions, partition IDs, operations, and correlation are recorded. Do not use this callback to swallow handler errors or mark events successful. The handler must decide processing, retry/quarantine, and checkpointing; the error callback supports observability, alerting, and diagnostics.

Use a structured logger:
- Consumer group and event hub name.
- Partition ID.
- Exception class and sanitized error codes.
- Correlation/trace ID if available.
- Timestamp and processor state.
- Never log credentials, SAS tokens, or sensitive payloads.

### 11.3. Backoff and Nested Retries

The Azure SDK has retry policies for transient errors. If you add retries at the service layer, define total attempts, per-attempt timeout, and an overall flow deadline. Do not let the SDK retry multiple times while Spring Retry wraps and retries the whole operation in multiple loops. That can cause retry storms and duplicate events.

Do not retry 401/403, invalid payloads, or misspelled resource names indefinitely. For send timeouts, keep the same event ID and let consumers deduplicate. For indeterminate database commits, check status via idempotency records instead of minting a new event ID.

## 12. Monitoring and Day-to-Day Operations

### 12.1. Producer Metrics

- Incoming messages and incoming bytes.
- Send operation count, successes/failures, throttled requests.
- Average batch size and rate of batches running out of capacity.
- Producer send latency p50/p95/p99.
- Retry counts and final errors after retries.
- Event counts by event type/tenant/partition key (never put sensitive data into metric labels).

### 12.2. Processor Metrics

- Outgoing messages/bytes and consumer lag.
- Age of unprocessed events.
- Partition ownership count and ownership changes.
- Event processing success/failure counts and durations.
- Last checkpoint timestamp per partition.
- Checkpoint write failures and Blob latency.
- Duplicates suppressed, quarantine count, replay count.
- Processor active/stopped status and rebalance duration.

Distinguish **consumer lag** from **checkpoint lag**. A consumer may have processed events while checkpoints have not been written yet; conversely, a stale checkpoint can trigger replays even though side effects already committed.

### 12.3. Alerts and Runbooks

Example alert conditions:
- Consumer lag continuously rising above business thresholds.
- Unowned partitions or frequent ownership churn.
- Checkpoints not advancing for an abnormal period.
- Sudden spikes in throttling or server errors.
- Rapid growth in poison/quarantined events.
- Processor failing to start or failing to complete shutdown.
- Blob checkpoint store returning 403/timeouts.
- Incoming rate exceeding processing capacity for a sustained period.

Every alert needs an owner, severity, dashboard link, steps to verify principal/resource, and remediation steps. Do not apply one fixed threshold across all event hubs; baselines depend on throughput, tier, retention, and SLOs.

## 13. Integration Testing

Use dedicated test namespaces, event hubs, consumer groups, and Blob checkpoint containers. Never reset production checkpoints or change production partition counts for testing.

| Scenario | How to Test | Expected Result |
|---|---|---|
| Producer sends single event | Send event with a test event ID | Event is received and recorded accurately by consumer |
| Full batch | Send many events up to batch limits | No events lost when splitting batches |
| Single event exceeds batch size | Build a large test payload | Explicitly rejected or offloaded to object/reference storage |
| Partition key | Send multiple events with same aggregate key | Routed to the same partition under stable topology |
| Send timeout | Simulate lost response after send | Retries keep event ID; consumer deduplicates |
| Processor scale-out | Run multiple instances in the same group | Ownership redistributes; not every instance reads the full stream |
| Crash before checkpoint | Stop processor after DB commit | Events may replay; side effects do not repeat |
| Checkpoint store 403 | Use an identity missing the Blob data role | Processor reports errors; does not falsely advance checkpoints |
| Handler exception | Send invalid-schema payload | Quarantined or halted per policy |
| Graceful shutdown | Send SIGTERM while processing | Controlled stop; uncheckpointed events may replay |
| Network partition | Temporarily block DNS/endpoint | Processor recovers; checkpoints/ownership verified |
| Retention/replay | Use a new test consumer group with initial position | Replays exact range of data still within retention |
| Cross-environment access | Dev identity accesses prod hub | Denied by RBAC/network |
| Quota/throttling | Ramp up load within test limits | Controlled retries/backpressure without retry storms |

Unit tests verify serialization, partition keys, idempotency, and handler logic. Integration tests on Azure verify RBAC, networking, checkpoint stores, processor ownership, and real service behavior. Cap tests by quota/cost and clean up resources after runs.

## 14. Common Operational Scenarios

### Scenario A: Producer Sends Successfully, Yet Consumer Sees No Events

Check:
- Are producer and consumer pointing to the same namespace/event hub/Region?
- Is the consumer group right, and where are the initial position/checkpoint?
- Is the event still within retention?
- Does the processor own partitions, and are there errors in processError?
- Is consumer filtering/logic skipping the event?
- Are networking and RBAC valid for the runtime principal?

Do not conclude events were lost solely from one consumer group's dashboard; the group may be reading from an old offset or the consumer may not be started.

### Scenario B: Processor Restarts and Reprocesses Many Events

This may be a replay from the last checkpoint. Check checkpoint frequency, Blob store availability, shutdown behavior, rebalancing, and handler duration. Confirm DB deduplication works; if not, add an inbox/unique event ID before increasing checkpoint frequency.

### Scenario C: Processor Runs, Yet Checkpoints Do Not Advance

Check Storage Blob Data Contributor permissions, container URL, DNS/private endpoint, Blob client credentials, and exceptions in the error callback. Check whether handler code blocks indefinitely or callbacks never reach `updateCheckpoint`. Do not let a runtime role auto-create production checkpoint containers if your process requires IaC.

### Scenario D: Scale-Out Makes Event Processing Slower

Many instances can cause frequent rebalances, extra connections, and DB contention. Check partition count, ownership churn, CPU/DB pools, Blob checkpoint latency, and handler concurrency. Adding pods beyond the partition count adds no useful parallelism.

### Scenario E: Duplicate Events Sent After Timeout

A send response can be lost after the service already accepted the event. Check producer retries and event IDs. Keep event IDs stable across attempts; deduplicate in consumers. If publishing is tied to DB commits, use an outbox to eliminate gaps between the two systems.

## 15. Production Readiness Checklist for Producers and Processors

- **Resources:** namespace/event hub/consumer group/checkpoint container provisioned in the right environment and Region.
- **Identity:** producer has Event Hubs Data Sender; processor has Event Hubs Data Receiver; checkpoint has Blob Data Contributor at least-privilege scope.
- **Client lifecycle:** producer reused as a bean; processor started/stopped with Spring lifecycle; shutdown tested.
- **Producer:** clear event schema/version, event ID, partition key, batch size, retry/timeout, and backpressure.
- **Consumer:** idempotent handler, schema validation, duplicate handling, poison event quarantine, and timely checkpointing.
- **Checkpoints:** store available, permissions and networking verified, checkpoint frequency aligned with replay budget.
- **Ordering:** assume ordering only within a partition; use aggregate versions when business ordering is needed.
- **Reliability:** timeouts, retries, jitter, deadlines, outbox/inbox, and graceful shutdown.
- **Security:** Managed Identity/workload identity, no hardcoded SAS/connection strings, no logged secrets or sensitive payloads.
- **Observability:** send latency, retries, throttling, consumer lag, ownership, checkpoint age, quarantine, and error callbacks.
- **Testing:** batch overflow, send timeout, duplicates, crash/replay, checkpoint 403, scale-out/in, cross-environment denial.
- **Cost:** tier/capacity, throughput, retention, Blob checkpoint operations, Capture, networking, and monitoring.
- **Runbooks:** owners and steps for producer failure, processor stopped, checkpoint failure, hot partitions, and rising lag.

## 16. Summary

Producers are responsible for creating events with clear contracts, choosing partition keys, sending batches within limits, keeping event IDs stable, and handling timeouts/throttling safely. **EventProcessorClient** is responsible for reading the stream and coordinating partition ownership; the application is responsible for business processing, deduplication, checkpointing after durable side effects, quarantine, and graceful shutdown. The Blob checkpoint store is a separate dependency requiring its own identity, permissions, networking, and monitoring.

When integrating Event Hubs with Spring Boot, manage clients via lifecycle, use Managed Identity and least-privilege RBAC, isolate resources by environment, test failures after send/commit/checkpoint, and monitor lag alongside ownership. This operational discipline prevents producers from generating unexpected load, lets consumers recover safely, and keeps data accurate when processes, networks, or services fail.
