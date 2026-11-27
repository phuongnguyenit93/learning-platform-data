# Limiting the Dynamic Destination Cache and Controlling Target Counts

`StreamBridge` enables an application to send messages to a destination determined at runtime. This is useful when an HTTP request, an external system event, or a business rule decides where a message should go. However, if every input value can create a new destination, the application must manage the number of dynamic bindings, and broker resources can grow rapidly.

Spring Cloud Stream provides two important control mechanisms: limiting the dynamic output binding cache with `spring.cloud.stream.dynamic-destination-cache-size`, and restricting destination names allowed to be bound dynamically with `spring.cloud.stream.dynamic-destinations`. The cache mechanism controls how many bindings are kept in the application's memory; the allowlist controls which destinations are permitted to be dynamically bound. The two mechanisms solve different problems and should be used alongside bounded routing rules.

## 1. When do dynamic destinations appear?

With a pre-declared output binding, the application knows the binding name and destination right from configuration time. `StreamBridge` can send data through that binding without creating a new binding for each send.

When the sending target is only determined at runtime, the application can call `StreamBridge.send(...)` with a destination name that has no binding yet. Spring Cloud Stream creates a dynamic output binding for that target and stores the binding in a cache so subsequent sends can reuse it.

Example of an API receiving an event and choosing a destination by region:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

public record OrderCreated(String orderId) {}

@Service
public class OrderPublisher {

    private final StreamBridge streamBridge;

    public OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String destination, OrderCreated event) {
        return streamBridge.send(destination, event);
    }
}
```

In the example, the first parameter of `send` is the binding or destination name that `StreamBridge` will use. If that name is not yet a declared binding, it can be handled as a dynamic destination. Do not pass an arbitrary string directly from an external request into this parameter; a later section builds the mapping and input control layer.

## 2. Distinguishing binding cache and broker resources

When a dynamic destination is used, there are two resource layers to distinguish:

| Layer | Example | Management mechanism |
| --- | --- | --- |
| Application-side binding/channel | Output binding and message channel used by `StreamBridge` to send | Spring Cloud Stream's dynamic cache keeps a number of bindings for reuse and evicts old entries when the limit is exceeded |
| Broker-side destination | Kafka topic, RabbitMQ exchange/queue, or Pulsar topic | Binder and broker manage provisioning, access permissions, lifecycle, and resource deletion |

The dynamic cache is not the maximum list of topics the broker is allowed to have. When an entry is evicted from the cache, that binding may need to be recreated if the application sends to that destination again. Evicting a binding from the cache does not mean the corresponding Kafka topic, RabbitMQ exchange/queue, or Pulsar topic has been deleted from the broker.

Therefore, increasing cache size is not a direct solution for having too many topics or queues. To control the number of broker resources, restrict valid destinations, design resource lifecycles, and configure provisioning appropriately for the binder.

## 3. Bounded dynamic cache and LRU mechanism

Spring Cloud Stream uses an evicting cache for dynamic output bindings. The default size is **10**. The cache uses a Least Recently Used (LRU) policy: when the limit is reached and a new destination needs to be added, the least recently used entry can be evicted from the cache.

Configuration property:

```yaml
spring:
  cloud:
    stream:
      dynamic-destination-cache-size: 32
```

The value `32` is an example, not a recommended level for every application. The appropriate size depends on the number of frequently used destinations, number of application instances, target switching frequency, and binding recreation cost.

For example, if an instance frequently sends to 8 destinations and the cache size is 10, most bindings can be reused. If the instance cycles through 100 destinations with a cache size of 10, many bindings will be evicted and must be recreated the next time they are used. This increases initialization, provisioning, or connection costs, depending on the binder.

### How to choose a cache size

Start from the *working set* — the number of distinct destinations an instance actually uses frequently over a representative period:

1. Measure the number of active destinations during peak hours.
2. Identify targets accessed repeatedly vs. targets used only once.
3. Choose a cache large enough for the frequently active target set, with reasonable headroom.
4. Monitor binding recreation frequency and memory usage after deployment.
5. Adjust according to instance count and traffic distribution.

You do not necessarily have to set the cache equal to the total number of destinations that could possibly exist. A system with an allowlist of 500 targets where each instance stably uses 20 targets over a period can size the cache for the working set after measuring eviction and binding recreation costs.

## 4. Restricting destinations allowed for dynamic binding

The `spring.cloud.stream.dynamic-destinations` property allows declaring a list of destinations that can be bound dynamically. If the list is configured, only destinations whose names appear in the list are allowed to bind. If left empty or unconfigured, this allowlist does not impose a limit by default.

Example:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders-north
        - orders-central
        - orders-south
        - orders-international
      dynamic-destination-cache-size: 16
```

The list above restricts which names can be dynamically bound. The cache of size 16 retains recently used bindings; since the allowlist has only 4 names in the example, the cache will not fill up from these valid targets alone.

If the allowlist has more targets than the cache size, that is still valid: the application is only allowed to bind names in the allowlist, while the cache keeps a subset of recently used bindings. When an evicted target is called again, its binding may need to be recreated.

An allowlist is an important control layer, but input validation in code is still needed. It does not replace caller authentication, per-tenant authorization, or checking whether a user is allowed to publish to a specific data region.

## 5. Mapping external input to a fixed set of destinations

A common design flaw is concatenating a request value directly into a topic name:

```java
// Avoid: input values can create an unbounded number of destination names.
String destination = "orders-" + request.tenantId();
streamBridge.send(destination, event);
```

If `tenantId` can be any string, the number of potential target names is unbounded. Callers could also accidentally or intentionally create destinations outside the business scope.

Instead, map a validated business key to a managed set of target names:

```java
import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class RegionalOrderPublisher {

    private static final Map<String, String> DESTINATIONS = Map.of(
            "north", "orders-north",
            "central", "orders-central",
            "south", "orders-south"
    );

    private final StreamBridge streamBridge;

    public RegionalOrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String region, OrderCreated event) {
        String destination = DESTINATIONS.get(region);
        if (destination == null) {
            throw new IllegalArgumentException("Unsupported region: " + region);
        }

        return streamBridge.send(destination, event);
    }
}
```

With this approach, `region` can only select one of the three defined destinations. The allowlist configuration also only needs to contain the three corresponding names. If a new region is added, the development team updates the mapping, allowlist, broker permissions, and provisioning process in a single reviewable change.

In a multi-tenant application, you do not necessarily have to create one destination per tenant. You can use a shared destination and put `tenantId` in the payload or header for consumer partitioning and processing. Choose a destination-per-tenant model only when there are explicit requirements for data isolation, access control, retention, throughput, or separate lifecycles.

## 6. Complete configuration for StreamBridge

The following example combines the allowlist and cache size with the regional mapping service above:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders-north
        - orders-central
        - orders-south
      dynamic-destination-cache-size: 16
      bindings:
        orders-north:
          content-type: application/json
        orders-central:
          content-type: application/json
        orders-south:
          content-type: application/json
```

Bindings can be created dynamically when `StreamBridge` first sends to the corresponding name. Depending on how bindings are declared and the Spring Cloud Stream version, additional per-target producer properties or binders can be configured. If a set of targets is already known and needs to be initialized at application startup, consider declaring explicit output bindings instead of waiting for the first send.

The binding/destination name passed to `send` in code must be consistent with the allowlisted and configured name. Verify the exact name actually used by the binder, especially when the application has multiple binders or multiple clusters.

## 7. Choosing between fixed bindings and dynamic destinations

Not every routing scenario requires creating dynamic destinations.

| Scenario | Suitable approach | Reason |
| --- | --- | --- |
| Sending to only one audit topic | Fixed output binding | Target name known in advance, no dynamic cache needed |
| Sending to 3 known regions | Fixed output bindings or StreamBridge with allowlist | Small and stable target set |
| Sending to a destination set changing per admin config | Dynamic StreamBridge with controlled allowlist | Targets change yet remain bounded |
| Every request can invent arbitrary target names | Disallow directly; map or reject | Avoids unbounded cardinality and resource abuse |
| Only need to distinguish tenants in the same stream | One shared destination, tenant ID in payload/header | Avoids creating too many topics or queues |

For a finite and stable destination set, fixed bindings keep configuration clear, making permission checks and observability easier. Dynamic destinations fit when target selection is genuinely only known at runtime and the benefits outweigh binding management overhead.

## 8. Cache size is neither a tenant limit nor a total topic limit

Three numbers are frequently confused:

- **Cache size:** maximum number of dynamic bindings retained in a single application instance's cache.
- **Allowlist size:** number of destinations the application is allowed to bind dynamically per configuration.
- **Broker destination count:** total number of topics, exchanges, queues, or equivalent resources existing on the broker.

For example, configuring a cache size of 20 and an allowlist of 100 names means an instance keeps at most 20 recent bindings in its cache, yet can still cycle through all names in the allowlist. Depending on the binder and provisioning permissions, created broker resources may continue to exist after a binding is evicted from the cache.

If business requirements limit total tenants, total topics, or total queues, enforce those limits at the business management and broker layers. Do not use cache size as a tenant counter or a resource quota mechanism.

## 9. Impact when running multiple instances

The dynamic cache lives inside the application process. When deploying multiple replicas, each replica has its own cache and can hold different bindings depending on the traffic it receives.

If the cache size is 32 and the service runs 5 replicas, the total number of bindings held in memory across all replicas can exceed 32; the configured number applies per instance, not as a cluster-wide shared cache. Therefore, capacity planning must account for both replica count and each replica's working set.

When autoscaling creates or stops instances, a new instance's cache starts empty; destinations called for the first time on that instance may need binding initialization. This can increase binding overhead during scale-out. Monitor binding creation time and broker provisioning capacity in this situation.

## 10. Notes on broker provisioning and destination lifecycle

Having `StreamBridge` create a binding does not guarantee every broker always auto-creates resources the same way. The binder can auto-provision destinations if configured and granted appropriate permissions, or require resources to be pre-created.

With Kafka, destinations are typically topics; topic creation can depend on broker config, ACL permissions, and governance policies. With RabbitMQ, the binder works with exchanges, queues, and bindings between them; queue counts can grow with consumer groups or consumer config. With Pulsar, destinations are typically topics and subscriptions with separate lifecycles.

Eviction from the application cache should not be used as a signal to delete broker resources. If a topic, queue, or subscription needs deletion, use a separate controlled provisioning/deprovisioning process, considering retention, active consumers, and data recovery capabilities.

## 11. Safety and authorization when selecting destinations

Dynamic destinations create an important boundary: input data can influence where messages are sent. Design the routing layer as part of your access policy:

1. Authenticate callers before accepting send requests.
2. Check whether the caller has permission to publish to the corresponding region, tenant, or event type.
3. Map external values to defined internal destination names.
4. Reject names not present in the mapping and allowlist.
5. Do not let clients directly submit topic, exchange, or queue names if they are not authorized to manage routing.
6. Configure broker ACLs/credentials following the principle of least privilege.
7. Log routing decisions using normalized region or target codes, avoiding logging sensitive payloads.

The allowlist in `spring.cloud.stream.dynamic-destinations` limits which destinations are dynamically bound in the framework. It does not authenticate users on its own and does not replace Kafka, RabbitMQ, or Pulsar ACLs.

## 12. Monitoring eviction and performance

A cache too small for the working set can cause churn: bindings are repeatedly evicted and recreated. A cache too large keeps more bindings and resources in the process than necessary. Monitor these signs:

- Number of distinct dynamic destinations used within a time window.
- Frequency of new binding creation and time to bind successfully.
- Eviction frequency or signs that a destination is frequently recreated.
- Heap usage and number of active channels/bindings.
- Send failure rate, send latency, and provisioning errors from the broker.
- Actual count of topics, queues, exchanges, or subscriptions on the broker.

Do not simply increase cache size when latency increases. First determine whether the latency comes from binding recreation, broker connections, serialization, broker overload, or network errors. If the root cause is uncontrolled destination growth, reduce cardinality via mappings and allowlists.

## 13. Testing destination limits

There should be tests for both the business mapping layer and sending behavior:

### Unit tests for mapping

Verify valid keys return the expected destination name, while invalid keys are rejected. This catches routing bugs early and prevents arbitrary input from becoming a destination name.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.stream.function.StreamBridge;

record OrderCreated(String orderId) {}

class RegionalOrderPublisherTest {

    @Test
    void rejectsUnknownRegion() {
        StreamBridge bridge = org.mockito.Mockito.mock(StreamBridge.class);
        RegionalOrderPublisher publisher = new RegionalOrderPublisher(bridge);

        assertThrows(IllegalArgumentException.class,
                () -> publisher.publish("unknown", new OrderCreated("O-1")));
    }
}
```

The snippet is an illustrative skeleton; the project's constructors and records must match the actual model. Additional tests can verify that valid regions call `streamBridge.send` with the right destination.

### Testing allowlist configuration

Start an application context with a `dynamic-destinations` list and verify that sending to a destination in the list works, while unlisted names are rejected when the binder performs dynamic binding. This test should run with the Spring Cloud Stream version and binder used by the application.

### Testing cache and broker

In integration tests, send round-robin to more destinations than the cache size, then send again to a previously used destination. Verify the application can still send and observe the cost of binding recreation. Do not use the test binder to conclude that broker resources are created/deleted properly, because provisioning and resource lifecycles must be tested against a real broker or equivalent environment.

## 14. Selection and operations workflow

When designing a flow that uses dynamic destinations, follow this sequence:

1. Determine whether dynamic destinations are truly needed or if fixed output bindings can be used.
2. Define the set of valid destinations and who has authority to change that set.
3. Map input data to normalized destinations; reject invalid values.
4. Configure `spring.cloud.stream.dynamic-destinations` to restrict bindable names.
5. Measure the working set and choose an appropriate `spring.cloud.stream.dynamic-destination-cache-size`.
6. Determine whether the binder auto-provisions destinations and what broker permissions are needed.
7. Test eviction, binding recreation, send errors, and scale-out.
8. Monitor cache churn, heap, latency, and broker resource counts.
9. Manage creating/deleting broker resources through a separate process.

## References

- [Spring Cloud Stream — Producing and Consuming Messages: StreamBridge and Dynamic Destinations](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Service Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-service-properties.html)
- [Spring Cloud Configuration Properties — dynamic-destination-cache-size and dynamic-destinations](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)

Consult the documentation for the release train your project uses before applying configurations to production, as properties and binder behavior may change across versions.

## Conclusion

`spring.cloud.stream.dynamic-destination-cache-size` limits the number of dynamic output bindings kept in each instance's LRU cache; the default is 10. `spring.cloud.stream.dynamic-destinations` restricts which destination names can be dynamically bound when configured. Cache size, allowlist size, and total broker resources are three distinct concepts. Combining an allowlist, mapping input to a finite target set, capacity planning by working set, and separate provisioning management allows `StreamBridge` to route flexibly while keeping memory, performance, and destination counts under control.
