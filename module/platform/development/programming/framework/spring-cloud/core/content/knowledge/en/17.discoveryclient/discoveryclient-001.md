# `DiscoveryClient` and `ReactiveDiscoveryClient` Contracts

In a distributed system, a service often has multiple instances running on different machines or containers. Clients need to locate the addresses of those instances without hardcoding hostnames and ports in source code. Spring Cloud Commons provides two discovery read contracts: **`DiscoveryClient`** for synchronous calls and **`ReactiveDiscoveryClient`** for reactive calls based on Project Reactor.

These two interfaces create a common boundary between the application and a service discovery provider such as Eureka, Consul, or ZooKeeper. The application queries by service ID and receives `ServiceInstance` objects; connecting to the registry, caching, heartbeats, and data mapping belong to the specific implementation.

This lesson belongs to the **DiscoveryClient** chapter of the **SPRING_CLOUD_CORE** module. Learners will master the exact methods in both contracts, how to read instance information, differences between blocking and reactive models, ordering when multiple discovery clients exist, and the boundary between service lookup and service registration.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the role of service discovery in a distributed system.
2. Describe the methods of `DiscoveryClient` and `ReactiveDiscoveryClient`.
3. Distinguish between `List` and `Flux` return types and use them properly in each application model.
4. Read the fields of `ServiceInstance`, including service ID, instance ID, URI, host, port, scheme, and metadata.
5. Understand the meaning of `description()`, `probe()`, `reactiveProbe()`, and `getOrder()`.
6. Distinguish discovery read APIs from `ServiceRegistry` register/deregister APIs.
7. Understand how Spring Cloud discovers implementations, `SimpleDiscoveryClient`, and multi-provider ordering.
8. Combine discovery with Spring Cloud LoadBalancer instead of picking instances arbitrarily.
9. Test the contracts using mocks or simple discovery configuration.
10. Diagnose cases where a service exists with no instances, discovery fails, or instance data is invalid.

## 2. Service Discovery and the Role of Both Contracts

### 2.1. Service ID and Service Instance

Suppose a system has the following services:

- `orders-service`: processes orders.
- `inventory-service`: manages inventory.
- `pricing-service`: calculates pricing.
- `identity-service`: handles authentication and identity.

Each service can run multiple instances:

~~~text
inventory-service
  ├── instance A: http://inventory-1.internal:8080
  ├── instance B: http://inventory-2.internal:8080
  └── instance C: https://inventory-3.internal:8443
~~~

A **Service ID** is the logical name of a service, for example `inventory-service`. A **service instance** is a specific process with a network address, port, metadata, and routing attributes.

Clients should query discovery by service ID. The registry returns the instances published by the provider. The client does not need to know the address of each machine in advance.

### 2.2. DiscoveryClient Is a Read Abstraction

`DiscoveryClient` and `ReactiveDiscoveryClient` provide read operations:

- Retrieve the list of known service IDs.
- Retrieve the instances belonging to a service ID.
- Describe the implementation.
- Probe whether the discovery provider can be queried.
- Determine the order when multiple implementations exist.

These two interfaces **do not define operations to register or deregister an instance**. Those operations belong to `ServiceRegistry` and `Registration`, covered later.

### 2.3. High-Level Architecture

~~~mermaid
flowchart TD
    A[Application service] --> B[DiscoveryClient or ReactiveDiscoveryClient]
    B --> C[Spring Cloud provider implementation]
    C --> D[Service registry]
    D --> E[Service IDs]
    D --> F[Service instances]
    B --> G[ServiceInstance]
    G --> H[Load balancer or service-calling client]
~~~

The application uses the Commons contract; the concrete provider is responsible for communicating with the registry. After receiving the list of instances, the application or load balancer decides how to select an instance and send the request.

## 3. The Synchronous `DiscoveryClient` Contract

The interface resides in package:

~~~java
org.springframework.cloud.client.discovery.DiscoveryClient
~~~

`DiscoveryClient` extends `org.springframework.core.Ordered`. The current contract has the following core methods:

| Method | Return Type | Meaning |
| --- | --- | --- |
| `description()` | `String` | Human-readable description of the implementation |
| `getInstances(String serviceId)` | `List<ServiceInstance>` | Retrieves instances belonging to a service ID |
| `getServices()` | `List<String>` | Retrieves known service IDs |
| `probe()` | `void` | Checks that the client can perform a discovery query |
| `getOrder()` | `int` | Priority order when sorting multiple clients |

### 3.1. `getInstances(serviceId)`

Method:

~~~java
List<ServiceInstance> getInstances(String serviceId);
~~~

Takes a service ID and returns the corresponding list of instances.

Example:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

if (instances.isEmpty()) {
    throw new IllegalStateException(
            "No inventory-service instance is currently available"
    );
}
~~~

If the service ID has no instances, implementations typically return an empty list. Do not rely on list order to infer which instance is best or least loaded. The returned order depends on the provider and registry data.

Two cases must be distinguished:

- Empty list: the query completed, but no matching instances were returned.
- Exception: the query failed, such as when the registry is unreachable or the provider encounters an error.

The application should handle these two situations with different policies. An empty list may lead to a "no instance available" error; an exception may require retries, a circuit breaker, or reporting discovery as unavailable.

### 3.2. `getServices()`

Method:

~~~java
List<String> getServices();
~~~

Returns the service IDs known to the discovery client. Example:

~~~java
List<String> serviceIds = discoveryClient.getServices();

serviceIds.forEach(log::info);
~~~

This API is useful for admin dashboards, diagnostics, or exploration tools. It should not be called on every business request if the registry contains many services or if listing is expensive.

This list also does not mean every service is healthy. It reflects the data returned by the provider at query time; instance status must be evaluated via health checks, registry leases/heartbeats, or dedicated verification mechanisms.

### 3.3. `description()`

Method:

~~~java
String description();
~~~

Returns a human-readable description of the implementation. Spring Cloud uses this description in some observability components, such as `DiscoveryClientHealthIndicator`.

Example:

~~~java
@Override
public String description() {
    return "Inventory discovery through Consul";
}
~~~

This is descriptive information for diagnostics. Do not use `description()` as a service ID, routing key, or authentication credential.

### 3.4. `probe()`

The contract has a default method:

~~~java
default void probe() {
    getServices();
}
~~~

A call to `probe()` that succeeds without throwing an exception indicates that the discovery client can execute a query operation. Implementations may override the method to use a lighter operation instead of listing all services.

Example:

~~~java
try {
    discoveryClient.probe();
    log.info("Discovery provider is reachable");
}
catch (RuntimeException ex) {
    log.warn("Discovery provider probe failed", ex);
}
~~~

`probe()` does not check every instance of every service, does not send business requests to downstream services, and does not prove every address in the registry is reachable. It is only an operational check of the discovery client according to its implementation.

### 3.5. `getOrder()`

`DiscoveryClient` extends `Ordered`. The default value of `getOrder()` is `0`.

~~~java
@Override
public int getOrder() {
    return 10;
}
~~~

When multiple discovery clients exist, the order helps Spring Cloud sort implementations and use composites in that order. A lower order value has higher priority according to Spring `Ordered` rules.

Order is not load weight, not per-instance priority order, and not a load balancing policy. Do not use `getOrder()` to replace a server selection algorithm.

## 4. The Reactive `ReactiveDiscoveryClient` Contract

The interface resides in package:

~~~java
org.springframework.cloud.client.discovery.ReactiveDiscoveryClient
~~~

This interface also extends `Ordered`, but uses Project Reactor return types:

| Method | Return Type | Meaning |
| --- | --- | --- |
| `description()` | `String` | Implementation description |
| `getInstances(String serviceId)` | `Flux<ServiceInstance>` | Emits instances belonging to a service ID |
| `getServices()` | `Flux<String>` | Emits known service IDs |
| `reactiveProbe()` | `Mono<Void>` | Checks query capability via a reactive pipeline |
| `getOrder()` | `int` | Client order |
| `probe()` | `void` | Legacy API deprecated in current versions |

### 4.1. `getInstances(serviceId)` Returning Flux

~~~java
Flux<ServiceInstance> getInstances(String serviceId);
~~~

Example:

~~~java
Flux<ServiceInstance> instances =
        reactiveDiscoveryClient.getInstances("inventory-service");
~~~

`Flux` may emit zero, one, or multiple elements. When no instances are found, the publisher usually completes without emitting elements. When the query fails, the publisher emits an error signal.

You can take the first instance:

~~~java
Mono<ServiceInstance> firstInstance =
        reactiveDiscoveryClient.getInstances("inventory-service")
                .next();
~~~

If you need to handle the case with no instances:

~~~java
Mono<URI> resolveInventoryUri() {
    return reactiveDiscoveryClient.getInstances("inventory-service")
            .next()
            .map(ServiceInstance::getUri)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException("No inventory instance")
            ));
}
~~~

This snippet illustrates taking a single instance to understand the contract. In production applications, let Spring Cloud LoadBalancer select the instance instead of manually taking the first element.

### 4.2. `getServices()` Returning Flux

~~~java
Flux<String> getServices();
~~~

Example:

~~~java
Flux<String> serviceIds =
        reactiveDiscoveryClient.getServices();

return serviceIds
        .filter(id -> id.endsWith("-service"))
        .sort();
~~~

Reactor operators build a pipeline. There is no need to block to collect a list before further processing in a WebFlux application; keep the data inside `Flux` or `Mono` until the framework subscribes.

### 4.3. `reactiveProbe()`

The current contract provides:

~~~java
Mono<Void> reactiveProbe();
~~~

You can combine it with timeout and error handling:

~~~java
Mono<Void> checkDiscovery() {
    return reactiveDiscoveryClient.reactiveProbe()
            .timeout(Duration.ofSeconds(2))
            .doOnSuccess(ignored ->
                    log.info("Discovery provider is reachable"))
            .doOnError(error ->
                    log.warn("Discovery provider probe failed", error));
}
~~~

`Mono<Void>` is a publisher. The pipeline executes only when subscribed to. Therefore, return the publisher to the caller or integrate it into an appropriate lifecycle/health flow; creating a `Mono` and discarding it does not perform the check.

### 4.4. Why Is Reactive `probe()` Deprecated?

In current Spring Cloud Commons APIs, `ReactiveDiscoveryClient.probe()` has been deprecated in favor of `reactiveProbe()`.

The reason is that the old method called `getServices()`, which returns a `Flux`, without subscribing or blocking to consume the publisher. As a result, it did not perform the reactive check properly. Do not use the old method in new code.

Consult the Javadoc of your project's release train if using an older Spring Cloud version; the deprecation status and availability of `reactiveProbe()` depend on the version.

## 5. `ServiceInstance`: Data Returned by Discovery

Both contracts return `org.springframework.cloud.client.ServiceInstance`.

Key properties:

| Method | Meaning |
| --- | --- |
| `getInstanceId()` | Unique ID of the instance; may not be provided by the provider |
| `getServiceId()` | Registered service ID |
| `getHost()` | Hostname of the instance |
| `getPort()` | Port of the instance |
| `isSecure()` | Indicates whether the instance uses HTTPS |
| `getUri()` | Full URI to access the instance |
| `getMetadata()` | Key/value metadata map of the instance |
| `getScheme()` | Scheme if provided by the implementation |

Example of reading information:

~~~java
void logInstances(List<ServiceInstance> instances) {
    for (ServiceInstance instance : instances) {
        log.info(
                "service={}, instance={}, uri={}, secure={}, metadata={}",
                instance.getServiceId(),
                instance.getInstanceId(),
                instance.getUri(),
                instance.isSecure(),
                instance.getMetadata()
        );
    }
}
~~~

### 5.1. Service ID and Instance ID Are Different

`getServiceId()` identifies the logical service group, for example `inventory-service`. `getInstanceId()` identifies one instance in that group, for example `inventory-service-7f9c`.

Multiple instances can share the same service ID while having different instance IDs. If a provider does not supply an instance ID, `getInstanceId()` may return `null`; do not use it as a mandatory key without a null check.

### 5.2. URI and Host/Port

`getUri()` returns the instance URI. This is usually the right choice when you need a complete address because the URI can carry the scheme and other details supplied by the provider.

Do not manually concatenate `http://` with host and port if an instance might use HTTPS. `isSecure()` and `getUri()` help the application preserve the exact protocol advertised by the provider.

Example:

~~~java
URI uri = instance.getUri();
String scheme = uri.getScheme();
String host = uri.getHost();
int port = uri.getPort();
~~~

Do not assume every URI has an explicit port; a URI might use the scheme's default port or have a different structure depending on the provider.

### 5.3. Metadata

Metadata lets providers or applications publish additional information:

~~~text
zone=ap-southeast-1a
version=v2
canary=true
protocol=grpc
~~~

Metadata can be used for routing policies, version selection, or geographic zoning. However, the discovery contract does not require every provider to supply the same set of metadata. Application code must handle missing keys and differing formats.

Do not put credentials, tokens, or secrets into metadata because this data can be read by many clients.

## 6. Choosing Blocking or Reactive?

The two interfaces represent two programming models. Choose based on the application and provider model, not merely on interface names.

| Situation | Appropriate Contract |
| --- | --- |
| MVC application or synchronous service | `DiscoveryClient` |
| WebFlux application and Reactor pipeline | `ReactiveDiscoveryClient` |
| Code running on an event-loop | Avoid calling blocking APIs directly |
| Component needing `Mono`/`Flux` composition | `ReactiveDiscoveryClient` |
| Synchronous library or legacy API | `DiscoveryClient` may be suitable |

### 6.1. Blocking Example

~~~java
@Service
class InventoryResolver {

    private final DiscoveryClient discoveryClient;

    InventoryResolver(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<URI> resolveAll(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .stream()
                .map(ServiceInstance::getUri)
                .toList();
    }
}
~~~

`getInstances()` returns the list immediately during the call. If the implementation has to call the registry over the network, the call can block the thread while waiting for results.

### 6.2. Reactive Example

~~~java
@Service
class ReactiveInventoryResolver {

    private final ReactiveDiscoveryClient discoveryClient;

    ReactiveInventoryResolver(ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    Flux<URI> resolveAll(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .map(ServiceInstance::getUri);
    }
}
~~~

Reactive code keeps results inside the pipeline. Do not call `.block()` on the WebFlux event-loop to turn a reactive API into a synchronous one; doing so can cause stalls or runtime errors.

### 6.3. A Reactive Interface Does Not Automatically Guarantee Every Implementation Is Non-Blocking

The reactive contract returns `Flux` and `Mono`, yet the application still needs to choose a provider with proper reactive support. If an implementation wraps a blocking call, it must schedule work on the appropriate scheduler and resources. Simply looking at a `Flux` return type is not enough to conclude the entire query path is non-blocking.

Check the provider documentation and observe threads during integration tests. Do not push a blocking call onto an event-loop merely by wrapping it in `Mono.just(...)`.

## 7. Discovering Implementations and Spring Cloud Configuration

### 7.1. Provider Implementations

Spring Cloud Commons defines the abstractions; provider projects supply corresponding implementations, for example:

- Spring Cloud Netflix Eureka Discovery.
- Spring Cloud Consul Discovery.
- Spring Cloud Zookeeper Discovery.
- Other discovery integrations supported by the ecosystem.

When a suitable starter/provider is on the classpath, auto-configuration creates the corresponding discovery client bean and connects according to the provider's configuration.

### 7.2. Is `@EnableDiscoveryClient` Still Required?

In current Spring Cloud versions, `@EnableDiscoveryClient` is no longer required when a suitable `DiscoveryClient` implementation is already on the classpath. The annotation still exists and can be used when explicit configuration is needed, such as disabling auto-registration via `autoRegister=false`.

Do not add the annotation purely out of habit from older projects. Check the release train and provider starter before deciding.

### 7.3. Disabling Individual Contracts or All Discovery

Spring Cloud Commons provides control properties:

~~~yaml
spring:
  cloud:
    discovery:
      blocking:
        enabled: true
      reactive:
        enabled: true
      enabled: true
~~~

You can disable blocking or reactive discovery clients individually:

~~~properties
spring.cloud.discovery.blocking.enabled=false
spring.cloud.discovery.reactive.enabled=false
~~~

To disable service discovery globally via configuration:

~~~properties
spring.cloud.discovery.enabled=false
~~~

The exact behavior of auto-configuration and health contributors may vary by version. Check the configuration metadata of your project's release train before using these properties in production.

### 7.4. `SimpleDiscoveryClient`

If no service-registry-backed discovery implementation is on the classpath, Spring Cloud can use `SimpleDiscoveryClient`, reading the instance list from configuration.

Example:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-1.internal:8080
              - uri: http://inventory-2.internal:8080
            pricing-service:
              - uri: http://pricing-1.internal:8080
~~~

This is useful for local environments, tests, or small systems with static endpoint lists. It does not automatically track new instances or query a remote registry like Eureka/Consul.

When using SimpleDiscoveryClient, updating the instance list must be handled through configuration sources and the application lifecycle by design. Do not confuse this static configuration with a dynamic service registry.

## 8. Multiple DiscoveryClients and Ordering

An application can have multiple discovery implementations. For example, a system combining a central registry with a static instance list for a group of internal services.

Both `DiscoveryClient` and `ReactiveDiscoveryClient` extend `Ordered`. `CompositeDiscoveryClient` and `ReactiveCompositeDiscoveryClient` can aggregate clients and delegate in order.

### 8.1. Order Values

By default `getOrder()` returns `0`. You can override it in a custom implementation:

~~~java
@Override
public int getOrder() {
    return 20;
}
~~~

Some providers have dedicated order configuration properties, such as `spring.cloud.{clientIdentifier}.discovery.order`; Eureka has `eureka.client.order` according to Commons documentation.

### 8.2. Order Is Not Load Balancing

Three concepts must be separated:

- **Discovery client order:** the order in which implementations are sorted when multiple clients coexist.
- **Instance list:** the list of instances returned by a provider for a service ID.
- **Load balancing:** choosing one instance to send a request, which can be based on round robin, random, zone, health, or a custom policy.

Do not use `getOrder()` to prefer instance A over B. Do not rely on list order to create an implicit load-balancing algorithm.

### 8.3. When to Use Composite?

Composite is useful when multiple discovery providers participate in supplying data. However, you must verify the order and delegation behavior of the implementation in your exact version. If two providers both return a service ID, the application must understand how the composite combines or selects their results; do not assume all implementations merge data identically.

## 9. Discovery and Service Registration Are Two Different Contracts

A common misconception is thinking `DiscoveryClient` has a register method. This interface only describes read operations.

### 9.1. `ServiceRegistry` and `Registration`

Spring Cloud Commons provides:

- `ServiceRegistry<R extends Registration>`: contract for registering and deregistering.
- `Registration`: marker interface describing a provider-specific registration.

Common operations include:

~~~java
serviceRegistry.register(registration);
serviceRegistry.deregister(registration);
serviceRegistry.getStatus(registration);
serviceRegistry.setStatus(registration, status);
~~~

The concrete `Registration` type depends on the provider, such as `EurekaRegistration`, `ConsulRegistration`, or `ZookeeperRegistration`.

### 9.2. Auto-registration

Provider implementations typically register the local server automatically when the application starts. You can disable auto-registration with:

~~~java
@EnableDiscoveryClient(autoRegister = false)
@SpringBootApplication
public class OrdersApplication {
}
~~~

Or via configuration:

~~~properties
spring.cloud.service-registry.auto-registration.enabled=false
~~~

Disabling auto-registration does not mean disabling discovery read operations. An application may refrain from registering itself while still using `DiscoveryClient` to find other services.

### 9.3. Registration Events

Spring Cloud Commons can publish events related to auto-registration:

- `InstancePreRegisteredEvent`: before registration.
- `InstanceRegisteredEvent`: after registration.

Listeners can be used to log or perform actions after the service is registered. These events are not published if auto-registration is disabled via the corresponding property.

## 10. DiscoveryClient and Spring Cloud LoadBalancer

`DiscoveryClient` returns a list of instances. It is not a full load balancer.

Spring Cloud LoadBalancer uses discovery as the source of instance lists and then applies a selection strategy. A client can use a logical service ID instead of a concrete hostname.

Example with `WebClient`:

~~~java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Using a service ID:

~~~java
@Service
class InventoryApi {

    private final WebClient webClient;

    InventoryApi(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<InventoryResponse> getInventory(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/items/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

In this example, `inventory-service` is the service ID. LoadBalancer works with discovery to obtain the instance list and pick an address for the request.

Do not manually take `getInstances().get(0)` on every request to replace LoadBalancer. Doing so bypasses health checks, retries, zone preference, caching, metrics, and instance selection policies.

## 11. Health and Discovery Capability Checks

Spring Cloud Commons can configure a health indicator based on the discovery client.

Commonly used properties:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          include-description: false
          use-services-query: true
        composite-indicator:
          enabled: true
~~~

### 11.1. `DiscoveryClientHealthIndicator`

This health indicator relies on the available discovery implementation. By default, it may call `getServices()` to check discovery and gather descriptive information.

In systems with a very large number of services, listing all services on every health check can be expensive. You can set:

~~~properties
spring.cloud.discovery.client.health-indicator.use-services-query=false
~~~

Then the health indicator uses `probe()` instead of querying the full service list.

### 11.2. Reactive Health Indicator

For reactive discovery, Spring Cloud provides a corresponding health indicator. In current APIs, reactive checks should use `reactiveProbe()`; avoid using the deprecated `ReactiveDiscoveryClient.probe()`.

### 11.3. Discovery Health Is Not the Health of Every Downstream Service

The discovery health indicator checks the operational health of the discovery client/provider in the way the implementation supports. It does not automatically send business requests to every instance of every service.

To evaluate a specific downstream service, you need dedicated health checks, timeouts, circuit breakers, or LoadBalancer instance health checks. A registry may be reachable while a service instance has stopped serving requests.

## 12. Writing a Custom Implementation

In some systems, it is necessary to integrate discovery with an internal source or static data. You can implement the corresponding interface.

### 12.1. Blocking Implementation

Example illustrating a simple client backed by a map:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class InMemoryDiscoveryClient implements DiscoveryClient {

    private final Map<String, List<ServiceInstance>> instancesByService;

    public InMemoryDiscoveryClient(
            Map<String, List<ServiceInstance>> instancesByService
    ) {
        this.instancesByService = Map.copyOf(instancesByService);
    }

    @Override
    public String description() {
        return "In-memory discovery client";
    }

    @Override
    public List<ServiceInstance> getInstances(String serviceId) {
        return instancesByService.getOrDefault(serviceId, List.of());
    }

    @Override
    public List<String> getServices() {
        return List.copyOf(instancesByService.keySet());
    }

    @Override
    public int getOrder() {
        return 100;
    }
}
~~~

This example only illustrates the contract. In a real implementation, data might come from a backend, cache, or dynamically updated source. Thread safety, data freshness, backend errors, and bean registration must be clearly defined.

### 12.2. Reactive Implementation

A reactive implementation can emit values from a data source:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.ReactiveDiscoveryClient;

public class InMemoryReactiveDiscoveryClient
        implements ReactiveDiscoveryClient {

    private final Map<String, List<ServiceInstance>> instancesByService;

    public InMemoryReactiveDiscoveryClient(
            Map<String, List<ServiceInstance>> instancesByService
    ) {
        this.instancesByService = Map.copyOf(instancesByService);
    }

    @Override
    public String description() {
        return "In-memory reactive discovery client";
    }

    @Override
    public Flux<ServiceInstance> getInstances(String serviceId) {
        return Flux.fromIterable(
                instancesByService.getOrDefault(serviceId, List.of())
        );
    }

    @Override
    public Flux<String> getServices() {
        return Flux.fromIterable(instancesByService.keySet());
    }

    @Override
    public Mono<Void> reactiveProbe() {
        return Mono.fromRunnable(() -> {
            // Check data source status if needed.
        });
    }
}
~~~

In this example, `java.util.List` and `java.util.Map` must be imported. If the source is truly a reactive backend, use the backend's publishers rather than pushing blocking data into Reactor on an event-loop.

### 12.3. Guarantees an Implementation Must Maintain

A good implementation should:

- Return the exact instances belonging to the requested service ID.
- Return an empty list or empty publisher when no instances exist.
- Never return `null` instead of a collection/publisher.
- Distinguish missing data from backend connection errors.
- Provide a clear implementation description.
- Set an appropriate order when multiple discovery clients exist.
- Return `ServiceInstance` objects with consistent URI, host, port, scheme, and metadata.
- Ensure thread safety for data updates.
- Have timeouts and observability when the backend is slow.
- Never place secrets into metadata or logs.

## 13. Testing the Contract

### 13.1. Testing a Blocking Client with Mockito

~~~java
@Test
void returnsInstancesForServiceId() {
    DiscoveryClient discoveryClient = mock(DiscoveryClient.class);

    ServiceInstance instance = mock(ServiceInstance.class);
    when(instance.getUri()).thenReturn(
            URI.create("http://inventory-1.internal:8080")
    );

    when(discoveryClient.getInstances("inventory-service"))
            .thenReturn(List.of(instance));

    List<ServiceInstance> result =
            discoveryClient.getInstances("inventory-service");

    assertThat(result).hasSize(1);
    assertThat(result.get(0).getUri())
            .isEqualTo(URI.create("http://inventory-1.internal:8080"));
}
~~~

This test verifies that the consumer handles data from the contract properly. It does not prove that a real provider can connect to a registry.

### 13.2. Testing a Reactive Client

~~~java
@Test
void emitsInstancesForServiceId() {
    ReactiveDiscoveryClient discoveryClient =
            mock(ReactiveDiscoveryClient.class);

    ServiceInstance instance = mock(ServiceInstance.class);
    when(instance.getUri()).thenReturn(
            URI.create("http://inventory-1.internal:8080")
    );

    when(discoveryClient.getInstances("inventory-service"))
            .thenReturn(Flux.just(instance));

    StepVerifier.create(
            discoveryClient.getInstances("inventory-service")
                    .map(ServiceInstance::getUri)
    )
    .expectNext(URI.create("http://inventory-1.internal:8080"))
    .verifyComplete();
}
~~~

`StepVerifier` subscribes to the publisher and verifies emitted signals. Tests should not call `.block()` on reactive code that must stay non-blocking.

### 13.3. Testing the No-Instance Case

Blocking:

~~~java
when(discoveryClient.getInstances("missing-service"))
        .thenReturn(List.of());

assertThat(discoveryClient.getInstances("missing-service"))
        .isEmpty();
~~~

Reactive:

~~~java
when(reactiveDiscoveryClient.getInstances("missing-service"))
        .thenReturn(Flux.empty());

StepVerifier.create(
        reactiveDiscoveryClient.getInstances("missing-service")
)
.verifyComplete();
~~~

Having no instances is a valid query outcome, not necessarily a registry connection error. The consumer must decide when an empty list becomes a business error.

### 13.4. Testing Probe

For a blocking client, verify that `probe()` does not throw an exception when the backend is reachable. For a reactive client, subscribe to `reactiveProbe()` with StepVerifier and verify completion/error.

Do not test `ReactiveDiscoveryClient.probe()` in new code because that method is deprecated and has subscription issues.

### 13.5. Integration Testing with SimpleDiscoveryClient

You can use properties configuration to test service ID and instance mapping:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: https://localhost:8443
~~~

Verify `getServices()`, `getInstances("inventory-service")`, URIs, and the secure flag. This approach is well suited for testing consumers without running a real Eureka/Consul instance.

For integration testing a real provider, use a container or test server for that provider to verify registration, heartbeat, deregistration, and querying.

## 14. Common Issues and Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| `getInstances()` returns an empty list | Wrong service ID, service not registered yet, or registry not updated yet | Check service ID, registration status, and registry |
| `getServices()` does not include expected service | Provider does not see the service or access permissions are restricted | Check provider configuration and registry read permissions |
| Blocking request is slow | Discovery provider queries registry synchronously or has a large timeout | Set timeouts, observe latency, and avoid calling on the event-loop |
| Reactive pipeline does not run | Publisher has not been subscribed to | Return the publisher to the framework or subscribe at the appropriate boundary |
| `reactiveProbe()` is not executed | Created Mono without subscribing/composing | Use StepVerifier, health integration, or a chain with a subscriber |
| Reactive `probe()` emits no signals | Using deprecated API | Switch to `reactiveProbe()` |
| Cannot inject `DiscoveryClient` | Missing provider dependency or discovery is disabled | Check starter, auto-configuration, and condition report |
| Multiple clients give unexpected results | Order or composite behavior is unclear | Check `getOrder()` and the list of clients |
| Service ID exists but requests cannot reach instance | Discovery only returns registration data; instance may be dead or network failed | Check health, network, port, and LoadBalancer |
| URI uses wrong scheme | Code manually concatenates host/port and ignores `isSecure()`/`getUri()` | Use the URI provided by `ServiceInstance` |
| `getInstanceId()` returns null | Provider does not supply a dedicated ID | Use service ID and URI or another suitable key |
| Discovery health is down even though service still serves | Temporary registry failure or overly heavy probe query | Check health indicator, timeouts, and provider |

### 14.1. Distinguishing Discovery Failure from No Instance

These are two cases that must be handled separately:

- **No instance:** the provider queried successfully but found no instances.
- **Discovery failure:** the provider could not query due to timeout, authentication, DNS, network, or server error.

Do not convert every exception into an empty list without logging/recording it. Doing so prevents the application from distinguishing an unregistered service from a failing registry.

### 14.2. Do Not Cache Indefinitely on the Consumer

A consumer can cache discovery results to reduce query frequency, but the cache needs a TTL or refresh mechanism. Caching instance addresses indefinitely can cause the application to keep calling deregistered instances or instances whose IPs changed.

When using Spring Cloud LoadBalancer, leverage its configured cache and supplier mechanisms rather than building an ad-hoc cache with no invalidation policy.

## 15. Security and Operations

Discovery metadata and instance lists can expose internal topology. When deploying to production:

- Grant registry read/write permissions strictly by role.
- Protect credentials and TLS between providers and the registry.
- Do not write tokens, passwords, or secrets into metadata.
- Restrict registry administration endpoints.
- Monitor errors, latency, and instance counts per service.
- Verify published instance addresses are reachable from the consumer's network.
- Use proper health/heartbeats and deregistration to remove stopped instances.
- Keep discovery query timeouts finite.
- Have appropriate fallback and retry policies, avoiding retry storms when the registry fails.
- Check discovery order if multiple providers are configured together.

Do not treat an instance appearing in the registry as proof that it is serving requests properly. Registry updates can lag; health checks and network paths still need to be verified.

## 16. Practice Exercises

**Exercise 1 — Reading the blocking contract.** Inject `DiscoveryClient`, call `getServices()` and `getInstances("inventory-service")`. Print each instance's service ID, URI, host, port, and metadata.

**Exercise 2 — Reading the reactive contract.** Inject `ReactiveDiscoveryClient`, return `Flux<ServiceInstance>` from a WebFlux service. Use `StepVerifier` to verify both instance-present and no-instance cases.

**Exercise 3 — Comparing probe methods.** Write tests for `DiscoveryClient.probe()` and `ReactiveDiscoveryClient.reactiveProbe()`. Prove that reactive probe executes only when the publisher is subscribed to.

**Exercise 4 — SimpleDiscoveryClient.** Declare two instances for `inventory-service` using YAML. Verify `getServices()` and `getInstances()` return accurate data, including HTTP and HTTPS.

**Exercise 5 — ServiceRegistry.** Disable auto-registration while still using `DiscoveryClient` to read other services. Explain why reading discovery and registering the local service are two separate responsibilities.

**Exercise 6 — Multiple providers.** Create two discovery clients with different orders. Observe composite ordering and inspect results when both know the same service ID.

**Exercise 7 — Load balancing.** Use `@LoadBalanced WebClient.Builder` to call `http://inventory-service/...`. Compare with manually calling `getInstances().get(0)` and list the responsibilities LoadBalancer handles.

**Exercise 8 — Error classification.** Simulate a service with no instances and a timed-out registry. Design different responses/logs for the two cases.

## 17. Key Takeaways and References

- `DiscoveryClient` is the blocking contract; discovery methods return `List`.
- `ReactiveDiscoveryClient` is the reactive contract; discovery methods return `Flux`.
- Both provide `description()` and extend `Ordered`.
- `DiscoveryClient.probe()` defaults to calling `getServices()`; implementations may override it with a lighter check.
- For reactive discovery, use `reactiveProbe()`; the old reactive `probe()` is deprecated.
- `ServiceInstance` describes an instance's address and metadata; `getInstanceId()` may have no value.
- DiscoveryClient only reads data. `ServiceRegistry` and `Registration` are responsible for register/deregister.
- `@EnableDiscoveryClient` is no longer required if a provider implementation is already on the classpath.
- `SimpleDiscoveryClient` supports static instance configuration when no registry-backed client is used.
- `getOrder()` orders discovery providers, not load balancing algorithms.
- Use Spring Cloud LoadBalancer to select instances; do not default to taking the first element.
- Distinguish an empty list from a registry query error and test both blocking and reactive paths.

Official sources for cross-checking against your project's Spring Cloud/Spring Boot version:

1. [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
2. [Spring Cloud Commons 5.0.2 Javadoc – `DiscoveryClient`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/discovery/DiscoveryClient.html)
3. [Spring Cloud Commons 5.0.2 Javadoc – `ReactiveDiscoveryClient`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/discovery/ReactiveDiscoveryClient.html)
4. [Spring Cloud Commons Javadoc – `ServiceInstance`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/ServiceInstance.html)
5. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
6. [Spring Cloud LoadBalancer – Reference Guide](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
7. [Spring Cloud – Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
