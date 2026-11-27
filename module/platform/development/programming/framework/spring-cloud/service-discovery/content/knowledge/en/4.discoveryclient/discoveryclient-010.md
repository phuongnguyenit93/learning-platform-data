# Limitations of the Common Contract and Provider-Specific Characteristics

Spring Cloud provides abstractions such as `DiscoveryClient`, `ServiceInstance`, `Registration`, and `ServiceRegistry` so applications can interact with a service registry through a relatively unified API. As a result, most consumer code can look up instances by service ID without knowing whether the registry in use is Eureka or Consul.

However, the common contract only standardizes basic operations and information. It does not turn every registry into a system with the same data model, health check mechanism, data freshness, metadata, security policies, or operational capabilities. When an application relies on a specific characteristic of Eureka or Consul, clearly identify that dependency and place it behind an appropriate boundary.

## 1. The common Spring Cloud Discovery contract

The discovery abstractions belong to Spring Cloud Commons. They create an interface layer between a Spring application and a concrete implementation.

### DiscoveryClient: looking up services and instances

`DiscoveryClient` is the read-side API. Commonly used methods include:

- `getServices()`: retrieves the service IDs known to the current implementation.
- `getInstances(serviceId)`: retrieves the instances registered under a service ID.
- `description()`: describes the discovery implementation currently in use.

Example of a consumer that only needs to know the logical name `inventory-service`:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

The code contains no Eureka or Consul URLs. The implementation is configured by Spring Boot through dependencies and application properties. When changing implementations, code calling `DiscoveryClient` typically does not have to change if it only uses capabilities belonging to the common contract.

`getServices()` is useful for diagnostics or internal admin screens, but this list should not be treated as a global catalog with identical meaning across all providers. Data scope can depend on datacenter, namespace, access permissions, caching, and how the implementation filters services.

### ServiceInstance: describing an instance

`getInstances(serviceId)` returns `ServiceInstance` objects. Commonly used shared properties include:

| Property/API | Meaning |
| --- | --- |
| `getServiceId()` | Logical name of the service |
| `getHost()` | Hostname or IP of the instance |
| `getPort()` | Port the instance is serving on |
| `isSecure()` | Indicates whether the instance uses a secure connection per information supplied by the implementation |
| `getUri()` | URI constructed from the instance's connection information |
| `getMetadata()` | Key/value metadata map provided by the implementation |
| `getInstanceId()` | Instance ID if the implementation and API version provide this value |

When building requests, prefer `getUri()` instead of manually concatenating host and port strings. The URI can reflect the HTTP/HTTPS scheme and how the implementation represents the address. When concatenating URLs manually, code easily misses `isSecure()`, IPv6, default ports, or URI rules.

Example converting discovery results into display data:

```java
import java.net.URI;
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InstanceInspector {

    private final DiscoveryClient discoveryClient;

    public InstanceInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> describe(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .stream()
                .map(this::format)
                .toList();
    }

    private String format(ServiceInstance instance) {
        URI uri = instance.getUri();
        return instance.getServiceId() + " -> " + uri
                + ", metadata=" + instance.getMetadata();
    }
}
```

Metadata is a general key/value map, yet key names, semantics, encoded data types, and update behavior are still determined by the provider. Do not assume every provider has the same set of keys such as `zone`, `version`, `weight`, or `health`.

### ServiceRegistry and Registration: registering instances

`ServiceRegistry` is the write-side abstraction. It defines lifecycle operations such as registering, deregistering, reading, or updating registration status. `Registration` describes the information needed for an implementation to register an instance. The concrete registration type depends on the provider.

Distinguishing the two API groups:

| Abstraction | Primary role | Typical caller |
| --- | --- | --- |
| `DiscoveryClient` | Read service IDs and instance lists | Consumers, observability tools |
| `ServiceInstance` | Describe instance address and metadata | Consumers, LoadBalancer |
| `Registration` | Carry registration details of an instance | Provider/registration lifecycle |
| `ServiceRegistry` | Register, deregister, and manage status | Providers, lifecycle integration |

Spring Cloud can automatically register an application on startup and deregister it on shutdown via auto-configuration. Therefore, applications do not necessarily need to call `ServiceRegistry.register()` manually. Only call it manually when there is a special lifecycle management requirement and you understand how the implementation integrates with auto-registration; registering twice can create duplicate data or instance ID conflicts.

## 2. What the common contract does not guarantee

Abstractions reduce vendor coupling in code, but do not guarantee that all behavioral differences disappear.

| Aspect | What the common contract provides | What must not be assumed |
| --- | --- | --- |
| Lookup | Service ID and list of `ServiceInstance` | Every provider returns the same list at the same point in time |
| Ordering | A collection of instances | Returned order is stable or already load-balanced |
| Freshness | Data the implementation currently holds | Results are always the instantaneous state from the authoritative server |
| Health | Instance info published by the implementation | Consul's `passing` is strictly equivalent to Eureka's status |
| Metadata | Key/value map | Same keys, same schema, same encoding rules across all providers |
| Identity | Service ID and basic instance info | Identical name normalization and instance ID rules |
| Scope | Service IDs returned by the implementation | All datacenters, namespaces, or partitions appear in a single result |
| Load balancing | Can be combined with Spring Cloud LoadBalancer | `DiscoveryClient` picks an instance itself or guarantees request success |
| Security | Integrated via configuration and implementation | Identical ACLs, authentication, TLS, and query permissions |
| Lifecycle | Common registration API | Every registry shares the same lease, heartbeat, deregistration, or eviction rules |

The key point is that `DiscoveryClient` only returns discovery data. It does not guarantee an instance will still be alive when a request actually arrives, does not execute business retries by itself, and does not guarantee the registry has converged after a network disruption. Consumers still need timeouts, connection error handling, and appropriate retry policies.

## 3. DiscoveryClient is not LoadBalancer

A common misconception is that calling `DiscoveryClient.getInstances()` amounts to load balancing. In reality, these two tasks are distinct:

1. Discovery finds the instances belonging to a service ID.
2. LoadBalancer selects an instance from the list suitable for the request.
3. The HTTP client sends the request to the selected instance's URI.

An application can fetch the instance list directly for display or diagnostics:

```java
List<ServiceInstance> instances = discoveryClient.getInstances("inventory-service");
```

However, in normal service call paths, let Spring Cloud LoadBalancer integrated with the HTTP client handle instance selection. Do not manually take the first element of the list because ordering is not a load-balancing contract.

Example with `RestTemplate`:

```java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

When using this bean, a URL whose host is a service ID, such as `http://inventory-service/api/items/42`, is processed through LoadBalancer. A discovery implementation and compatible LoadBalancer dependency are required. If you create a plain `RestTemplate` without `@LoadBalanced`, the service name may be treated as a DNS hostname and the request will fail.

LoadBalancer can use components such as `ServiceInstanceListSupplier` to obtain the instance list, apply caching, or filter by attributes. Detailed configuration for suppliers, zone preference, retries, and instance selection algorithms can vary by Spring Cloud version and application.

## 4. Eureka-specific characteristics

Eureka is a registry built on the application and instance model. An application can have multiple instances; clients register instances, send heartbeats to renew leases, and fetch the registry to look up services.

### Identity and metadata

In Eureka, properties commonly focused on include:

- Application name: the application/service name the client registers under.
- Instance ID: the unique identifier of an instance within the application.
- Hostname/IP and port: the address advertised by Eureka.
- Metadata map: key/value pairs configured by the application.
- Status and instance-related URLs: status, health/status page if configured.

Example configuring metadata for a Eureka client:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: 8084

eureka:
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${spring.cloud.client.ip-address}:${server.port}
    metadata-map:
      version: "2.1"
      zone: "zone-a"
      team: "warehouse"
```

Consumers can read metadata through `ServiceInstance.getMetadata()`, provided the Eureka implementation maps those fields into the common map. Still, the `metadata-map` configuration property name is specific to the Eureka client. Do not expect a Consul configuration to share the exact same property name.

### Heartbeats, leases, and self-preservation

Eureka clients send periodic heartbeats to renew leases. If heartbeats stop, the server can mark or evict the instance after the lease expiration and eviction process. The self-preservation mechanism helps curb mass instance removal when the server receives abnormally few heartbeats, such as during a widespread network outage.

Consequently, instance status on Eureka is governed by heartbeats, leases, eviction, and self-preservation. This is a different model from a Consul agent executing HTTP/TCP/script health checks and publishing check states.

### Zones and peer configuration

Eureka has concepts of region and availability zone along with zone-based server list configuration. Clients can prefer a registry in a nearby zone depending on configuration. Eureka peer clusters replicate registries with one another and can temporarily diverge during network interruptions. Reading from one peer should not be treated as proof that all peers hold the exact same state at that moment.

When you need Eureka-specific capabilities such as reading applications/instances via the Netflix API, retrieving specific server details, tuning zone preferences, or inspecting peer status, the `DiscoveryClient` abstraction may not suffice. In that case, use Eureka-specific APIs or properties, isolated inside an adapter.

## 5. Consul-specific characteristics

Consul organizes discovery around a service catalog, nodes, service instances, and health checks. Spring Cloud Consul applications typically communicate with a Consul agent; the agent manages registrations and checks on the node and synchronizes data with the server cluster.

### Service name, instance ID, tags, and metadata

Consul provides tags and metadata for services. Spring Cloud Consul maps its discovery configuration into Consul registrations. Example:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        register: true
        service-name: inventory-service
        instance-id: ${spring.application.name}:${spring.cloud.client.hostname}:${server.port}
        tags:
          - "version=2.1"
          - "team=warehouse"
        metadata:
          release: "2026.11"
          protocol: "http"
        health-check-path: /actuator/health
        health-check-interval: 15s

server:
  port: 8084
```

In this example, `service-name`, `instance-id`, `tags`, `metadata`, and the health-check properties are Spring Cloud Consul configuration. The Consul catalog has its own notions of tags and metadata; when migrating to Eureka, map them intentionally rather than expecting every field to carry over automatically.

### Health checks are a core part of Consul

The Consul agent can run HTTP, TCP, gRPC, or script checks depending on configuration and version. Common check states include `passing`, `warning`, and `critical`. Health-service queries can filter only instances that are `passing`.

For example, Spring Cloud Consul declares an HTTP check to `/actuator/health`. The agent must be able to reach the application's address and port. If the app binds to loopback inside a separate container, an agent outside the container may fail to reach that endpoint even though calls from inside the app succeed.

Consul also has scopes and features such as datacenter, ACL, namespace, or partition depending on edition/configuration. A simple `DiscoveryClient` cannot fully express all of those routing and scoping options.

### Consul catalog and specific APIs

When you need to query by tag, filter by health status, select a datacenter, interact with KV, or enforce ACLs, you must use Consul-specific properties or APIs. `DiscoveryClient.getInstances(serviceId)` only represents a basic lookup by service ID; it has no generic parameters to pass arbitrary Consul filters.

## 6. Comparing Eureka and Consul from the common-contract perspective

| Topic | Eureka | Consul | Implication when using the common abstraction |
| --- | --- | --- | --- |
| Data model | Application and instance | Node, service, service instance, and catalog | Both return `ServiceInstance`, yet origins and underlying fields differ |
| Registration | Client registration and heartbeat | Agent receives registration and manages service/checks | Lifecycle behind the API differs |
| Health | Heartbeat/lease, eviction, self-preservation | Agent runs health checks and updates check state | Statuses do not map one-to-one |
| Metadata | Instance metadata map | Service tags and metadata | Schema must be standardized at the application layer |
| Identity | Application name and instance ID | Service name, node, and service ID/instance ID | Uniqueness and normalization rules may differ |
| Partitioning | Region and availability zone | Datacenter; namespace/partition per config | Service ID does not describe the entire search scope |
| Peers/cluster | Peer replication, eventual consistency | Agent/server cluster, catalog, and query modes | Data freshness and topology differ |
| Security | Deployment-dependent auth/TLS configuration | ACLs, tokens, TLS, and policies | Configuration and permissions cannot be transferred verbatim |
| Extended API | Eureka client/server API | Consul HTTP API, catalog, health, KV | Provider-specific features require dedicated adapters |

This table does not say which provider is better. It shows that the same basic discovery operation can be implemented with different mechanisms and semantics. The choice should be based on requirements for topology, health, consistency, security, operations, and the existing ecosystem.

## 7. Designing applications when provider-specific features are needed

Do not scatter native Eureka or Consul API calls throughout business code. If an application genuinely needs a capability absent from the common contract, create an application-layer interface describing the exact business need, then implement adapters per provider.

For example, suppose the system needs to find healthy instances for a specific service version:

```java
public interface VersionedServiceLocator {

    List<ServiceInstance> findHealthyInstances(
            String serviceId,
            String version
    );
}
```

One adapter can use Eureka metadata to filter `version`; another adapter can use a Consul health query and tags/metadata. Controllers and business services only call `VersionedServiceLocator`, unaware of vendor API details.

Do not write an adapter assuming every provider shares the exact same notion of "healthy." The adapter must clearly define how the provider evaluates health, the data source, update timing, and behavior when the registry is unreachable. If two providers lack equivalent capabilities, the interface should surface the difference or the application should deliberately choose one provider.

### Example filtering metadata via the common contract

If `version` is already mapped into `ServiceInstance.getMetadata()`, you can filter in shared code:

```java
public List<ServiceInstance> findByVersion(
        DiscoveryClient discoveryClient,
        String serviceId,
        String expectedVersion) {

    return discoveryClient.getInstances(serviceId).stream()
            .filter(instance -> expectedVersion.equals(
                    instance.getMetadata().get("version")))
            .toList();
}
```

This snippet is only portable when every implementation registers the exact same `version` key with the same meaning and format. Naming that key is an application convention, not an automatic rule of Spring Cloud. Ensure every provider writes the metadata before consumers filter on this key.

If you need provider-specific health filtering or queries by datacenter, region, zone, or complex tags, use an adapter rather than stuffing provider-specific logic into a shared utility function.

## 8. Caching, data freshness, and error handling

The `DiscoveryClient` contract does not specify a single update latency across all implementations. A registry may cache lists on the client, replicate across peers, or return results under its own consistency mode. Therefore:

- `getInstances()` results can be older than the application's actual state.
- A newly started instance may not appear immediately in every consumer.
- A stopped instance may remain in caches for a period of time.
- A passing health check does not guarantee the application can handle every business request.
- An empty list may result from an unregistered service, wrong service ID, query scope, access permissions, or registry connection failure.

Consumers should handle these situations with timeouts, bounded retries, circuit breakers, and logging including the service ID/instance URI. Retries must avoid amplifying load when the registry or provider is experiencing an outage. For non-idempotent operations, have duplicate-execution safeguards before retrying automatically.

Do not hold onto a `ServiceInstance` indefinitely and reuse it as an immutable address. If the application needs its own cache, give it an expiration and proper refresh policy, or use the cache/refresh mechanism supported by Spring Cloud LoadBalancer in your project's version.

## 9. Choosing the common API or a provider-specific API

| Need | Recommended approach |
| --- | --- |
| Get instances by service ID | Use `DiscoveryClient` |
| Read host, port, URI, and basic metadata | Use `ServiceInstance` |
| Call a service and select an instance | Use Spring Cloud LoadBalancer with an HTTP client |
| Standard-lifecycle register/deregister | Let auto-configuration manage it or use `ServiceRegistry` when needed |
| Filter metadata by an application-defined schema | Use `getMetadata()` after standardizing keys/values |
| Select by Consul-specific tags or health states | Use a Consul adapter/API |
| Read Eureka-specific applications, zones, or peer states | Use a Eureka adapter/API |
| Need equivalent behavior when switching providers | Define the intersecting feature set and run contract tests on each implementation |

A helpful rule of thumb is to keep the bulk of service-calling flows on the common abstraction, extending to provider-specific APIs only where concrete requirements demand it. This keeps consumer code easy to evolve without hiding differences that directly affect correctness.

## 10. Testing compatibility across providers

If an application plans to support multiple registries, have contract tests running against each implementation. Tests should not merely confirm that the `DiscoveryClient` bean exists, but verify the behaviors the application actually depends on.

Example test scenarios:

1. Register a provider with the agreed service ID.
2. Look up the service ID and confirm at least one instance is returned.
3. Verify the returned URI has the expected scheme, host, and port for the test environment.
4. Verify the metadata required by the application uses the same keys and format.
5. Mark an instance unhealthy in the way supported by the provider and verify the consumer does not select it according to the defined policy.
6. Stop the provider or disconnect the registry, then observe detection time and consumer behavior.
7. Restart the provider and verify the registry/consumer converge within an acceptable time bound.

Do not write a test expecting the exact same failure-detection time or identical intermediate states for both Eureka and Consul if the two providers have different health/lease configurations. Verify the application's observable requirements while setting appropriate thresholds for each implementation.

## 11. Common design mistakes

| Practice | Risk | How to improve |
| --- | --- | --- |
| Using `getInstances().get(0)` for load balancing | Relies on unguaranteed ordering | Use Spring Cloud LoadBalancer |
| Treating metadata as a universal registry schema | Missing keys or altered semantics when switching providers | Define an application schema and test adapters |
| Treating provider health statuses as equivalent | Risk of calling an instance that fails requirements | Standardize health policies at the application layer |
| Hardcoding native Eureka/Consul URLs in business code | Hard to switch implementations and hard to test | Use abstractions or well-scoped adapters |
| Using `localhost` as the advertised address in containers | Other consumers cannot connect | Advertise a routable hostname/IP |
| Caching instance URIs indefinitely | Calling addresses that were replaced or deregistered | Use refresh/TTL and handle connection errors |
| Assuming an empty list definitely means the service is down | Misses permission, scope, or registry connection errors | Check logs, registry URL, scope, and credentials |
| Reusing the same instance ID across multiple replicas | Registrations can overwrite or conflict | Combine hostname/IP, port, or a unique ID |

## 12. Checklist when using DiscoveryClient

- [ ] Code uses `DiscoveryClient` only for basic lookup operations.
- [ ] Code uses `ServiceInstance.getUri()` when a service call address is needed.
- [ ] Does not rely on instance list order to pick a server.
- [ ] Load balancing is delegated to Spring Cloud LoadBalancer or an equivalent component.
- [ ] Metadata has an application-defined schema written consistently by all providers.
- [ ] Defined how each provider evaluates health and excludes failing instances.
- [ ] Defined discovery scope such as region, zone, or datacenter.
- [ ] Native Eureka/Consul APIs are isolated inside adapters.
- [ ] Consumers handle stale data, empty lists, timeouts, and registry errors.
- [ ] Contract tests run against each provider the application claims to support.

`DiscoveryClient` gives Spring Cloud applications a common entry point for finding service instances. The value of this abstraction lies in reducing coupling to specific APIs in ordinary business flows. When provider-specific health semantics, metadata, topology, or management capabilities are needed, the application must make those differences explicit and integrate deliberately. A sound design keeps basic communication on the common contract while preserving important provider characteristics through adapters and contract tests.
