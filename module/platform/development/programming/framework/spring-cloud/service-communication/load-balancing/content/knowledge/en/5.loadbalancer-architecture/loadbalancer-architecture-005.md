# ServiceInstanceListSupplier in the Instance Provisioning Chain

Spring Cloud LoadBalancer needs to know which instances can serve a request before choosing a specific instance. The component providing that list is `ServiceInstanceListSupplier`. It sits between the service discovery source and the instance selector: it retrieves a list of `ServiceInstance` items, optionally caches or filters the list by health, zone, or request context, and supplies the candidates to LoadBalancer.

This lesson belongs to the **LoadBalancer Architecture** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. The module focuses on client-side load balancing: selecting a `ServiceInstance` by service ID, discovery, health checks, and routing policies; integrating `RestClient`, `WebClient`, and OpenFeign; configuring retries/timeouts; and observing errors. Understanding `ServiceInstanceListSupplier` helps you trace where the candidate list comes from, why certain instances are excluded, and why selection results can vary between requests.

After this lesson, you will be able to:

- Place `ServiceInstanceListSupplier` in the right spot within Spring Cloud LoadBalancer's processing flow.
- Distinguish providing the instance list from selecting a single instance.
- Explain how a discovery client, caching, health checks, and filters combine into a supplier chain.
- Configure a supplier per service using `@LoadBalancerClient`.
- Understand when to use zone, hint, or request context information to filter candidates.
- Test supplier lists and investigate empty lists, stale data, or unavailable instances.

## 1. Where ServiceInstanceListSupplier Fits in the Architecture

One service calls another using a logical name, such as `inventory-service`. This name is the service ID. The discovery client queries registered replicas for that service ID and obtains `ServiceInstance` objects. Each instance holds connection details such as host, port, secure flag, metadata, and service ID.

Spring Cloud LoadBalancer needs a candidate list so the instance selector can decide where to send a request. `ServiceInstanceListSupplier` is responsible for providing this list.

~~~mermaid
flowchart LR
    A["HTTP client calls inventory-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["Discovery source"]
    D --> E["ServiceInstance list"]
    E --> F["Cache / health / zone / request filters"]
    F --> G["Final candidate list"]
    G --> H["LoadBalancer selects an instance"]
    H --> I["HTTP request to host:port"]
~~~

The flow can be separated into two questions:

1. **Which instances are allowed to be candidates?** The supplier chain answers this by fetching and transforming the list.
2. **Among those candidates, which instance is selected for the current request?** The LoadBalancer algorithm, such as round robin or random, answers this.

The supplier does not send HTTP requests itself, nor is it the round-robin algorithm. It prepares the input list for the instance selector. Once an instance is chosen, LoadBalancer replaces the service ID in the URI with that instance's address so the HTTP client can send the request.

## 2. What Data Does ServiceInstanceListSupplier Provide?

`ServiceInstanceListSupplier` is an abstraction in Spring Cloud LoadBalancer. From a usage standpoint, it exposes the service ID and a stream of `ServiceInstance` lists. The API has a standard method to retrieve the list and an overload that can accept a request context:

~~~java
String getServiceId();

Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
~~~

This represents the conceptual shape of the API; the reactive `Flux` return type lets the supplier emit lists in a way compatible with LoadBalancer's pipeline. The `get(Request request)` method allows a supplier to inspect the request context when filtering candidates. Default implementations may ignore the request context when per-request filtering is unnecessary.

A `ServiceInstance` typically provides information such as:

| Field | Meaning |
|---|---|
| `serviceId` | Logical service to which the instance belongs. |
| `host` | Hostname or IP address of the replica. |
| `port` | HTTP/HTTPS port of the replica. |
| `isSecure()` | Indicates whether the instance uses a secure connection. |
| `metadata` | Additional attributes such as zone, version, rack, or weight. |
| `instanceId` | Instance identifier if provided by the discovery implementation. |

For example, discovery might return three instances of `inventory-service`:

~~~text
inventory-service -> 10.0.1.21:8080, zone=zone-a
inventory-service -> 10.0.1.22:8080, zone=zone-a
inventory-service -> 10.0.2.31:8080, zone=zone-b
~~~

The supplier may return all three instances, or a downstream decorator may filter the list based on conditions. The final output serves as the input to the LoadBalancer algorithm.

## 3. List Source: Service Discovery

In applications using Eureka, Consul, or another discovery system, the discovery client queries the registry to find replicas for a service ID. The base supplier converts results from the discovery client into the `ServiceInstance` list that LoadBalancer understands.

Common sources include:

- **Discovery client**: dynamically fetches instances from a registry. The list changes as services register, deregister, or change status.
- **Reactive discovery client**: supplies data through a reactive discovery API when the application uses that client type.
- **SimpleDiscoveryClient**: a lightweight configuration-backed source, often useful in development or testing when declaring static instances in configuration.
- **Custom source**: an application can implement its own supplier to retrieve instances from an internal system or another data source.

Example configuration using SimpleDiscoveryClient:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
                metadata:
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

With a static source, the instance list does not automatically reflect live process status. If a port stops serving traffic, configuration can still list that address until updated. For environments with frequently changing replicas, a discovery registry and proper status updates become essential.

Keep in mind that `ServiceInstanceListSupplier` does not have to query the registry directly on every request. It can read from cache, from a static source, or from another supplier. The underlying supplier and the decorators stacked on top determine how the list is produced.

## 4. The Supplier Chain and Decorator Pattern

A supplier chain typically consists of a base supplier wrapped by one or more outer suppliers. The base supplier retrieves the initial list; subsequent suppliers delegate to the previous supplier and layer on behavior such as caching or filtering.

Example of a list passing through the chain:

~~~text
Discovery client
    |
    v
[instance A, instance B, instance C]
    |
    v
Caching supplier
    |
    v
[instance A, instance B, instance C]  (cached data)
    |
    v
Health-check supplier
    |
    v
[instance A, instance C]              (instance B is unhealthy)
    |
    v
Zone-preference supplier
    |
    v
[instance A]                          (prefers caller's zone)
    |
    v
LoadBalancer algorithm
    |
    v
Select instance A
~~~

This is an example illustrating a single evaluation pass. The actual list depends on the configured suppliers, metadata, and instance status.

Wrapping suppliers typically follow delegation: holding a reference to a delegate supplier, calling `get()` or `get(request)` on the delegate, and transforming the returned list. This pattern lets you compose multiple policies without rewriting discovery querying logic.

**Ordering in the chain matters.** For example, caching should directly wrap the discovery source so upper filters operate on the cached list. If caching is placed outside a request-dependent filter, a list filtered for a previous request could be reused in the wrong context for a subsequent request. With request-context-aware suppliers, pay close attention to what data is cached and at which layer.

Not every application needs every decorator. Start with an appropriate discovery source, and only add caching, health checks, or filters when operational requirements genuinely call for them.

## 5. Common Suppliers

Spring Cloud LoadBalancer provides suppliers and decorators for common requirements. Exact class names and configuration options can vary across Spring Cloud versions; verify against the dependency version in your project when implementing.

| Supplier / Feature Group | Role |
|---|---|
| Discovery client supplier | Fetches the instance list from a discovery client. |
| Caching supplier | Caches the instance list to reduce discovery queries. |
| Health-check supplier | Checks instance readiness/health and removes unhealthy instances from eligible candidates. |
| Zone-preference supplier | Prefers instances in the same zone as the caller when zone metadata is available. |
| Hint-based supplier | Filters or prioritizes candidates using hints attached to the request and metadata. |
| Same-instance preference | Can prefer reusing a previously selected instance within a suitable context. |
| Request-based sticky-session supplier | Supports session-affine selection based on request/cookie data per configuration. |
| Weighted supplier | Uses weight metadata to influence the candidate set or selection as supported by the version. |
| Retry-aware supplier | Can exclude previously attempted instances in a retry context so the next attempt picks another candidate. |

Do not treat all of these features as an always-on default chain. Some suppliers only make sense when corresponding metadata, request context, or configuration is present. For instance, zone preference requires knowing both the caller's zone and the instances' zones; weighted selection requires declared weights and a supporting algorithm; sticky sessions require a mechanism to pass and read session info.

### Caching Supplier

Discovery may be queried frequently, whereas the instance list does not usually change on every request. A caching supplier stores results for a period to reduce registry load and lookup latency.

Caching improves performance but introduces update lag. When an instance is newly added or deregistered, the cache may not reflect the change until the next refresh.

When configuring caching, consider:

- A TTL aligned with how fast instances churn.
- Cache capacity and eviction policy.
- Whether caching is already provided by Spring Cloud LoadBalancer or by the discovery client.
- Risk of stacking multiple cache layers causing stale data to persist longer than expected.
- How the application behaves when the registry is temporarily unreachable.

Spring Cloud LoadBalancer supports cache integration through appropriate configuration and dependencies. If using Caffeine or another cache provider, ensure the dependency and cache manager are configured properly. Do not enable extra caching simply because an example shows it; first verify what caching is already active.

### Health-Check Supplier

An instance may still appear in the registry even if the application has stopped serving traffic or part of its functionality is broken. A health-check supplier can actively probe an instance's health endpoint and only expose instances considered healthy under the policy.

Health checks must be configured consistently with the actual endpoint. If the application uses Spring Boot Actuator, choose the appropriate health path and ensure that endpoint is reachable from the component performing the probe.

Distinguish supplier health checks from registry-managed health status. Both mechanisms can coexist, but inconsistent configuration can cause duplicate checks or cause an instance to be excluded even when healthy. The health endpoint must also accurately reflect service readiness; an endpoint returning a trivial HTTP 200 does not necessarily prove critical dependencies are operational.

### Zone Preference

In multi-zone deployments, instance metadata can include a zone, such as `zone-a` or `zone-b`. A zone-preference supplier prioritizes instances in the same zone as the caller when matching candidates exist.

The goal is to reduce network latency and cross-zone data transfer costs. If no same-zone instances exist, fallback behavior depends on how the supplier is configured; verify the policy rather than assuming all versions fall back identically.

Zone preference only works when instance zone metadata and client zone configuration are aligned. If a zone name is misspelled or metadata is missing, the supplier may fail to find same-zone instances.

### Hints and Request Context

A request can carry a hint to target a specific group of instances, such as requests intended for a canary version or a particular zone group. A supplier capable of reading the request context can use that hint to filter the list.

Clarify where the hint originates, who is allowed to send it, and how server metadata is tagged by convention. Never use values sent by untrusted callers to unlock access to sensitive instance groups. If filtering produces an empty list, requests may fail due to no remaining candidates; define a fallback policy aligned with business requirements.

## 6. Configuring Suppliers per Service

Spring Cloud LoadBalancer supports per-service configuration via `@LoadBalancerClient` or `@LoadBalancerClients`. This is useful when `inventory-service` requires zone preference while `pricing-service` only needs discovery and caching.

Example supplier configuration for `inventory-service`:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryLoadBalancerConfiguration.class
)
class InventoryLoadBalancerClientRegistration {
}

@Configuration(proxyBeanMethods = false)
class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .withHealthChecks()
            .withZonePreference()
            .build(context);
    }
}
~~~

This example demonstrates a chain with discovery as the source, caching directly over discovery, followed by health checks and zone preference. Builder methods and discovery implementations must match the Spring Cloud version and discovery client type in your project. If the application uses a reactive discovery client or a specific blocking discovery client, choose the corresponding base supplier per that version's API.

An important note: the configuration class referenced by `@LoadBalancerClient` should be placed outside the application's standard component scan scope, or excluded from component scanning. LoadBalancer configuration is loaded inside a per-service child context. If this configuration accidentally becomes global, custom beans may affect other services unexpectedly.

Do not declare multiple competing `ServiceInstanceListSupplier` beans for the same LoadBalancer context without explicit intent. Ensure each service has a single final chain used by LoadBalancer.

## 7. Request-Aware Suppliers and Candidate Filtering

The `get(Request request)` method lets a supplier receive request information instead of merely returning a static list. The request context can carry hints or metadata understood by a specialized supplier.

General processing flow:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant L as LoadBalancer
    participant S as ServiceInstanceListSupplier
    participant D as Discovery
    C->>L: Request to service ID + context
    L->>S: get(request)
    S->>D: Fetch instance list if needed
    D-->>S: Instance list
    S->>S: Apply cache / health / metadata filters
    S-->>L: Candidate list
    L->>L: Select an instance
    L-->>C: Selected instance
~~~

For example, a system may carry `zone` and `version` metadata on each instance. A request might ask for version `v2`. Based on the request context and metadata, the supplier prioritizes or restricts matching candidates. If no instance satisfies the constraint, the application must decide whether to fall back to another version or return an error. That decision is a business and deployment policy and should not happen accidentally.

For a custom filter, use the delegate pattern:

1. Accept the base supplier in the constructor.
2. Invoke `get(request)` on the delegate to preserve the request context.
3. Filter or sort the list according to agreed metadata conventions.
4. Return the resulting list; do not perform HTTP calls inside the supplier.
5. Define clear behavior when the result is empty and write tests for that case.

Do not mutate a shared list returned from a cache in place. Create a new result list when filtering so you do not alter data that other concurrent requests may be reading.

## 8. The Supplier and Instance Selection Algorithm Are Two Separate Steps

Suppose the supplier chain returns three candidates:

~~~text
[A, B, C]
~~~

Round-robin might select A, then B, then C across subsequent calls. Random might pick any candidate from the list. The selection algorithm does not inherently know which instance is in a closer zone or healthier unless those constraints are already reflected in the list or the selection strategy.

This can be visualized as:

~~~mermaid
flowchart TD
    A["Discovery returns A, B, C, D"] --> B["Supplier chain"]
    B --> C["Filter out B because health check failed"]
    C --> D["Prefer A, C in the same zone"]
    D --> E["Final list: A, C"]
    E --> F["RoundRobinLoadBalancer"]
    F --> G["Select A or C"]
~~~

If the final list contains only one instance, regardless of whether the algorithm is round robin or random, that instance becomes the sole candidate. If the list is empty, LoadBalancer has no instance to send the request to. The application must handle the no-available-instance error while observing why the supplier eliminated all candidates.

The supplier also does not replace retries. A retry-aware supplier can help exclude an already tried instance during a retry context so the next attempt picks a different candidate, but retry policies, attempt limits, timeouts, and request idempotency still need to be configured in the corresponding retry mechanism.

## 9. Testing ServiceInstanceListSupplier

Supplier tests should focus on the inputs and outputs of each stage. You can construct mock instances with varying hosts, ports, and metadata to verify filters behave as expected.

Cases to test:

| Case | Expected Outcome |
|---|---|
| Discovery returns multiple instances | Base supplier provides the right service ID and list. |
| Cache is still valid | Multiple reads reuse the cached result per configuration. |
| Instance is marked unhealthy | Health-check supplier excludes the instance according to policy. |
| Same-zone instances exist | Zone preference prioritizes the same-zone group. |
| No same-zone instances exist | Fallback behavior matches configuration and version. |
| Request carries a hint | Request-aware supplier filters or prioritizes by hint. |
| No matching instances exist | Returns an empty list or falls back per designed policy. |
| Discovery updates the list | Cache refreshes after the appropriate TTL/refresh interval. |

A useful integration test registers two or three instances under the same service ID, calls them through a `@LoadBalanced` HTTP client, and records the instance ID from the response. This verifies that discovery, the supplier chain, the selection algorithm, and URI substitution all work together.

When testing caching, do not test only the first call. Also test behavior after the registry adds or removes an instance, after TTL expiration, and when the cache cannot fetch fresh data. When testing health checks, simulate an unresponsive health endpoint to confirm instances are handled per policy.

## 10. Observing and Troubleshooting Common Errors

When requests fail to reach a service or only certain replicas receive traffic, inspect the list before and after each step in the supplier chain.

Common symptoms include:

- **No instances:** wrong service ID, instance not registered in discovery, registry unreachable, or supplier filters eliminated all candidates.
- **Stale instance still selected:** cache TTL is too long, multiple cache layers exist, or the registry has not updated status yet.
- **Unhealthy instance still selected:** health-check supplier is not enabled, health path is wrong, or the health check does not reflect necessary readiness state.
- **Only same-zone instances selected:** may be intended zone-preference behavior; verify fallback when that zone has no remaining instances.
- **Request hint has no effect:** client did not pass the request context, supplier is not reading the right context type, or metadata does not match.
- **One service is affected by another service's configuration:** LoadBalancer configuration may have been component-scanned and applied outside its intended scope.

Log or emit enough metrics to answer:

- Which service ID is being requested?
- Which supplier chain is configured for that service?
- What is the initial instance list and candidate count after filtering?
- Is the cache serving stale data?
- Was an instance excluded due to health, zone, hint, or another reason?
- Which instance did LoadBalancer ultimately select?

You do not need to log entire metadata maps or request payloads. Log only necessary fields, avoiding secrets and personal data. For production environments, prefer metrics with controlled cardinality; do not put dynamic instance IDs or unbounded request IDs into metric labels.

## 11. Key Takeaways

- `ServiceInstanceListSupplier` supplies the candidate list; the LoadBalancer algorithm selects one instance from that list.
- The base supplier typically sources data from a discovery client, `SimpleDiscoveryClient`, or a custom source.
- The supplier chain composes decorators such as caching, health checks, zone preference, and request-aware filtering.
- Chain ordering affects the data each decorator receives; place caching appropriately relative to the data source and avoid accidentally caching request-dependent outputs.
- `@LoadBalancerClient` enables customizing suppliers per service ID; preserve proper context boundaries.
- An empty list means LoadBalancer has no candidates; inspect discovery and each filtering condition.
- Test input lists, each filter's output, and the end-to-end flow through the HTTP client.

Understanding `ServiceInstanceListSupplier` lets you explain where LoadBalancer gets its candidates, which conditions alter the list, and why the selection algorithm can only pick from the instances the supplier provides.
