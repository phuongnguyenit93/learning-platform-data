# From serviceId to Instance List to an HTTP Request

In a microservice system, a service often runs multiple replicas. Replicas may be added, restarted, or moved across machines while the system is running. Therefore, a consumer should not hardcode the IP address and port of a provider. The consumer needs to know the **logical name of the service**, discover the available instances, and then send the request to a suitable instance.

Spring Cloud provides abstractions to implement this flow. **DiscoveryClient** reads the instance list by serviceId; **ServiceRegistry** represents registration and status management operations; Eureka and Consul are systems that can store registration information; **Spring Cloud LoadBalancer** selects an instance to send the request to. These components work together to turn a logical address such as `http://inventory-service` into an actual network address.

## 1. Distinguishing serviceId, instance, and registry

Suppose an e-commerce system has an inventory management service. This service is deployed with three replicas:

| Concept | Example | Meaning |
|---|---|---|
| serviceId | `inventory-service` | Logical name that a consumer uses to find the service |
| Instance | `10.20.1.11:8081` | A running provider process capable of receiving requests |
| Instance ID | `inventory-service:node-a:8081` | Identifier of a specific replica in the registry |
| Registry | Eureka or Consul | The place that stores information about registered instances |
| Discovery client | `DiscoveryClient` | API for an application to query the instance list by serviceId |

A serviceId can map to zero, one, or many instances. This list changes according to deployment state. An instance record typically contains the serviceId, instance ID, host, port, security scheme, and metadata such as zone or version.

The service name usually comes from the provider's `spring.application.name` configuration:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
~~~

When there are multiple replicas, each replica registers the same serviceId but has its own address and instance ID. The consumer only needs to know the serviceId; it does not need to know the physical addresses in advance.

## 2. Lifecycle from provider startup to leaving the registry

A typical registration flow proceeds as follows:

1. **Application startup:** the provider loads configuration, determines its serviceId, instance ID, reachable address, and port.
2. **Registration:** the discovery client sends instance information to the registry. The registry stores the record so consumers can look it up.
3. **Status monitoring:** the client sends heartbeats or the registry performs health checks depending on each platform's mechanism. The check result helps the registry determine whether the instance can still serve traffic.
4. **Lookup and usage:** the consumer fetches the instance list and selects an instance to send a request.
5. **Leaving the system:** when the application shuts down gracefully, the client attempts to deregister. If the process crashes unexpectedly, the registry typically removes the record only after the lease, TTL, or health check indicates the instance is no longer valid.

Eureka and Consul both support service registration, but their operational details differ. A Eureka client typically maintains a lease via heartbeats; Eureka Server has a mechanism to evict instances that do not renew their leases, and can also adjust eviction under certain registry protection states. Consul uses service registration combined with health checks such as HTTP, TCP, or TTL. Therefore, do not assume every registry detects dead instances immediately or uses the same check interval.

Successful registration also does not mean the application is ready to handle every request. The health endpoint must accurately reflect serving readiness; if the application reports healthy too early, consumers may call an instance that has not finished initializing. Conversely, an overly sensitive health check may remove a temporarily slow instance from the list.

## 3. Using DiscoveryClient to retrieve the instance list

In Spring Cloud Commons, `DiscoveryClient` provides an abstracted discovery lookup API. The application does not need to depend directly on Eureka-specific or Consul-specific APIs:

- `getServices()` returns the serviceIds known to the discovery implementation.
- `getInstances(serviceId)` returns the known instances for that serviceId.

The following example illustrates how to look up the addresses of an instance:

~~~java
import java.net.URI;
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryInstanceLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryInstanceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findInstanceUris() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("inventory-service");

        if (instances.isEmpty()) {
            throw new IllegalStateException(
                    "No instance registered for inventory-service");
        }

        return instances.stream()
                .map(ServiceInstance::getUri)
                .toList();
    }
}
~~~

The result may contain multiple URIs, for example:

~~~text
http://10.20.1.11:8081
http://10.20.1.12:8081
http://10.20.1.13:8081
~~~

This code snippet only illustrates the **serviceId → instance list** step. It does not perform load balancing yet. If you always pick the first element, every request may pile onto the same replica; the list order is also not a guarantee of priority. In a real application, let Spring Cloud LoadBalancer select an instance or implement an intentional selection policy.

An empty list should be handled as a service dependency failure: return an appropriate error to the caller, apply timeouts and a bounded retry policy if appropriate, and log the issue for investigation. Do not loop lookups indefinitely or pass an externally user-supplied serviceId directly into the discovery API.

### DiscoveryClient and ServiceRegistry have different roles

These two abstractions often appear together but serve two opposite directions:

| API | Role | Typical operations |
|---|---|---|
| `DiscoveryClient` | Consumer looking up services | Reading serviceIds and instance lists |
| `ServiceRegistry` | Provider or registration management component | Registering, deregistering, reading or updating registration status |

`ServiceRegistry` is an abstraction for registration operations; it is not another name for Eureka Server or Consul Server. In a Spring Cloud application, auto-registration is typically configured via the discovery starter and the application lifecycle. Only call the manual registration API when you have a special management need and clearly understand the registration lifecycle. Duplicate registration, forgetting to deregister, or manually updating status out of sync with health checks can cause the registry to reflect reality inaccurately.

In addition to the synchronous `DiscoveryClient`, Spring Cloud also has a corresponding reactive abstraction in integrations that support reactive discovery. Choose the API that matches your application stack and avoid blocking the event loop when handling reactive requests.

## 4. From an instance list to an HTTP request

Looking up the instance list only answers the question "which replicas exist?". To send an HTTP request, the application also has to select a replica, build the target address, and handle the call result.

There are two approaches:

- **Manual lookup and manual selection:** call `DiscoveryClient`, select a `ServiceInstance`, and then call the instance's URI. This approach is useful for administrative tools, diagnostics, or cases requiring a custom selection policy.
- **Using Spring Cloud LoadBalancer:** the consumer sends a request to the serviceId; LoadBalancer retrieves candidate instances via the discovery integration, selects an instance, and forwards the request to the physical address. This is usually the right choice for standard service-to-service calls.

With Spring WebFlux, you can declare a `WebClient.Builder` annotated with `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

The consumer uses that builder to make calls by service name:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<InventoryResponse> findInventory(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

In the example, `inventory-service` is the serviceId. With a builder annotated with `@LoadBalanced`, Spring Cloud adds serviceId resolution and instance selection. LoadBalancer translates the logical target into the selected instance's host and port before the request is sent. If you use a plain `WebClient.Builder` without load balancing configuration, the name `inventory-service` may be treated as a DNS hostname and fail to resolve through the registry.

You need the discovery starter corresponding to your registry and Spring Cloud LoadBalancer on the classpath. For example, an application using Eureka typically adds `spring-cloud-starter-netflix-eureka-client`; an application using Consul typically adds `spring-cloud-starter-consul-discovery`. Add `spring-cloud-starter-loadbalancer` when the application configuration requires this starter directly. Manage versions using the Spring Cloud BOM compatible with your Spring Boot version; do not arbitrarily mix release train versions.

Overall processing flow:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant LB as Spring Cloud LoadBalancer
    participant D as DiscoveryClient
    participant R as Eureka or Consul
    participant I as Selected instance

    C->>LB: GET http://inventory-service/api/inventory/sku-1
    LB->>D: Get instances by serviceId
    D->>R: Read registry or discovery cache
    R-->>D: List of registered instances
    D-->>LB: Candidate instances
    LB->>LB: Select an instance
    LB->>I: HTTP GET to actual host:port
    I-->>LB: HTTP response
    LB-->>C: HTTP response
~~~

In practice, the discovery client or service instance supplier may use caching; not every request necessarily makes a network query to the registry. The default selection policy is usually round-robin, though the application can configure a different supplier or algorithm. The outcome also depends on registry data, cache state, and health check configuration at selection time.

## 5. Registry configuration on provider and consumer

Example of a provider registering with Eureka:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
~~~

A consumer has its own serviceId but calls the provider's name:

~~~yaml
spring:
  application:
    name: order-service

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
~~~

In the code of order-service, a call to `http://inventory-service/...` is resolved to an inventory-service instance. With Consul, the provider and consumer configure the connection to the Consul agent/server using `spring.cloud.consul` properties; the registered service name is usually taken from `spring.application.name`. Specific configuration depends on the environment and starter version.

In container or Kubernetes environments, ensure the address registered by the provider is reachable from the consumer. An instance registering a loopback address, a hostname that only exists inside another container, or an unpublished internal port will cause lookup to succeed while HTTP connections fail.

## 6. Common errors and how to investigate

| Symptom | Possible cause | What to check |
|---|---|---|
| No instance found | Provider not registered, wrong serviceId, or registry not ready | Compare `spring.application.name`, the name called by the consumer, and the service list in the registry |
| Instance exists but call times out | Host/port unreachable from consumer, firewall, or wrong network | Test connectivity from the consumer's runtime environment to the instance address |
| Calling a dead instance by mistake | Heartbeat, lease, health check, or cache not updated | Check health status, check intervals, and cache TTL |
| Requests pile onto one replica | Code always picks the first element or LoadBalancer is misconfigured | Check the instance selection logic and log the selected instance ID |
| Provider starts up but is not ready | Health endpoint reports healthy too early | Adjust readiness/health checks to accept traffic only after dependencies are ready |
| Registry has duplicate or stale records | Unstable instance ID, shutdown without deregister, or overly long TTL | Check instance ID, application lifecycle, and expiration policy |

When diagnosing, log the serviceId, instance ID, host, port, and call outcome so you can correlate requests with actual instances. Do not log tokens, passwords, or sensitive metadata. Clearly distinguish three situations: the registry has no instances, LoadBalancer cannot select an instance, and an instance was selected but the HTTP connection failed. Each situation sits at a different layer.

Retries do not replace health checks or discovery. If a request was sent to a failing instance, retrying can help try another instance when LoadBalancer and retry configuration allow it; however, retries must be bounded, have clear timeouts, and account for the operation's idempotency. For data-writing operations, blind retries can cause repeated side effects.

## 7. Security and reliability

The registry is a critical data source for internal routing, so both the registration channel and the lookup channel must be protected:

- Restrict network access to the registry; enable authentication and ACLs according to platform capabilities.
- Use TLS for connections to the registry and consider mTLS between services when the security model requires it.
- Do not store secrets, access tokens, or personal data in instance metadata.
- Do not treat finding an instance address as proof that the caller is authorized to call the API. The provider must still authenticate and authorize requests.
- Only allow serviceIds from configuration or a controlled allowlist; do not turn discovery into an arbitrary proxy to user-specified services.
- Monitor instance counts, health status, registration duration, and inter-service call errors.

Request reliability depends on multiple layers: the provider must register properly, the registry must update status, the consumer must receive a sufficiently fresh list, LoadBalancer must select a valid candidate, and the network must be able to reach the instance. No single abstraction alone guarantees the entire chain will always succeed.

## 8. Adoption workflow

When integrating a service-to-service call, you can follow this sequence:

1. Set a stable serviceId for the provider via `spring.application.name`.
2. Choose a registry and configure the corresponding discovery starter on both the provider and consumer.
3. Verify the provider registers the correct host, port, instance ID, and health check.
4. Verify the consumer can read the list with `DiscoveryClient.getInstances(serviceId)`.
5. Use Spring Cloud LoadBalancer for standard HTTP requests; only perform manual instance selection when there is a specific reason.
6. Configure timeouts, bounded retries, empty list handling, and logging for the selected instance.
7. Test scenarios where the provider starts up, scales replicas, stops gracefully, crashes unexpectedly, and temporarily loses connectivity to the registry.
8. Secure the registry and provider APIs according to the system's security policy.

The key takeaway is: **serviceId identifies the logical service; DiscoveryClient provides the instance list; LoadBalancer selects an instance; the HTTP client sends the request to that instance's actual address.** The registry and health checks maintain the data supporting this process, while the application must still handle timeouts, network errors, and instance state changes while a request is in flight.
