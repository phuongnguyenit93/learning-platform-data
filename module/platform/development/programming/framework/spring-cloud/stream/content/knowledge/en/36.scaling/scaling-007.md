# ProvisioningProvider and Resource Lifecycle of a Custom Binder

Spring Cloud Stream allows applications to process events through **`Supplier`**, **`Function`**, and **`Consumer`**, while the binder connects those bindings to Kafka, RabbitMQ, Pulsar, or another middleware. When a middleware lacks a suitable binder, you can build a **custom binder** using the Binder SPI. The first crucial component of a custom binder is **`ProvisioningProvider`**: it translates a logical destination name from application configuration into a reference to a physical resource capable of sending or receiving messages.

For example, an application configures destination `orders.created`, while internal middleware must create stream `events/orders.created`, subscription `fulfillment`, and four data shards. A custom binder must decide when to create the stream, when to verify it exists, how to map a group to a subscription, what to do if multiple instances start simultaneously, and which resources are permitted to be deleted when the application stops.

This lesson focuses on **provisioning, resource ownership management, and scaling across multiple instances**. Illustrative code uses a hypothetical middleware named `ExampleBus` to clarify the SPI contract. Admin API calls are illustrative interfaces, **not built-in Spring Cloud Stream classes**; when working with real middleware, replace them with the SDK/Admin Client and adapt to your library version.

## 1. Why Does a Custom Binder Need ProvisioningProvider?

Spring Cloud Stream separates three concepts:

| Concept | Role | Example |
|---|---|---|
| Binding | Input/output of a function inside the application | `processOrder-in-0` |
| Logical destination | Name declared by the deployer | `orders.created` |
| Physical resource | Actual topic, exchange, queue, stream, or subscription | `tenant-a/orders.created`; `orders.created.fulfillment` |

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: fulfillment
          binder: exampleBus
~~~

These settings do not specify whether the middleware needs to create a queue, how the queue name incorporates the group, or whether the resource is durable. That is the provisioning layer's responsibility.

**`ProvisioningProvider` does not process business payloads.** It prepares or locates resources and returns a destination object that endpoints can use. Record-sending logic belongs to the producer handler; record-receiving logic belongs to the consumer endpoint.

If the middleware already has an official binder, use that binder before building your own. A custom binder fits when connecting proprietary middleware, specialized protocols, or resource semantics unsupported by existing binders.

## 2. Where ProvisioningProvider Sits in the Binder SPI

A message-channel-style custom binder typically includes:

- **`ProvisioningProvider`**: creates/verifies destinations for producers and consumers.
- **`Binder`**: implements the contract linking Spring Cloud Stream inputs/outputs to middleware.
- **`MessageHandler`**: sends data from an output channel out to the middleware.
- **`MessageProducer`**: receives messages from middleware and pushes them into an input channel.
- **Binder configuration**: initializes beans, connection/admin clients, and binder settings.
- **`META-INF/spring.binders`**: informs the framework of the binder name and configuration class.

The initialization flow can be visualized as follows:

~~~mermaid
flowchart TD
    A[application.yml] --> B[BindingService]
    B --> C{Select Binder}
    C --> D[bindProducer or bindConsumer]
    D --> E[ProvisioningProvider]
    E --> F[Verify / create broker resources]
    F --> G[ProducerDestination or ConsumerDestination]
    G --> H[createProducerMessageHandler / createConsumerEndpoint]
    H --> I[Start endpoint / Binding]
    I --> J[Exchange messages]
~~~

**Ordering matters:** an endpoint should start sending/receiving only after required resources exist or have been verified. If provisioning fails, do not report that the binding initialized successfully and silently drop messages.

A custom binder does not strictly have to extend `AbstractMessageChannelBinder` if implementing a different binder style. However, Spring Cloud Stream provides this base class to reuse lifecycle management and Spring Integration wiring when the binding target is `MessageChannel`.

## 3. The ProvisioningProvider Contract

The interface belongs to package:

~~~java
org.springframework.cloud.stream.provisioning.ProvisioningProvider
~~~

It takes two type parameters: a consumer properties type and a producer properties type. For general needs, the common types can be used:

~~~java
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ProvisioningProvider;

public final class ExampleProvisioner
        implements ProvisioningProvider<
            ConsumerProperties, ProducerProperties> {

    @Override
    public ProducerDestination provisionProducerDestination(
            String name,
            ProducerProperties properties) {
        throw new UnsupportedOperationException("Not implemented");
    }

    @Override
    public ConsumerDestination provisionConsumerDestination(
            String name,
            String group,
            ConsumerProperties properties) {
        throw new UnsupportedOperationException("Not implemented");
    }
}
~~~

The two methods serve different roles:

| Method | Key parameters | Result |
|---|---|---|
| `provisionProducerDestination` | `name`, `ProducerProperties` | `ProducerDestination` |
| `provisionConsumerDestination` | `name`, `group`, `ConsumerProperties` | `ConsumerDestination` |

- **`name`** is the logical destination name declared by the binding, not necessarily the physical resource name.
- **`group`** is the logical consumer group. Middleware can use it to create a subscription, durable queue, or other receiving group construct.
- **`properties`** holds common configuration such as `partitionCount`, `requiredGroups`, `concurrency`, `partitioned`, `instanceCount`, and `instanceIndex`.
- **The returned destination** describes the resource so producer/consumer endpoints can connect.

When middleware reports it cannot provision, the provider should throw a **`ProvisioningException`** carrying context without passwords, tokens, or message contents. Never return a fake destination if the broker is unready and business rules require the resource to exist before the binding runs.

## 4. ProducerDestination and ConsumerDestination

The two destination interfaces expose references to physical resource names:

~~~java
public interface ConsumerDestination {
    String getName();
}

public interface ProducerDestination {
    String getName();
    String getNameForPartition(int partition);
}
~~~

`ProducerDestination` adds **`getNameForPartition(int)`** because some middleware represents each partition as a distinct physical destination. For example:

~~~text
orders.created
  -> events/orders.created-0
  -> events/orders.created-1
  -> events/orders.created-2
~~~

For middleware with native partitions, all records may go to the same topic/stream name while passing the partition as transport metadata. In that case `getNameForPartition` can return the same name, provided the producer handler actually passes the partition ID to the client SDK.

**Do not confuse returning the same name with supporting partitioning.** If the middleware lacks native partitions and `getNameForPartition` always returns a shared name, the binder may send every record to the same resource and defeat partitioning.

`ConsumerDestination` typically provides only the resource name the consumer reads from. How partitions or subscription groups are assigned depends on the endpoint and middleware design.

## 5. Designing Logical-to-Physical Name Mapping

Suppose `ExampleBus` separates namespaces and streams:

~~~text
Logical destination: orders.created
Namespace:           tenant-a
Physical stream:     tenant-a/events/orders.created
Group:               fulfillment
Subscription:        tenant-a/events/orders.created/fulfillment
~~~

Mapping rules should be:

1. **Deterministic**: identical inputs and configuration always yield the same name.
2. **Stable**: names do not change on Pod restarts or horizontal scaling.
3. **Collision-safe**: two tenants or two environments never accidentally collide.
4. **Valid**: names respect character sets, length limits, and middleware rules.
5. **Observable**: traceable from binding back to physical resource.
6. **Secure**: arbitrary names cannot escape the authorized namespace.

Illustrative naming utility:

~~~java
import java.util.Locale;
import java.util.regex.Pattern;

public final class DestinationNames {

    private static final Pattern VALID =
        Pattern.compile("[a-zA-Z0-9._-]{1,128}");

    private DestinationNames() {}

    public static String stream(String namespace, String logicalName) {
        requireValid(namespace);
        requireValid(logicalName);

        return namespace + "/events/" + logicalName;
    }

    public static String subscription(String stream, String group) {
        requireValid(group);
        return stream + "/" + group;
    }

    private static void requireValid(String value) {
        if (value == null || !VALID.matcher(value).matches()) {
            throw new IllegalArgumentException(
                "Invalid destination identifier"
            );
        }
    }
}
~~~

This is an illustrative naming convention, not an official rule for Kafka, RabbitMQ, or Pulsar. For real brokers, follow the official naming rules of the SDK and infrastructure. Never silently trim or replace characters if doing so could cause two distinct valid names to collide onto one resource.

## 6. Example Interface for Middleware Admin API

To decouple the SPI from a middleware SDK, define an adapter/admin interface created by **the application itself**:

~~~java
public interface ExampleBusAdmin {

    void ensureStream(String physicalName, int partitions);

    // Only verify/create if missing; do not alter partitions of an existing stream.
    void ensureStreamForConsumer(String physicalName);

    void ensureDurableSubscription(
        String physicalStream,
        String group
    );

    void verifyStream(String physicalName, int expectedPartitions);

    void verifyStreamExists(String physicalName);

    void verifyDurableSubscription(
        String physicalStream,
        String group
    );
}
~~~

These methods are **illustrative assumptions**:

- `ensureStream` creates the resource if missing, or verifies the existing resource is compatible.
- `ensureStreamForConsumer` only ensures the stream exists while preserving existing partition topology.
- `ensureDurableSubscription` creates a durable subscription/group if missing.
- `verifyStream` checks a resource pre-provisioned by infrastructure.
- `verifyStreamExists` only checks existence when the consumer does not know the broker's partition count.
- `verifyDurableSubscription` verifies the consumer group is provisioned in read-only mode.
- Every operation must have explicit timeouts and error policies in a real SDK.

Not every broker shares the same stream and subscription concepts. Kafka consumer groups are managed via coordinators and metadata; RabbitMQ typically needs exchanges, queues, and bindings; Pulsar uses topics and subscriptions. Real adapters must reflect the exact broker model.

## 7. Writing a Complete ProvisioningProvider at the SPI Level

The following example combines naming logic with the Admin API. It supports only **named durable groups**, not anonymous consumers; that restriction is intentional to avoid assuming temporary or auto-delete queues exist.

~~~java
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ProvisioningException;
import org.springframework.cloud.stream.provisioning.ProvisioningProvider;

public final class ExampleBusProvisioningProvider
        implements ProvisioningProvider<
            ConsumerProperties, ProducerProperties> {

    private final ExampleBusAdmin admin;
    private final String namespace;
    private final boolean autoProvision;

    public ExampleBusProvisioningProvider(
            ExampleBusAdmin admin,
            String namespace,
            boolean autoProvision) {
        this.admin = admin;
        this.namespace = namespace;
        this.autoProvision = autoProvision;
    }

    @Override
    public ProducerDestination provisionProducerDestination(
            String name,
            ProducerProperties properties) {

        String physical = DestinationNames.stream(namespace, name);
        int partitions = properties.getPartitionCount();

        if (partitions < 1) {
            throw new ProvisioningException(
                "Producer partitionCount must be positive"
            );
        }

        try {
            String[] requiredGroups = properties.getRequiredGroups();
            if (autoProvision) {
                admin.ensureStream(physical, partitions);

                if (requiredGroups != null) {
                    for (String group : requiredGroups) {
                        admin.ensureDurableSubscription(physical, group);
                    }
                }
            }
            else {
                admin.verifyStream(physical, partitions);
                if (requiredGroups != null) {
                    for (String group : requiredGroups) {
                        admin.verifyDurableSubscription(physical, group);
                    }
                }
            }

            return new ExampleProducerDestination(physical, partitions);
        }
        catch (RuntimeException exception) {
            throw new ProvisioningException(
                "Producer destination provisioning failed: " + physical,
                exception
            );
        }
    }

    @Override
    public ConsumerDestination provisionConsumerDestination(
            String name,
            String group,
            ConsumerProperties properties) {

        if (group == null || group.isBlank()) {
            throw new ProvisioningException(
                "This binder requires a named durable group"
            );
        }

        String physical = DestinationNames.stream(namespace, name);

        try {
            if (autoProvision) {
                admin.ensureStreamForConsumer(physical);
                admin.ensureDurableSubscription(physical, group);
            }
            else {
                admin.verifyStreamExists(physical);
                admin.verifyDurableSubscription(physical, group);
            }

            return new ExampleConsumerDestination(physical, group);
        }
        catch (RuntimeException exception) {
            throw new ProvisioningException(
                "Consumer destination provisioning failed: " + physical,
                exception
            );
        }
    }
}
~~~

Key design points:

- The provider does not send or receive messages itself.
- The Admin API performs idempotent operations: re-running yields compatible outcomes.
- Neither streams nor subscriptions are deleted inside provision methods.
- **`autoProvision=false`** enables verify-only mode, suited for production environments that lock down resource creation permissions.
- **`requiredGroups`** lets a producer ensure durable groups are prepared before the producer starts emitting messages.
- Consumer groups are validated to be non-blank because this example does not support anonymous groups.
- Admin failures are translated into `ProvisioningException`, failing the binding instead of returning a non-existent destination.

### A Constraint to Address in Real Implementations

In the example, the consumer calls `ensureStreamForConsumer` instead of forcing `partitionCount` to 1, because `ConsumerProperties` does not by itself determine the broker's physical partition count. With real middleware, **never shrink an existing four-partition stream down to one partition**. This operation must detect existing resources and preserve their partition count, or inspect metadata before creating. When the partition count is needed, query broker metadata or binder-defined extended properties.

If a producer creates a four-partition resource first, the consumer only needs to verify the stream exists and create the appropriate subscription; do not impose a partition count from an unreliable default.

## 8. Destination Implementations Returned to the Binder

A minimal implementation for a native-partition environment:

~~~java
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;

public record ExampleProducerDestination(
    String physicalName,
    int partitionCount
) implements ProducerDestination {

    @Override
    public String getName() {
        return physicalName;
    }

    @Override
    public String getNameForPartition(int partition) {
        if (partition < 0 || partition >= partitionCount) {
            throw new IllegalArgumentException("Partition out of range");
        }

        // Middleware receives the partition via separate metadata.
        return physicalName;
    }
}

public record ExampleConsumerDestination(
    String physicalName,
    String group
) implements ConsumerDestination {

    @Override
    public String getName() {
        return physicalName;
    }
}
~~~

With `ExampleBus`, `group` is stored in `ExampleConsumerDestination` so the endpoint can subscribe to the right durable subscription. **`getName()` does not necessarily return the subscription name**; it returns the destination reference the binder needs. The endpoint uses both `physicalName` and `group` to create its client, as the interface leaves implementation details open.

To minimize bugs, destination objects should be immutable. Avoid putting open connections, mutable admin state, or secrets inside destination objects unless lifecycle explicitly requires it.

If the middleware splits partitions into separate physical queues, replace `getNameForPartition` with the right partition naming rule—such as `physicalName + "-p" + partition`—and ensure provisioning actually created all corresponding queues/streams.

## 9. Integrating the Provider into AbstractMessageChannelBinder

For message-channel binders, Spring Cloud Stream provides **`AbstractMessageChannelBinder`**. It invokes the provisioning provider before creating endpoints. Skeleton example:

~~~java
import org.springframework.cloud.stream.binder.AbstractMessageChannelBinder;
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.integration.core.MessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

public final class ExampleBusBinder
        extends AbstractMessageChannelBinder<
            ConsumerProperties,
            ProducerProperties,
            ExampleBusProvisioningProvider> {

    private final ExampleBusTransport transport;

    public ExampleBusBinder(
            ExampleBusProvisioningProvider provider,
            ExampleBusTransport transport) {
        super(null, provider);
        this.transport = transport;
    }

    @Override
    protected MessageHandler createProducerMessageHandler(
            ProducerDestination destination,
            ProducerProperties properties,
            MessageChannel errorChannel) {

        return message -> transport.publish(
            destination.getName(),
            message
        );
    }

    @Override
    protected MessageProducer createConsumerEndpoint(
            ConsumerDestination destination,
            String group,
            ConsumerProperties properties) {

        return new ExampleBusMessageProducer(
            transport,
            destination.getName(),
            group
        );
    }
}
~~~

**`ExampleBusTransport`** and **`ExampleBusMessageProducer`** must be implemented separately. The example only shows where they plug into the SPI, not a ready-to-run binder. `ExampleBusMessageProducer` must implement message reception, conversion to Spring `Message`, thread/subscription management, acknowledgment, and stop/cleanup. `Transport` must handle serialization, headers, retry/error channels, producer confirms, and partition metadata per middleware rules.

In Spring Integration, `MessageProducer` should have an explicit lifecycle, typically by extending `MessageProducerSupport`. If the middleware consumer opens sockets or threads, initialize them when the endpoint starts and close them when it stops. Never spawn threads per bind without a corresponding shutdown path.

Provisioning should be unit-tested independently before wiring into `MessageHandler`/`MessageProducer`; otherwise topic creation errors and deserialization/publish errors are easily confused.

## 10. Declaring Binder Configuration and Discovery

A custom binder needs a configuration class instantiating the provider and binder, plus binder-type registration so Spring Cloud Stream discovers it.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExampleBusBinderConfiguration {

    @Bean
    ExampleBusProvisioningProvider exampleBusProvisioner(
            ExampleBusAdmin admin) {
        return new ExampleBusProvisioningProvider(
            admin,
            "tenant-a",
            true
        );
    }

    @Bean
    ExampleBusBinder exampleBusBinder(
            ExampleBusProvisioningProvider provisioner,
            ExampleBusTransport transport) {
        return new ExampleBusBinder(provisioner, transport);
    }
}
~~~

In the binder library, **`META-INF/spring.binders`** declares the binder name and configuration class:

~~~properties
exampleBus:\
com.example.stream.ExampleBusBinderConfiguration
~~~

When an application uses multiple binders, binding configuration must select the right binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        routeOrder-in-0:
          destination: orders.created
          group: fulfillment
          binder: exampleBus
~~~

When using named binders, environment configurations can be isolated per cluster, tenant, or account. The provider needs the exact namespace, credentials, and Admin API for that binder instance. Never share a singleton admin client pointing to a different cluster across binder contexts without strict scoping.

## 11. Resource Lifecycle: From Deploy to Shutdown

Separate **in-process binding lifecycle** from **durable broker resource lifecycle**.

~~~mermaid
flowchart TD
    A[Deploy configuration] --> B[Provision / verify resources]
    B --> C[Create producer/consumer endpoint]
    C --> D[Start binding]
    D --> E[Exchange messages]
    E --> F{Lifecycle event?}
    F -->|Restart/scale/rebalance| G[Stop or unbind local endpoint]
    G --> H[Durable resources still remain]
    H --> B
    F -->|Intentional resource deletion| I[External cleanup workflow]
    I --> J[Verify ownership, retention, consumers, and data]
    J --> K[Delete if approved]
~~~

Draw a sharp line between the two worlds:

- **Binding stop/unbind**: stops listeners, producers, and subscription clients, and releases local threads/connections.
- **Broker resource cleanup**: deletes topics/queues/subscriptions on the broker per ownership policy; never happens automatically just because an application shuts down.

The `ProvisioningProvider` interface has only two provision methods. It **does not define a generic resource-deletion callback** across middleware. Therefore, never design around the assumption that Spring Cloud Stream automatically deletes durable topics or queues upon `unbind`.

If ephemeral resources are created per broker policy (temporary queues, auto-delete subscriptions), the broker may reclaim them once its own conditions are met. That is middleware semantics, not a universal rule for custom binders.

## 12. Producer Lifecycle and Resource Ownership

When an output binding starts, the provider typically:

1. Resolves the physical destination from the logical name.
2. Validates producer properties, `partitionCount`, and `requiredGroups`.
3. Creates or verifies the stream/exchange/topic.
4. Prepares durable groups/queues if `requiredGroups` demands it.
5. Returns `ProducerDestination`.
6. The binder creates the producer `MessageHandler` and begins sending messages.

When the producer stops:

- Stop accepting new messages from the binding.
- Wait for or flush in-flight publishes within an allowed timeout.
- Close producer clients, connections, threads, and callbacks.
- **Do not delete durable destinations**, because other producers or consumers may still be using them.

If resources are created by Terraform, Helm, or an external provisioning platform, the custom binder should not unexpectedly alter metadata. Verify-only mode helps catch mismatches and fail early.

## 13. Consumer Lifecycle, Groups, and Subscriptions

For grouped consumers, the provider may create a durable subscription or queue to retain backlog while all instances are stopped. This suits most production workloads.

In our hypothetical middleware:

~~~text
Destination: tenant-a/events/orders.created
Group:       fulfillment
Resource:    durable subscription fulfillment
~~~

When Pod A and Pod B both join the group:

- There is one shared logical subscription for the group.
- Both consumer clients coordinate or competing-consume per broker semantics.
- Each instance must not create a randomly named private durable subscription if they are meant to share load.
- Re-running provisioning on each instance must locate the same resource without breaking configuration.

If `group` is unnamed, the binder must specify how anonymous subscriptions are created. It may use ephemeral resources deleted on connection close, but must clearly document potential backlog loss. `ExampleBusProvisioningProvider` in the earlier section intentionally rejects anonymous groups because those semantics are not designed there.

## 14. Idempotent Provisioning During Horizontal Scaling

When Kubernetes scales from 1 to 10 Pods, 10 concurrent `provisionConsumerDestination` calls can occur. If the method uses a check-then-create pattern without race handling, Pods collide:

~~~text
Pod A: exists(topic)? no
Pod B: exists(topic)? no
Pod A: create(topic) -> OK
Pod B: create(topic) -> AlreadyExists
~~~

**`AlreadyExists` is not necessarily an error** if the newly created resource matches requirements. The provider should implement ensure semantics:

1. Call create-if-absent or upsert as supported by the SDK.
2. On `AlreadyExists`, read current metadata.
3. Compare type, `partitionCount`, durability, ownership, and retention.
4. If compatible, treat as success.
5. If incompatible, report a provisioning mismatch.
6. Never delete and recreate to "fix" a mismatch when data is present.

Illustrative admin contract:

~~~java
public void ensureStream(String name, int partitions) {
    try {
        brokerAdmin.createStream(name, partitions);
    }
    catch (AlreadyExistsException ignored) {
        StreamInfo current = brokerAdmin.describeStream(name);

        if (current.partitions() < partitions) {
            throw new ResourceMismatchException(
                "Stream has fewer partitions than required"
            );
        }
    }
}
~~~

`brokerAdmin`, `AlreadyExistsException`, `StreamInfo`, and `ResourceMismatchException` are **illustrative SDK adapter types**, not Spring Cloud Stream APIs. Some brokers support safely expanding partitions; on others, changing partition counts alters key distribution or is unsupported. Follow middleware policies rather than mutating schemas or partitions while multiple Pods run.

## 15. Partition Count and Scaling Changes

`ProducerProperties` includes **`partitionCount`**. `ConsumerProperties` has properties for partitioned consumers, concurrency, and instance configuration. However, physical meaning depends on the binder.

| Middleware | Common partition resource | Considerations |
|---|---|---|
| Kafka | One topic with multiple native partitions | Consumer group auto-assigns partitions; increasing count changes key mapping |
| RabbitMQ Binder | Queues/routing paths per partition in certain setups | May need explicit `instanceIndex`/`instanceCount` |
| Pulsar | Partitioned topics and subscriptions | Subscription type/assignment governs distribution |
| Custom middleware | Stream shards, queue-per-partition, or native partitions | Binder must define mapping and scaling strategy |

When producers route by stable keys, changing partition counts can send the same key to a different partition. This affects ordering, stateful processing, and consumer-local state. Never treat increasing partitions as a harmless change merely because the provisioning provider can create extra resources.

In the `ExampleBus` example, `getNameForPartition` returns the same name assuming native partitions. The producer transport must receive the partition ID computed by the binder; otherwise the example only describes the resource without implementing partition routing. For queue-per-partition middleware, the provider must create or verify the full set of queues and return the exact partition name.

## 16. requiredGroups: Preparing Consumers Before Consumers Run

`ProducerProperties` supports **`requiredGroups`**. Its goal is ensuring specified groups have resources ready to retain messages even before group consumers start.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        produceOrder-out-0:
          destination: orders.created
          binder: exampleBus
          producer:
            required-groups:
              - fulfillment
              - analytics
            partition-count: 4
~~~

If the broker requires queues/subscriptions to exist beforehand to hold messages, the provider should call `ensureDurableSubscription` for required groups. If the middleware retains topic backlogs independently of subscriptions, `requiredGroups` may not need to create queues the way RabbitMQ does; the binder must still document semantics.

Never delete groups when a producer stops because unprocessed messages may still reside in the backlog. If `requiredGroups` contains invalid names or policy-violating groups, fail provisioning explicitly.

## 17. Auto-Provision vs. Verify-Only in Production

There are two primary operational models:

**Binder Auto-Provisions**

- Simple for development and integration testing.
- The binder holds permissions to create topics/queues/subscriptions.
- Scaling multiple Pods can invoke the Admin API concurrently.
- Must handle idempotency, metadata mismatches, and quotas.

**Infrastructure Pre-Provisions, Binder Verifies Only**

- IaC or platform teams provision resources, ACLs, quotas, and retention.
- Applications run with a lower-privilege principal.
- The provider only describes/verifies resource existence and compatibility.
- Missing-resource errors surface before rollout or fail binding startup.

For a custom binder, **`autoProvision` is an option you define yourself**, not a mandatory built-in Spring Cloud Stream property. To configure it via YAML, write a `@ConfigurationProperties` class and bind it to the provider under your binder's prefix.

Example custom configuration:

~~~yaml
app:
  example-bus:
    namespace: tenant-a
    auto-provision: false
~~~

Do not invent a property in configuration assuming the framework understands it without a corresponding configuration class.

## 18. Permissions and Security During Provisioning

In organizations with strict resource governance, message-processing applications should not hold blanket permissions to create or delete arbitrary queues/topics on the broker.

Separate permissions by role:

| Principal | Required permissions |
|---|---|
| Infrastructure provisioner | Create/alter resources within assigned scope |
| Application producer | Publish/write to authorized destinations |
| Application consumer | Subscribe/read/ack authorized groups |
| Observability agent | Read metrics/metadata |
| Cleanup operator | Delete via approved workflow and audit |

In verify-only mode, applications usually need only metadata describe plus read/write permissions. If an SDK forces admin privileges just to inspect resources, evaluate security policy instead of granting cluster-wide admin rights.

Credentials must never appear in exceptions or logs. `ProvisioningException` should include safe destination names, operations, and error codes—never tokens, passwords, or connection strings with embedded secrets.

## 19. Provisioning Timeouts, Retries, and Fail-Fast

An Admin API call can fail due to an unready broker, bad permissions, rate limits, or unpropagated metadata. The provider must not hang indefinitely at startup.

Design should include:

- Connection timeout.
- Request timeout for create/describe.
- Bounded retries with backoff exclusively for transient failures.
- Distinction among `AlreadyExists`, `NotFound`, `Unauthorized`, `QuotaExceeded`, and `Timeout`.
- Maximum wait time for eventual consistency after creation.
- Error messages containing operation, logical/physical destination, and non-sensitive root cause.

Example policy:

| Error | Recommended behavior |
|---|---|
| `AlreadyExists`, compatible metadata | Succeed |
| `AlreadyExists` with wrong type/partitions | Fail with `ResourceMismatch` |
| Transient timeout | Retry bounded times, then fail |
| Bad authentication/authorization | Fail fast, do not retry indefinitely |
| Quota exhausted | Fail and alert operations |
| Resource still invisible after create | Wait with bounded consistency window, then fail |
| Conflicting consumer group semantics | Fail explicitly; never auto-fix or delete |

Some binders support reconnect retries, but do not rely on them to cure permanent resource provisioning errors. If a topic name is invalid or ACLs are missing, endless retries only stall startup.

## 20. Which Resources Are Cleaned Up on Unbind?

When Spring Cloud Stream unbinds, `Binding` is asked to stop its endpoint. The `Binding` contract requires **`unbind` to be idempotent** and the target to stop receiving messages afterward.

Do not delete these resources on a mere stop or unbind:

- Kafka topics containing data.
- RabbitMQ durable queues for consumer groups holding backlog.
- Pulsar durable subscriptions with unacked messages.
- `ExampleBus` streams/shards shared across multiple Pods.
- DLT/DLQ or retry destinations used by other services.

Resources that typically can be released at the local endpoint:

- Consumer/producer clients.
- Network connections and channels.
- Poller threads, schedulers, and thread pools owned by the endpoint.
- Listener callbacks, metric registrations, and timers.
- Transient buffers/caches that do not require recovery.

Even for ephemeral resources, deletion conditions must be transparent. A temporary queue may be auto-deleted by the broker when the last consumer leaves; deleting it prematurely when one Pod scales down can sever another Pod's path.

## 21. Who Owns Cleanup?

Define **resource ownership** across the lifecycle:

| Resource | Owner | Cleanup |
|---|---|---|
| Production topic/stream with retention | Platform/IaC | Infrastructure change workflow with data checks |
| Durable group queue/subscription | Service owner/Platform | Delete only on intentional service decommissioning |
| Retry queues and DLQ/DLT | Service owner | Per retention/replay policy; never delete alongside binding |
| Anonymous temporary consumer | Binder/broker per policy | Auto-delete or controlled cleanup |
| Local producer/consumer client | Binder endpoint | Close/stop on unbind or shutdown |

Deletion logic must distinguish **application-owned** resources from **shared** resources across applications. If multiple producers share a topic, no single producer may delete the topic just because it stops.

To prevent orphan resources, attach metadata labels/tags such as `appName`, `environment`, `ownerTeam`, `provisionedBy`, `createdAt`, and `retentionPolicy`. Cleanup jobs must check live data and protect unprocessed backlogs prior to deletion.

## 22. Scaling From One to Many Instances

Suppose you deploy an app with one input group running three instances:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: fulfillment
          binder: exampleBus
          consumer:
            concurrency: 2
~~~

If `ExampleBus` supports competing consumers on one durable subscription, all three instances join group `fulfillment` and share messages. The provider must still run idempotently on every instance.

If `ExampleBus` requires each consumer to bind to a specific shard, the binder must document how **`instanceCount`** and **`instanceIndex`** prevent shard collisions:

~~~yaml
spring:
  cloud:
    stream:
      instance-count: 3
      instance-index: 1
      bindings:
        processOrder-in-0:
          consumer:
            partitioned: true
~~~

These values illustrate only the second instance (index 1 of 0..2). For RabbitMQ and middleware lacking native partition assignment, index/count usually must be managed explicitly; with Kafka auto-rebalance, the Kafka group coordinator assigns partitions without fixed indices.

**Concurrency does not create extra partitions.** It adjusts concurrent consumers/workers depending on the binder. Partition provisioning and consumer assignment must be designed to match actual middleware behavior.

## 23. Common Scaling Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Second Pod fails startup | Provisioning is not idempotent; `AlreadyExists` treated as fatal | Switch to ensure semantics, verify metadata |
| Consumer instance receives no messages | Wrong group or shard mapping | Check `group`, `instanceIndex`, assignment |
| Messages processed twice after scale-down | Unacked records redelivered | Fix ack/commit timing and idempotency |
| Topic deleted when one Pod stops | Cleanup coupled to `unbind` | Close only local endpoints; separate ownership |
| Backlog disappears after restart | Using anonymous queue/subscription instead of durable group | Declare a stable `group` |
| Partitions lack throughput | Provisioner created too few shards or partition expansion unsupported | Re-evaluate scaling strategy and partition topology |
| Producer partitions inaccurately | `getNameForPartition` mismatches actual routing | Test key → partition and physical destinations |
| Multi-binder uses wrong namespace | Provider or admin client shared across wrong context | Isolate binder instances/environments |
| Startup hangs on broker error | Admin API lacks timeout/retry caps | Enforce bounded timeouts and fail policies |
| Resource mismatch silently ignored | Provider checks only existence | Validate type, partitions, retention, and policies |

## 24. Testing ProvisioningProvider in Isolation

First unit-test the provider with a mocked `ExampleBusAdmin`. Verify it constructs exact names, passes groups/partitions, and wraps exceptions properly.

JUnit/Mockito example:

~~~java
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ProducerDestination;

class ExampleBusProvisioningProviderTest {

    @Test
    void provisionsProducerAndRequiredGroup() {
        ExampleBusAdmin admin = mock(ExampleBusAdmin.class);

        ExampleBusProvisioningProvider provider =
            new ExampleBusProvisioningProvider(
                admin,
                "tenant-a",
                true
            );

        ProducerProperties properties = new ProducerProperties();
        properties.setPartitionCount(4);
        properties.setRequiredGroups("fulfillment");

        ProducerDestination destination =
            provider.provisionProducerDestination(
                "orders.created",
                properties
            );

        assertThat(destination.getName())
            .isEqualTo("tenant-a/events/orders.created");

        verify(admin).ensureStream(
            "tenant-a/events/orders.created", 4
        );

        verify(admin).ensureDurableSubscription(
            "tenant-a/events/orders.created", "fulfillment"
        );
    }
}
~~~

Additional tests should verify:

- Nameless consumer groups are rejected when anonymous mode is unsupported.
- `autoProvision=false` only verifies and never creates.
- Compatible `AlreadyExists` succeeds.
- Incompatible `AlreadyExists` throws `ProvisioningException`.
- Invalid destination names are rejected before calling the broker.
- `ProducerDestination.getNameForPartition` rejects out-of-range partitions.
- The provider never calls delete when provisioning fails.

## 25. Multi-Instance Integration Testing

Unit tests cannot catch every broker semantics issue. Use Testcontainers or an integration environment with real middleware to verify:

1. Two Pods/test contexts provision the same destination concurrently.
2. Both receive the same physical destination and share the durable group.
3. Adding a third consumer does not create a differently named subscription.
4. Messages are produced while all consumers stop; backlog persists.
5. Consumers restart; unacked messages redeliver per middleware policy.
6. One instance stops/unbinds; topics/queues/subscriptions persist and other instances keep running.
7. Increasing partition count per policy does not lose data or corrupt routing.
8. Resources are pre-created via IaC; verify-only boots without create permissions.
9. Intentional type or retention mismatch causes the provider to fail explicitly.
10. Broker unavailable at startup fails within bounded retry/timeout limits.
11. Rejected quota or ACL creates no partial orphaned resources.
12. DLT/DLQ survives restarts and scale-downs.
13. Connection/thread counts stay flat across repeated bind/unbind cycles to catch leaks.

If the custom binder lacks a dedicated Testcontainers module, use `GenericContainer` with the middleware image or a CI-managed ephemeral environment. What matters is exercising the real SDK and provisioning infrastructure; in-memory mocks prove only Java control flow.

## 26. Observing Provisioning and Resource Lifecycle

A custom binder should expose logs/metrics for both provisioning and bindings:

| Metric/log | Question answered |
|---|---|
| `provision_requests_total` by operation | How many creates vs. verifies occurred? |
| `provision_duration_seconds` | How slow is the Admin API? |
| `provision_conflicts_total` | How many `AlreadyExists` races or mismatches occurred? |
| `provision_failures_total` by error code | ACL, timeout, quota, or validation failures? |
| `binder_bindings_active` | How many binding endpoints are active? |
| `producer_publish_failures_total` | Do publishes succeed after provisioning? |
| `consumer_lag` / `unacked` / `subscription_backlog` | Are consumers making progress? |
| `resource_orphans` | Are unowned resources left behind? |
| `consumer_reconnect_total` | Is there a reconnect storm after rollout? |
| `cleanup_requests_total` | Who is deleting resources? |

Do not use raw unbounded destination names as metric labels, as this causes high cardinality. Use `app`, `binder`, `environment`, `errorCode`, and resource type for metrics, while logging exact resource names in controlled logs.

Provisioning logs should capture operation, physical name, group, outcome, elapsed time, and correlation/trace ID if available. Never log credentials, message payloads, or sensitive security data.

## 27. Custom Binder Deployment and Upgrade Process

Before promoting a custom binder to production:

1. Decide resource ownership: platform/IaC vs. binder auto-provisioning.
2. Establish stable naming conventions and versioning rules.
3. Define group semantics: durable, ephemeral, competing consumers, partition assignment.
4. Define partition strategies and how partitions scale up/down.
5. Define create/describe/read/write/delete permissions for each principal.
6. Set timeouts, bounded retries, and error classification on the Admin API.
7. Ensure create-if-absent is idempotent and race-safe under scaling.
8. Define policies for metadata mismatches; never silently drop/recreate.
9. Never couple durable deletion to `Binding.unbind`.
10. Maintain a separate cleanup process with ownership and retention approvals.
11. Test restarts, scaling, failover, backlog retention, and replays.
12. Monitor provisioning latency, failures, backlogs, and orphan resources.

When upgrading a binder, check compatibility across Spring Cloud Stream APIs, Spring Integration APIs, middleware SDKs, and transport protocols. If an upgrade changes naming or partitioning strategies, create a migration plan; do not simply deploy the new version and let the provider create new resources that strand old backlogs.

## 28. References

- [Spring Cloud Stream — Implementing Custom Binders](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-custom-binder-impl.html): guide to `ProvisioningProvider`, `MessageProducer`, `MessageHandler`, `AbstractMessageChannelBinder`, configuration, and `spring.binders`.
- [Spring Cloud Stream — Binder SPI](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-api.html): `bindProducer`, `bindConsumer`, and extension points.
- [Spring Cloud Stream — Binder Abstraction](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-abstraction.html): meaning of bindings and destinations.
- [ProvisioningProvider Javadoc](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-stream/latest/org/springframework/cloud/stream/provisioning/ProvisioningProvider.html): contract and methods of the provisioning SPI.
- [ProducerDestination Javadoc](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-stream/latest/org/springframework/cloud/stream/provisioning/ProducerDestination.html): `getName` and `getNameForPartition`.
- [ConsumerDestination Javadoc](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-stream/latest/org/springframework/cloud/stream/provisioning/ConsumerDestination.html): destination reference for consumers.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): producer/consumer properties, `partitionCount`, `requiredGroups`, `concurrency`.
- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html): `instanceCount`/`instanceIndex` and binder-native partitioning.
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html): `Binding` lifecycle, stop/start, and binding management.
- [Spring Cloud Stream — Using Existing RabbitMQ Destinations](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html): auto-provisioning vs. existing infrastructure options.

**Conclusion:** `ProvisioningProvider` turns Spring Cloud Stream logical destinations into compatible physical resources and returns references for the binder to build endpoints. Under scaling, provision methods can be invoked concurrently across multiple instances, so they must be deterministic, idempotent, and validate metadata. Endpoint lifecycles (`start`, `stop`, `unbind`) must stay decoupled from durable topics, queues, subscriptions, and DLQs. A well-engineered custom binder does more than create resources on first boot—it restarts safely, preserves backlog when Pods stop, avoids conflicts when scaling, and deletes resources only under explicit ownership policies.
