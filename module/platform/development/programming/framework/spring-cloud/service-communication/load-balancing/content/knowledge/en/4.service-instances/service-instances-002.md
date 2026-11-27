# Static Lists and Lists Retrieved from DiscoveryClient

In a multi-service system, a service ID such as `catalog-service` can represent multiple processes running on different machines or containers. Spring Cloud LoadBalancer needs to know the corresponding addresses to select a `ServiceInstance` for each request. The instance list can be declared statically in configuration or retrieved from a service discovery source via `DiscoveryClient`.

In the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module, understanding these two data sources helps choose a deployment approach suited to the runtime environment: static lists are useful for small applications and fixed environments; `DiscoveryClient` is suitable when the number or addresses of instances change during operations.

## 1. Service ID and ServiceInstance

**Service ID** is the logical name that a client uses to call a service. For example, an ordering application sends a request to:

~~~text
http://catalog-service/api/items/42
~~~

In this URL, `catalog-service` is the service ID. It does not necessarily have to be a DNS-resolvable hostname. When the request goes through an HTTP client integrated with Spring Cloud LoadBalancer, the load balancer resolves the service ID to a specific instance.

A **ServiceInstance** describes a replica of the service that can receive requests. Typical information includes:

- `serviceId`: the name of the service to which the instance belongs.
- `host` and `port`: the network address to connect to.
- `uri`: the full address formed from host, port, and scheme.
- `instanceId`: the instance identifier if provided by the data source.
- `secure`: indicates whether the instance uses a secure connection.
- `metadata`: additional attributes such as zone, version, or deployment group.

For example, a service has two replicas:

| Service ID | Instance | Address |
|---|---|---|
| catalog-service | catalog-1 | http://10.0.1.11:8080 |
| catalog-service | catalog-2 | http://10.0.1.12:8080 |

The two replicas share the same service ID but have different addresses. The load balancer picks one replica from the list to send the request.

~~~mermaid
flowchart TD
    A["Client calls catalog-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["ServiceInstance list"]
    C --> D["catalog-1 · 10.0.1.11:8080"]
    C --> E["catalog-2 · 10.0.1.12:8080"]
    D --> F["Select an instance"]
    E --> F
    F --> G["Send HTTP request"]
~~~

The source providing the instance list and the instance-selection algorithm are two separate parts. The source returns the instances it knows about; Spring Cloud LoadBalancer's chooser decides which instance is used for the current request.

## 2. Static lists with SimpleDiscoveryClient

When instance addresses are known in advance and rarely change, an application can declare them in configuration. Spring Cloud provides **SimpleDiscoveryClient** to read a simple instance list from application configuration.

For example, declaring two replicas of `catalog-service` in `application.yml`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
                metadata:
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

Each element in the list is an instance. The `uri` property supplies the target address; `metadata` holds additional information that can be used by filters or instance-selection policies.

An equivalent declaration can be written using properties:

~~~properties
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://localhost:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://localhost:8082
spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone=zone-a
spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.zone=zone-b
~~~

In common configurations, SimpleDiscoveryClient is used when the application has no other DiscoveryClient implementation providing the instance list. It implements Spring Cloud's DiscoveryClient abstraction, so components needing a DiscoveryClient can query the declared list.

### How is a request resolved?

Suppose the application has a client annotated with `@LoadBalanced`:

~~~java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

A service using that builder can make calls by service ID:

~~~java
@Service
class CatalogClient {

    private final RestClient restClient;

    CatalogClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    ItemDto getItem(String itemId) {
        return restClient.get()
            .uri("http://catalog-service/api/items/{id}", itemId)
            .retrieve()
            .body(ItemDto.class);
    }
}
~~~

When the request is sent, the load-balancing integration queries the instance list of `catalog-service`, selects an instance, and sends the request to that instance's address. The caller still works only with the service ID.

### Advantages and limitations of static lists

Static lists have several advantages:

- Easy to configure, with no need to install or operate a separate registry.
- Suitable for local development, demos, testing, or systems with a fixed number of instances.
- Easy to read and control target addresses in deployment configuration.

However, static lists have clear limitations:

- When an instance changes its IP, port, or is removed, the configuration must be updated.
- When adding a new replica, the application must receive the updated configuration via the established deployment or refresh mechanism.
- A configuration list does not itself prove that the process at that address is running.
- If multiple environments use different addresses, configuration must be separated by profiles or corresponding configuration sources.

SimpleDiscoveryClient does not register instances with a centralized registry. It provides the configured list to the running application. If a process stops while its address remains in configuration, that instance can still appear in the list until the configuration is changed or a health-filtering mechanism is added.

## 3. Lists retrieved from DiscoveryClient

In an environment where many instances change over time, declaring addresses manually is labor-intensive and error-prone. A **service registry** can store information about registered instances. Services register or renew their status with the registry; clients query the registry to learn which instances can be used.

Spring Cloud defines the **DiscoveryClient** abstraction so applications can query services without depending directly on each registry's proprietary API.

Two commonly used methods are:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

- `getServices()` returns the service IDs known to the discovery client.
- `getInstances(serviceId)` returns the instances belonging to the specified service ID.

DiscoveryClient implementations can connect to different systems, such as Eureka, Consul, or a corresponding discovery platform. Details of registration, heartbeats, leases, and instance eviction depend on the integrated system.

### Registration and discovery flow

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Service instance
    participant Registry as Service registry
    participant Client as Calling application
    participant LB as Spring Cloud LoadBalancer
    participant Target as Selected instance

    App->>Registry: Register service ID and address
    App->>Registry: Renew status per registry mechanism
    Client->>LB: Send request to service ID
    LB->>Registry: Query instances
    Registry-->>LB: ServiceInstance list
    LB->>LB: Filter and select instance
    LB->>Target: Send HTTP request
    Target-->>Client: HTTP response
~~~

The flow above illustrates the general concept. In actual implementations, DiscoveryClient may read data directly from the registry or through the integration library's cache. When the list updates depends on cache configuration, refresh mechanisms, and the registry system.

### Example of querying DiscoveryClient

You can use the DiscoveryClient abstraction to inspect the list of instances the application currently receives:

~~~java
@Service
class CatalogInstanceInspector {

    private final DiscoveryClient discoveryClient;

    CatalogInstanceInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }

    List<String> findKnownServices() {
        return discoveryClient.getServices();
    }
}
~~~

This is an example for observing the instance list. In normal HTTP call flows, you should let Spring Cloud LoadBalancer choose the instance instead of grabbing the first element yourself or writing your own distribution algorithm inside a business service.

If the list is empty, the application does not yet have any instances provided by DiscoveryClient for that service ID. Possible causes include the service not being registered yet, a mismatched service ID name, an out-of-sync registry, evicted instances, or incorrect registry connection configuration.

### Synchronous DiscoveryClient and ReactiveDiscoveryClient

Spring Cloud provides two abstractions to match an application's processing model:

- **DiscoveryClient** provides a synchronous API. Calling `getInstances()` returns the list directly on the calling thread; the lookup operation may block the thread depending on the implementation.
- **ReactiveDiscoveryClient** provides a reactive API, returning `Flux<ServiceInstance>` for the instance list. This approach suits reactive pipelines.

Example using ReactiveDiscoveryClient:

~~~java
@Service
class ReactiveCatalogInstanceInspector {

    private final ReactiveDiscoveryClient discoveryClient;

    ReactiveCatalogInstanceInspector(
            ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    Flux<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }
}
~~~

You should not invoke a synchronous discovery API directly on the WebFlux event loop if that operation might block. Use the corresponding reactive implementation or isolate blocking calls onto an appropriate scheduler.

## 4. How does Spring Cloud LoadBalancer receive the instance list?

Spring Cloud LoadBalancer does not need to know every specific detail of Eureka, Consul, or SimpleDiscoveryClient. It works through the list-supplying abstraction **ServiceInstanceListSupplier**.

A supplier is the component that returns the instance list for a service ID. Depending on configuration, the list can come from DiscoveryClient, ReactiveDiscoveryClient, a static configuration source, or a custom supplier. Suppliers can also be combined to cache, filter, or check instances before the chooser uses them.

~~~mermaid
flowchart TD
    A["HTTP client with @LoadBalanced"] --> B["Spring Cloud LoadBalancer"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["SimpleDiscoveryClient"]
    C --> E["DiscoveryClient"]
    C --> F["ReactiveDiscoveryClient"]
    C --> G["Custom supplier"]
    D --> H["ServiceInstance list"]
    E --> H
    F --> H
    G --> H
    H --> I["Instance chooser"]
    I --> J["HTTP client sends request"]
~~~

In common setups, Spring Cloud LoadBalancer provides integrations to retrieve lists from the DiscoveryClient matching the client type in use. When an application has multiple discovery sources or wants to customize how instances are filtered, cached, and ordered, you can configure the appropriate supplier according to the guide for your Spring Cloud version.

This creates a clear boundary:

- DiscoveryClient or a static source answers the question **which instances are known**.
- ServiceInstanceListSupplier supplies the list to LoadBalancer and can apply additional processing steps.
- LoadBalancer's chooser answers the question **which instance will receive this request**.
- The HTTP client establishes the connection and sends the request to the selected address.

Both static lists and lists retrieved from DiscoveryClient can be used behind the same load-balancing mechanism. The difference lies in how the list is created and updated.

## 5. Comparing static lists and DiscoveryClient

| Criterion | Static list (SimpleDiscoveryClient) | DiscoveryClient from registry |
|---|---|---|
| Data source | Application configuration file or properties | Service registry or discovery system |
| Instance updates | Requires updating configuration and reapplying | Follows registry registration, renewal, and synchronization mechanisms |
| Additional infrastructure | No separate registry required | Usually requires a registry or discovery platform |
| Adaptability when scaling | Limited if addresses change frequently | Better suited for dynamically scaling instances up and down |
| Operational complexity | Low | Requires operating and monitoring discovery |
| Suitable use cases | Local, demo, test, fixed environments | Multi-instance systems, distributed deployments, frequent scaling |

Neither list source guarantees on its own that every instance is healthy. A discovery registry can maintain status via heartbeats or leases, yet status in the registry may lag behind the actual process state. Static lists especially need health checks or an update procedure when an instance stops running.

## 6. List updates, caching, and instance health

Three concepts must be distinguished in operations:

**Registration and discovery** determine which instances are recorded in the data source. With a registry, an instance can register, renew its lease, or be evicted according to the registry's mechanism. With a static list, instances come from application configuration.

**List caching** reduces queries to the discovery source and latency when fetching instances. However, caching too long can cause LoadBalancer to keep seeing stale addresses after instances have changed. Cache duration must balance load on the registry against data freshness.

**Health checks** evaluate whether an instance can serve requests. An instance appearing in DiscoveryClient does not mean its business endpoints are definitely healthy. You can configure health-checking mechanisms or a supplier that filters out instances failing conditions, depending on client type and Spring Cloud version.

When configuring health checks, define the endpoint to call, check interval, timeout, failure threshold before exclusion, and how an instance is brought back into the list. Checking too frequently can create unnecessary load; checking too infrequently can keep failing instances in the list longer.

Metadata can also assist selection decisions. For example, each instance can declare `zone` or `version`. A supplier or custom selection policy can use metadata to prefer instances in the same zone or restrict to compatible versions. Metadata only takes effect when the selection component is configured to read and use it; declaring metadata does not automatically alter the default algorithm.

## 7. Common errors and how to check them

### Calling the wrong service ID

If the URL uses `catalog-service` while the registry registers `catalog`, DiscoveryClient may return an empty list. Verify the exact service ID name in the providing application's configuration and the name used by the client.

### Registry has no instances yet

An application may start up before the target service finishes registering. In that case, the first lookup may receive an empty list. Inspect registration logs, registry state, and client retry mechanisms; do not assume a service always has instances immediately at application startup.

### List contains unreachable addresses

The registry may record an internal address that the client cannot route to, or an instance may advertise a hostname that resolves only in another network. Check the URI, DNS, port, security groups, network policies, and connectivity from the caller's actual runtime environment.

### Stopped instance still appears

With static lists, the address remains until configuration is updated. With a registry, eviction depends on heartbeats, leases, deregistration, and caching. Check both registry state and the supplier's cache duration.

### Static configuration and registry coexisting causing confusion

If an application has multiple discovery implementations or multiple suppliers, clearly identify which supplier is providing the list for the service ID. Do not assume SimpleDiscoveryClient declarations are always merged automatically with lists from another registry. Check the auto-configuration and actual supplier of the version you are using.

### Manually choosing an instance in business code

Calling `getInstances(serviceId).get(0)` and manually constructing a URL bypasses Spring Cloud LoadBalancer's selection policy, filters, caching, and retry integration. Use an HTTP client configured with `@LoadBalanced` for requests by service ID; only query DiscoveryClient directly when you need observability or specialized business handling.

## 8. Choosing a list source for each environment

For local environments or hands-on exercises, SimpleDiscoveryClient lets you declare two or three addresses and observe how LoadBalancer distributes requests without setting up a registry. Each instance can run on a different port on the same machine.

For integration or production environments where many replicas are created and destroyed frequently, DiscoveryClient connected to a registry enables clients to receive updated lists across the instance lifecycle. Supplement this with caching, timeouts, health checks, and registry monitoring so the list maintains appropriate freshness.

When inspecting a routed request, verify in order:

1. The client's URL contains the right service ID.
2. DiscoveryClient or SimpleDiscoveryClient returns the expected instance list.
3. ServiceInstanceListSupplier provides the right list after caching and filtering steps.
4. LoadBalancer's chooser selects a valid instance.
5. The HTTP client can connect to the instance's URI.
6. Logs and metrics show which instance received the request, response time, and any errors.

Observing both the input list and the final selected instance helps distinguish discovery errors from instance-selection errors or connection errors. You can then pinpoint the exact layer to adjust instead of changing the load-balancing algorithm when the initial instance data is already wrong.
