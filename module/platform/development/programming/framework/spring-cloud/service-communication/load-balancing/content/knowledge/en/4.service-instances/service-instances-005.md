# Mapping a Service ID to Available Replicas

In a microservices architecture, a client usually knows the **logical name of the service** it wants to call, while the system must determine which deployed replicas currently provide that service. Spring Cloud LoadBalancer handles the target-selection part by working with a list of `ServiceInstance`s associated with the service ID.

For example, the client calls `catalog-service`. At lookup time, this service might have three registered replicas:

| Service ID | Instance ID | Address |
|---|---|---|
| `catalog-service` | `catalog-1` | `http://10.0.1.21:8081` |
| `catalog-service` | `catalog-2` | `http://10.0.1.22:8081` |
| `catalog-service` | `catalog-3` | `http://10.0.1.23:8081` |

This mapping can be visualized as a lookup entry:

~~~text
catalog-service
    ├── catalog-1 -> http://10.0.1.21:8081
    ├── catalog-2 -> http://10.0.1.22:8081
    └── catalog-3 -> http://10.0.1.23:8081
~~~

The service ID is the key for finding the instance group. Each instance is a specific call target. The list can change when applications start, stop, register, deregister, or when the discovery source updates status.

## 1. Components participating in the mapping

Mapping a service ID to an instance list involves several coordinating components. Each component has its own responsibility:

| Component | Responsibility |
|---|---|
| Service registry | Stores information about registered services and instances |
| `DiscoveryClient` | Provides an API to query instances by service ID |
| `ServiceInstanceListSupplier` | Supplies the instance list to Spring Cloud LoadBalancer |
| LoadBalancer | Selects one instance from the supplied list |
| Integrated HTTP client | Sends the request to the address of the chosen instance |

The service registry can be Eureka, Consul, ZooKeeper, or a discovery system integrated with Spring Cloud. In simple environments, an application can also use a statically configured instance list.

`DiscoveryClient` is the abstraction for querying discovery data. `ServiceInstanceListSupplier` is the abstraction Spring Cloud LoadBalancer uses to receive the candidate list. A supplier can call a discovery client, use static configuration, or combine data with caching and filters.

~~~mermaid
flowchart TD
    A["Client calls catalog-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["DiscoveryClient or configuration source"]
    D --> E["ServiceInstance list"]
    E --> F["Filters / cache if configured"]
    F --> G["Candidate list"]
    G --> H["LoadBalancer selects an instance"]
    H --> I["HTTP client sends request to instance URI"]
~~~

An actual flow may include additional caching, filters, or custom suppliers. The diagram illustrates the main relationship between the service ID, instance-supplying source, and target-selection step.

## 2. Querying the instance list with DiscoveryClient

Spring Cloud Commons defines the `org.springframework.cloud.client.discovery.DiscoveryClient` interface. Two commonly used operations are:

- `getServices()`: retrieves the list of service IDs known to the discovery client.
- `getInstances(serviceId)`: retrieves the list of `ServiceInstance`s currently registered for that service ID.

Example inspecting replicas of `catalog-service`:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class ServiceDiscoveryInspector {

    private final DiscoveryClient discoveryClient;

    ServiceDiscoveryInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    void printCatalogInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        if (instances.isEmpty()) {
            System.out.println("No instances found for catalog-service");
            return;
        }

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "serviceId=%s, instanceId=%s, uri=%s%n",
                    instance.getServiceId(),
                    instance.getInstanceId(),
                    instance.getUri()
            );
        }
    }
}
~~~

The code above is for inspecting discovery data. It shows which instances the discovery client returns at query time. This is not yet the operation of picking an instance for an HTTP request.

In applications using reactive discovery, Spring Cloud also provides the `ReactiveDiscoveryClient` abstraction. The reactive API returns data as Reactor types, fitting reactive processing pipelines. Choosing the discovery client type depends on the integration and stack the application uses.

Note that the list returned by `DiscoveryClient` may differ from the final list used by LoadBalancer. `ServiceInstanceListSupplier` can apply caching, zone filtering, health checks, or request criteria before handing candidates to the chooser.

## 3. ServiceInstanceListSupplier maps a service ID to a candidate list

`ServiceInstanceListSupplier` belongs to the `org.springframework.cloud.loadbalancer.core` package. It is the component that directly supplies the `ServiceInstance` list to Spring Cloud LoadBalancer.

Conceptually, each supplier is tied to a service ID and provides a stream of instance lists:

~~~java
Flux<List<ServiceInstance>> get(Request request);
~~~

Several points to understand:

- A supplier works with the instance list and does not itself decide which instance an HTTP request will go to.
- The supplied list can be produced from a discovery client or another source.
- A supplier can be wrapped by other suppliers to add caching, filtering, or instance prioritization.
- A request context can be used by suppliers whose policies depend on request information.

In a typical configuration with discovery integration, Spring Cloud LoadBalancer can use a discovery-client-backed supplier to retrieve instances by service ID. Applications can also customize LoadBalancer configuration per service if a dedicated data source or list-supplying policy is needed. Exact bean declarations and supplier chaining depend on the Spring Cloud version in use.

### Distinguishing discovery sources and suppliers

These two components are often mentioned together but do not replace each other:

| Question | Answering component |
| --- | --- |
| Which services does the registry know about? | Discovery client |
| Which instances does this service ID have in the registry? | `DiscoveryClient.getInstances(serviceId)` |
| Which candidate list does LoadBalancer receive? | `ServiceInstanceListSupplier` |
| From the candidate list, which instance is chosen? | LoadBalancer's chooser |

This separation allows an application to change how lists are supplied without changing the HTTP client. For example, the same service ID can be looked up from Eureka in a deployed environment and from a static list in a test environment.

## 4. List sources: dynamic discovery and static configuration

### Dynamic discovery from a service registry

In multi-instance environments, each deployed replica typically registers its information with a registry. Clients or discovery integration components query the registry to obtain the list of instances by service ID.

Example of registry data:

~~~text
catalog-service
    catalog-1: host=10.0.1.21, port=8081
    catalog-2: host=10.0.1.22, port=8081
    catalog-3: host=10.0.1.23, port=8081
~~~

When a new instance registers, the list can grow. When an instance stops and deregisters—or is evicted by the registry after missing heartbeats—the list can shrink. When clients see changes depends on synchronization, heartbeats, caching, and registry update intervals.

### Static configuration with SimpleDiscoveryClient

Not every environment requires a standalone service registry. Spring Cloud Commons provides `SimpleDiscoveryClient` to declare instances in application configuration.

YAML example:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-1:8081
                metadata:
                  zone: zone-a
              - uri: http://catalog-2:8081
                metadata:
                  zone: zone-b
            payment-service:
              - uri: http://payment-1:8090
~~~

In this example:

- `catalog-service` maps to two URIs.
- `payment-service` maps to one URI.
- `zone` metadata is attached to each instance so compatible policies can use it.

Static configuration is useful for local development, demos, or integration testing. When instance counts change frequently, a dynamic registry is usually more suitable because information can update along the deployment lifecycle.

Do not confuse instance-list configuration with a fixed URL configuration in an HTTP client. When using LoadBalancer, the client still calls by service ID, such as `http://catalog-service/products`; the supplier is responsible for providing the matching instances.

## 5. The instance list changes across the service lifecycle

Mapping a service ID to instances is not immutable data. A typical lifecycle might unfold as follows:

1. Application `catalog-1` starts and registers service ID `catalog-service` along with its address.
2. The registry stores the instance info and includes it in lookup results.
3. Application `catalog-2` starts; the list for `catalog-service` gains another element.
4. An instance stops gracefully and deregisters; the registry removes the instance from the list.
5. If an instance loses connectivity abruptly, heartbeats or the registry's failure-detection mechanism can remove it after an interval.
6. The supplier pulls new data based on update mechanisms or cache expiration; LoadBalancer uses the new candidate list.

~~~mermaid
sequenceDiagram
    participant App as Catalog instance
    participant Registry as Service Registry
    participant Supplier as ServiceInstanceListSupplier
    participant LB as LoadBalancer
    App->>Registry: Register catalog-service
    Supplier->>Registry: Query list
    Registry-->>Supplier: catalog-1
    App->>Registry: catalog-2 registers
    Supplier->>Registry: Refresh list
    Registry-->>Supplier: catalog-1, catalog-2
    LB->>Supplier: Request candidate list
    Supplier-->>LB: Currently available instances
~~~

This is a conceptual model. Some registries use push mechanisms while others use polling or caching; therefore, the moment a client observes list updates may lag behind when an instance registers or stops.

### Successful registration does not guarantee the instance is ready

An instance can appear in the registry while the application is still initializing or not yet ready to receive traffic. Depending on the integration, the registry may rely on heartbeats, registration status, or health indicators to manage instances.

Therefore, distinguish three states:

- **Registered:** the registry holds the instance information.
- **Supplied by the supplier:** the instance appears in the candidate list received by LoadBalancer.
- **Able to handle requests:** the endpoint is genuinely ready and reachable from the client.

These three states are related but are not guaranteed to always coincide.

## 6. Caching and filtering the list before LoadBalancer chooses

When request volume is high, querying the registry for every request can add overhead and latency. Spring Cloud LoadBalancer supports additional suppliers to control how the list is provided.

Some examples:

| Supplier / mechanism | Purpose |
|---|---|
| `CachingServiceInstanceListSupplier` | Caches the instance list obtained from the underlying supplier |
| `HealthCheckServiceInstanceListSupplier` | Checks endpoint health and supplies instances passing criteria |
| `ZonePreferenceServiceInstanceListSupplier` | Prefers instances belonging to the matching zone |
| `HintBasedServiceInstanceListSupplier` | Filters or prioritizes instances based on a request hint |
| `SameInstancePreferenceServiceInstanceListSupplier` | Can prefer a previously used instance according to supported mechanisms |

These suppliers do not all have to be enabled together in every application. Choose according to deployment requirements and configure the order properly when combining multiple suppliers.

### Caching affects when changes become visible

Suppose the registry has removed `catalog-2`, yet the client-side cache still holds the old list:

~~~text
Current registry:
catalog-1, catalog-3

Client cache:
catalog-1, catalog-2, catalog-3
~~~

While the cache has not refreshed, the supplier may still supply `catalog-2`. If LoadBalancer picks that instance, the request may fail. Caching reduces registry lookup frequency, but requires a TTL and refresh strategy suited to the system's rate of change.

### Health checks help filter unhealthy endpoints

Health checks can probe each instance's endpoint and exclude instances failing conditions from the candidate list. This complements discovery: the registry answers which instances are registered, while health checks evaluate whether endpoints meet health criteria.

Health checks must be configured to fit the application, such as probe endpoint, check interval, and timeout. Do not assume that merely using a service registry causes LoadBalancer to automatically check every endpoint with HTTP health checks.

## 7. LoadBalancer receives the list and selects an instance

After the supplier provides the candidate list for the service ID, Spring Cloud LoadBalancer's chooser applies the configured policy to pick one instance.

For example, the list provided by the supplier:

~~~text
catalog-service -> [catalog-1, catalog-2, catalog-3]
~~~

With the round-robin algorithm, consecutive requests can be distributed cyclically across instances in the list. Specific selection also depends on chooser state, list ordering, and applied filters.

Points to distinguish:

- The supplier returns **the candidate list**.
- The chooser decides **one instance for the current call**.
- The HTTP client performs **the connection to the chosen instance's URI**.

If the list is empty, LoadBalancer has no instance to select. If the list has elements but all endpoints are unreachable, requests can still fail. Having a list is not a guarantee that the request will succeed.

## 8. Diagnosing when a service ID fails to map to instances

When a client calls `http://catalog-service/...` without finding a suitable instance, inspect sequentially from identifier to data source:

| Symptom | Common cause | Inspection direction |
|---|---|---|
| Service list lacks `catalog-service` | Application not registered yet or registry has not received data | Check registration status and service name on the registry |
| Service exists in registry but instance list is empty | No active registered instances or queried with wrong service ID | Call `getInstances("catalog-service")` and compare exact names |
| DiscoveryClient has instances but supplier returns an empty list | Filter, health check, or custom supplier excluded instances | Check the supplier chain and filter conditions |
| Supplier holds stale instances | Cache has not expired or discovery data has not synced | Check TTL, refresh schedule, and heartbeats |
| Instance selected but connection fails | Host/port unreachable or application not ready | Test from the client's exact network environment |
| Only some clients fail to see instances | Different discovery config, namespace, zone, or registry permissions | Compare discovery configuration and scope across clients |

Several important failures to distinguish:

**Wrong service ID.** The client calls `catalog-service`, whereas the application registers under `catalog`. Align the service name across logical URLs, registry, and LoadBalancer configuration.

**Registry has not updated in time.** An instance just started or stopped, yet the client does not see the change yet. Check heartbeats, synchronization mechanisms, and caching before concluding the load-balancing algorithm has a bug.

**Supplier filters out the entire list.** Zone filters or health checks can eliminate every instance if metadata, zone, or probe endpoints are misconfigured. Inspect the list before and after each filtering step.

**Instance appears in the list but cannot be reached.** Check host and port from the container or host running the client. Results tested from a developer machine can differ from results inside the deployment network.

## 9. Hands-on check of service ID mapping

You can use a simple test to confirm the registry returns the expected instance list:

1. Start at least two replicas of `catalog-service`.
2. Confirm each replica registers under the exact same service ID.
3. Call `DiscoveryClient.getInstances("catalog-service")` and record the instance IDs and URIs.
4. Gracefully stop one replica, wait for the registry to update, and query again.
5. Inspect the list provided by the supplier to determine whether caching or filters altered the result.
6. Send requests via a LoadBalancer-integrated HTTP client and observe which instance actually handles each request.

When logging for diagnostics, include service ID, instance ID, URI, query timestamp, and data source. Avoid logging only "service not found", because that message does not distinguish a registration error, a query error, or a list-filtering error.

## 10. Design principles for service ID mapping

A stable service ID mapping should satisfy these principles:

- Use a consistent service ID across clients, registry, and LoadBalancer configuration.
- Each instance must advertise a host and port reachable from the client's network.
- Update registrations and deregistrations along the application lifecycle.
- Choose a TTL/cache aligned with instance change frequency.
- Enable health checks or filters when the system needs to exclude unready endpoints.
- Observe the list from the discovery client, the list from the supplier, and the final selected instance.

The service ID helps clients locate the right service group. Discovery supplies data about deployed replicas, while `ServiceInstanceListSupplier` feeds the candidate list into Spring Cloud LoadBalancer. When each step is clearly understood, you can pinpoint whether a fault lies in service registration, list updates, instance filtering, or connecting to the chosen endpoint.
