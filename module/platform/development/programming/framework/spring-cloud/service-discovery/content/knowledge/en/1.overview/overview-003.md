# Core Concepts: Service, Instance, Registry, and Consumer

When a microservice needs to call another microservice, the calling application typically only knows the name of the service it wants to use. For example, order-service needs to find inventory-service to read item information. In an actual deployment environment, inventory-service may run as multiple processes across different machines or containers. These processes have their own network addresses and statuses, which can change throughout the application lifecycle.

To understand service discovery in Spring Cloud, you first need to distinguish four concepts: a **service** is the logical capability a system provides; an **instance** is a running copy of the service; a **service registry** stores information about registered instances; and a **consumer** is the application that needs to find and call the service. DiscoveryClient connects these concepts by allowing the consumer to look up instances by service name.

## 1. Service: The Logical Identity of a Capability

A service is a software component that provides a group of capabilities over an interface, typically an HTTP API, gRPC, or another communication protocol. In a microservice architecture, each service is usually responsible for a relatively well-defined business domain.

For example:

- **inventory-service** manages stock and provides an API to query item quantities.
- **order-service** receives and manages orders.
- **payment-service** processes payments.
- **shipping-service** manages deliveries.

The service name is a logical name that other components reference. A consumer can request inventory-service without needing to know which process is executing that functionality, which machine it is running on, or which port it is using.

In Spring Cloud, the service name is typically represented by a **service ID**. The service ID is the lookup key that the discovery client and registry use to group instances belonging to the same service. For example, multiple instances register together under the service ID inventory-service.

The service ID must be consistent between where the provider registers and where the consumer looks up. If the provider registers as inventory-service but the consumer searches for product-inventory, the consumer will not receive the expected group of instances. Some registries have name normalization rules or case sensitivity; you must follow the rules of the integrated platform.

### A Service Does Not Equal a Single Process

A service can have one or many instances. The service is the logical identity and functional scope; an instance is a specific process executing that functionality.

~~~text
Service ID: inventory-service
  ├── Instance A: 10.0.2.15:8081
  ├── Instance B: 10.0.2.16:8081
  └── Instance C: 10.0.3.21:8081
~~~

Three instances together provide one logical service, yet each instance has its own address and lifecycle. When Instance B stops, inventory-service can continue operating thanks to Instances A and C. When processing capacity needs to increase, the platform can spin up additional instances without changing the service ID.

## 2. Instance: A Running Copy of a Service

A **service instance** is a specific running copy of a service. In a deployment environment, an instance can be a Java process, a container, a pod, or another execution unit depending on the platform. From a service discovery perspective, what matters is that the instance can be located and called using its connection information.

An instance record typically includes the following information:

| Attribute | Meaning |
|---|---|
| Service ID | Logical name of the service the instance belongs to, e.g. inventory-service. |
| Instance ID | Identifier of a specific instance within the service's instance group. |
| Host | Hostname or IP address reachable by consumers. |
| Port | Port on which the instance accepts requests. |
| Scheme or secure flag | Indicates how to build the URI, e.g. HTTP or HTTPS depending on configuration. |
| Metadata | Additional information such as zone, region, application version, or deployment group. |

Illustrative example of a record:

~~~yaml
serviceId: inventory-service
instanceId: inventory-7f8c9d
host: 10.0.2.15
port: 8081
metadata:
  zone: zone-a
  version: v2
~~~

This is an illustrative structure to explain the data, not a mandatory universal configuration format for all registries. Eureka and Consul each have their own ways of storing, representing, and adding attributes.

### Instance ID and Service ID Solve Two Different Needs

The service ID groups instances that jointly provide a service. The instance ID distinguishes each running copy within that group. If there are three inventory-service instances, all three share the service ID inventory-service, yet each needs a distinct identifier so the registry can track registration, updates, and deregistration.

The instance ID needs to be stable enough for the lifecycle managed by the registry while avoiding collisions among instances of the same service. How the ID is generated depends on the platform: it can be based on hostname, port, container ID, pod identity, or a value configured by the application.

### Application Version and Instance Are Not the Same Concept

An application version is a software release, such as v1.4.0 or v2.0.0. An instance is a specific running execution of a software version. One version can run as multiple instances; during a rolling deployment, multiple versions can coexist within a single service.

~~~text
inventory-service
  ├── Instance A — application version v1.4
  ├── Instance B — application version v1.4
  └── Instance C — application version v2.0
~~~

Version information can be placed in metadata to support observability, routing, or compatibility checks. However, service discovery does not automatically decide that a new version is compatible with all consumers. Version selection policies, canary deployments, traffic splitting, or retiring old versions must be designed separately.

## 3. Service Registry: The Directory of Instances

A **service registry** is the place that stores registration information for service instances. Providers register when an instance joins the system and deregister when stopping gracefully. The registry provides data so consumers or routing components can find instances by service ID.

~~~mermaid
flowchart TD
    P1["Inventory instance A"] -->|"Register"| R[("Service Registry")]
    P2["Inventory instance B"] -->|"Register"| R
    P3["Inventory instance C"] -->|"Register"| R
    C["Order Service"] -->|"Look up inventory-service"| R
    R -->|"Instance list"| C
~~~

A registry typically supports the following operations or equivalent mechanisms:

- **Register:** adds an instance record when a provider joins the system.
- **Renew or heartbeat:** periodically refreshes a liveness signal, if the registry uses a lease or heartbeat mechanism.
- **Update:** modifies registration attributes when instance information changes.
- **Deregister:** removes the record when an instance stops gracefully.
- **Health check and expiration:** detects instances that are no longer healthy or no longer renewing their registration according to registry policy.
- **Query:** returns a list of instances by service ID.

Not every registry implements these operations in the same way. For example, Eureka commonly uses a lease and heartbeat mechanism to track clients; Consul can combine service registration with health checks. Specific configuration and behavior must follow the version and integration in use.

### The Registry Is Not Where Business Logic Executes

The registry holds location information and registration status. It does not handle business logic such as looking up stock, creating orders, or processing payments. Once the consumer finds an instance address, the business request is still sent to the provider application.

The registry also does not necessarily sit on the path of every request. In client-side discovery, the consumer can fetch the instance list and then call the provider directly. The list may be cached or refreshed periodically. In server-side discovery, a load balancer or gateway can query the registry or receive a synchronized list to forward requests.

### The Registry Can Lag Behind Reality

A record in the registry reflects what the registry knew at the time of the most recent update. If an instance crashes suddenly, the record may remain until the heartbeat expires or a health check detects the failure. Conversely, a new instance may take a short time to register and appear in lookup results.

Therefore, an instance list is not a guarantee that every address can be connected to successfully at the exact moment a consumer sends a request. Consumers still need timeouts, connection error handling, and appropriate retry policies. Heartbeat, health check, cache, and refresh intervals affect the delay in detecting changes.

## 4. Provider: The Component That Registers Instances

A **service provider** is an application that provides functionality to consumers. On startup, the provider typically participates in a registration process so the registry knows its service ID and the address that can be used to reach the instance.

For example, an inventory-service instance starts on host 10.0.2.15, port 8081. It registers the service ID inventory-service along with the corresponding location information. When the instance shuts down gracefully, it can deregister so the registry stops handing out that address to consumers.

In Spring Cloud, the **ServiceRegistry** abstraction describes registering and deregistering a registration. The Registration carries the information a specific implementation needs to register an instance. Starters for Eureka, Consul, or other platforms can automate most of this lifecycle based on configuration. Applications should not assume every registry shares the same registration type or internal workflow.

The operational responsibilities of a provider typically include:

1. Starting the application and determining the service ID, instance ID, and address information.
2. Registering the instance with the registry or letting the integration handle it automatically.
3. Maintaining heartbeats or responding to health checks as required by the registry.
4. Updating registration information if the address or metadata needs to change.
5. Deregistering during graceful shutdown while completing or rejecting new requests per the graceful shutdown policy.

The registered address must be reachable from consumers or from the routing component that will call the provider. A container may see an internal address that differs from the address reachable by consumers outside the container network. Advertised addresses, port mappings, DNS, and firewalls must be configured to match the deployment topology.

## 5. Consumer: The Party That Finds and Calls Services

A **service consumer** is an application that needs to use functionality provided by a provider. The consumer does not need to know a specific instance at coding time. It can reference a service ID, then use discovery to obtain the current list of instances.

For example, order-service needs to check stock before confirming an order. It looks up inventory-service and receives one or more instances. A load-balancing mechanism can then select an instance to send the request to.

~~~mermaid
sequenceDiagram
    participant O as Order Service (Consumer)
    participant D as DiscoveryClient
    participant R as Service Registry
    participant I as Inventory Instance
    O->>D: getInstances(inventory-service)
    D->>R: Look up service ID
    R-->>D: List of registered instances
    D-->>O: List of ServiceInstance
    O->>I: Call inventory API at selected instance
    I-->>O: Business result
~~~

Consumers typically have the following responsibilities:

- Identifying the correct service ID to call.
- Retrieving the instance list via the discovery client or routing integration.
- Selecting an instance via a load balancer if there are multiple options.
- Sending the request to the instance address.
- Handling timeouts, connection errors, business errors, and cases where no instance is found.

A consumer can be another Spring Cloud service, an application running in a different language, an API Gateway, or an infrastructure component. Integration depends on the discovery model and registry accessibility of each consumer type.

## 6. Spring Cloud Abstractions Connecting These Concepts

Spring Cloud provides abstractions so applications can use service discovery without depending directly on the API of a specific registry.

| Abstraction | Role | Connection to Concepts |
|---|---|---|
| DiscoveryClient | Query the list of services and instances by service ID | Consumer finds provider |
| ServiceInstance | Describe a discovered instance | Address and metadata of a running copy |
| ServiceRegistry | Register and deregister a registration | Provider adds an instance to or removes it from the registry |
| Registration | Carry registration data needed by the registry implementation | Instance information at registration time |
| Spring Cloud LoadBalancer | Select a suitable instance for a request | Consumer decides which instance to send the request to |

### Looking Up with DiscoveryClient

DiscoveryClient provides an API to list service IDs known to the client and retrieve instances by service ID. For example:

~~~java
@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

The result is a list of ServiceInstance. Each element describes an instance known to the discovery client, including information such as service ID, host, port, URI, and implementation-specific metadata.

Other usage examples:

~~~java
List<String> serviceIds = discoveryClient.getServices();
List<ServiceInstance> instances =
    discoveryClient.getInstances("inventory-service");
~~~

The list of service IDs and instances reflects the data the client can access at the time of the call. If the list is empty, check the service ID, registration status, registry configuration, network connectivity, and access permissions.

### Registering with ServiceRegistry

ServiceRegistry represents registering a Registration and deregistering that registration. The concrete Registration type depends on the integrated registry. In many Spring Cloud applications, the starter automatically registers the instance based on configuration; you should only call the registration API manually when necessary and once you understand the registration lifecycle.

The key point is that ServiceRegistry serves the provider side, whereas DiscoveryClient is typically used by the consumer for lookups. The two abstractions are related but handle opposite directions of interaction.

### Load Balancing Is the Selection Step

Discovery tells you which instances are known. Load balancing chooses which instance will receive the current request. When there are multiple instances, Spring Cloud LoadBalancer can perform selection according to the application's configuration and strategy.

For example, a RestTemplate annotated with @LoadBalanced can make calls using a service ID:

~~~java
@Bean
@LoadBalanced
RestTemplate restTemplate(RestTemplateBuilder builder) {
    return builder.build();
}
~~~

~~~java
restTemplate.getForObject(
    "http://inventory-service/api/items/{id}",
    ItemDto.class,
    itemId
);
~~~

The name inventory-service is resolved through the discovery integration and Spring Cloud LoadBalancer. The provider must have a registered instance, and the consumer must have the corresponding dependencies and configuration. This snippet illustrates usage; imports, DTOs, dependencies, and registry configuration need to be added in an actual application.

## 7. Putting the Concepts Together into a Complete Flow

Suppose a system has order-service and inventory-service. The inventory service is running three instances. When order-service needs to check stock, the components coordinate as follows:

1. **Service:** inventory-service is the logical name of the stock-checking capability.
2. **Instance:** three running inventory-service processes have three separate addresses and instance IDs.
3. **Provider:** each process registers its information with the registry.
4. **Registry:** stores the records and the status it observes.
5. **Consumer:** order-service asks to find inventory-service by service ID.
6. **DiscoveryClient:** queries the registry or discovery data maintained by the client and returns a list of ServiceInstance.
7. **Load balancer:** selects an appropriate instance for the request.
8. **Request:** order-service calls the selected instance's address directly, or sends it through an intermediary component depending on the architecture.

~~~mermaid
flowchart TB
    S["Service: inventory-service"]
    S --> A["Instance A"]
    S --> B["Instance B"]
    S --> C["Instance C"]
    A -->|"Register / heartbeat"| R[("Registry")]
    B -->|"Register / heartbeat"| R
    C -->|"Register / heartbeat"| R
    O["Consumer: order-service"] -->|"Service ID"| D["DiscoveryClient"]
    D -->|"Query"| R
    R -->|"ServiceInstance list"| D
    D --> L["Load Balancer"]
    L -->|"Request to selected instance"| A
~~~

When Instance B stops, the provider can deregister or the registry detects the expired/unhealthy record according to its mechanism. Once the consumer receives the updated list, the load balancer can pick A or C. During the window before the registry or cache updates, the consumer may still encounter errors when calling B; therefore, timeouts and error handling remain necessary.

## 8. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Service and instance are the same thing | A service is a logical identity; an instance is a specific running copy of that service. |
| Instance ID and service ID are identical | Service ID groups instances; instance ID distinguishes each running copy. |
| The registry processes business requests | The registry stores registration info; the provider handles business logic. |
| Having a record in the registry means the instance is definitely healthy | Records can lag behind reality; health checks, timeouts, and error handling are still needed. |
| DiscoveryClient automatically picks an instance for every request | DiscoveryClient queries instances; the load balancer handles selection when integrated. |
| Application version is the instance | One version can have multiple instances; multiple versions can also run concurrently. |
| The consumer must always call the registry on every request | Depending on the implementation, the discovery client or proxy can cache or synchronize the list. |

When troubleshooting a discovery issue, identify which step failed: provider has not registered, service ID mismatch, registry not updated yet, consumer cannot query, stale instance list, load balancer picking an unsuitable target, or the instance address is unreachable from the consumer's network. Breaking it down step by step makes it easier to isolate the root cause.

## 9. Design Takeaways

- Set a stable, consistent service ID across providers and consumers.
- Ensure each instance has a unique identifier and an address reachable by consumers.
- Understand the registration, heartbeat, health check, and deregistration mechanisms of the registry in use.
- Use DiscoveryClient for lookups and ServiceRegistry for registration operations according to the appropriate Spring Cloud abstractions.
- Separate finding the instance list from selecting an instance to send requests to.
- Track metadata such as zone or version when routing requires it, and clearly define policies for using metadata.
- Design timeouts, bounded retries, and graceful shutdown to handle synchronization lag when registry state changes.

Mastering service, instance, registry, and consumer provides the foundation for diving deeper into DiscoveryClient, ServiceRegistry, Eureka, Consul, health checks, and load balancing. Together, these components form the mechanism that maps a logical service name to an instance capable of handling requests in an ever-changing microservice environment.
