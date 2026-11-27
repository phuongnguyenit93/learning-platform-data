# DiscoveryClient and ReactiveDiscoveryClient in the Load-Balancing Flow

Spring Cloud LoadBalancer needs to know which replicas provide a service ID before it can choose an instance to send a request to. This information usually comes from a service registry system such as Eureka, Consul, or ZooKeeper. Spring Cloud Commons standardizes how applications read this information through two abstractions: **DiscoveryClient** for synchronous calls and **ReactiveDiscoveryClient** for reactive calls.

Both abstractions return **ServiceInstance** objects, yet how they retrieve data and integrate with HTTP clients differs. Understanding this distinction helps an application pick the right discovery path for RestClient, OpenFeign, and WebClient while avoiding blocking reactive execution flows.

## 1. Where does service discovery sit in the load-balancing flow?

Service discovery answers the question: "Which instances are currently registered under this service name and what are their addresses?". LoadBalancer answers the next question: "From that list, which instance will receive the current request?".

The discovery client reads data from the registry and converts it into ServiceInstance objects. LoadBalancer consumes this list through ServiceInstanceListSupplier, which may cache or filter the list, and then applies an instance-selection algorithm.

~~~mermaid
flowchart TD
    A["Order Service"] --> B["HTTP client"]
    B --> C["LoadBalancer"]
    C --> D["ServiceInstanceListSupplier"]
    D --> E{"Discovery source"}
    E --> F["DiscoveryClient"]
    E --> G["ReactiveDiscoveryClient"]
    F --> H["Service Registry"]
    G --> H
    H --> I["ServiceInstance list"]
    I --> J["Cache and filters"]
    J --> K["LoadBalancer selects instance"]
    K --> L["Send request to host and port"]
    L --> M["Service instance"]
~~~

This flow can be divided into four responsibilities:

1. **Service registration:** an instance supplies its information to the registry.
2. **Service discovery:** the discovery client reads instances by service ID.
3. **List supplying:** ServiceInstanceListSupplier turns discovery results into a list for LoadBalancer and can add caching or filters.
4. **Instance selection:** ReactiveLoadBalancer or BlockingLoadBalancerClient picks an instance, and then the HTTP client sends the request to the physical address.

A discovery client does not perform Round Robin or Random itself. It provides the input data for LoadBalancer to make a selection.

## 2. How does ServiceInstance represent a replica?

Spring Cloud Commons defines the **ServiceInstance** interface to describe an instance independently of the registry type in use. Commonly used fields include:

| Property | Meaning |
| --- | --- |
| serviceId | Logical name of the service under which the instance is registered |
| instanceId | Identifier of the deployed instance, if provided by the provider |
| host | Hostname or IP address of the instance |
| port | Port receiving requests |
| secure | Indicates whether the instance uses a secure connection |
| metadata | Additional labels such as zone, version, or hints |
| uri | Physical URI constructed from instance information |

For example, a registry might return three instances of **inventory-service**:

| Service ID | Instance ID | Address | Metadata |
| --- | --- | --- | --- |
| inventory-service | inventory-1 | 10.0.0.21:8080 | zone=zone-a |
| inventory-service | inventory-2 | 10.0.0.22:8080 | zone=zone-a |
| inventory-service | inventory-3 | 10.0.1.31:8080 | zone=zone-b |

The client does not need to hardcode these addresses in business logic. It sends requests to the service ID; LoadBalancer uses the chosen ServiceInstance to build the actual URL.

Metadata can assist routing by zone, hints, or API version. The meaning of each metadata key depends on the provider and LoadBalancer configuration. Simply having a metadata key appear in the registry does not mean LoadBalancer will automatically use it.

## 3. DiscoveryClient: synchronous API

**DiscoveryClient** resides in the package org.springframework.cloud.client.discovery. It is the abstraction for reading service discovery information under a blocking model.

Key methods:

| Method | Result | Purpose |
| --- | --- | --- |
| description() | String | Describes the implementation, often used for health indicators |
| getInstances(serviceId) | List<ServiceInstance> | Retrieves instances for a service ID |
| getServices() | List<String> | Retrieves the list of known service IDs |
| probe() | void | Checks whether the discovery client can execute a call |
| getOrder() | int | Determines ordering when multiple discovery clients exist |

Example reading instances of a service:

~~~java
@Service
class InventoryDiscoveryInspector {

    private final DiscoveryClient discoveryClient;

    InventoryDiscoveryInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }

    List<String> findRegisteredServices() {
        return discoveryClient.getServices();
    }
}
~~~

This is a synchronous call. The calling thread waits for the implementation to retrieve the result from its data source. With a remote registry, wait time depends on the network, timeouts, and how the provider is implemented.

If the service ID is unknown or no instances are registered, implementations usually return an empty list. Callers should distinguish an empty list from a registry connection error: an empty list can be a valid result, whereas connection errors are typically represented by exceptions.

### 3.1. Multiple DiscoveryClients and ordering priority

An application can have multiple discovery implementations on the classpath, for example one client reading Eureka and another reading Consul. DiscoveryClient extends the Ordered interface. The getOrder() value allows sorting implementations when Spring Cloud combines them.

The default order value of DiscoveryClient is 0. Providers or custom implementations can supply a different order. For clients with dedicated configuration properties, order can be set via provider configuration, such as:

~~~yaml
eureka:
  client:
    order: 0
~~~

The order property name depends on the provider. When multiple registries supply the same service ID, check the order and how a composite client merges or prioritizes results across implementations. Do not assume every registry returns the exact same instance list.

## 4. ReactiveDiscoveryClient: reactive API

**ReactiveDiscoveryClient** also belongs to the package org.springframework.cloud.client.discovery, but returns results as Reactor Publishers. Instead of returning an already constructed List, the API emits elements as a reactive stream.

Key methods:

| Method | Result | Purpose |
| --- | --- | --- |
| description() | String | Describes the implementation |
| getInstances(serviceId) | Flux<ServiceInstance> | Emits instances for a service ID |
| getServices() | Flux<String> | Emits known service IDs |
| reactiveProbe() | Mono<Void> | Checks discovery reachability under a reactive model |
| getOrder() | int | Determines the order of the implementation |

Example:

~~~java
@Service
class ReactiveInventoryDiscoveryInspector {

    private final ReactiveDiscoveryClient discoveryClient;

    ReactiveInventoryDiscoveryInspector(
            ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    Flux<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }

    Flux<String> findRegisteredServices() {
        return discoveryClient.getServices();
    }
}
~~~

A Flux emits data only upon subscription. Callers can chain operators such as map, filter, collectList, or timeout onto this stream without blocking a thread to wait for results.

Do not call block() inside a WebFlux thread or on an event loop to obtain results from ReactiveDiscoveryClient. Blocking negates non-blocking benefits, holds the event loop while waiting on the registry, and degrades overall application throughput.

### 4.1. Reactive is not just turning a List into a Flux

ReactiveDiscoveryClient is appropriate when the underlying implementation can perform I/O reactively. If a provider only offers a synchronous API, wrapping a blocking call inside a Flux does not automatically make that I/O non-blocking.

When choosing a provider, verify whether the provider truly offers a ReactiveDiscoveryClient or only a DiscoveryClient. If only DiscoveryClient is available, the application can still use the blocking path supported by Spring Cloud LoadBalancer; do not write your own reactive adapter assuming the registry call has become non-blocking.

## 5. How do DiscoveryClient and ReactiveDiscoveryClient differ?

| Criterion | DiscoveryClient | ReactiveDiscoveryClient |
| --- | --- | --- |
| API style | Synchronous, blocking | Reactive, non-blocking if supported by provider |
| Instance list | List<ServiceInstance> | Flux<ServiceInstance> |
| Service ID list | List<String> | Flux<String> |
| Connectivity check | probe() | reactiveProbe() |
| How it is consumed | Invoke method and receive result | Subscribe or chain into a Reactor pipeline |
| Suitable for | RestClient, OpenFeign, and blocking stacks | Reactive WebClient, WebFlux |
| Note | Thread may have to wait on I/O | Do not block the event loop; requires a genuinely reactive provider |

The two interfaces are not two load-balancing algorithms. They are two ways to retrieve discovery data. Whichever interface is chosen, the resulting ServiceInstance list is ultimately supplied to LoadBalancer to pick a target.

## 6. How does LoadBalancer connect to the two discovery client types?

Spring Cloud LoadBalancer uses **ServiceInstanceListSupplier** to fetch the instance list. The supplier acts as the intermediary layer between the discovery client and the instance-selection algorithm. It is also where caching, health checks, zone preferences, or other filters can be attached.

The ServiceInstanceListSupplier builder has two key methods:

| Builder method | Discovery API used | Meaning |
| --- | --- | --- |
| withBlockingDiscoveryClient() | DiscoveryClient | Fetches instances via synchronous API |
| withDiscoveryClient() | ReactiveDiscoveryClient | Fetches instances via reactive API |

Example configuring a reactive supplier:

~~~java
class InventoryReactiveLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Example configuring a blocking supplier:

~~~java
class InventoryBlockingLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

These are two mutually exclusive alternatives for the same client ID. Do not register both configurations simultaneously for one LoadBalancer client in a way that creates multiple competing ServiceInstanceListSupplier beans. Choose the source matching your service-calling stack and Spring Cloud version.

A dedicated configuration can be bound to a service ID with @LoadBalancerClient:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryReactiveLoadBalancerConfiguration.class)
class OrderApplication {
}
~~~

This example selects the reactive configuration for inventory-service. To use the blocking configuration, substitute the corresponding configuration class. The class passed to the configuration attribute should not be picked up by component scan as a global configuration; per Spring Cloud guidance, that class may omit @Configuration or be placed outside component-scan scope. If no supplier customization is needed, use LoadBalancer's default auto-configuration.

Spring Cloud LoadBalancer auto-configures the supplier based on the discovery client present in the ApplicationContext and properties enabling/disabling blocking or reactive discovery. In current default configuration:

- The reactive branch is created when ReactiveDiscoveryClient is present and reactive discovery is enabled. The supplier uses withDiscoveryClient().
- The blocking branch is created when DiscoveryClient is present and blocking discovery is enabled. The supplier uses withBlockingDiscoveryClient().

Applications normally do not need to define a custom supplier if auto-configuration already provides the right implementation. Create a custom configuration only when changing caching, health checks, zones, hints, or instance-filtering policies.

## 7. Choosing a discovery path by HTTP client

### 7.1. RestClient

RestClient is a synchronous HTTP client. When using a builder annotated with @LoadBalanced, Spring Cloud integrates BlockingLoadBalancerClient to resolve the service ID and select an instance.

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

The application calls the service ID like a logical host:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    InventoryResponse getInventory(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

With a blocking stack, the supplier can fetch data using DiscoveryClient via withBlockingDiscoveryClient(). The request waits until instance selection and the HTTP call complete or time out.

### 7.2. WebClient

WebClient can use ReactorLoadBalancerExchangeFilterFunction to resolve service IDs inside a reactive pipeline.

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Example calling a service:

~~~java
@Service
class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<InventoryResponse> getInventory(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

In the reactive path, ServiceInstanceListSupplier typically fetches data from ReactiveDiscoveryClient via withDiscoveryClient(). Discovery results are chained into the reactive pipeline of LoadBalancer and WebClient.

### 7.3. OpenFeign

OpenFeign generates synchronous clients from interfaces. When integrated with Spring Cloud LoadBalancer, Feign uses the service ID to look up instances through the load-balanced client on the blocking stack.

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/inventory/{sku}")
    InventoryResponse getInventory(@PathVariable String sku);
}
~~~

Do not declare a fixed URL if you want Feign to resolve names through LoadBalancer. A fixed URL makes the client call the configured address directly and bypasses discovery/load balancing.

OpenFeign and RestClient follow a blocking call model; WebClient can run reactively. Even so, verify the actual dependencies and configuration of your release train because whether a provider exposes DiscoveryClient or ReactiveDiscoveryClient depends on the integration modules on the classpath.

## 8. Configuring service discovery for local testing

When not yet connected to Eureka, Consul, or ZooKeeper, Spring Cloud can use **SimpleDiscoveryClient** if no service-registry-backed discovery client is on the classpath. SimpleDiscoveryClient reads instance information from application properties.

Example declaring two instances of inventory-service:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

The application invokes the request using a logical URL:

~~~text
http://inventory-service/api/inventory/BOOK-01
~~~

LoadBalancer receives the service ID inventory-service, fetches the two declared addresses, and selects one address to send the request to.

SimpleDiscoveryClient is useful for local development, illustrative examples, and simple integration tests. This list is static configuration; it does not automatically detect a process that has just started or stopped. When instances change, update the configuration or use a service registry capable of dynamic registration and status updates.

SimpleDiscoveryClient is a blocking implementation. This setup works well for testing DiscoveryClient alongside RestClient or OpenFeign. To test the reactive WebClient path, you need a provider offering ReactiveDiscoveryClient or supply a corresponding reactive implementation yourself; do not assume SimpleDiscoveryClient configuration creates a ReactiveDiscoveryClient.

Note: spring-cloud-starter-loadbalancer provides the load-balancing mechanism. To read an external registry, the application also needs the starter or integration corresponding to that registry. Adding only the LoadBalancer starter does not automatically create a connection to Eureka, Consul, or ZooKeeper.

## 9. Service registration and service discovery are two separate responsibilities

**DiscoveryClient** and **ReactiveDiscoveryClient** focus on reading service and instance lists. Registering or deregistering an instance belongs to the **ServiceRegistry** abstraction.

| Abstraction | Responsibility | Example operations |
| --- | --- | --- |
| DiscoveryClient | Read discovery information synchronously | getInstances(), getServices() |
| ReactiveDiscoveryClient | Read discovery information reactively | getInstances(), getServices() |
| ServiceRegistry | Register or deregister an instance | register(), deregister() |

Many integrations automatically register the running application with the registry at startup and deregister on shutdown. In current Spring Cloud, simply placing the appropriate discovery implementation on the classpath enables auto-configuration; @EnableDiscoveryClient is usually no longer required. To disable automatic registration, configure:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Disabling auto-registration does not mean disabling discovery reading. These two behaviors belong to separate responsibilities and should be configured according to operational needs.

## 10. Caching the instance list

A discovery client could query the registry every time LoadBalancer needs an instance list. To reduce registry calls, Spring Cloud LoadBalancer provides **CachingServiceInstanceListSupplier** and a default cache.

A supplier configuration with caching:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .build(context);
~~~

Caching lowers lookup overhead but introduces a delay when the registry has just updated instances. If a pod has just been deleted, the cached list may retain the old address until the TTL expires or the cache is refreshed.

Common properties:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

The current default values for the LoadBalancer cache are a 35-second TTL and a capacity of 256. If Caffeine is added to the classpath, Spring Cloud can use a Caffeine-backed cache instead of the default cache.

Some discovery clients such as Eureka already have their own caching mechanism. If the provider already caches the instance list, consider disabling caching at LoadBalancer to avoid two layers of caching increasing update lag. Cache configuration should be based on actual provider behavior rather than applying one TTL value across all environments.

## 11. Discovery health indicator and instance health checks

These two mechanisms serve different goals:

- **DiscoveryClientHealthIndicator** checks whether the discovery client or registry is operational. By default, it may call getServices() to fetch the list of service IDs.
- **HealthCheckServiceInstanceListSupplier** checks individual instances supplied by the supplier, then filters the list for LoadBalancer.

A registry health indicator reports that the application can communicate with the discovery system. It does not prove every instance of inventory-service is handling requests properly.

If a registry contains very many services, calling getServices() on every health check can be expensive. You can instruct the health indicator to use probe() instead of querying the service list:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

When using reactive discovery, the reactive health indicator can use reactiveProbe().

With a real registry that already supplies healthy instance status, periodic health checks inside LoadBalancer are often unnecessary. HealthCheckServiceInstanceListSupplier is more useful with SimpleDiscoveryClient or instance sources that do not supply health status themselves.

## 12. Enabling or disabling each discovery path

Spring Cloud Commons provides properties to control service discovery:

| Property | Effect |
| --- | --- |
| spring.cloud.discovery.enabled | Enables or disables service discovery overall |
| spring.cloud.discovery.blocking.enabled | Enables or disables the synchronous DiscoveryClient path |
| spring.cloud.discovery.reactive.enabled | Enables or disables the ReactiveDiscoveryClient path |

Example disabling only the reactive path:

~~~yaml
spring:
  cloud:
    discovery:
      reactive:
        enabled: false
~~~

Disable the reactive path only when the application does not need reactive discovery. If WebClient relies on ReactiveDiscoveryClient while that path is disabled or lacks a corresponding implementation, LoadBalancer may fail to obtain the instance list along the configured reactive path.

Do not disable discovery overall if HTTP clients are still calling URLs by service ID. When disabling discovery, ensure another instance source exists or switch to appropriate fixed addresses.

## 13. Diagnosing discovery issues in the load-balancing flow

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| getInstances() returns an empty list | Wrong service ID, instance not registered yet, or registry not updated | Compare service ID, registration status, and service list in registry |
| No DiscoveryClient bean | Missing provider starter or discovery disabled | Check dependencies and spring.cloud.discovery properties |
| WebClient cannot find instances | Missing ReactiveDiscoveryClient or reactive discovery disabled | Check provider's reactive integration and reactive configuration |
| RestClient or Feign cannot find instances | Missing blocking DiscoveryClient or blocking discovery disabled | Check blocking provider and blocking configuration |
| Stopped old instance is still selected | Cache or registry not updated yet | Check cache TTL, heartbeat interval, deregistration, and health state |
| Some requests go to another zone | Incorrect zone metadata or zone preference not enabled | Check metadata and LoadBalancer zone configuration |
| WebFlux threads slow down or stall | Blocking calls inside reactive pipeline | Find block() calls or blocking adapters and replace with appropriate reactive APIs |
| Health indicator is DOWN even though service serves requests | Registry unreachable or probe failed | Check registry connectivity, credentials, and discovery client logs |

When diagnosing, check sequentially from the discovery client to the supplier, and only then to the instance-selection algorithm. If getInstances(serviceId) already returns an empty list, replacing Round Robin with Random cannot fix the problem.

## 14. Hands-on verification of both discovery paths

You can test the local discovery flow without spinning up a full service registry:

1. Declare two URIs for inventory-service using SimpleDiscoveryClient, such as localhost:8081 and localhost:8082.
2. Start two instances, each returning its own instance ID in the response.
3. Inject DiscoveryClient and call getInstances("inventory-service") to observe the synchronous list.
4. If the provider supports ReactiveDiscoveryClient, inject that interface and subscribe to getInstances("inventory-service") to observe the reactive list. SimpleDiscoveryClient in the local example is blocking, so do not use it to demonstrate the reactive path.
5. Create a RestClient annotated with @LoadBalanced and call a URL using the service ID.
6. When a ReactiveDiscoveryClient provider is available, create a WebClient annotated with @LoadBalanced and call the endpoint reactively.
7. Send multiple requests and record the instance IDs to confirm LoadBalancer is selecting from the discovery list.
8. Stop one instance and observe the difference between the registry list, cached list, and request outcomes.
9. Adjust the cache TTL or disable caching in a test environment to observe update latency.

Outcomes to verify:

- DiscoveryClient returns the instance list synchronously.
- ReactiveDiscoveryClient emits instances via Flux upon subscription.
- ServiceInstanceListSupplier supplies the list to LoadBalancer.
- LoadBalancer selects an instance and the HTTP client calls that instance's physical address.
- When the registry or cache changes, the list updates after an interval depending on the provider and configuration.

## 15. Key operational takeaways

- DiscoveryClient only reads service information; ServiceRegistry handles registration and deregistration.
- ReactiveDiscoveryClient returns data via Reactor; do not call block() on the event loop.
- LoadBalancer needs a ServiceInstanceListSupplier to obtain the instance list before selecting a target.
- withDiscoveryClient() uses ReactiveDiscoveryClient; withBlockingDiscoveryClient() uses DiscoveryClient.
- RestClient and OpenFeign follow the blocking stack; WebClient can use the reactive path.
- SimpleDiscoveryClient fits local or test setups, whereas an external registry suits dynamically changing instance lists.
- Caching reduces registry lookup load but can delay awareness of newly added or stopped instances.
- Health indicators check the discovery client; health-check suppliers check individual instances.
- If no instances are available, fix the discovery source or supplier configuration before changing the instance-selection algorithm.

## 16. References

- [Spring Cloud Commons - Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, ReactiveDiscoveryClient, SimpleDiscoveryClient, ServiceRegistry, health indicators, and discovery client ordering.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, caching, health checks, supplier configuration, and RestClient/WebClient integration.
- [DiscoveryClient source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java): synchronous API contract.
- [LoadBalancerClientConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/annotation/LoadBalancerClientConfiguration.java): auto-configuration conditions for reactive and blocking discovery suppliers.
