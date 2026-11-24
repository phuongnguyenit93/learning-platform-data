# Containers for Dynamic Tenants or Topics

## 1. When Should You Create Listener Containers Dynamically?

In Spring Kafka, listeners are usually declared statically with `@KafkaListener`. When the application starts, Spring creates a listener container corresponding to the annotation and manages the container lifecycle. This works well when the list of topics and consumer groups is known in advance.

Some systems have a list of tenants or topics that changes while the application is running. For example:

- A SaaS platform creates a dedicated topic for each large tenant.
- Tenants are activated or deactivated via administrative configuration.
- A service needs to start reading a new topic after a customer subscribes.
- An integration application receives its topic list from a managed control plane.
- Per-tenant topics are provisioned along contract lifecycles.

In such cases, the application can create, start, stop, and remove listener containers at runtime. Spring Kafka supports creating containers from `ConcurrentKafkaListenerContainerFactory` or registering listener endpoints with `KafkaListenerEndpointRegistry`.

A dynamic container is a background resource: it creates consumers, joins a consumer group, polls the broker, and invokes the listener. Therefore, container creation must be tied to a clear lifecycle policy. Do not create a new container per HTTP request or per Kafka record.

## 2. Distinguishing Dynamic Containers, Dynamic Topics, and Dynamic Tenants

These three concepts are related but not synonymous:

| Concept | What Changes Dynamically? | Example |
|---|---|---|
| Dynamic topic | Topic name or list of topics changes at runtime | `tenant-acme.orders` |
| Dynamic tenant | Tenants are activated, paused, or deactivated | `acme`, `globex` |
| Dynamic listener container | Consumer containers are created/stopped per runtime config | Dedicated container reading `acme`'s topic |

A tenant does not necessarily require its own container. If all tenants write to the shared `orders` topic and payloads carry `tenantId`, usually a single listener container reading the shared topic and routing business logic by tenant is enough. Creating one container per tenant in that setup would cause every container to read the same topic if each uses a separate group, resulting in each record being consumed multiple times.

Create a separate container only when the topology requires an independent consumer group, subscription, concurrency, access control, or lifecycle for that tenant/topic.

## 3. Choosing the Right Topology

There are three common design patterns.

### One Shared Topic for Multiple Tenants

All tenants write to a single topic, such as `orders`. Records carry `tenantId` in the payload or headers; the key can be `tenantId` or `orderId` depending on partition ordering requirements.

~~~mermaid
flowchart LR
    A["Tenant A"] --> T["Topic orders"]
    B["Tenant B"] --> T
    C["Tenant C"] --> T
    T --> L["One listener container / consumer group"]
    L --> R["Business routing by tenantId"]
~~~

The advantages are fewer topics, fewer containers, and easy partition scaling. Access permissions must be checked at the application layer since topic ACLs do not isolate individual tenants sharing a topic.

### One Topic per Tenant, Shared Container

One container can subscribe to multiple topics or subscribe via a pattern. This is useful when all topics share the same schema, processing policies, and access permissions.

~~~mermaid
flowchart LR
    A["tenant-acme.orders"] --> L["One listener container"]
    B["tenant-globex.orders"] --> L
    C["tenant-initech.orders"] --> L
    L --> R["Process event"]
~~~

Using a single container reduces consumer group and thread counts. However, concurrency and errors from one listener can affect other tenants sharing that container.

### One Container per Tenant or Topic Group

Each container has its own subscription and group ID. This is the choice when you need isolated lifecycles, concurrency, retries, DLTs, or operational permissions.

~~~mermaid
flowchart TD
    A["Tenant A topic"] --> CA["Container A / Group A"]
    B["Tenant B topic"] --> CB["Container B / Group B"]
    C["Tenant C topic"] --> CC["Container C / Group C"]
~~~

In return, consumer counts, connections, threads, group metadata, and monitoring overhead grow with the number of containers. With thousands of small tenants, one container per tenant is rarely economical.

## 4. Creating Containers Directly from a Factory

`ConcurrentKafkaListenerContainerFactory` can create a container from a topic name at runtime. After creation, the application configures the group ID, listener, and concurrency, then calls `start()`.

Example listener processing records of type `OrderCreatedEvent`:

~~~java
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListener;

public class TenantContainerManager {

    private final ConcurrentKafkaListenerContainerFactory<
        String, OrderCreatedEvent> containerFactory;

    public TenantContainerManager(
            ConcurrentKafkaListenerContainerFactory<
                String, OrderCreatedEvent> containerFactory) {
        this.containerFactory = containerFactory;
    }

    public ConcurrentMessageListenerContainer<
            String, OrderCreatedEvent> create(
                    String topic,
                    String groupId,
                    int concurrency) {

        var container = containerFactory.createContainer(topic);

        container.getContainerProperties().setGroupId(groupId);
        container.setConcurrency(concurrency);

        container.setupMessageListener(
            (MessageListener<String, OrderCreatedEvent>) record -> {
                OrderCreatedEvent event = record.value();
                process(event);
            }
        );

        return container;
    }

    private void process(OrderCreatedEvent event) {
        // Invoke business service.
    }
}
~~~

`createContainer(topic)` creates a stopped container. `setupMessageListener()` attaches the record listener. `setGroupId()` sets the group ID on the container properties; this value overrides the default group ID in the consumer factory. `setConcurrency()` sets the number of child consumers managed by the concurrent container.

The method above only creates and configures the container. The caller must manage its lifecycle and call `start()` after registering the container in the application's management registry.

The factory should be pre-configured with the consumer factory, deserializers, error handler, converter, and shared settings. Dynamically created containers inherit those settings. If a tenant needs different security or deserializer configuration, do not mutate a shared factory while containers are running; create a separate factory with explicit configuration.

## 5. Managing Lifecycle with an Application Registry

When creating containers manually, the application must keep references to prevent duplicates and stop containers at the right time. A simple registry can use a map keyed by tenant key.

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.annotation.PreDestroy;

import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class TenantContainerRegistry {

    private final ConcurrentKafkaListenerContainerFactory<
        String, OrderCreatedEvent> factory;

    private final TenantOrderService tenantOrderService;

    private final Map<String,
        ConcurrentMessageListenerContainer<String, OrderCreatedEvent>>
            containers = new ConcurrentHashMap<>();

    public TenantContainerRegistry(
            ConcurrentKafkaListenerContainerFactory<
                String, OrderCreatedEvent> factory,
            TenantOrderService tenantOrderService) {
        this.factory = factory;
        this.tenantOrderService = tenantOrderService;
    }

    public synchronized void startTenant(
            String tenantKey,
            String topic,
            String groupId) {

        if (containers.containsKey(tenantKey)) {
            return;
        }

        var container = factory.createContainer(topic);
        container.getContainerProperties().setGroupId(groupId);
        container.setConcurrency(2);

        container.setupMessageListener(
            (MessageListener<String, OrderCreatedEvent>) record -> {
                var event = record.value();

                if (!tenantKey.equals(event.tenantKey())) {
                    throw new IllegalArgumentException(
                        "Record does not belong to the container's tenant"
                    );
                }

                tenantOrderService.process(tenantKey, event);
            }
        );

        containers.put(tenantKey, container);

        try {
            container.start();
        } catch (RuntimeException ex) {
            containers.remove(tenantKey, container);
            container.stop();
            throw ex;
        }
    }

    public synchronized void stopTenant(String tenantKey) {
        var container = containers.remove(tenantKey);
        if (container != null) {
            container.stop();
        }
    }

    public boolean isRunning(String tenantKey) {
        var container = containers.get(tenantKey);
        return container != null && container.isRunning();
    }

    @PreDestroy
    public synchronized void stopAll() {
        containers.values().forEach(
            ConcurrentMessageListenerContainer::stop
        );
        containers.clear();
    }
}
~~~

This example uses `synchronized` to illustrate that check, registration, and start/stop operations must be coordinated atomically. In systems with concurrent administrative operations, this can be replaced with per-tenant locks or a state machine with `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, and `FAILED` states.

`synchronized` only coordinates threads within the same JVM. If the application runs multiple replicas, each replica has its own registry. When replicas must jointly maintain a container for a tenant, use the same group ID so Kafka divides partitions across members. If only one replica may own a container, distributed coordination or a lease in the control plane is required; an in-memory lock does not stop other replicas from creating containers.

`tenantKey` in the example is a validated and normalized internal key, not an arbitrary string sent directly by a client. `topic` and `groupId` must come from trusted tenant configuration. Never allow an HTTP request to pass an arbitrary topic name and ask the application to subscribe.

If `startTenant()` is called again for the same tenant when the topic/group has changed, this simple example ignores the subsequent call. In a real application, the registry should compare the running configuration and execute a controlled replacement workflow when subscriptions must change.

## 6. Safely Stopping and Replacing Containers

When a tenant is paused or a topic is no longer used, stop the container to release consumers and threads.

`container.stop()` requests the container to stop; Spring Kafka closes the consumer and leaves the group. You can use a stop callback if you need to know exactly when stopping finishes before cleaning up related resources.

`start()` starts the container lifecycle, yet it does not mean the consumer has already connected to the broker, received partition assignments, or begun processing records. Likewise, `isRunning()` reflects lifecycle state rather than business readiness. If the control plane should mark a tenant `RUNNING` only after the consumer actually receives partitions, observe container/consumer lifecycle events or use a `ConsumerRebalanceListener` to confirm assignment. Broker connection errors may be retried by the Kafka client after `start()` returns, so a `try/catch` around `start()` only catches synchronous startup errors.

A container replacement workflow can include:

1. Marking the tenant as `STOPPING` to reject duplicate start requests.
2. Calling stop and waiting for the container to finish shutting down.
3. Removing the old container from the registry.
4. Updating the subscription or group ID per approved configuration.
5. Creating, registering, and starting the new container.
6. Transitioning the tenant to `RUNNING` once the container starts successfully.

In production deployments, distinguish `STARTED` from `READY`: a started container may not have been assigned partitions yet. Only publish the ready status once the operational conditions required by the application are confirmed.

Do not change the topic/group ID of a running container by modifying the consumer factory. Consumer subscriptions are established when the consumer initializes; changing them requires stopping and creating a new container or using the appropriate subscription management API.

When the application shuts down, stop all dynamic containers. If references to containers are not retained or lifecycle is not managed, consumers may linger until the process exits, complicating rebalance control and shutdown logs.

## 7. Using KafkaListenerEndpointRegistry for Dynamic Endpoints

If you want dynamic listeners managed through Spring Kafka's endpoint model, you can register a `KafkaListenerEndpoint` with `KafkaListenerEndpointRegistry`. This is helpful when the application needs to manage listeners by ID and reuse the registry's lifecycle mechanism.

The application must enable Spring Kafka's listener infrastructure, typically via `@EnableKafka` or the corresponding Spring Boot auto-configuration, so the registry and container factory are created in the application context.

Simple endpoint example:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.config.SimpleKafkaListenerEndpoint;
import org.springframework.kafka.listener.MessageListener;

public void registerTenantEndpoint(
        String listenerId,
        String topic,
        String groupId,
        KafkaListenerEndpointRegistry registry,
        ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            factory) {

    var endpoint = new SimpleKafkaListenerEndpoint<
        String, OrderCreatedEvent>();

    endpoint.setId(listenerId);
    endpoint.setGroupId(groupId);
    endpoint.setTopics(topic);

    endpoint.setMessageListener(
        (MessageListener<String, OrderCreatedEvent>) record ->
            process(record.value())
    );

    registry.registerListenerContainer(endpoint, factory, true);
}
~~~

`listenerId` must be unique within the registry. An endpoint registered with `startImmediately=true` starts immediately if the registry is ready. If registered before the context starts, the registry's lifecycle starts the container as configured.

The registry can look up containers by ID to inspect or stop them. When removing dynamic endpoints, use the unregister API if supported by your Spring Kafka version; otherwise, stop the container and manage endpoint release through the application lifecycle. Check the exact API of your dependency version because endpoint management methods can differ across major/minor releases.

Do not register the same listener ID multiple times. Check the ID in the registry first and synchronize register/unregister operations when concurrent administrative requests arrive.

## 8. Subscribing by Topic List or Pattern

Creating a separate container for each topic is not always necessary. One container can subscribe to a list of topics or a topic-name pattern.

### Subscribing to a List of Topics

Use this when the list of topics is already configured at container creation time:

~~~java
var container = factory.createContainer(
    "tenant-acme.orders",
    "tenant-globex.orders",
    "tenant-initech.orders"
);
~~~

Topics in the list are processed by the same listener container and consumer group. This is a compact option if schemas, permissions, error handling, and business logic are uniform.

### Subscribing by Regex Pattern

When topics are created dynamically following a naming convention, you can use pattern subscription instead of continually updating a topic list:

~~~java
import java.util.regex.Pattern;

var pattern = Pattern.compile(
    "^tenant-[a-z0-9-]+-orders$"
);

var container = factory.createContainer(pattern);
container.getContainerProperties().setGroupId("tenant-orders-discovery");
container.setupMessageListener(
    (MessageListener<String, OrderCreatedEvent>) record ->
        process(record.value())
);
container.start();
~~~

Pattern subscription allows the Kafka consumer to discover new matching topics via metadata refresh. It neither creates topics nor guarantees that a new tenant has been granted permissions. The regex must be tight enough to subscribe only to the application's namespace.

A single pattern-subscribing container fits when topics share the same contract and policies. If each tenant needs its own group ID, concurrency, credentials, or DLT, consider separate containers or grouping workloads by tenant tier.

## 9. Tenants Sharing a Topic: Application-Layer Routing

If multiple tenants write to the `orders` topic, it is usually best to use one consumer group and route by tenant ID in the payload:

~~~java
public record OrderCreatedEvent(
    String eventId,
    String tenantId,
    String orderId
) {}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection"
)
public void handle(OrderCreatedEvent event) {
    tenantAuthorizationService.requireKnownTenant(event.tenantId());

    tenantOrderService.process(
        event.tenantId(),
        event
    );
}
~~~

In this model, the consumer reads each record once within the group and dispatches it to the tenant-handling service. Do not create a separate container/group per tenant on the same topic unless there is a clear reason: each independent group receives all records from the topic and could duplicate work across all tenants.

The Kafka key can use `tenantId` so records for the same tenant land in the same partition under the default partitioner. However, that is not a security mechanism and does not guarantee a tenant can only read its own partition. Consumer groups still receive partitions according to Kafka's assignment.

If strict data isolation is required, use appropriate topics/clusters/credentials/ACLs and enforce authorization at the business layer. Do not treat the tenant ID inside a payload as proof of tenant identity.

## 10. Tenants with Dedicated Topics: Routing and Group IDs

With dedicated topics, a naming convention might be:

| Tenant Key | Topic | Consumer Group |
|---|---|---|
| `acme` | `tenant-acme.orders` | `orders-projection-acme` |
| `globex` | `tenant-globex.orders` | `orders-projection-globex` |
| `initech` | `tenant-initech.orders` | `orders-projection-initech` |

The same topic can have multiple consumer groups if multiple services need to read independently. Within a consumer group, multiple instances split the topic's partitions. Therefore, the group ID must reflect processing semantics:

- Same application needing scale-out and partition sharing: share one group ID.
- Each subscriber needing an independent copy: use separate group IDs.
- Each tenant with an independent subscription: can use a per-tenant group ID.
- Do not generate a random group ID on each restart if you want to resume from committed offsets.

Generating a new group ID for every registration can make the consumer re-read from `auto.offset.reset` or start from a nonexistent offset. Use stable group IDs per subscriber and tenant, and define a policy to clean up old groups when a tenant is permanently deleted.

## 11. Concurrency and Resource Limits

A container's concurrency determines how many child consumers are created inside a `ConcurrentMessageListenerContainer`. A consumer is assigned partitions solely according to consumer group rules; increasing concurrency beyond the partition count does not increase useful parallelism.

For example, a topic with 4 partitions and container concurrency 8: at most 4 consumers can hold partitions at the same time; the remaining consumers will have no partition assignment.

When creating containers for many tenants, the total consumer count can grow rapidly:

\[
\text{Total consumers} \approx
\sum_{\text{tenant}} \text{container concurrency}
\]

With 300 tenants and concurrency 2 per container, the application can create around 600 consumers. Account for application replicas, consumer connections, threads, heartbeats, memory, and the number of partitions the broker must manage.

Useful strategies:

- Set a cap on total running containers.
- Start containers only for active tenants.
- Consolidate small tenants into shared topics/containers.
- Use low concurrency for low-traffic tenants.
- Use a pool/queue to pace start/stop requests and avoid spawning many consumers simultaneously.
- Monitor consumer count, thread count, rebalances, and lag.
- Stop containers that no longer have valid tenant subscriptions.

Do not choose concurrency based on tenant count. Size it based on partition counts, throughput, latency, and the service's parallel processing capacity.

## 12. Topic Provisioning and Tenant Lifecycle

Creating a container does not mean the topic already exists. Before starting a consumer, the system must verify that the topic is provisioned and configured properly.

A tenant activation flow can include:

1. Checking that the tenant exists and is in an active-eligible state.
2. Generating the topic name from the normalized tenant key via an internal resolver.
3. Checking or creating the topic according to Kafka governance policy.
4. Verifying partitions, replication factor, retention, and ACLs.
5. Creating the container with a stable group ID.
6. Starting the container and waiting for the running state.
7. Recording subscription status in a durable registry or control plane.

When a tenant is deactivated:

1. Transitioning the tenant to stop accepting new events if business rules require it.
2. Stopping the container gracefully.
3. Verifying offsets are committed per `AckMode` and processing policy.
4. Retaining the topic per retention/archival policy.
5. Deleting the topic or group only through a separate administrative workflow, never automatically right as the container stops.

Do not delete a topic merely because a tenant is temporarily suspended. The topic may still hold data needed for replay or auditing. Topic lifecycle and container lifecycle should be managed as separate resources.

## 13. Error Handling, Retries, and DLT for Dynamic Containers

Containers created from a factory can inherit the common error handler, record converter, deserializers, and shared configurations set on the factory. If tenants require different policies, use separate factories or configure container properties appropriately before starting.

With dedicated per-tenant topics, DLTs can follow a convention:

- `tenant-acme.orders.DLT`
- `tenant-globex.orders.DLT`

If the DLT resolver appends a suffix to the source topic, ensure the target topic is created with enough partitions when the resolver preserves the original partition. If using a shared DLT, the original metadata must be sufficient to identify the tenant, topic, and subscriber owning the failed record.

Do not create DLTs per exception or per request. Use stable naming conventions and bound the number of topics. When handling failed records, do not trust a tenant ID in headers to authorize replay; validate the tenant against controlled metadata.

## 14. Security and Tenant Isolation

Dynamic containers expand the configuration surface because topic names, group IDs, and tenants are resolved at runtime.

Principles to apply:

- Create containers only for authenticated tenants in an active state.
- Resolve topics from internal configuration; never accept arbitrary topics from query parameters or message payloads.
- Validate tenant keys and restrict characters/length before using them in topic/group names.
- Grant least-privilege ACLs to the application's principal.
- Do not share credentials broader than the tenant scope if isolation requirements demand that level of protection.
- Do not log sensitive payloads or tenant data.
- Verify that the tenant ID in the payload matches the tenant the subscription is permitted to process.
- Cap container counts to prevent a single tenant from exhausting resources.

Kafka ACLs typically apply at cluster, topic, group, or transactional ID level depending on the authn/authz mechanism. If multiple tenants share one principal that can read all topics, creating separate containers does not itself provide security isolation. Choose credentials and ACLs based on the threat model and cluster manageability.

## 15. Observing and Operating Dynamic Containers

Static containers have annotation-defined IDs and are easy to find in logs. Dynamic containers need stable identifiers for operations.

You should record:

| Metadata | Purpose |
|---|---|
| Listener/container ID | Identify the container |
| Normalized tenant key | Identify the subscription without exposing sensitive data |
| Topic or pattern | Know which source the container is reading |
| Consumer group ID | Cross-reference offsets and assignments |
| Concurrency | Understand child consumer count |
| Lifecycle state | `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED` |
| Start/stop reason | Know who or which workflow changed the subscription |
| Consumer lag | Track ability to keep up with incoming data |
| Retry/DLT count | Spot tenants experiencing elevated record failures |

Metrics should cover active container count, actual consumer count, failed starts/stops, rebalances, lag by group/topic/partition, listener errors, and DLT publish errors.

Do not use a very high-cardinality tenant ID as a metric label if the system has tens of thousands of tenants; time-series counts can explode. Use aggregated metrics alongside correlated logs to investigate specific tenants.

## 16. Testing Dynamic Containers

Tests should not merely assert that a container was constructed. Verify lifecycle, subscriptions, group IDs, and that stopping containers does not lose data.

Key scenarios:

- Start a container with a valid topic and receive records.
- Calling start twice for the same tenant does not unintentionally create two containers.
- Two tenants with separate topics do not cross-process each other's records.
- Containers use stable group IDs across application restarts.
- Stopping a container releases the consumer and stops receiving new records.
- Restarting a container resumes from offsets per the commit policy.
- Missing topics or insufficient ACLs cause observable startup failures.
- Pattern subscriptions discover newly created matching topics.
- Concurrency stays within expected resource bounds.
- Application shutdown stops all dynamic containers.
- Per-tenant DLTs preserve metadata and source topic info.

You can use Embedded Kafka or Testcontainers to create topics and send real records. In tests, wait for container states and listener results using Awaitility or timeout-bounded polling; avoid fixed `Thread.sleep()` for synchronization.

For example, lifecycle unit tests should check registry idempotency: starting a tenant once creates one container; starting a second time creates none; stopping the tenant removes the registration. Integration tests should verify real records flow through the broker and are handled by the right container.

## 17. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| No records received | Container not started or topic does not exist | Check lifecycle, topic metadata, and consumer logs |
| Two containers both process the same record | Different group IDs on the same topic when load-sharing was intended | Share a group ID if instances should divide partitions |
| Tenant receives another tenant's data | Shared topic lacking tenant verification in business logic | Validate tenant ID and enforce authorization |
| Duplicate containers started | Missing registry or non-idempotent start operation | Use a registry and synchronize lifecycle |
| Consumer spawns too many threads | Too many containers/too high concurrency per tenant | Limit containers, consolidate tenants, and tune concurrency |
| Restarted container re-reads records | Uncommitted offsets or changed group ID | Choose appropriate `AckMode`, group ID, and idempotency |
| Dynamic topic not subscribed | Non-matching regex or metadata refresh has not occurred yet | Check pattern, permissions, and metadata |
| DLT publish fails | Target topic missing partitions or wrong ACL/serializer | Provision DLT and test the resolver |
| False tenant isolation | Separate containers sharing a principal allowed to read all topics | Design ACLs/credentials matching the threat model |

## 18. Implementation Checklist

- [ ] Chosen shared topic, pattern-based shared container, or dedicated per-tenant container.
- [ ] Dedicated containers created only when separate subscription, group, lifecycle, or policy is required.
- [ ] Containers created via `ConcurrentKafkaListenerContainerFactory`.
- [ ] Group IDs configured stably and aligned with processing semantics.
- [ ] Listeners attached before calling `start()`.
- [ ] Containers tracked in a registry to prevent duplicates and support stopping.
- [ ] Start/stop/register/unregister operations synchronized.
- [ ] All containers stopped when tenants suspend and on application shutdown.
- [ ] Topics, partitions, replication, retention, and ACLs provisioned before starting.
- [ ] Concurrency and total consumer counts capped.
- [ ] Arbitrary topics never accepted from untrusted tenants or payloads.
- [ ] Tenant ID validated in both payloads and business logic.
- [ ] Retries, error handlers, and DLTs configured per policy.
- [ ] Lifecycle states, consumer lag, rebalances, and DLTs monitored.
- [ ] Start, stop, restart, duplicate registration, and shutdown tested against a real broker.

Dynamic listener containers enable Spring Kafka to adapt to lists of tenants or topics that change at runtime. Choose the topology first, manage containers via a registry with explicit lifecycles, keep group IDs stable, and cap resources. When tenant is just metadata inside a shared topic, a single listener routing by tenant is usually simpler; dedicated containers should only be created when isolation of subscriptions, groups, concurrency, or operational policies is required.
