# Risks of Uncontrolled Container Creation

Spring Kafka allows creating listener containers while an application is running. This capability is useful when a system needs to toggle subscriptions per tenant, topics are configured dynamically, or an operational task requires a dedicated listener. However, each running container typically owns one or more Kafka consumers, threads, network connections, and consumer group state. Creating containers per request, per message, or from an unbounded data source can multiply consumers faster than the application and Kafka cluster can manage.

The risk is not merely memory consumption. Containers that introduce additional consumer groups or members can overload the group coordinator, trigger frequent rebalances, increase broker connections, complicate offset management, and prevent clean resource release during shutdown or redeploy. An improperly stopped container can keep polling even after a tenant is deleted; a duplicate container can accidentally process the same topic twice.

The core principle is that every container must have a clear reason to exist, a stable identifier, resource bounds, an offset policy, and an explicit lifecycle. Before creating many containers, consider a single listener consuming multiple topics or a `topicPattern`; use dynamic containers only when subscriptions genuinely require independent lifecycles or configurations.

## 1. Listener Containers Are Background Resources

In Spring Kafka, `KafkaMessageListenerContainer` manages a Kafka consumer and its processing thread. `ConcurrentMessageListenerContainer` manages multiple child containers to increase concurrency. A container is not a lightweight Java object; when running, it creates and manages consumers, poll loops, heartbeats, fetches, offset commits, and broker connections.

With a `ConcurrentMessageListenerContainer` configured with concurrency 4, the application typically runs four child consumers. Creating 30 such containers per application instance can produce around 120 consumers on that instance. Across 5 instances, the total can reach roughly 600 consumers. Exact counts depend on container type, partition assignments, and start/stop timing, yet this calculation reveals the multiplicative effect.

```text
Application with 5 instances
  each instance creates 30 containers
  each container concurrency = 4

5 x 30 x 4 = up to approximately 600 consumers
```

Each consumer can allocate threads, buffers, socket/network traffic, heartbeats, and metadata requests. Therefore, container count must be treated as a resource budget rather than a configuration variable that can grow without bound.

## 2. Risks of Uncontrolled Container Creation

| Risk | Cause | Consequence |
|---|---|---|
| Thread and memory exhaustion | Each container/concurrency adds consumers and poll loops | CPU, heap, GC, and context switching increase |
| Excessive broker connections | Many consumers concurrently fetching, heartbeating, and querying metadata | Broker absorbs extra network and request load |
| Consumer group explosion | Each tenant/container uses a separate group ID | Group coordinator must manage many groups and offset states |
| Continuous rebalances | Frequent consumer start/stop or subscription changes | Partitions repeatedly revoked/reassigned, disrupting processing |
| Idle/excess consumers | Consumer count exceeds assignable partitions | Many consumers hold no partitions while still consuming resources |
| Leaked containers | Containers created without proper stopping or unregistering | Old consumers keep running, double-reading, or holding connections |
| Duplicate listeners | Two concurrent requests create containers for the same tenant | Two unintended consumers join the group or read the same data |
| Unpredictable offsets | Group IDs generated randomly or reused improperly | Unintended replay or skipped data |
| Invalid topics/ACLs | Unvalidated dynamic inputs | Containers continuously fail, retry metadata, or cannot consume |
| Difficult shutdown/redeploy | Lifecycle decoupled from Spring context or registry | Consumers stay active as the application shuts down |

These risks can compound at once. For instance, an API creating a listener per tenant without idempotency can spawn duplicate containers on HTTP retries; if each container also uses a random group ID, group and consumer counts surge while new offsets start per `auto.offset.reset`.

## 3. Estimating Consumer Count Before Creation

Before permitting dynamic container creation, calculate how many consumers can run concurrently:

```text
total consumers
  = application instances
  x active listener containers per instance
  x concurrency per container
```

For example:

| Parameter | Value |
|---|---:|
| Application instances | 3 |
| Max dynamic containers per instance | 20 |
| Concurrency per container | 2 |
| Estimated total consumers | 120 |

This is the theoretical ceiling when all containers are active. Add consumers from static listeners, reply containers, retry topics, DLT consumers, and other services sharing the cluster. Beyond consumer count, account for group ID count, partition assignments, fetch volume, thread count, and connection count.

For an 8-partition topic within one group, maximum useful concurrency generally does not exceed 8 partition-assigned consumers. Creating 20 consumers for that topic will not proportionally increase throughput; excess consumers still incur overhead without partitions to process. If each tenant has a dedicated group, each group can re-read the entire topic and scale broker load with group count.

## 4. Creating Dynamic Containers via ContainerFactory

Spring Kafka supports creating containers at runtime from `ConcurrentKafkaListenerContainerFactory`. Simple example:

```java
public ConcurrentMessageListenerContainer<String, String> createContainer(
        ConcurrentKafkaListenerContainerFactory<String, String> factory,
        String topic,
        String groupId,
        MessageListener<String, String> listener) {

    ConcurrentMessageListenerContainer<String, String> container =
            factory.createContainer(topic);
    container.getContainerProperties().setGroupId(groupId);
    container.getContainerProperties().setMessageListener(listener);
    container.setBeanName("dynamic-" + groupId + "-" + topic);
    container.start();
    return container;
}
```

`factory.createContainer(topic)` builds a container using the factory's configuration. The application must supply the listener, appropriate group ID, and call `start()`. A container created directly this way does not automatically become a Spring bean and is not automatically managed by `KafkaListenerEndpointRegistry`. Whatever component creates it must retain the reference and handle stopping/destroying it when no longer needed.

The snippet above only demonstrates the API. Never accept `topic` and `groupId` directly from unvalidated requests; validate the topic, tenant, permissions, and quotas before creating. Also store the container in an internal management registry rather than returning it and losing the reference.

## 5. Managing Containers with an Application Registry

A safer approach is a dedicated service responsible for creating, looking up, and stopping containers. Use stable IDs to ensure the same tenant/topic does not spawn duplicate listeners.

```java
@Service
public class DynamicListenerManager {

    private final ConcurrentKafkaListenerContainerFactory<String, String> factory;
    private final Map<String, MessageListenerContainer> containers =
            new ConcurrentHashMap<>();

    public DynamicListenerManager(
            ConcurrentKafkaListenerContainerFactory<String, String> factory) {
        this.factory = factory;
    }

    public MessageListenerContainer start(
            String listenerId,
            String topic,
            String groupId,
            MessageListener<String, String> listener) {

        return containers.computeIfAbsent(listenerId, id -> {
            var container = factory.createContainer(topic);
            container.getContainerProperties().setGroupId(groupId);
            container.getContainerProperties().setMessageListener(listener);
            container.setBeanName(id);
            container.start();
            return container;
        });
    }

    public void stop(String listenerId) {
        containers.computeIfPresent(listenerId, (id, container) -> {
            container.stop();
            return null;
        });
    }
}
```

`computeIfAbsent` prevents creating two containers for the same key within one JVM under concurrent requests. However, it does not resolve races across multiple application instances. If only one instance may own a tenant's listener, a distributed lease/lock or external leader assignment mechanism outside the JVM is needed.

The example above also needs validation, failure handling when `start()` fails, container count caps, and stopping all containers on Spring context shutdown. When a container fails to start, do not leave a failed entry sitting in the map causing subsequent requests to assume the listener is active. `computeIfAbsent` only guards per-key creation; the application must still coordinate start/stop/shutdown with a lifecycle lock or state machine so a container is not created right as shutdown iterates over the map.

## 6. Stopping Containers and Releasing Resources

Creating containers without a corresponding stop path is a common source of leaks. When a tenant is deleted, a topic is no longer consumed, or a subscription is replaced, the application must stop the container and remove its managed reference.

```java
public void stop(String listenerId) {
    containers.computeIfPresent(listenerId, (id, container) -> {
        container.stop();
        return null;
    });
}

@PreDestroy
public void stopAll() {
    containers.forEach((id, container) -> container.stop());
    containers.clear();
}
```

`stop()` requests the container to stop and terminates the consumer lifecycle. If you need to await a callback or handle asynchronous shutdown, use the lifecycle overload suited to your Spring Kafka version and clear management state only after stopping is confirmed. During shutdown, do not skip containers that are mid-start or mid-stop.

Define an explicit shutdown timeout and log the container ID, topic, group ID, and final state. Do not keep consumers running simply because a map or cache still holds a reference to the container.

## 7. Using KafkaListenerEndpointRegistry for Dynamic Endpoints

For listeners that should follow Spring Kafka's endpoint model, you can register a `KafkaListenerEndpoint` with `KafkaListenerEndpointRegistry`. Example using `SimpleKafkaListenerEndpoint`:

```java
public void registerEndpoint(
        KafkaListenerEndpointRegistry registry,
        ConcurrentKafkaListenerContainerFactory<String, String> factory,
        String id,
        String topic,
        String groupId,
        MessageListener<String, String> listener) {

    SimpleKafkaListenerEndpoint<String, String> endpoint =
            new SimpleKafkaListenerEndpoint<>();
    endpoint.setId(id);
    endpoint.setGroupId(groupId);
    endpoint.setTopics(topic);
    endpoint.setMessageListener(listener);

    registry.registerListenerContainer(endpoint, factory, true);
}
```

The registry creates a container from the endpoint and manages the registered container's lifecycle. The endpoint ID must be unique. This approach fits when you want unified endpoint, container factory, and registry mechanics alongside `@KafkaListener`.

When removing an endpoint, remember that `unregisterListenerContainer(id)` only removes the container from the registry; it does not call `stop()` or `destroy()` on the application's behalf. Stop the container before or after unregistering per the chosen lifecycle order. The unregister API arrived in Spring Kafka 2.8.9; on earlier versions, do not assume this method exists.

```java
public void unregisterEndpoint(
        KafkaListenerEndpointRegistry registry,
        String id) {

    MessageListenerContainer container = registry.getListenerContainer(id);
    if (container != null) {
        container.stop();
        registry.unregisterListenerContainer(id);
    }
}
```

Do not call `unregisterListenerContainer` first and drop the reference without stopping the container. The container may keep running even though the registry no longer manages it.

## 8. Distinguishing Registry-Managed Containers from Spring Bean Containers

Containers created from `@KafkaListener` are registered in `KafkaListenerEndpointRegistry`; they are not ordinary Spring beans in the application context. Conversely, containers declared directly with `@Bean` are Spring-managed beans and do not belong to the registry's lifecycle container list.

This affects how containers are located and stopped:

| Container Type | How Accessed/Managed |
|---|---|
| Created by `@KafkaListener` | `KafkaListenerEndpointRegistry.getListenerContainer(id)` |
| Dynamically registered via registry | Registry manages lifecycle; use endpoint ID to access and unregister |
| Declared with `@Bean` | Retrieve from `ApplicationContext` or inject bean; Spring manages bean lifecycle |
| Created directly via `factory.createContainer()` | Application must retain references and manage start/stop itself |

Do not assume `registry.getListenerContainers()` returns every container ever created. The registry manages only containers belonging to it. `getAllListenerContainers()` on supported versions can also include bean containers, though it does not instantiate uninitialized lazy beans.

## 9. Late Registration and autoStartup

A common surprise is that endpoints registered after the application context has refreshed may start immediately to satisfy the lifecycle contract, regardless of the endpoint's `autoStartup`. Since Spring Kafka 2.8.7, the registry has an `alwaysStartAfterRefresh` property; setting it to `false` lets `autoStartup` decide whether a late-registered container starts.

If the application needs to pre-register a listener and only enable it when a tenant is activated, verify behavior for your exact Spring Kafka version. Do not assume `autoStartup=false` always guarantees a newly registered container stays stopped after context refresh.

Usually Spring Boot already provides the infrastructure registry. Do not declare a new `KafkaListenerEndpointRegistry` just to change a property, as doing so can create a second registry that does not manage existing endpoints. Inject the framework-provided registry and set `alwaysStartAfterRefresh` before context refresh completes, such as in an early-initializing configuration bean. If you only want to control one specific endpoint, consider the `startImmediately` parameter of `registerListenerContainer(...)` along with your version's late-registration behavior.

## 10. Risks of Creating One Container per Tenant

A common design gives each tenant its own topic and creates a listener container for that tenant. This can work when each tenant has independent lifecycles, access permissions, group IDs, and processing policies. Yet as tenants grow from dozens to thousands, consumer and group counts scale along with them.

For example, with 1,000 tenants, one container per tenant, concurrency 1, and 4 application instances:

```text
1,000 containers/instance x 1 consumer x 4 instances
= approximately 4,000 consumers
```

If each tenant has a stable group ID, the cluster must manage thousands of groups and offset states. If each application instance generates a different group ID for the same tenant, every group becomes an independent subscriber and can re-read all data, multiplying load by instance count.

Before choosing this model, determine which tenants genuinely need dedicated consumers. If all tenants share the same schema, retry policy, and lifecycle, a single consumer subscribing to multiple topics or a single topic with a tenant key is usually simpler.

## 11. Alternative: One Listener Subscribing to Multiple Topics

If multiple topics share the same listener, serializers, group ID, and error policy, you can configure a single `@KafkaListener` reading multiple topics:

```java
@KafkaListener(
        id = "tenantEventsListener",
        topics = {"tenant-a.events", "tenant-b.events", "tenant-c.events"},
        groupId = "tenant-events-reader")
public void onEvent(ConsumerRecord<String, TenantEvent> record) {
    tenantEventService.handle(record.topic(), record.key(), record.value());
}
```

One container can consume multiple topics and Kafka distributes the subscribed partitions across the consumer group. This reduces container and group counts compared to creating a container per topic. In return, the topics share the listener's lifecycle, concurrency, and error policy; if strong tenant isolation is needed, evaluate carefully.

If the topic list changes over time, consider pattern subscription instead of spawning a new container per topic.

## 12. Alternative: topicPattern

`@KafkaListener(topicPattern = "...")` lets you subscribe to topics matching a regular expression. The Kafka consumer refreshes metadata and discovers new matching topics via metadata refresh.

```java
@KafkaListener(
        id = "tenantPatternListener",
        topicPattern = "tenant\\.[a-z0-9-]+\\.events",
        groupId = "tenant-events-reader")
public void onEvent(ConsumerRecord<String, TenantEvent> record) {
    tenantEventService.handle(record.topic(), record.value());
}
```

The pattern must be narrow enough to avoid accidentally subscribing to system topics or unauthorized tenant topics. A pattern listener does not create one container per topic; it uses one subscription that can match many topics. This is often a clean option when topics are created dynamically yet share contracts and processing policies.

Do not use broad regexes like `.*` on a cluster with many topics if the consumer is only permitted to read a small subset. Pattern subscription also does not replace ACLs; the broker must still enforce `READ` permissions for the consumer's principal.

## 13. Risks of Dynamic Group IDs

The group ID determines committed offset positions and partition sharing scope. Generating a random group ID each time a container starts makes Kafka treat the consumer as a brand-new group. Without committed offsets, `auto.offset.reset` determines whether reading starts from `earliest` or `latest`.

Consequences:

- `earliest`: a new group may re-read large amounts of historical data, spiking load and causing duplicate side effects.
- `latest`: a new group may skip data produced before the group started reading.
- Stable group ID: the consumer resumes from the group's committed offsets, appropriate when preserving progress across restarts.

Do not generate UUID-based group IDs on every start unless you genuinely intend a brand-new independent subscription. If a tenant needs separate offsets, construct deterministic group IDs per tenant and environment, such as `orders-tenant-42-prod`; never use arbitrary request data as a group ID without character and length validation.

If multiple containers share a group ID and subscribe to the same topic, Kafka divides partitions among them. If consumers exceed partitions, some consumers receive no partitions. If containers have differing subscriptions yet share a group, understand the assignment strategy and topic union before deploying.

## 14. Rebalance Storms from Frequent Start/Stop

Every time a member joins or leaves a consumer group, Kafka may execute a rebalance to redistribute partitions. If the application continuously creates and stops containers on HTTP requests or tenant events, the group may rebalance frequently.

Rebalances can cause:

- Partitions being revoked while the listener is processing.
- Consumers having to commit offsets or reprocess records depending on ack/commit strategy.
- Listeners pausing record receipt while new assignments settle.
- Increased duplicate processing if side effects are not idempotent.
- Growing consumer lag even when incoming message rates are flat.
- Higher group coordinator load and log churn.

Do not start/stop containers per message or per short-lived request. If a tenant temporarily does not need processing, consider pausing the container or applying application-level filtering/routing instead of continually creating and destroying consumers.

## 15. Concurrency Is Not a Way to Multiply Containers Arbitrarily

`ConcurrentKafkaListenerContainerFactory.setConcurrency(n)` creates multiple child consumers for one listener container. Useful consumers are bounded by assignable partitions in the group. For example, on a 6-partition topic, concurrency 12 will not deliver double the throughput of concurrency 6; half the consumers will have no partitions.

If you create 10 dynamic containers with concurrency 5 each, the application can spawn around 50 consumers for one subscription type. Size concurrency at the system level, not only per container.

Choose concurrency based on:

- Partition counts of subscribed topics.
- Throughput and average processing time per record.
- CPU, memory, connection pools, and downstream limits.
- Application instance count and concurrent dynamic container count.
- Rebalance tolerance and poll intervals.

Raising concurrency will not fix a database or HTTP dependency bottleneck. If downstream only handles 20 concurrent requests, creating 200 consumers can overload downstream and drive up retries.

## 16. Race Conditions When Concurrent Requests Create Containers

An API such as `POST /tenants/{id}/listeners` may receive two concurrent requests. If code checks `containsKey()` before creating a container, both requests may observe it absent and create two containers.

Anti-pattern:

```java
if (!containers.containsKey(listenerId)) {
    MessageListenerContainer container = createContainer(...);
    containers.put(listenerId, container);
}
```

Use atomic operations like `computeIfAbsent`, per-listener-ID locks, or a state machine tracking `CREATING`, `RUNNING`, `STOPPING`, `STOPPED`, and `FAILED`. Do not store only the container reference; also store start state, creation timestamp, topic, group ID, owner, and last error.

In multi-instance environments, `ConcurrentHashMap` only protects a single JVM. To guarantee a single listener owner across the cluster, use distributed coordination or explicit tenant partitioning so each instance manages a disjoint tenant set.

## 17. Validating Topics and Limiting Dynamic Inputs

Never create a container from a client-supplied topic name directly. The topic could contain invalid characters, not exist, or fall outside the tenant's scope. An unvalidated API could be abused to spawn thousands of consumers reading unrelated topics.

Before creating a container, verify:

- The tenant exists and the caller is authorized to manage that tenant.
- The topic is on an allowlist or was created by a trusted governance workflow.
- The topic exists and has appropriate partitions/replication.
- The application's Kafka principal holds the required `READ` and `DESCRIBE` permissions.
- The group ID follows naming policy and does not collide with another tenant.
- The tenant has not exceeded container/concurrency quotas.
- Deserializers, error handlers, and offset policies match the topic contract.

Do not enable `allow.auto.create.topics` or create topics for every incoming API request. Topic creation should have separate governance over quotas, naming conventions, retention, replication factor, and ACLs.

## 18. Managing State and Quotas

A dynamic listener manager should enforce clear quotas:

| Limit | Example Policy |
|---|---|
| Max containers per application instance | Stay within tested consumer budget |
| Max containers per tenant | One active listener per approved subscription |
| Max concurrency per container | Do not exceed useful partition count or downstream capacity |
| Creation/destruction rate | Disallow continuous per-request churn |
| Lifetime | Containers must have an owner and stop condition |
| Startup deadline | Transition to `FAILED` and alert if not started within deadline |
| Shutdown deadline | Stop containers within grace period before process exit |

Subscription state should be persisted durably if recovery after restart is required. If stored only in memory, the application will not know which tenants need listeners upon restart. However, do not automatically restore all containers without checking quotas and tenant status; container counts could spike right after deployment.

## 19. Observing Dynamic Containers in Production

Every container should have a traceable ID and metadata. At a minimum, observe:

- Counts of `running`, `stopped`, `starting`, and `failed` containers.
- Total consumers/child containers per application instance.
- Concurrency, topic subscriptions, and group IDs.
- Consumer lag by topic/partition/group.
- Rebalance count and rebalance duration.
- Start/stop counts over a time window.
- Record processing time, poll intervals, and listener errors.
- Count of consumers without assigned partitions.
- Count of expired or ownerless containers.
- Shutdown/stop errors and consumers still running on application close.

You can use `KafkaListenerEndpointRegistry.getListenerContainers()` to inspect registry-managed containers; `getAllListenerContainers()` on supported versions also includes bean-declared containers. For containers created directly from a factory, inspect via the application's internal management registry.

Do not put high-cardinality tenant IDs, topic IDs, or listener IDs into metric labels when counts are large. Use structured logs or traces for detailed IDs; keep metrics focused on counts by state, listener type, topic group, and exception category.

## 20. Testing Container Lifecycle and Load

Dynamic container tests must cover creation, usage, stopping, and release. Do not merely check that `start()` throws no exception.

| Scenario | Expectation |
|---|---|
| Create a valid container | Consumer is created, subscribes to right topic, and processes records |
| Call start twice with same listener ID | No second container is created |
| Two concurrent requests create same listener | Only one container is registered/running |
| Nonexistent topic or missing ACL | Container reports clear error, manager marks `FAILED` and cleans up reference |
| Stop tenant | Container stops, consumer closes, and no new records are received |
| Stop application | All dynamic containers stop within shutdown grace period |
| Unregister registry endpoint | Container stopped before/after unregister per workflow; no orphaned consumers remain |
| Exceed quota | Request rejected before creating new consumer |
| Concurrency exceeds partitions | Throughput does not exceed partition capacity; metrics show idle consumers |
| Frequent start/stop | Monitor rebalances, lag, and resources to confirm no abnormal churn |
| Application restart | Only approved and currently valid subscriptions are restored |
| Multiple application instances | One tenant does not spawn duplicate consumers violating ownership strategy |

Run integration tests against Kafka via Testcontainers or Embedded Kafka and measure consumer/thread counts before, during, and after tests. Verify both broker group membership and proper offset continuation after stopping and recreating a container.

## 21. Controlled Container Creation and Teardown Workflow

1. Receive subscription request from an authenticated source.
2. Validate tenant, topic, group ID, ACLs, quotas, and processing config.
3. Derive a deterministic listener ID and check current state.
4. Mark state as `CREATING` to block duplicate creation requests.
5. Create container from factory or endpoint registry.
6. Attach listener, group ID, concurrency, ack/error policy, and bean name.
7. Start container and verify running state/assignment as required.
8. Record `RUNNING` state with owner and timestamp.
9. When subscription expires or tenant is removed, mark `STOPPING`.
10. Stop container, wait for required shutdown completion, then unregister/remove reference.
11. Confirm consumer left the group and state transitions to `STOPPED`.
12. Emit audit event tracking who created, modified, or stopped the subscription.

If startup fails, transition to `FAILED`, log the cause, and allow container creation retries with bounded backoff. Do not keep a false `RUNNING` entry or spawn a fresh container on every request while old containers remain unreleased.

## 22. Common Misconceptions

| Misconception | Reality |
|---|---|
| A container is just a lightweight Java object | A running container manages consumers, threads, poll loops, and broker connections |
| Creating more containers always increases throughput | Throughput is bounded by partitions, downstream, and resources |
| One group ID per tenant is free | Each group maintains separate offsets and lifecycle, increasing coordinator/broker load |
| `KafkaListenerEndpointRegistry` manages every container | The registry only manages containers registered with it; directly created containers must be managed by the application |
| Unregistering automatically stops a container | `unregisterListenerContainer` only removes from the registry; you must stop separately |
| `autoStartup=false` always prevents late-registered endpoints from running | Late registration has distinct behavior; check `alwaysStartAfterRefresh` and version |
| Increasing concurrency without limit | Useful consumers are bounded by partitions and downstream capacity |
| `ConcurrentHashMap` prevents cluster-wide duplicates | It only synchronizes within one JVM; multi-instance deployments need distributed coordination |
| Stopping a container only requires removing it from the map | You must stop consumers and release lifecycle before dropping references |
| Topic patterns can replace ACLs | Patterns only filter topic names; broker ACLs still control read access |

## Pre-Production Checklist for Dynamic Containers

- Clear justification exists for dedicated containers instead of a multi-topic/`topicPattern` listener.
- Total consumer count estimated across application instances, containers, and concurrency.
- Quotas enforced on containers, group IDs, tenants, and start/stop frequency.
- Deterministic listener IDs and group IDs used; random UUIDs on every start avoided.
- Internal registry or `KafkaListenerEndpointRegistry` manages lifecycle.
- Race conditions handled when concurrent requests create the same subscription.
- Topics, tenants, ACLs, partitions, and naming policies validated before creation.
- Clear workflow exists for stopping, unregistering, and shutting down all containers.
- Unregistering is never assumed to stop containers automatically.
- Late registration/`autoStartup` behavior verified for the Spring Kafka version.
- Consumer counts, group counts, rebalances, lag, and container states monitored.
- Start/stop, duplicate creation, quotas, restarts, and cleanup tested.
- Runbook prepared for orphaned containers, abnormal group growth, and rebalance storms.

Dynamic listener containers are a tool for managing runtime subscriptions, not for multiplying consumers without limit. Each container adds consumers and lifecycle responsibilities; large numbers can exhaust resources, trigger continuous rebalances, leave idle consumers, and complicate offset control. Prefer multi-topic or topic-pattern listeners when subscriptions share policies; when dedicated containers are truly needed, manage them with stable IDs, quotas, coordination, and verified stop/unregister workflows.

## References

- [Spring for Apache Kafka – Dynamically Creating Containers](https://docs.spring.io/spring-kafka/reference/kafka/dynamic-containers.html)
- [Spring for Apache Kafka – @KafkaListener Lifecycle Management](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/kafkalistener-lifecycle.html)
- [KafkaListenerEndpointRegistry API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/config/KafkaListenerEndpointRegistry.html)
