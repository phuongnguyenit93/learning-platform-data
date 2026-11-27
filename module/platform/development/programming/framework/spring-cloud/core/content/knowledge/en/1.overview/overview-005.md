# Role of Spring Cloud Commons for Shared Components

## 1. Why Does a Distributed System Need a Shared Abstraction Layer?

In a standalone Spring Boot application, one component can call another using a Java object or a known URL. When a system is split into multiple services, each instance's address changes due to deployments, autoscaling, restarts, or infrastructure failures. Services may also use different registration and discovery solutions.

If business code calls APIs of Eureka, Consul, or a specific load balancer directly, switching infrastructure forces changes across many application layers. **Spring Cloud Commons** provides *shared programming contracts* so that most application code works with concepts like `service ID`, `ServiceInstance`, service discovery, service registration, and load balancing rather than coupling immediately to a single provider.

In the **SPRING_CLOUD_CORE** module, Commons is the foundation for service coordination capabilities. It works alongside Spring Cloud Context, Spring Boot's externalized configuration mechanism, and the Spring Cloud ecosystem; each part has its own responsibility.

> Core idea: **Commons standardizes how components coordinate; concrete libraries and infrastructure handle the implementation.** A shared interface does not create a registry, network connection, or fault tolerance by itself.

## 2. Where Does Commons Fit in the Spring Cloud Architecture?

| Component | Primary responsibility | Examples |
| --- | --- | --- |
| **Spring Boot** | Application startup, auto-configuration, externalized configuration, Actuator | `application.yml`, `@ConfigurationProperties`, health endpoints |
| **Spring Cloud Commons** | Common contracts for discovery, service instances, service registration, load balancing, and integration points | `DiscoveryClient`, `ServiceInstance`, `ServiceRegistry`, `@LoadBalanced` |
| **Spring Cloud Context** | `ApplicationContext` lifecycle integration, configuration sources, and scoped bean refreshing | `@RefreshScope`, refresh handling |
| **Concrete implementations** | Connecting to registries, selecting instances, HTTP communication, centralized configuration management | Eureka/Consul/Kubernetes integrations, Spring Cloud LoadBalancer, Spring Cloud Config, `WebClient` |

Dependency relationships can be visualized as:

~~~mermaid
flowchart TB
    A["Business code: order-service"] --> B["Common APIs of Spring Cloud Commons"]
    B --> C["DiscoveryClient / ServiceInstance"]
    B --> D["LoadBalancerClient / @LoadBalanced"]
    B --> E["ServiceRegistry / Registration"]
    C --> F["Adapter: Eureka, Consul, Kubernetes, or static list"]
    D --> G["Spring Cloud LoadBalancer"]
    E --> F
    H["Spring Cloud Context: refresh and configuration lifecycle"] -. "Complements" .-> A
    I["Spring Boot: externalized config and auto-configuration"] -. "Foundation" .-> A
~~~

The diagram highlights boundaries of responsibility. An application can use Commons' `DiscoveryClient` interface, while querying the registry and updating instance lists depend on the installed adapter. Similarly, shared load-balancing APIs only function when a matching implementation is on the classpath.

## 3. Key Shared Contracts

### 3.1. `ServiceInstance`: representing an instance

`org.springframework.cloud.client.ServiceInstance` is the common model describing a service instance. It provides commonly used information such as:

- `getServiceId()`: logical service name, such as `catalog-service`.
- `getHost()`, `getPort()`, `isSecure()`, `getUri()`: connection details.
- `getMetadata()`: additional attributes provided by the implementation or registry.

For example, the same `serviceId` can point to two instances:

| Service ID | Instance | URI |
| --- | --- | --- |
| `catalog-service` | `catalog-1` | `http://localhost:8081` |
| `catalog-service` | `catalog-2` | `http://localhost:8082` |

Application code can iterate over `ServiceInstance` objects without knowing which registry supplied the addresses. Metadata can carry zone, version, or deployment labels, though the meaning, reliability, and freshness of metadata depend on the specific solution.

### 3.2. `DiscoveryClient`: finding instances by logical name

`org.springframework.cloud.client.discovery.DiscoveryClient` provides synchronous methods such as `getInstances(String serviceId)` and `getServices()`. The `ReactiveDiscoveryClient` variant provides access suited to reactive applications.

Example of a class that only reads endpoints currently published by discovery:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogLocator {
    private final DiscoveryClient discoveryClient;

    public CatalogLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> endpoints() {
        return discoveryClient.getInstances("catalog-service")
                .stream()
                .map(ServiceInstance::getUri)
                .toList();
    }
}
~~~

In practice, `DiscoveryClient` can be provided by libraries compatible with Eureka, Consul, Kubernetes, or `SimpleDiscoveryClient` reading a preconfigured instance list. `CompositeDiscoveryClient` can combine multiple sources when the application has multiple discovery clients.

The code above is for observing the instance list; **it does not perform load balancing yet**. If the list is empty, the caller must have a handling strategy such as an appropriate response, bounded retry, or business fallback.

### 3.3. `ServiceRegistry` and `Registration`: the service registration side

Discovery and registration are two different tasks:

- `DiscoveryClient` answers: “Which instances of this service can currently be found?”
- `ServiceRegistry<R extends Registration>` models register, deregister, and registration-status query/update operations as supported by the implementation.
- `Registration` represents the information an instance uses when registering, and extends `ServiceInstance`.

A registry adapter can provide auto-registration when the application starts and deregistration when it stops. Details regarding heartbeats, leases, readiness, and when an instance is evicted from the registry **are not uniform** across providers. Commons provides a common integration language, not a replacement for the registry server.

### 3.4. Load balancing integration: choosing an instance to call

`LoadBalancerClient` is the synchronous Commons abstraction for selecting an instance and executing against a chosen instance. In modern Spring Cloud applications, **Spring Cloud LoadBalancer** provides the implementation and integrates with appropriate HTTP clients. For reactive flows, components such as `ReactorServiceInstanceLoadBalancer` and `ServiceInstanceListSupplier` can participate in instance list supply and selection.

Typical flow:

1. Business code requests `http://catalog-service/...`; `catalog-service` is a **logical name**, not a hostname requiring DNS lookup.
2. The load balancer integration requests the `ServiceInstance` list from the appropriate source, typically backed by discovery.
3. The algorithm selects an eligible instance and sends HTTP to its actual host/port.
4. Timeouts, retries, circuit breakers, idempotency, and HTTP error handling still need to be configured in their respective layers.

Discovery and load balancing should not be treated as the same thing: discovery **knows which instances exist**, whereas load balancing **decides which instance to use**.

## 4. Example: `order-service` Calling `catalog-service`

Suppose there is an `order-service` and two `catalog-service` instances on ports `8081` and `8082`. This illustrative example uses static configuration to focus on Commons without standing up a real registry.

### Step 1. Choose dependencies

With Maven, the calling application needs WebClient and the load balancer:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

In a real project, manage Spring Cloud dependencies with the **Spring Cloud BOM/release train compatible with the Spring Boot version** in use. Do not pick separate versions for each Spring Cloud library individually. When replacing `SimpleDiscoveryClient` with a real registry, add the corresponding discovery starter/adapter.

### Step 2. Declare static instances for development or testing

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

`SimpleDiscoveryClient` uses the addresses in configuration. This is helpful in local/test environments; **it does not automatically update as instances scale up or down** like a dynamic registry. Both addresses must actually have target applications running for HTTP calls in this example to succeed.

### Step 3. Create a load-balanced `WebClient.Builder`

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ClientConfiguration {
    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

The `@LoadBalanced` annotation marks the builder so Spring Cloud attaches service ID resolution and instance selection. `WebClient` performs HTTP; Commons together with Spring Cloud LoadBalancer provides the integration points for finding and selecting addresses. Do not put `@LoadBalanced` on every HTTP client if some calls must go to fixed external URLs.

### Step 4. Call by service ID without coupling instance addresses into business logic

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {
    private final WebClient client;

    public CatalogGateway(@LoadBalanced WebClient.Builder builder) {
        this.client = builder.build();
    }

    public Mono<String> getProduct(String productId) {
        return client.get()
                .uri("http://catalog-service/api/products/{id}", productId)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Assuming both instances serve `GET /api/products/{id}`, Spring Cloud LoadBalancer can distribute calls between them according to the configured strategy. **Do not claim every call will alternate strictly**: actual distribution depends on the algorithm, instance filters, caching, retries, and system state.

A sequential view:

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant L as LoadBalancer
    participant D as DiscoveryClient
    participant R as Instance source
    participant C as catalog-service
    O->>L: GET http://catalog-service/api/products/42
    L->>D: Find instances of catalog-service
    D->>R: Read current list
    R-->>D: catalog-1, catalog-2
    D-->>L: List<ServiceInstance>
    L->>C: GET /api/products/42 to selected instance
    C-->>O: HTTP response (via client)
~~~

In the static configuration example, “Instance source” is the `spring.cloud.discovery.client.simple.instances` configuration. When moving to a real registry, the business flow and service ID can remain unchanged; adapter configuration and operational characteristics must be reviewed.

## 5. Relationship to Context, Externalized Configuration, and Version Compatibility

Commons is often used alongside Spring Cloud Context, yet the two libraries do not play the same role:

| Need | Suitable mechanism | Limitations to understand |
| --- | --- | --- |
| Change URLs, credentials, or parameters per environment | Spring Boot externalized configuration; can be combined with a centralized config source | Changing a value at the source does not guarantee running beans have received the new value |
| Refresh scoped beans | Spring Cloud Context and `@RefreshScope` | Beans are recreated only when a refresh mechanism is actually triggered; does not refresh all application state automatically |
| Locate instances when services change | Commons `DiscoveryClient` plus an appropriate implementation | Data freshness depends on the registry, caching, polling, and network |
| Select an instance for a call | Spring Cloud LoadBalancer and integration | Does not replace timeouts, retries, circuit breakers, or authentication |
| Pair Cloud libraries with Boot | Spring Cloud release train/BOM and compatibility verification tools if available | Must consult the official compatibility matrix for each version pair |

For example, changing static `catalog-service` addresses in configuration is a **configuration source update** problem; whether the running application sees the new list depends on that source's reload/refresh mechanism. When a new instance registers into Eureka/Consul/Kubernetes, that is a **discovery update** problem and does not necessarily require refreshing `@RefreshScope` beans.

With modern Spring Cloud, many discovery implementations auto-configure via starters; `@EnableDiscoveryClient` is often optional. Always check the requirements of the specific integration and version. Avoid carrying old Ribbon configuration or deprecated components into new projects without reviewing the version's documentation.

## 6. What Benefits Does the Shared Layer Bring?

**Reduced vendor lock-in:** business layers can request `DiscoveryClient` or make HTTP calls by service ID. Replacing Eureka with a compatible discovery implementation generally reduces application code changes, though dependencies, configuration, health checks, and operational rules may still need updates.

**Unified models and integrations:** `ServiceInstance` provides a common model for instance lists. Components like load balancers and health integrations can share the same service ID/instance concept, helping the Spring ecosystem work together more cohesively.

**Easier testing:** an interface like `DiscoveryClient` can be mocked to test logic at the unit level. Static discovery configuration enables integration tests without standing up full registry infrastructure.

**Operational flexibility:** a system can run multiple instances behind a single service name. However, actual behavior depends on the adapter, unhealthy-instance eviction, network call limits, and client configuration.

## 7. Testing Commons Abstractions

The `CatalogLocator` class above can be unit-tested independently using `Mockito` and `JUnit 5`, without connecting to a registry:

~~~java
import java.net.URI;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CatalogLocatorTest {
    @Test
    void readsEndpointsFromDiscoveryClient() {
        DiscoveryClient discovery = mock(DiscoveryClient.class);
        when(discovery.getInstances("catalog-service")).thenReturn(List.of(
            new DefaultServiceInstance(
                "catalog-1", "catalog-service", "localhost", 8081, false
            )
        ));

        CatalogLocator locator = new CatalogLocator(discovery);

        assertThat(locator.endpoints())
                .containsExactly(URI.create("http://localhost:8081"));
    }
}
~~~

This example assumes the project has Spring Boot test dependencies or equivalent providing JUnit, Mockito, and AssertJ.

At the integration level, cover the following scenarios:

| Scenario | What to verify |
| --- | --- |
| Two healthy instances available | Calls by service ID reach a selected instance and receive responses |
| Discovery returns an empty list | Client fails in a controlled manner rather than hanging indefinitely |
| One instance stops serving | Timeout, retry, and instance eviction policies behave as configured |
| Registry temporarily unreachable | Caching, fallback, and recovery behavior are understood; do not assume data is always up-to-the-second |
| Runtime configuration changes | Identify exactly which components refresh/rebind and whether a restart is required |
| Spring Boot/Spring Cloud upgrade | Boot the application and verify dependencies, auto-configuration, discovery, and load balancing |

In production, monitor logs, error/latency metrics for service calls, registry status, and health. Timeouts, retry budgets, and circuit breaker policies must be defined at the appropriate layers; Commons does not choose these parameters for every application automatically.

## 8. Common Misconceptions

1. **“Adding Spring Cloud Commons gives you service discovery right away.”** Commons provides the API; an appropriate implementation or statically configured instance list is still required.
2. **“`DiscoveryClient` will distribute requests evenly.”** Discovery only returns a list. Load balancing is a separate step requiring integration and an instance selection algorithm.
3. **“`ServiceRegistry` is the registry server itself.”** It is an application-side contract; the server, protocol, and lease rules depend on the provider.
4. **“`@RefreshScope` makes every configuration change take effect immediately.”** Refresh requires a trigger/signal and does not arbitrarily cover every object or open connection.
5. **“Having the same service ID means instances are guaranteed compatible.”** API contracts, versions, data, and rolling-deployment compatibility must be managed independently.
6. **“Using shared interfaces means versions don't matter.”** Boot and Cloud must form a compatible version set; APIs, starters, and auto-configuration can change across release trains.

## 9. When to Use Which Abstraction?

| What you need... | Starting point |
| --- | --- |
| Display or inspect instances of a service | `DiscoveryClient` or `ReactiveDiscoveryClient` |
| Represent an instance's info vendor-independently | `ServiceInstance` |
| Integrate provider-specific registration/deregistration | `ServiceRegistry` and `Registration` |
| Call an API via `http://service-id/...` | `@LoadBalanced`-integrated HTTP client plus Spring Cloud LoadBalancer |
| Per-environment configuration | Spring Boot externalized configuration |
| Refresh beans upon a refresh signal | Spring Cloud Context, `@RefreshScope` when appropriate |

**Key takeaway:** Spring Cloud Commons is the shared contract layer between business code and Spring Cloud's infrastructure components. It allows discovery, registration, and load balancing to integrate through more stable contracts; actual runtime behavior still comes from the implementation, configuration, and operations of each distributed system.
