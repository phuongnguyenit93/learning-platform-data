# The DiscoveryClient Contract and How to Retrieve the Service List

In Spring Cloud Service Discovery, an application can run as multiple instances across different machines or containers. The address of each instance can change during deployment, scaling, or restarts. Therefore, a consumer needs to look up instances by service name rather than hardcoding IP addresses and ports.

**DiscoveryClient** is the query contract of Spring Cloud Commons: it allows an application to ask which service IDs the registry currently knows about and find the instances belonging to a service ID. Eureka, Consul, and other discovery mechanisms can provide their own implementations, while the consumer's business code continues to work through the same API.

This lesson focuses on that contract, how to read the service list, and how to interpret the results in a microservice system. It is part of Spring Cloud Service Discovery, where registration, health checks, load balancing, security, and handling an asynchronous registry together determine the ability to find and call the right instance.

## 1. Distinguishing between a service and an instance

A **service** is a logical capability, for example `inventory-service`. An **instance** is a specific running process providing that service, for example a process at `10.0.2.15:8080`.

| Concept | Meaning | Example |
|---|---|---|
| Service ID | Logical name used to look up the service | `inventory-service` |
| Service instance | A specific running copy of the service | Instance A, instance B |
| Endpoint | Address reachable to connect to the instance | `http://10.0.2.15:8080` |
| Registry | Place storing registration information and instance status | Eureka Server, Consul |
| Discovery client | Component reading service information from the registry | EurekaDiscoveryClient, ConsulDiscoveryClient |

A service can have zero, one, or many instances. The service ID is usually configured consistently across running copies; for many Spring Boot applications, `spring.application.name` is the value commonly used as the service name. The final name visible to the consumer depends on the configuration and registry implementation.

General flow:

~~~mermaid
flowchart LR
    P["Provider instance"] -->|"register / renew"| R[("Service registry")]
    C["Consumer"] --> D["DiscoveryClient"]
    D -->|"read service IDs and instances"| R
    C --> L["Spring Cloud LoadBalancer"]
    L -->|"select an instance"| P
~~~

The provider registers instance information with the registry. The consumer uses DiscoveryClient to read that information. When sending a request to a service, the consumer typically combines discovery with Spring Cloud LoadBalancer to choose an appropriate instance.

## 2. The DiscoveryClient contract

DiscoveryClient belongs to the `org.springframework.cloud.client.discovery` package in Spring Cloud Commons. The two core methods are:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

DiscoveryClient also provides implementation description information via `description()`. In current Spring Cloud Commons versions, the contract also participates in the `Ordered` ordering mechanism, which is useful when an application has multiple discovery clients or uses a composite client. Supporting details may vary by version; when writing application code, rely on the API of the Spring Cloud release train that the project is using.

| Method | Input | Result | When to use |
|---|---|---|---|
| `getServices()` | None | List of service IDs visible to the client | When you want to list published services |
| `getInstances(serviceId)` | Service ID | List of instances for that service | When you want to find host, port, URI, and metadata of a service |
| `description()` | None | Implementation description | Logging or diagnosing which discovery client type is active |

Points to remember:

- `getServices()` returns service names, not host addresses. To get addresses, you need to call `getInstances(serviceId)` next.
- `getInstances(serviceId)` returns a list because a service can have multiple running copies. Do not assume there is only one instance.
- Results depend on the data currently provided by the registry and discovery implementation. The list can change as instances register, shut down, or are evicted from the registry.
- Do not rely on element order to select an instance. The returned order is not a load-balancing contract.

### What does ServiceInstance contain?

Each element in the `getInstances()` result is a `ServiceInstance`, belonging to the `org.springframework.cloud.client` package. Commonly used information includes:

| Property / method | Meaning |
|---|---|
| `getServiceId()` | Service ID under which the instance registered |
| `getHost()` | Host of the instance |
| `getPort()` | Port of the instance |
| `isSecure()` | Whether the instance uses a secure connection |
| `getUri()` | Connection URI to the instance |
| `getMetadata()` | Key-value metadata provided by the provider or registry |
| `getInstanceId()` | Instance identifier if provided by the implementation |

Prefer using `getUri()` when you need a connection URI. Manually concatenating host and port may miss the scheme or security details. Metadata can be useful for classifying instances or passing operational attributes, but should not contain passwords, tokens, or secrets.

## 3. Injecting and using DiscoveryClient

Spring manages DiscoveryClient as a bean when appropriate discovery dependencies and configuration are included in the application. A consumer can inject this interface; as a result, the business layer does not have to depend directly on Eureka or Consul.

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceCatalog {

    private final DiscoveryClient discoveryClient;

    public ServiceCatalog(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> listServiceIds() {
        return discoveryClient.getServices();
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
~~~

The class above has two separate operations:

1. `listServiceIds()` retrieves the service IDs that the discovery client currently sees.
2. `findInstances(serviceId)` retrieves the specific running instances of a service.

Example of calling from another component:

~~~java
List<String> services = serviceCatalog.listServiceIds();

List<ServiceInstance> instances =
        serviceCatalog.findInstances("inventory-service");

if (instances.isEmpty()) {
    // No matching instance found at query time.
} else {
    for (ServiceInstance instance : instances) {
        System.out.println(instance.getServiceId());
        System.out.println(instance.getUri());
        System.out.println(instance.getMetadata());
    }
}
~~~

When the result is empty, the consumer should handle it according to business logic: report that the service is unavailable, return a controlled error, or retry according to an appropriate policy. Do not access the first element without checking the list first.

If exposing discovery information through an administrative API, map `ServiceInstance` to a DTO containing only the necessary fields. Avoid returning all metadata or internal addresses to users who do not have permission to view the system topology.

## 4. DiscoveryClient and ServiceRegistry handle two different directions

In Spring Cloud, two abstractions often appear together but solve two different tasks:

| Abstraction | Role | Example operation |
|---|---|---|
| `ServiceRegistry` | Register, update status, or deregister an instance | Provider registers on startup and leaves the registry on shutdown |
| `DiscoveryClient` | Query service IDs and instance lists | Consumer looks up instances of `inventory-service` |

You can think of it as:

- **ServiceRegistry is the write path**: the provider announces which service it provides, at what address, and with what metadata.
- **DiscoveryClient is the read path**: the consumer asks the registry which services currently exist and which instances belong to the desired service.

In a typical lifecycle, the provider starts up and registers an instance; the registry receives heartbeats or runs health checks depending on the backend mechanism; the consumer queries the discovery client; when the provider stops, the instance is deregistered or removed by the registry after its lease expires. The exact mechanism depends on Eureka, Consul, and deployment configuration.

Having a record in the registry does not guarantee that the next request will definitely succeed. The instance may have just failed, the network may be interrupted, or registry data may not have updated yet. Discovery answers the question "which addresses are currently published"; health checks and actual requests provide further evidence of serving capability.

## 5. Combining with load balancing

DiscoveryClient helps find instances. It does not automatically turn a normal HTTP call into a load-balanced call.

For example, if calling the first instance directly:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

ServiceInstance selected = instances.get(0);
URI target = selected.getUri();
~~~

This approach only illustrates how to obtain the URI. In a real application, it has several problems:

- The list may be empty, causing access to the first element to fail.
- The first instance is not necessarily the healthiest or most suitable one.
- Multiple consumers may choose the same instance, causing uneven load distribution.
- Calling code has to handle selection, list updates, and error cases itself.

For service-to-service calls, Spring Cloud LoadBalancer should generally be used. The load balancer takes the service ID, obtains the instance list from the discovery client, and selects an instance according to the configured strategy.

A familiar example with RestTemplate:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
~~~

The consumer can call by service ID:

~~~java
restTemplate.getForObject(
        "http://inventory-service/api/items",
        ItemResponse[].class
);
~~~

To use this pattern, the application needs a Spring Cloud LoadBalancer dependency compatible with the Spring Cloud release train. Depending on the Spring Boot version and HTTP client type, the project can also use WebClient or RestClient with the corresponding load-balancing integration.

Once using a load balancer, avoid manually calling `getInstances()` and selecting an instance in each business class. Let a single mechanism be responsible for selecting instances, caching the list, and applying an appropriate retry policy. Retries should be bounded and applied only where safe for the corresponding request type; retrying a non-idempotent write operation can cause duplicate side effects.

## 6. Differences between discovery backends

DiscoveryClient provides a common access point, but it does not make every registry behave identically in operation.

| Backend | How discovery is provided | Things to watch out for |
|---|---|---|
| Eureka | Clients register with Eureka Server and typically renew leases via heartbeats | Client-side cache and update intervals can prevent changes from appearing immediately |
| Consul | Services are registered in the catalog; health checks can affect published status | Check the health check policy and how healthy services are queried |
| SimpleDiscoveryClient | Uses a statically configured list of instances | Suitable for simple environments or testing; does not automatically reflect dynamic instance lifecycles |

Therefore, code calling DiscoveryClient should rely on the common contract, while heartbeat configuration, health checks, registry access permissions, cache durations, and deregistration mechanisms need to be verified against the actual backend.

In reactive applications, Spring Cloud Commons also has the `ReactiveDiscoveryClient` abstraction. Choose the synchronous or reactive API that fits the application's processing model, avoiding blocking the event loop with synchronous calls on reactive threads.

## 7. Handling empty results, registry failures, and stale data

When querying discovery, distinguish between the following situations:

| Situation | Possible interpretation | Recommended handling |
|---|---|---|
| `getServices()` returns an empty list | The client does not see any services yet | Check whether providers have registered, service IDs, and discovery configuration |
| `getInstances(id)` returns an empty list | No instances are published for that ID at query time | Check service name, health checks, registration status, and environment |
| Query throws an exception or times out | Registry, network, authentication, or discovery provider has an issue | Log with context, set timeouts, and handle errors per policy |
| Instances exist but calls fail | The record may be stale or the endpoint is unreachable from the consumer | Check health checks, network, security groups, DNS, and provider logs |

An empty list does not necessarily mean the registry is broken. Conversely, a list with instances does not prove every instance is healthy. How failures manifest depends on the implementation; do not assume every backend turns errors into an empty list.

Some operational principles:

- Use appropriate health checks and heartbeats/leases so the registry removes instances that are no longer serving.
- Configure graceful shutdown so providers deregister when possible.
- Set timeouts for network calls and use a circuit breaker or fallback when business logic allows.
- Monitor instance counts, registry refresh timestamps, query errors, and request failure rates.
- Do not query the registry continuously on every request if the load balancer already manages caching and list updates.
- Protect the registry and discovery administrative endpoints with authentication, authorization, and network access restrictions.
- Do not put sensitive information in metadata or log full connection configurations.

## 8. Quick checklist when the consumer cannot find a service

When `getInstances("inventory-service")` does not return the expected instances, check in order:

1. **Is the service ID right?** Compare the name the provider registers with the name the consumer queries, including case differences if the backend is case-sensitive.
2. **Has the provider registered?** Check startup logs, discovery configuration, and application status on the registry.
3. **Is the instance passing health checks?** An instance marked unhealthy may not appear in the results used by the consumer.
4. **Can the consumer connect to the registry?** Check DNS, network policy, credentials, TLS, and timeouts.
5. **Is the data stale?** Check heartbeat intervals, refresh intervals, and caches on the registry or client.
6. **Is the endpoint reachable from the consumer?** The published host and port must be routable from the consumer's network; a provider's internal address may not work across network boundaries.

Check logs on the provider, registry, and consumer. Looking only at the service list on one side is often not enough to determine whether the issue lies in registration, registry synchronization, or network connectivity.

## 9. Key takeaways

- `getServices()` returns the list of service IDs; `getInstances(serviceId)` returns the instances of a service.
- `ServiceInstance` provides the URI, host, port, secure status, and metadata describing a running copy.
- `ServiceRegistry` handles registration and status updates; `DiscoveryClient` handles querying.
- Discovery and load balancing are two related but distinct responsibilities. Use Spring Cloud LoadBalancer to select an instance when calling a service.
- A registry can lag or contain stale records. Health checks, timeouts, error handling, security, and operational observability are needed for service discovery to work reliably.

Once you understand the DiscoveryClient contract, a consumer can look up services through Eureka, Consul, or another implementation without coupling business logic to a specific registry.
