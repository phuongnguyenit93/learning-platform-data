# Client-Side and Server-Side Discovery

In microservices, a service typically has multiple instances running across different machines or containers. Each instance's address can change during deployment, scaling, or restarts. Therefore, a consumer needs a way to call a service by a logical name, such as **inventory-service**, rather than knowing the IP address and port of each instance in advance.

Service discovery solves the problem of finding the currently registered instances for a service. Once the list of instances is obtained, the system also has to decide which instance will handle the request. These two decisions can be placed on the calling application side or in an intermediary component. That is the core difference between **client-side discovery** and **server-side discovery**.

In Spring Cloud, concepts such as **DiscoveryClient**, **ServiceRegistry**, Eureka, Consul, and Spring Cloud LoadBalancer frequently appear together. Understanding the exact role of each component helps you choose the right architecture and avoid confusing a registry with a load balancer.

## 1. Components involved in service discovery

A discovery architecture typically has three roles:

| Component | Responsibility |
|---|---|
| Service provider | Starts instances and registers service information such as service ID, host, port, and metadata. |
| Service registry | Stores registered instance information and the status known to the registry. Eureka Server and Consul are popular choices. |
| Service consumer | Looks up instances by service ID, selects a destination, and sends requests. |

Spring Cloud provides abstractions so that applications do not depend directly on a specific registry:

- **ServiceRegistry** represents the operations to register and deregister an instance.
- **DiscoveryClient** provides an API to query instances by service ID.
- **ServiceInstance** describes a discovered instance, typically including host, port, URI, service ID, and metadata.
- **Spring Cloud LoadBalancer** selects an instance from the eligible list when the application needs to call a service by its logical name.

Eureka or Consul acts as the registry. They store and provide instance information using their own platform-specific mechanisms. Spring Cloud LoadBalancer is the component that selects an instance on the client side. A registry does not automatically become a load balancer just because it stores a list of instances.

## 2. Client-side discovery

With client-side discovery, the consumer application itself queries the registry or uses an instance list updated by the discovery client. Then, the consumer selects an instance and connects directly to that instance.

~~~mermaid
flowchart LR
    C["Order Service<br/>Consumer"] -->|"1. Look up inventory-service"| R[("Service Registry")]
    R -->|"2. Instance list"| C
    C -->|"3. Select instance and call directly"| I1["Inventory instance A"]
    C -.->|"May be selected on next request"| I2["Inventory instance B"]
~~~

Typical processing flow:

1. On startup, each instance of **inventory-service** registers its service ID along with its reachable address in the registry.
2. **order-service** needs to call **inventory-service**, so it asks the discovery client to find instances with the corresponding service ID.
3. The discovery client returns the list of **ServiceInstance** objects it knows about. This list may come from the registry or from a periodically refreshed cache.
4. The client-side load balancer selects an instance according to the configured strategy.
5. The consumer sends the request directly to the address of the selected instance.

### Example with Spring Cloud LoadBalancer and RestTemplate

You can declare a RestTemplate integrated with Spring Cloud LoadBalancer:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

The consumer calls the service using its service ID:

~~~java
@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public ItemDto getItem(String itemId) {
        return restTemplate.getForObject(
            "http://inventory-service/api/items/{id}",
            ItemDto.class,
            itemId
        );
    }
}
~~~

In the URL above, **inventory-service** is the logical service name. When a request goes through a **@LoadBalanced** RestTemplate, Spring Cloud LoadBalancer uses the service ID to look up and select an eligible instance, then replaces the logical address part with the actual address of the chosen instance. The application does not need to hardcode the IP addresses and ports of individual instances.

This example requires the appropriate Spring Cloud dependencies, including the integration for the registry used by the system and Spring Cloud LoadBalancer. **@LoadBalanced** only marks the HTTP client to apply the load-balancing mechanism; it neither creates a registry nor registers providers automatically.

### Querying instances directly with DiscoveryClient

When you need to inspect instance details or build a custom integration flow, the application can query DiscoveryClient:

~~~java
@Service
public class ServiceLookup {

    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

**getInstances** returns the instances that the discovery client currently knows about. An empty list can mean no instances have been registered yet, the registry has not updated, or the consumer could not fetch the required data. Having a list of instances also does not guarantee that every instance is currently handling requests properly.

In typical applications, you should let Spring Cloud LoadBalancer handle instance selection rather than writing custom selection algorithms inside each service. This keeps selection policies, configuration, and HTTP client integration managed more consistently.

### Advantages and limitations

Client-side discovery has the following advantages:

- The consumer calls the provider directly without an additional intermediate proxy per request.
- Instance selection strategies can be tailored to the needs of each consumer.
- Well suited for systems with many Spring Cloud services where all applications can reach the registry.
- Can be combined with retries, circuit breakers, and resilience policies on the consumer side.

This model also has some limitations:

- Each client type needs a compatible discovery library or mechanism. Clients written in other languages must integrate with the registry themselves or have a corresponding support layer.
- Consumers need network access to the registry and usually need direct network connectivity to provider instances.
- Client-side caches can retain stale addresses for a period of time, especially right after an instance stops or changes its address.
- With many types of consumers, managing library versions, configurations, and instance selection policies across multiple places can become complex.

## 3. Server-side discovery

With server-side discovery, the consumer sends requests to a stable address, such as a virtual IP, load balancer, or API Gateway. The intermediary component receiving the request finds an eligible instance and forwards the request to the provider.

The initial consumer does not need to query the registry and does not need to know the addresses of individual provider instances.

~~~mermaid
flowchart LR
    C["Web App or Order Service"] -->|"1. Call stable address"| L["Load Balancer or API Gateway"]
    L -->|"2. Look up or use synced list"| R[("Service Registry")]
    R -->|"3. Eligible instances"| L
    L -->|"4. Forward request"| I1["Inventory instance A"]
    L -.->|"May select another instance"| I2["Inventory instance B"]
~~~

Typical processing flow:

1. Providers register their instances with the registry just as in the client-side model.
2. The consumer sends a request to the load balancer or gateway address.
3. The intermediary component fetches the instance list from the registry, or uses a previously synchronized target list.
4. The intermediary component selects an instance based on health status and routing policies.
5. The request is forwarded to the selected provider; the response returns to the consumer through the intermediary component.

The intermediary component can be a network-level load balancer, reverse proxy, API Gateway, or a routing layer in a service mesh. Not every load balancer queries Eureka or Consul on its own; there needs to be an integration or target list synchronization mechanism suited to the deployment platform.

### Example with Spring Cloud Gateway

In a Spring Cloud system, an API Gateway can receive external requests and route them to a service ID using the **lb://** URI scheme:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
~~~

The Gateway receives requests matching the **/inventory/** path. With the URI **lb://inventory-service**, the Gateway uses discovery integration and Spring Cloud LoadBalancer to find and select an instance of **inventory-service**, then forwards the request to that instance. External consumers only need to know the Gateway address.

There is an important distinction to make: from the perspective of an external consumer, discovering and selecting the provider happens on an intermediate server, so this is a server-side discovery deployment. However, inside the Gateway, the routing component can still use Spring Cloud LoadBalancer to select an instance. The model name describes where the initial consumer sees discovery happening and assigns discovery responsibility, not necessarily the internal algorithm of each individual component.

### Advantages and limitations

Server-side discovery has the following advantages:

- Clients are simpler because they only need to call one stable address.
- Clients do not need to know about the registry or have direct access to the providers' internal network.
- Routing, authentication, rate limiting, TLS termination, and request observability can be centralized at the gateway or proxy.
- Well suited when the system serves diverse clients, including browsers, mobile apps, or services written in multiple languages.

Limitations to consider:

- Requests pass through an additional intermediary component, adding a network hop and potentially increasing latency.
- The gateway or load balancer needs sufficient capacity to handle traffic and must be deployed redundantly to avoid becoming a single point of failure.
- Connectivity or a synchronization mechanism must be maintained between the routing component and the registry.
- When the gateway, proxy, or registry experiences an outage, the blast radius can be wide if the architecture lacks redundancy.

## 4. Comparing the two models

| Criterion | Client-side discovery | Server-side discovery |
|---|---|---|
| Where instances are found and selected | Consumer application | Intermediate load balancer, gateway, or proxy |
| Address used by consumer | Service ID, then the client chooses the instance address | Stable address of the intermediary component |
| Does consumer need registry access? | Usually yes, directly or via a discovery client | No |
| Connection to provider | Consumer connects directly | Intermediary component connects to provider |
| Components requiring integration | Discovery client and load balancer in each client type | Load balancer or gateway with discovery integration |
| Network hops | Typically fewer because calls are direct | Extra hop through the intermediary component |
| Where instance selection policies are managed | Distributed across consumers | Centralized at the intermediary component |
| Best suited for | Service-to-service within an ecosystem whose clients support discovery | Diverse client types or environments that need to hide the internal network |

Neither model is always better. The decision depends on client integration capabilities, network boundaries, security requirements, latency, and how the system is operated.

## 5. Instance registration and update lifecycle

The two models differ in where discovery and instance selection happen, yet both still rely on a dependable service registration lifecycle:

1. **Startup:** the provider starts an instance and registers its service ID, address, port, and required metadata.
2. **Status maintenance:** the instance sends heartbeats or undergoes health checks according to the registry and deployment platform mechanisms.
3. **List updates:** the consumer or intermediary component fetches updated instance information. Some systems use caching to reduce registry query frequency.
4. **Request routing:** the load balancer picks an instance currently considered healthy/eligible and sends the request there.
5. **Instance shutdown:** the provider deregisters during a controlled shutdown; if an instance disconnects unexpectedly, the registry needs a timeout or health-check mechanism to evict invalid instances.

The state in the registry can lag behind the application's actual state. For example, an instance may have just failed while its entry still remains in the consumer's or gateway's cache. Therefore, health checks, cache TTLs, heartbeats, and graceful shutdown processes should be configured to match the system's target recovery time.

## 6. Implementation notes in Spring Cloud

**Distinguish registration from discovery.** Providers register using the ServiceRegistry mechanism or starter auto-configuration. Consumers discover via DiscoveryClient. Having a registration entry does not mean the consumer is properly configured to call the service.

**Distinguish discovery from load balancing.** Discovery answers the question of which instances exist for a service ID. Load balancing decides which instance receives the current request. In Spring Cloud, these two responsibilities work together, yet remain distinct concepts.

**Watch out for stale data.** When an instance is replaced, old addresses may linger in caches or synced target lists. Choose appropriate refresh intervals, heartbeats, and health checks, and handle connection errors when an address has just become invalid.

**Do not treat health checks as an absolute guarantee.** An instance that passes health checks can still fail on a specific endpoint, become overloaded, or lose connectivity right after the check. Consumers should use sensible timeouts, bounded retries, and circuit breakers where appropriate. Retries must consider operation idempotency to avoid sending duplicate write requests.

**Restrict registry access.** Only components that need it should be able to access the registry. Protect credentials, use TLS where appropriate, and avoid putting secrets into service instance metadata. With server-side discovery, secure the connection channel between the gateway or load balancer and the registry.

**Verify actual network connectivity.** Registered instance addresses must be reachable from where requests originate. An internal address valid only inside the provider's network may not work for a consumer on a different network. Account for subnets, DNS, ports, firewalls, and advertised addresses when deploying with containers or across multiple network zones.

## 7. Which model should you choose?

Client-side discovery is typically a good fit when internal services mainly use Spring Cloud, can all integrate a discovery client, and the team wants consumers to connect directly to providers. This model reduces intermediate hops and allows each consumer to apply tailored selection policies.

Server-side discovery is typically a good fit when clients are heterogeneous, cannot or should not access the registry, or when the system needs a centralized point to control routing and security. An API Gateway is a common choice at the system boundary; an internal load balancer or proxy can play a similar role across service networks.

A system can combine both. For example, browsers and mobile apps call through an API Gateway using the server-side model, while internal Spring Cloud services communicate with each other using client-side discovery. This hybrid approach keeps the external access interface stable while allowing internal services to communicate directly.

When designing, clearly determine which consumer is responsible for finding instances, which component selects the destination, how that component obtains data from the registry, and what happens when discovery data becomes stale. Answering these four questions will make your service discovery architecture clearer and easier to operate.
