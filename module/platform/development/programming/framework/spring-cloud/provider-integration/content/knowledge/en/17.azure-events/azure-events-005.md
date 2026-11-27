# Integrating Event Hubs with Spring Integration or the Stream Binder

Spring Boot has multiple ways to connect to Azure Event Hubs. With **Spring Integration**, the application builds message channels, inbound/outbound adapters, gateways, and processing endpoints following Spring's integration model. With **Spring Cloud Stream**, the application declares Supplier, Consumer, or Function beans and binds them to destinations through the **Event Hubs binder**. Both approaches can use the same underlying Azure SDK, yet differ in how flows are structured, configured, checkpointed, and how much direct control the application retains.

This lesson belongs to the **Azure Events** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with AWS, Azure, and Google Cloud managed services through the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. Within this lesson, the focus is on choosing the right abstraction for Event Hubs, configuring producers/consumers, handling checkpoints, partitions, errors, security, and operations.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **Spring Integration channel adapters** and the **Spring Cloud Stream binder** when connecting to Event Hubs.
- Choose the appropriate starter/dependencies and manage versions with the Spring Cloud Azure BOM.
- Send events via an outbound channel adapter/gateway or Stream binding.
- Receive events via `EventHubsInboundChannelAdapter` or a functional Consumer.
- Configure namespace, event hub, consumer group, and Blob checkpoint store.
- Use Microsoft Entra ID, Managed Identity/Workload Identity, and Azure RBAC instead of long-lived secrets whenever possible.
- Choose an appropriate checkpoint mode; confirm progress only after durable business processing.
- Understand partition keys, consumer groups, batch mode, error channels, retries, and idempotency.
- Write isolated integration tests, and monitor consumer lag, checkpoint age, throughput, and send/receive errors.

## 2. Choose the Abstraction Before Writing Code

### 2.1. Spring Integration

Spring Integration provides the **MessageChannel** and endpoint model. Adapters connect an external system with channels inside the application:
- **Outbound channel adapter:** receives messages from a channel and sends them to Event Hubs.
- **Inbound channel adapter:** receives events from Event Hubs and puts them onto a channel.
- **Messaging gateway:** provides a Java interface for business code to send messages into a channel.
- **Service activator/transformer/router/filter:** processes or routes messages across channels.

This approach fits when the application already uses Spring Integration, needs to plug Event Hubs into a multi-step transformation/routing flow, or needs explicit control over the container and checkpointing.

### 2.2. Spring Cloud Stream Binder

Spring Cloud Stream provides a functional model:
- **Supplier:** emits data to a binding.
- **Consumer:** receives data from a binding.
- **Function:** receives, transforms, and emits data.
- **Binding:** connects a function's input/output to a destination such as an Event Hub.
- **Binder:** a specialized adapter connecting Spring Cloud Stream to a broker.

The Event Hubs binder uses Spring Integration's Event Hubs channel adapters under the hood. The application works primarily with functions and binding configuration; the binder manages connections, consumer groups, partition ownership, and checkpointing per configuration.

### 2.3. Quick Comparison

| Criterion | Spring Integration | Spring Cloud Stream Binder |
|---|---|---|
| Programming model | MessageChannel, adapters, gateways, service activators | Supplier, Consumer, Function, and bindings |
| Sending events | Outbound adapter, EventHubsTemplate/MessageHandler, gateway | Output binding from Supplier/Function or sending via binding mechanisms |
| Receiving events | Inbound adapter and listener container | Input binding invoking Consumer/Function |
| Checkpointing | Container properties and Checkpointer in message header when MANUAL | Binder properties and Checkpointer header when MANUAL |
| Processing flow | Explicit; can compose routers/transformers/filters | Centered on functions and destination configuration |
| Abstraction reuse | Good when the app already uses Spring Integration | Good when organizing the app around the Cloud Stream model |
| Granular control | Direct access to channel adapters/container properties | Mostly through binder properties; lower-level APIs may be needed for special cases |
| Initial setup | Requires declaring channels and adapters | Relatively concise binding and function setup |

Neither approach creates business-level exactly-once guarantees automatically. Both rely on Event Hubs, partitions, consumer groups, and checkpoints; duplicates/replays must still be handled at the application layer.

## 3. Dependencies and Version Management

Spring Cloud Azure provides separate starters for the two approaches:

| Need | Suggested Artifact |
|---|---|
| Spring Integration with Event Hubs | `com.azure.spring:spring-cloud-azure-starter-integration-eventhubs` |
| Spring Cloud Stream Event Hubs binder | `com.azure.spring:spring-cloud-azure-starter-stream-eventhubs` |
| Binder module without the umbrella starter | `com.azure.spring:spring-cloud-azure-stream-binder-eventhubs` |

Maven dependency example for Spring Integration:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-integration-eventhubs</artifactId>
</dependency>
~~~

Maven dependency example for the Stream binder:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-stream-eventhubs</artifactId>
</dependency>
~~~

Manage Spring Cloud Azure dependencies using the **Spring Cloud Azure BOM** compatible with your project's Spring Boot and Spring Cloud release train. Do not arbitrarily mix individual starter, binder, Azure SDK, and Spring Integration versions.

APIs and properties have changed across library generations. For example, modern classes use names like `EventHubsInboundChannelAdapter`, `EventHubsMessageListenerContainer`, and `EventHubsTemplate`; older APIs such as `EventHubOperation` or `EventHubInboundChannelAdapter` may appear in legacy docs. Before copying code, check the version mapping and migration guide for the BOM you are using.

## 4. Preparing the Event Hub and Checkpoint Store

Before configuring Spring Boot, pre-create the resources:
- Event Hubs namespace.
- Event hub, e.g. `order-events`.
- A dedicated consumer group per logical application, e.g. `order-projection`.
- Storage account and Blob container for ownership/checkpoints.
- Managed Identity or workload identity for the runtime.
- Role assignments at the right scope.

The checkpoint store holds **partition ownership and checkpoint metadata**, not the entire event stream. Instances in the same consumer group need to share the same logical checkpoint store to coordinate. Never create a random new container on each deploy, or new processors will not find previous progress.

Create namespaces, event hubs, and containers via IaC or a platform process. Never grant broad resource management permissions to the runtime just so the app can auto-create resources at startup.

## 5. Authentication and Authorization

Prefer Microsoft Entra ID:
- Producers need the **Azure Event Hubs Data Sender** role.
- Consumers need the **Azure Event Hubs Data Receiver** role.
- Processors writing checkpoints need **Storage Blob Data Contributor** on the container or appropriate scope.
- Pipelines/IaC use a separate deployment identity with scoped resource management permissions.
- Local developers can use developer credentials, never reusing production principals.

With Managed Identity, configuration depends on the environment:
- System-assigned identity does not need a separate client ID.
- User-assigned identity requires the client ID of the attached identity.
- AKS can use Workload Identity.
- CI/CD can use workload identity federation.

Never commit connection strings, SAS tokens, storage account keys, or client secrets to source control. If a connection string must be used in a lab, place it in a secret store or environment variable and limit permissions/expiration. Namespace management roles do not equal data-plane roles; assign Data Sender/Receiver explicitly.

## 6. Shared Azure Configuration

Example configuration for the dev environment:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # For user-assigned identity, add client-id per environment configuration.
        # client-id: <user-assigned-managed-identity-client-id>
      eventhubs:
        namespace: ${AZURE_EVENTHUBS_NAMESPACE}
        processor:
          checkpoint-store:
            account-name: ${AZURE_CHECKPOINT_STORAGE_ACCOUNT}
            container-name: ${AZURE_CHECKPOINT_CONTAINER}
~~~

These are Spring Cloud Azure properties for credentials, namespace, and checkpoint store. Environment variables must be supplied by the deployment platform. For local development, use an appropriate credential chain rather than assuming Managed Identity is available.

From Spring Cloud Azure 4.x onward, the checkpoint container is not necessarily auto-created. Create the container beforehand with IaC; only enable `create-container-if-not-exists` if you intentionally want the application responsible for creating the container and the identity has the corresponding permissions.

Isolate checkpoint containers per environment and workload. Dev must not use the production checkpoint container; two different consumer groups need independent reading progress.

## 7. Spring Integration: Sending Events via Outbound Channel Adapter

### 7.1. Creating the Output Channel and MessageHandler

Spring Integration uses a channel as the entry point for the send flow. `EventHubsTemplate` provides sending capability, while `DefaultMessageHandler` binds the template to an event hub name.

~~~java
import com.azure.spring.integration.core.handler.DefaultMessageHandler;
import com.azure.spring.messaging.eventhubs.core.EventHubsTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
class EventHubOutboundConfiguration {

    @Bean
    MessageChannel eventHubOutput() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "eventHubOutput")
    MessageHandler eventHubMessageSender(EventHubsTemplate template) {
        return new DefaultMessageHandler("order-events", template);
    }
}
~~~

This is an illustrative configuration using modern Spring Integration Azure APIs; verify exact packages/classes against your BOM. Namespace and credentials are configured via Spring Cloud Azure. The producer runtime needs Event Hubs Data Sender.

### 7.2. Sending via a Messaging Gateway

A gateway keeps business code decoupled from `EventHubsTemplate` or channel implementations:

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.Message;

@MessagingGateway(defaultRequestChannel = "eventHubOutput")
interface OrderEventGateway {
    void send(Message<?> event);
}
~~~

Using the gateway in a service:

~~~java
import com.azure.spring.messaging.AzureHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final OrderEventGateway gateway;

    OrderPublisher(OrderEventGateway gateway) {
        this.gateway = gateway;
    }

    void publish(String orderId, String jsonPayload) {
        gateway.send(MessageBuilder.withPayload(jsonPayload)
                .setHeader(AzureHeaders.PARTITION_KEY, orderId)
                .setHeader("eventId", "order-" + orderId + "-created")
                .build());
    }
}
~~~

The partition key header is mapped to Event Hubs routing metadata; application headers are forwarded as application properties as supported by the adapter. Do not manually set system headers such as offset, sequence number, or enqueued time. Event IDs must remain stable across retries; the example above is illustrative, and real systems should generate unique business IDs.

### 7.3. Monitoring Send Failures

Asynchronous sending means errors can surface after the gateway method returns, depending on the configured handler and callbacks. You need observability for send failures and must not treat putting a message onto a channel as proof Event Hubs received the event.

For timeout failures, the send outcome may be indeterminate: the service may have received the event while the response was lost. Keep the same event ID across retries and make consumers idempotent. If database commits and publishing must stay consistent, use a transactional outbox.

## 8. Spring Integration: Receiving Events via Inbound Channel Adapter

### 8.1. Creating a Listener Container with MANUAL Checkpointing

`EventHubsInboundChannelAdapter` receives events from a listener container and pushes messages into a Spring channel. The container uses `EventProcessorClient` underneath and needs a consumer group and checkpoint store.

~~~java
import com.azure.spring.messaging.eventhubs.core.EventHubsProcessorFactory;
import com.azure.spring.messaging.eventhubs.core.checkpoint.CheckpointConfig;
import com.azure.spring.messaging.eventhubs.core.checkpoint.CheckpointMode;
import com.azure.spring.messaging.eventhubs.core.listener.EventHubsMessageListenerContainer;
import com.azure.spring.messaging.eventhubs.core.properties.EventHubsContainerProperties;
import com.azure.spring.integration.eventhubs.inbound.EventHubsInboundChannelAdapter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
class EventHubInboundConfiguration {

    @Bean
    MessageChannel eventHubInput() {
        return new DirectChannel();
    }

    @Bean
    EventHubsMessageListenerContainer eventHubsListenerContainer(
            EventHubsProcessorFactory processorFactory) {
        EventHubsContainerProperties properties =
                new EventHubsContainerProperties();
        properties.setEventHubName("order-events");
        properties.setConsumerGroup("order-projection");
        properties.setCheckpointConfig(
                new CheckpointConfig(CheckpointMode.MANUAL));

        return new EventHubsMessageListenerContainer(
                processorFactory, properties);
    }

    @Bean
    EventHubsInboundChannelAdapter eventHubsInboundAdapter(
            @Qualifier("eventHubInput") MessageChannel input,
            EventHubsMessageListenerContainer listenerContainer) {
        EventHubsInboundChannelAdapter adapter =
                new EventHubsInboundChannelAdapter(listenerContainer);
        adapter.setOutputChannel(input);
        return adapter;
    }
}
~~~

The imports illustrate the relevant APIs; verify exact packages and constructors against your dependency version. Never create a separate listener container per request. The container must follow the application lifecycle and share the same consumer group/checkpoint store with other replicas of the same workload.

### 8.2. Process First, Then Checkpoint

In MANUAL mode, messages carry the `AzureHeaders.CHECKPOINTER` header. The handler only calls success after business processing has durably committed:

~~~java
import com.azure.spring.messaging.AzureHeaders;
import com.azure.spring.messaging.checkpoint.Checkpointer;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
class OrderEventHandler {
    private final OrderService orderService;

    OrderEventHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    @ServiceActivator(inputChannel = "eventHubInput")
    public void receive(
            byte[] payload,
            @Header(AzureHeaders.CHECKPOINTER) Checkpointer checkpointer) {

        // The service transaction completes and commits before the method returns.
        orderService.processAndCommit(payload);

        // Only checkpoint after side effects are durable.
        checkpointer.success().block();
    }
}
~~~

`processAndCommit` should live on a separate transactional service bean; when the call through the Spring proxy returns, the transaction has committed. If you place `@Transactional` directly on `receive` and checkpoint inside that same method, checkpointing can run before the transaction commits because the transaction interceptor only commits after the method returns.

If the handler throws an exception, do not checkpoint that event. If the DB commit succeeds yet checkpointing fails, the event may be re-read; use an inbox/unique event ID to avoid repeated side effects. In reactive flows, compose the `Mono` instead of blocking on the event loop.

### 8.3. Batch Mode

The inbound adapter supports batch listeners. When `ListenerMode.BATCH` is enabled, the payload is a list of events and certain headers also become lists. Configure batch size and wait time on container properties. `BATCH` checkpoint mode only fits batch-consuming mode; `MANUAL` lets the application decide when a batch has been durably processed.

With batching, clearly decide:
- If one event in the batch fails, is checkpointing the entire batch safe?
- Do failed events need to be saved individually to quarantine before checkpointing the batch?
- Can you process in parallel while still maintaining a contiguous completion watermark?
- How do batch size and wait time affect latency, memory, and the replay window?

Do not checkpoint an entire batch merely because the batch was received. For database side effects, commit required data first and only then checkpoint.

## 9. Spring Cloud Stream: Configuring the Event Hubs Binder

### 9.1. Dependencies and Bindings

Use `spring-cloud-azure-starter-stream-eventhubs` or the binder module `spring-cloud-azure-stream-binder-eventhubs`. The binder connects function inputs/outputs to Event Hub destinations.

Example configuration for a consumer and producer on the same event hub:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
      eventhubs:
        namespace: ${AZURE_EVENTHUBS_NAMESPACE}
        processor:
          checkpoint-store:
            account-name: ${AZURE_CHECKPOINT_STORAGE_ACCOUNT}
            container-name: ${AZURE_CHECKPOINT_CONTAINER}
    stream:
      function:
        definition: consume;supply
      bindings:
        consume-in-0:
          destination: ${AZURE_EVENTHUB_NAME}
          group: ${AZURE_EVENTHUB_CONSUMER_GROUP}
        supply-out-0:
          destination: ${AZURE_EVENTHUB_NAME}
      eventhubs:
        bindings:
          consume-in-0:
            consumer:
              checkpoint:
                mode: MANUAL
~~~

Binding names `consume-in-0` and `supply-out-0` derive from function names and input/output direction. `destination` is the Event Hub name; `group` is the consumer group. Environment values are injected from deployment config—never write connection strings or account keys into files.

### 9.2. Functional Consumer with Manual Checkpointing

~~~java
import com.azure.spring.messaging.AzureHeaders;
import com.azure.spring.messaging.checkpoint.Checkpointer;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import java.util.function.Consumer;

@Component
class OrderFunctions {
    private final OrderService orderService;

    OrderFunctions(OrderService orderService) {
        this.orderService = orderService;
    }

    @Bean
    Consumer<Message<String>> consume() {
        return message -> {
            orderService.processAndCommit(message.getPayload());

            Checkpointer checkpointer = message.getHeaders()
                    .get(AzureHeaders.CHECKPOINTER, Checkpointer.class);
            if (checkpointer == null) {
                throw new IllegalStateException(
                        "Manual checkpoint header is missing");
            }
            checkpointer.success().block();
        };
    }
}
~~~

When checkpoint mode is `MANUAL`, the binder puts `Checkpointer` into message headers. The handler must call success after successful processing. Never swallow exceptions and never checkpoint before the transaction commits. With automatic modes, the binder decides checkpoints per configuration; understand the exact semantics before choosing them.

### 9.3. Functional Supplier for Publishing Events

A Supplier is polled on a schedule by the binder. Simple example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;

@Bean
Supplier<Message<String>> supply() {
    AtomicLong sequence = new AtomicLong();
    return () -> {
        String payload = """
                {"eventId":"demo-%d","eventType":"TelemetryReceived"}
                """.formatted(sequence.incrementAndGet());
        return MessageBuilder.withPayload(payload).build();
    };
}
~~~

A Supplier fits periodic data or demos. For events emitted in response to business requests, choose a binding/StreamBridge sending approach compatible with your Spring Cloud Stream version so you do not accidentally turn a poller into an unintended continuous emitter. In either case, events must have stable IDs and explicit schemas.

## 10. Checkpoint Modes and Batching in the Stream Binder

The binder supports per-binding checkpoint settings, depending on version:
- `RECORD`: checkpoint after each record when supported.
- `MANUAL`: application calls `Checkpointer` from headers after durable processing.
- `BATCH`: checkpoint per batch when using a batch consumer.
- `PARTITION_COUNT`: checkpoint after a configured number of events per partition.
- `TIME`: checkpoint on a configured time interval.

Exact mode names and properties must be verified against your BOM/binder version. Count and interval properties only take effect with their matching modes.

With `BATCH`, the binder automatically checkpoints a batch after receiving it per binder semantics; that does not prove business database transactions committed. If you need checkpoints tied to durable side effects, prefer `MANUAL` and call `Checkpointer` after the service transaction completes.

Batch consumer example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consume-in-0:
          consumer:
            batch-mode: true
      eventhubs:
        bindings:
          consume-in-0:
            consumer:
              batch:
                max-size: 100
                max-wait-time: 2s
              checkpoint:
                mode: MANUAL
~~~

When batch mode is enabled, the function receives `Message<List<T>>`; headers such as partition key, offset, sequence number, and enqueued time may be lists corresponding to each event. Batch-wide partition/checkpointer headers follow batch semantics. Do not cast a record consumer's headers as a list consumer's headers or vice versa.

The binder uses content-type negotiation by default. With a `String` payload and `application/json` content type, the content must be a valid JSON string for the converter; if plain text is needed, configure an appropriate content type such as `text/plain`. Verify serialization with contract tests instead of relying only on logged payloads.

## 11. Partition Keys, Consumer Groups, and Scaling

### 11.1. Partition Keys

Choose a partition key by the entity needing ordering, such as order ID or device ID. In Spring Integration, pass the partition key via an adapter-supported message header like `AzureHeaders.PARTITION_KEY`. With the Stream binder, use partitioning information/partition supplier mechanisms and partitioning properties supported by your binder version.

Do not confuse:
- Partition key: routing key for events to partitions.
- Partition ID: a specific partition.
- Consumer group: an independent reading cursor.
- Consumer instance: a process/pod processing partitions.

A hot key can make one partition lag while other partitions sit idle. There is no global order across partitions; if business ordering is required, include an aggregate version and validate it on the consumer.

### 11.2. Consumer Groups

Each logical application should have its own consumer group, e.g. `order-projection`, `analytics`, `fraud-detection`. Replicas of the same logical application share one group to split partitions. Do not create a new group per pod if your intent is load sharing; doing so makes each pod read an independent copy of the stream.

### 11.3. Checkpoint Store and Ownership

Both abstractions rely on Blob Storage for checkpoints/partition ownership. Spring Integration configures the checkpoint store via Spring Cloud Azure Event Hubs properties; the Stream binder uses the same checkpoint store properties group. Replicas of the same consumer group must share the same logical storage container. If Blob returns 403 or is unreachable, processors cannot persist progress or balance ownership.

Adding pods does not guarantee linear throughput gains; partition count bounds parallelism. Check consumer lag, ownership rebalancing, DB pools, and Blob latency before scaling.

## 12. Error Handling, Retries, and Idempotency

### 12.1. Spring Integration Error Channels

Spring Integration has a global error channel and per-endpoint/adapter error channels depending on configuration. Register handlers to record exceptions, correlation IDs, and sanitized context; never just log and drop. When a business handler fails, do not checkpoint the event.

### 12.2. Stream Binder Error Channels

The binder has per-destination/group consumer error channels. Producer error channels may require enabling `spring.cloud.stream.default.producer.errorChannelEnabled=true` before registering a handler. Check actual binding names to target the right channel; do not assume producer and consumer errors arrive on the same channel.

### 12.3. Retries and Non-Retryable Errors

Retries are only for transient failures like throttling or network blips, with bounds, backoff, jitter, and deadlines. 401/403, wrong namespace/event hub, invalid payloads, and schema errors require fixing configuration or data; infinite retries only amplify load.

The SDK/binder has its own retry policies. Before adding service-layer retries, calculate total attempts to avoid nested retry loops. Send timeouts can leave indeterminate results; keep the same event ID across retries.

### 12.4. Idempotency

Event Hubs is a stream capable of replaying from the latest checkpoint. Handlers must be idempotent:
- Use a stable event ID from the producer.
- Write the event ID to an inbox/processed-event table with a unique constraint.
- Write the dedup record and business changes in the same database transaction.
- If the event was already processed, do not repeat side effects.
- If the same ID arrives with a different payload, record a conflict for investigation.

Do not rely on offsets as business IDs. Offsets belong to partitions and consumer groups; replays or other workloads may read events in different contexts.

## 13. Transactional Outbox When Publishing from Spring Boot

If an API updates a database and then sends to Event Hubs, the two operations are not in a single atomic transaction by default. A DB commit can succeed while publishing fails, or publishing can succeed while the response is lost.

A transactional outbox closes the gap between DB commits and publishing:
1. Write business changes and the outbox event in the same transaction.
2. A worker reads the outbox and sends events through the gateway/binding.
3. Mark the outbox entry as sent after receiving confirmation.
4. If the worker crashes after sending but before marking, the event may be resent; consumers deduplicate by event ID.

~~~mermaid
flowchart TD
    API["Spring Boot API"] --> TX["Database transaction"]
    TX --> O["Update order"]
    TX --> OB["Insert outbox event"]
    OB --> W["Outbox publisher"]
    W --> EH["Event Hubs"]
    EH --> C["Idempotent consumer"]
    W -. "Send timeout / retry" .-> OB
~~~

An outbox does not create exactly-once across the database and Event Hubs; it guarantees events are not forgotten after commit while consumers handle duplicates safely.

## 14. Observability and Operations

Monitor metrics per binding, consumer group, and partition:
- Producer send successes/failures, send latency, retry counts, and throttling.
- Incoming/outgoing messages/bytes, consumer lag, and age of unprocessed events.
- Partition ownership/rebalances and active processor instance count.
- Checkpoint age, checkpoint failures, and Blob latency.
- Handler processing duration, duplicates suppressed, and quarantine counts.
- Batch size, batch wait time, prefetch, and in-flight events.
- CPU, memory, thread pools, DB connection pools, and networking.
- Costs for Event Hubs tier/capacity, Blob checkpoint operations, retention, Capture, and monitoring.

Logs should include sanitized event ID, correlation ID, consumer group, partition ID, sequence number, and offset; never log access tokens, SAS tokens, connection strings, or sensitive raw payloads.

Set alerts when checkpoints stop advancing, consumer lag rises, processors own zero partitions, the Blob checkpoint store returns 403/timeouts, or throttling spikes. Every alert needs a runbook to verify identity, resources, Region, and networking.

## 15. Integration Testing

Use dedicated test namespaces, event hubs, consumer groups, and checkpoint containers. Never reset production checkpoints or share a consumer group with live workloads.

| Scenario | Spring Integration | Stream Binder | Expected Result |
|---|---|---|---|
| Send event | Gateway/outbound adapter | Supplier/output binding | Event arrives in the target Event Hub |
| Receive event | Inbound adapter/channel | Consumer input binding | Handler receives expected payload and headers |
| Manual checkpoint | Checkpointer header | Checkpointer header | Checkpoints only after commit |
| Duplicate/replay | Resend same event ID or restart | Resend same event ID or restart | No repeated side effects |
| Checkpoint Blob 403 | Use identity lacking role | Use identity lacking role | Errors observed; progress not marked successful |
| Throttling/timeout | Simulate adapter/SDK failure | Simulate binder/SDK failure | Bounded retries, no retry storms |
| Batch | ListenerMode.BATCH | batch-mode=true | Batch and headers have expected types |
| Scale-out | Multiple containers in same group | Multiple instances in same binding/group | Partition ownership distributed |
| Cross-environment | Dev identity accesses prod resource | Dev identity accesses prod resource | Denied by RBAC/network |
| Shutdown | Controlled container stop | Controlled application stop | Uncheckpointed events can replay safely |

Unit tests verify serializers, event contracts, partition keys, and business idempotency. Only cloud integration tests verify Managed Identity, RBAC, private endpoints, checkpoint stores, and real processor ownership.

## 16. Common Errors

| Error | Possible Cause | Resolution |
|---|---|---|
| Producer 401/403 | Missing Data Sender or wrong principal | Verify runtime identity and role scope |
| Consumer receives no events | Wrong event hub/group/initial position or missing Data Receiver | Check binding destination, group, and permissions |
| Processor does not checkpoint | Wrong Blob container, missing Blob Data Contributor, or network failure | Check checkpoint store and endpoint |
| Event processed repeatedly | Crash after DB commit before checkpoint | Inbox/dedup in the same transaction |
| Batch skipped after error | Choosing `BATCH` checkpoint too early relative to business commits | Use `MANUAL` and checkpoint after processing |
| Lag stays high after adding replicas | Limited by partition count or downstream | Measure lag per partition, DB, and handler |
| Producer errors unseen | Producer error channel disabled or unhandled callback | Configure error channel/callback |
| Dev profile reads production | Misconfigured endpoint/credential | Isolate identities/resources and add startup guards |
| String payload parse error | Content type and serializer mismatch | Verify content-type/JSON contract |

## 17. Which Integration Approach Should You Choose?

Choose **Spring Integration** when:
- The application already has multiple MessageChannels and flows.
- You need routers, filters, transformers, gateways, or custom adapters.
- You want direct control over the listener container, batch mode, and Checkpointer.
- The integration flow is more complex than an input/output function.

Choose the **Spring Cloud Stream binder** when:
- The application is organized around Supplier/Consumer/Function.
- You want to declare destinations and consumer groups using binding properties.
- You need a uniform function/pub-sub model across multiple binders.
- The processing flow can be expressed cleanly with functions and error channels.

Do not use both abstractions to accidentally create two consumers reading the same event hub/group. If combining them in one application, clearly separate consumer groups, checkpoint stores, and flow responsibilities. If you need highly specific Event Hubs APIs not exposed by either abstraction, consider using the Azure SDK directly for that piece instead of forcing an abstraction.

## 18. Pre-Production Checklist

- **Versions:** Spring Cloud Azure BOM compatible with Spring Boot/Cloud; no legacy APIs used.
- **Resources:** Namespace, event hub, consumer group, and checkpoint container match the environment.
- **Identity:** Producer has Data Sender, consumer has Data Receiver, checkpoint has Blob Data Contributor at least-privilege scope.
- **Configuration:** Namespace, destination, group, checkpoint store, Region, and endpoints managed through deployment config.
- **Producer:** Stable event ID, schema version, partition key, send errors, and timeouts handled.
- **Consumer:** Idempotent handler, MANUAL checkpoint after commit or evaluated automatic mode.
- **Batch:** Listener/binder batch mode, payload types, and checkpoint semantics align.
- **Reliability:** Bounded retries, backoff/jitter, outbox/inbox, poison events, and graceful shutdown.
- **Observability:** Send latency, throttling, consumer lag, checkpoint age, ownership, and error channels have metrics/alerts.
- **Testing:** Duplicates, replays, checkpoint failures, RBAC denials, batching, scale-out, and cross-environment tests.
- **Cost:** Event Hubs capacity/tier, retention, Blob checkpoint operations, networking, and monitoring budgeted.
- **Runbooks:** Procedures for 401/403, timeouts, lag, checkpoint failures, and replays.

## 19. Summary

**Spring Integration** connects Event Hubs to message channels using outbound/inbound adapters, gateways, and listener containers. The **Spring Cloud Stream binder** connects Supplier/Consumer/Function beans to an Event Hub through bindings and destination/group configuration. The binder builds on channel adapters under the hood while offering a different functional programming and configuration model.

Regardless of which abstraction you choose, the application must still manage consumer groups, partitions, the Blob checkpoint store, Managed Identity/RBAC, event schemas, retries, and idempotency. The key rule is **perform durable business processing first, then checkpoint**. Testing crashes/replays, checkpoint failures, batching, and access controls on dedicated resources will keep your Spring Boot Event Hubs integration scalable and resilient.

## References

- Spring Cloud Azure Developer Guide: https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview
- Spring Integration support for Azure Event Hubs: https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html
- Spring Cloud Stream support for Azure Event Hubs: https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/spring-cloud-stream-support
- Spring Cloud Stream binding properties: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html
