# Why Fixed Addresses Are Unsuitable for Elastic Services

In a small application, configuring a fixed IP address and port for the service an application needs to call seems simple. For example, order-service might send requests to inventory-service at **10.0.2.15:8081**. This approach works when hosts rarely change and the number of instances is nearly fixed.

Microservices are typically deployed in environments with containers, virtual machines, or orchestration platforms. Instances can be added when load increases, replaced when errors occur, moved to other machines during deployment, or scaled down when demand drops. The IP address and port of each instance are therefore not always stable. If a consumer depends on a specific address, every change in topology can require updating configuration and redeploying.

This is why service discovery becomes an important component in microservice architecture. Instead of forcing consumers to know the address of each instance, the system uses a logical service name to find existing instances. In Spring Cloud, this is supported through abstractions such as **DiscoveryClient**, **ServiceRegistry**, registries such as Eureka or Consul, and instance selection mechanisms such as Spring Cloud LoadBalancer.

## 1. Fixed Addresses Create Infrastructure Coupling

An IP address and port describe where a process is listening at a specific point in time. It is not necessarily the long-term identity of the service.

Suppose inventory-service is running on a machine with address **10.0.2.15:8081**. order-service stores this address in a configuration file and calls it directly. If inventory-service is redeployed on another machine, the new address might be **10.0.3.22:8081**. The consumer will keep calling the old address until its configuration is updated.

When there are many services and many environments, tying configuration to individual machine addresses tightly couples the application to the infrastructure layout. A deployment change that seems to concern only the provider can force many consumers to change as well.

This coupling shows up clearly in several common scenarios:

- **Infrastructure changes:** virtual machines or containers that are recreated can receive new addresses.
- **Deploying a new version:** old instances are stopped and new instances are initialized elsewhere.
- **Network changes:** subnets, port mappings, NAT, or network configuration can change the address seen by consumers.
- **Multiple environments:** the address of the same service differs across developer machines, testing, staging, and production.

The issue is not that IP addresses cannot be used, but that the consumer must know and manage infrastructure details that can change independently of the service's functionality.

## 2. Scaling Instance Counts Quickly Makes Static Configuration Stale

A service often needs multiple instances to serve load and increase availability. When traffic increases, the platform can spin up more instances; when traffic drops, the system can remove excess instances.

Suppose inventory-service initially has two instances:

~~~text
inventory-service
  10.0.2.15:8081
  10.0.2.16:8081
~~~

When load increases, the system adds two more instances:

~~~text
inventory-service
  10.0.2.15:8081
  10.0.2.16:8081
  10.0.2.17:8081
  10.0.2.18:8081
~~~

If order-service is only configured with the two initial addresses, it does not automatically know that new instances have appeared. Part of the new processing capacity may go unused. If the system scales down and removes **10.0.2.16:8081**, the consumer may keep sending requests to an address that is no longer active.

When addresses must be managed manually, every scale-out or scale-in requires synchronizing configurations between the provider and consumers. The more consumers there are, the greater the risk of inconsistent configuration.

~~~mermaid
flowchart TD
    subgraph Static["Static address configuration"]
      C["Order Service"] --> A["IP A"]
      C --> B["IP B"]
      N["New instance IP C"] -.->|"Consumer unaware"| C
    end
    subgraph Discovery["Lookup by service name"]
      C2["Order Service"] -->|"inventory-service"| R[("Service Registry")]
      R --> A2["Instance A"]
      R --> B2["Instance B"]
      R --> C3["Instance C"]
    end
~~~

With service discovery, providers register instance information when joining the system. Consumers look up by service ID, such as **inventory-service**, to receive the list of instances the discovery client currently knows about. When the list is updated, the service calling mechanism can choose new instances without requiring the consumer to record each IP.

## 3. An Address May No Longer Represent a Healthy Instance

Having a syntactically valid address in configuration does not mean the process at that address is still serving requests. An instance may have crashed, run out of resources, lost network connectivity, or become unready to handle business logic.

If a consumer stores fixed addresses, it may continue sending requests to a broken instance. To avoid this, the consumer would have to check status itself, track connection failures, and update its address list. When there are many consumers, implementing this logic independently in every place becomes difficult to keep consistent.

A service registry helps centralize registration information and the status observed by the discovery system. Depending on the platform, instances can send heartbeats, undergo health checks, or be removed from the registry after a timeout period. Consumers and routers can use that information to avoid selecting instances that are no longer suitable.

However, the registry is not an instantaneous, absolute source of truth. An instance that just failed may still appear in the cache for a period of time; an instance that just started up may not yet be visible to every consumer. Therefore, applications still need timeouts, connection error handling, and appropriate resilience policies. Discovery reduces dependence on manual addressing, but it does not eliminate all network or application errors.

## 4. Per-Instance Address Configuration Increases Operational Overhead

Imagine a system with order, inventory, payment, and shipping services. Each service may have multiple consumers. If every consumer stores a list of provider IPs and ports, the operations team must ensure all configurations accurately reflect the current topology.

| Change | Consequence When Using Per-Instance Addresses |
|---|---|
| Adding an instance | Lists on consumers must be updated if the new instance is to be used. |
| Removing an instance | The old address must be removed from every related configuration. |
| Replacing a machine or container | Old addresses may become invalid; consumers must be updated. |
| Multi-environment deployment | Separate address sets must be maintained for each environment. |
| Provider temporarily unhealthy | Consumers may keep calling the failing target if there is no mechanism to detect and remove it. |

These changes increase the frequency of configuration edits, redeployments, and post-deployment checks. Static configurations also easily cause drift between environments: a consumer might call the right provider in staging while still holding a production address or an old instance address.

When using logical service names, consumers depend on a **service ID** instead of individual instance addresses. The address list is managed by the registry and discovery client. Adding or replacing instances can therefore be handled through registration and discovery updates rather than editing each consumer.

## 5. Logical Service Names Decouple Consumers from Physical Addresses

A logical service name describes the service a consumer wants to use, for example **inventory-service**. The registry maps this name to one or more registered instances.

~~~mermaid
flowchart LR
    C["Order Service"] -->|"Look up inventory-service"| D["Discovery Client"]
    D <--> R[("Registry")]
    D -->|"Instance list"| L["Load Balancer"]
    L --> I1["Inventory instance A"]
    L -.-> I2["Inventory instance B"]
~~~

The process typically proceeds as follows:

1. Each provider instance registers its service ID and connection information with the registry.
2. The consumer asks the discovery client to find instances by service ID.
3. The discovery client returns the known instances, either from the registry or cached data.
4. The load balancer selects a suitable instance for the request.
5. The consumer sends the request to the address of the selected instance.

As a result, the consumer only needs to know the name of the service to call. Providers can be redeployed, moved across machines, or scaled up and down without requiring consumers to store specific address lists.

This establishes a clear boundary between two types of information:

- **Logical identity:** the service ID, such as **inventory-service**. This is the name the consumer uses to request a capability.
- **Instance address:** the host, port, and connection details of a specific process. This is data that can change during operations.

Separating these two types of information ensures infrastructure changes have minimal impact on the consumer's business code.

## 6. Example in Spring Cloud

An approach that depends on a fixed address might be configured as follows:

~~~yaml
inventory:
  base-url: http://10.0.2.15:8081
~~~

The consumer uses this configuration to call the provider:

~~~java
String url = inventoryBaseUrl + "/api/items/" + itemId;
ItemDto item = restTemplate.getForObject(url, ItemDto.class);
~~~

When the instance address changes, the **inventory.base-url** configuration must be updated. If the provider has multiple instances, the application also needs a way to manage the list and choose a destination.

With Spring Cloud LoadBalancer, the consumer can use the service ID in the URL:

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

In this example, **inventory-service** is the service ID. RestTemplate is annotated with **@LoadBalanced** so Spring Cloud LoadBalancer handles finding and selecting an instance through the corresponding discovery integration. The provider still must be registered with the registry, and the application must have the appropriate dependencies and configuration for the registry being used.

If you need to query the instance list for a custom purpose, Spring Cloud provides **DiscoveryClient**:

~~~java
List<ServiceInstance> instances =
    discoveryClient.getInstances("inventory-service");
~~~

This list indicates which instances the discovery client currently knows about. Choosing an instance to call a service should generally be delegated to Spring Cloud LoadBalancer so that load-balancing policies are applied consistently.

## 7. Is a Fixed Address Always Wrong?

Not every fixed address is inappropriate. You need to distinguish between **the address of an individual instance** and **a stable address representing the entire service**.

A virtual IP, DNS name, or load balancer address can be designed to remain stable while the backend instances behind it continuously change. Consumers call that stable address; the load balancer or proxy is responsible for distributing requests to active instances. This is a valid implementation of server-side discovery.

| Address Type | Characteristics | Usage |
|---|---|---|
| IP and port of a single instance | Tied to a specific process, subject to change | Only suitable when the instance lifecycle is truly static or there is a clear operational reason |
| Logical service name | Represents the group of instances for a service | Suitable for client-side discovery when the client has discovery and load-balancing integration |
| Stable address of a load balancer or gateway | Represents a shared entry point; backend targets can change | Suitable for server-side discovery |

DNS can also provide a stable name for a service. However, you need to consider how DNS updates records, cache TTLs, the ability to remove unhealthy targets, and how load is distributed. A simple DNS name does not inherently provide all the capabilities of a registry and load balancer.

Therefore, what should be avoided is letting each consumer depend directly on the private address of individual short-lived instances. A stable address managed by a load balancer or a logical name managed by service discovery can still be an appropriate access point.

## 8. When Should You Use Service Discovery?

Service discovery is especially useful when a system has one or more of the following characteristics:

- The number of instances changes based on load or autoscaling policies.
- Containers or virtual machines are frequently created, replaced, and relocated.
- Multiple consumers need to call the same provider.
- Applications run across multiple environments with different topologies.
- The system needs to update the instance list and remove targets that are no longer valid.
- Consumers need to select one instance from many to distribute requests.

When designing, clearly identify where instances register, where service IDs are looked up, where instance selection happens, and how health status is updated. In Spring Cloud, these roles are typically coordinated via **ServiceRegistry**, **DiscoveryClient**, Eureka or Consul, and Spring Cloud LoadBalancer.

Service discovery does not make network addresses disappear. Every request must ultimately reach a specific host and port. The value of discovery lies in managing the mapping from a logical service name to current instance addresses, so consumers do not have to maintain address lists that change with the infrastructure.
