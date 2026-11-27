# OpenFeign Dependencies, LoadBalancer, and Integration Conditions

**Spring Cloud OpenFeign** helps Java applications call HTTP APIs using an interface declared with `@FeignClient`, instead of manually building each request in business code. However, **having Feign does not automatically guarantee client-side load balancing**. For Feign to use **Spring Cloud LoadBalancer** to select a replica (`ServiceInstance`) by service ID, the application needs the right dependencies, proper auto-configuration beans, an instance list source, and a client declaration without a fixed URL.

For example, `order-service` needs to call `catalog-service`, which has two replicas. The following declaration expresses the intent to call by service name:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeignClient {
    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}
~~~

If LoadBalancer integration is active, `catalog-service` acts as the **service ID**, and the physical target selected on each call may be `10.0.1.11:8081` or `10.0.1.12:8081`. If `url` is also declared, Feign calls the provided URL **without going through service-ID-based load balancing**.

This lesson in the **OpenFeign** chapter clarifies four questions: which dependencies are required, what conditions enable integration, how to distinguish Feign's HTTP transport from the instance selector, and how to verify whether the application actually calls through LoadBalancer.

## 1. Three Dependency Layers Not to Confuse

An HTTP call via Feign can pass through three distinct layers:

| Layer | Representative Components | Responsibility |
|---|---|---|
| **Declarative HTTP client** | `spring-cloud-starter-openfeign`, `@FeignClient`, Feign encoder/decoder/contract | Generates proxy from interface, translates method invocation into HTTP request, and decodes response |
| **Replica selection** | `spring-cloud-starter-loadbalancer`, `FeignBlockingLoadBalancerClient`, `ServiceInstanceListSupplier` | Looks up service ID, retrieves instance list, and picks a concrete endpoint |
| **Replica list provider** | Eureka/Consul/Zookeeper discovery client, `SimpleDiscoveryClient`, or custom supplier | Reports which `ServiceInstance`s are available for a service ID |

The three layers work together, yet they **do not replace one another**.

- Feign knows how to construct an HTTP request from an interface, but it does not create a registry on its own.
- LoadBalancer selects an endpoint from a list, but it does not register or run servers on its own.
- Discovery provides the list, but it does not automatically ensure Feign will use that list if Feign is not integrated with LoadBalancer.
- The HTTP transport beneath Feign remains responsible for TCP/TLS connections, connection pooling, timeouts, and data transmission.

~~~mermaid
flowchart TD
    A["Business code calls CatalogFeignClient"]
    B["Feign proxy / SpringMvcContract"]
    C["FeignBlockingLoadBalancerClient"]
    D["ServiceInstanceListSupplier"]
    E["Discovery client or static source"]
    F["LoadBalancer selects ServiceInstance"]
    G["Feign Client executes HTTP"]
    H["catalog instance at host:port"]
    A --> B --> C
    C --> D --> E
    E --> D --> F
    F --> C --> G --> H
~~~

The diagram illustrates the case where **LoadBalancer integration conditions are met**. If Feign is configured to call a physical URL directly, the `ServiceInstance` selection step by service ID does not participate.

## 2. Required and Optional Dependencies

### 2.1. OpenFeign Starter

To let Spring Boot create Feign clients, you first need the dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
}
~~~

This starter provides configuration for `@FeignClient`, Feign proxies, the Spring MVC contract, encoders/decoders, and appropriate Spring Cloud integrations.

### 2.2. LoadBalancer Starter — Must Be Added Explicitly When Instance Selection Is Needed

**`spring-cloud-starter-loadbalancer` is an optional dependency of Spring Cloud OpenFeign**; do not assume it is always present just because the OpenFeign starter was added.

When client-side load balancing by service ID is needed, explicitly declare both:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

If building HTTP controllers or REST endpoints in the same application, you may also need `spring-boot-starter-web`, though that is not a substitute for LoadBalancer.

**Do not pin different versions on individual Spring Cloud starters.** Use the Spring Cloud BOM (`spring-cloud-dependencies`) with a release train compatible with your project's Spring Boot version. The examples in this lesson show only the required dependencies; importing the BOM/version-management plugin is done in the project's build configuration.

In Maven, the two corresponding dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-openfeign</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

The XML snippet assumes the parent/BOM already manages versions; this is not a complete `pom.xml`.

### 2.3. Discovery Source: An External Registry Is Not Always Required

LoadBalancer needs an instance list for the service ID. Depending on the environment, you can use:

| Source | Dependency / Configuration | Best Suited For |
|---|---|---|
| Eureka | Compatible Eureka discovery client starter | Microservices systems with dynamic registration and deregistration |
| Consul | Compatible Spring Cloud Consul Discovery starter | Systems using Consul service discovery |
| `SimpleDiscoveryClient` | Declare instance list in `application.yml` | Demos, local tests, and environments with static endpoints |
| Custom supplier | Custom `ServiceInstanceListSupplier` bean per LoadBalancer configuration | When custom selection policies or data sources are needed |

**Adding Feign + LoadBalancer does not mean you must add Eureka.** In practice exercises you can use `SimpleDiscoveryClient`. Conversely, if no suitable instance source is configured, LoadBalancer may fail to find any replica to call.

## 3. Conditions for Feign to Actually Call Through LoadBalancer

In a standard Spring Cloud OpenFeign setup, all of the following must be satisfied simultaneously:

1. The application includes `spring-cloud-starter-openfeign` and Feign clients are registered by Spring.
2. Spring Cloud LoadBalancer is on the classpath and its auto-configuration is applied.
3. The Feign client uses **`name`/service ID**, and **does not declare a fixed URL** in the annotation or in client configuration properties.
4. A supplier/discovery mechanism returns at least one `ServiceInstance` for that service ID.
5. Custom configurations do not inadvertently replace the load-balanced `Client` with a direct Feign `Client`.

When Spring Cloud LoadBalancer is present, Spring Cloud OpenFeign's default configuration chooses `FeignBlockingLoadBalancerClient` to wrap the underlying HTTP transport. If LoadBalancer is absent from the classpath, Feign uses the default or configured HTTP client and skips Spring Cloud LoadBalancer's instance selection step.

This condition is **distinct** from having an HTTP library such as Apache HttpClient 5 or OkHttp installed: those libraries execute connections, not replica selection algorithms.

### Decision Table

| OpenFeign Starter | LoadBalancer Starter | Feign Has Fixed `url`? | Instance Source | Typical Outcome |
|---|---|---|---|---|
| Yes | Yes | No | Has instances | Feign selects via LoadBalancer, then sends HTTP |
| Yes | Yes | No | Empty list | No instance to select; error at client/integration |
| Yes | No | No | Has registry | Feign does not use Spring Cloud LoadBalancer; target name may be treated as a normal hostname |
| Yes | Yes | Yes | Yes or No | Calls the configured URL, **bypassing name-based load balancing** |
| Yes | Yes | No | No suitable source | Service ID lookup provides no endpoint to call |
| No | Yes | N/A | Yes | No corresponding OpenFeign configuration to create `@FeignClient` proxies |

This is the behavior under default configuration. Customized `Client` beans, Feign factories, targeters, transports, or auto-configurations can alter the path; inspect the actual beans when an application has multiple integrations.

## 4. Enabling Feign Client Scanning Properly

In a Spring Boot application, use `@EnableFeignClients` to register Feign interfaces. For multi-module projects, specifying explicit clients is often clearer than relying on default package scanning:

~~~java
package com.example.orders;

import com.example.orders.client.CatalogFeignClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(clients = CatalogFeignClient.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Interface in package `com.example.orders.client`:

~~~java
package com.example.orders.client;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
public interface CatalogFeignClient {

    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}
~~~

DTO:

~~~java
package com.example.orders.client;

public record ProductDto(Long id, String name) {}
~~~

Usage in a service:

~~~java
package com.example.orders;

import com.example.orders.client.CatalogFeignClient;
import com.example.orders.client.ProductDto;
import org.springframework.stereotype.Service;

@Service
class ProductLookupService {

    private final CatalogFeignClient catalog;

    ProductLookupService(CatalogFeignClient catalog) {
        this.catalog = catalog;
    }

    ProductDto load(long id) {
        return catalog.findById(id);
    }
}
~~~

In this example, business code contains no host, port, or hand-crafted `RestClient`. The Feign proxy handles the HTTP contract; if conditions are met, LoadBalancer selects the destination for `catalog-service`.

You can use `@EnableFeignClients(basePackages = "com.example.orders.client")` instead of `clients`. In multi-module projects, explicitly declaring packages or interfaces prevents cases where component scanning misses the Feign client and causes a missing-bean error.

## 5. Providing Instances for a Service ID

To test without Eureka, declare a static list using `SimpleDiscoveryClient`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: zone-a
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: zone-b
~~~

The configuration above places **two instances** under the `catalog-service` service ID key. This name must match `@FeignClient(name = "catalog-service")`. Each instance provides a physical URI for LoadBalancer.

Notes:

- `127.0.0.1` is only suitable when client and server share the same network namespace or localhost; in Docker/Kubernetes you need addresses reachable between workloads.
- `SimpleDiscoveryClient` is a **static** source. Stopping the server on port `8081` does not automatically remove that URI from configuration. To observe dynamically changing lists, use dynamic discovery or a supplier that updates the list.
- Zone metadata does not automatically enable zone preference. You must configure the corresponding supplier/policy if you want zone affinity.
- Do not add `spring.cloud.openfeign.client.config.catalog-service.url` in the same example if your goal is to test LoadBalancer.

If both backends expose `GET /products/{id}` and return JSON compatible with `ProductDto`, calling `catalog.findById(42L)` can be distributed to either instance when LoadBalancer uses round-robin and the candidate list is valid.

## 6. How Does FeignBlockingLoadBalancerClient Participate in the Call Flow?

Spring Cloud OpenFeign coordinates components in the following conceptual order:

~~~mermaid
sequenceDiagram
    participant App as ProductLookupService
    participant Proxy as CatalogFeignClient proxy
    participant FeignLB as FeignBlockingLoadBalancerClient
    participant LB as BlockingLoadBalancerClient
    participant Supplier as ServiceInstanceListSupplier
    participant HTTP as Feign HTTP Client
    participant Target as catalog-service instance
    App->>Proxy: findById(42)
    Proxy->>FeignLB: Feign Request to service ID
    FeignLB->>LB: choose("catalog-service")
    LB->>Supplier: get candidate list
    Supplier-->>LB: catalog-1, catalog-2
    LB-->>FeignLB: catalog-2: 127.0.0.1:8082
    FeignLB->>HTTP: Request to physical URI
    HTTP->>Target: GET /products/42
    Target-->>HTTP: HTTP response
    HTTP-->>App: ProductDto or error
~~~

Distinguish three outputs:

- **Discovery result:** list of `ServiceInstance`s for the service ID.
- **Selection result:** a single chosen `ServiceInstance`.
- **HTTP result:** status, headers, body, or exception from the transport.

Even when instance selection succeeds, the HTTP connection can still fail if the server stops or the host/port is unreachable. A Feign proxy does not turn a dead endpoint into a healthy one.

With load-balanced Feign, `FeignBlockingLoadBalancerClient` works alongside a delegate `feign.Client` to send the request after the selection step. The delegate may be the default transport, Apache HttpClient 5, or another configured option. Therefore, **do not confuse `FeignBlockingLoadBalancerClient` with a connection pool**: the former selects the instance/dispatches, while the latter transports the request.

## 7. Simply Adding url Can Bypass LoadBalancer

This is a frequent source of confusion when configuring Feign.

### 7.1. URL Directly Inside @FeignClient

~~~java
@FeignClient(
        name = "catalog-service",
        url = "http://127.0.0.1:8081"
)
interface DirectCatalogClient {

    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}
~~~

This client calls a fixed URL and **does not use LoadBalancer to select `catalog-service` from discovery**, even though `spring-cloud-starter-loadbalancer` is still on the classpath.

### 7.2. URL Inside Client Properties

If the interface does not declare `url`:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeignClient {
    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}
~~~

But `application.yml` contains:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            url: http://127.0.0.1:8081
~~~

Then `catalog-service` is also bound to a **fixed target** and does not run load balancing by service ID.

### 7.3. Both Annotation and Properties Specify a URL

According to Spring Cloud OpenFeign documentation, if `url` is provided in `@FeignClient`, the annotation's URL takes precedence when creating the client; the corresponding URL in properties is not used to override this case.

| URL in Annotation | URL in Properties | Target Selection Behavior |
|---|---|---|
| No | No | `@FeignClient` name is used as service ID for LoadBalancer (if integration is available) |
| Yes | No | Calls URL from annotation |
| No | Yes | Calls URL from properties |
| Yes | Yes | Calls URL from annotation; property URL does not determine target |

**`name` still must be declared**, even when `url` is present. Do not treat `@FeignClient(name = "catalog-service", url = "...")` as a way to "prefer this instance and fail over via LoadBalancer"; typically it only calls the specified target.

## 8. Add-Ons That Are Not Prerequisites for LoadBalancer

Many tools commonly appear alongside Feign, but serve different roles:

| Component | Required for Feign to Select `ServiceInstance`? | Role |
|---|---|---|
| `spring-cloud-starter-openfeign` | Required for Feign proxy | Declares and creates HTTP client |
| `spring-cloud-starter-loadbalancer` | Required for Spring Cloud LB integration by service ID | Selects instance |
| Eureka/Consul or `SimpleDiscoveryClient` | Required as an equivalent instance source | Provides endpoints |
| Apache HttpClient 5 | No | Connection pooling and HTTP execution |
| `feign-micrometer` + `ObservationRegistry` | No | HTTP client metrics/tracing when integration is enabled |
| Spring Cloud CircuitBreaker starter | No | Separate circuit breaker/fallback |
| Custom Retryer | No | Tunes retries according to policy |
| OAuth2 client | No | Supplies access tokens for configured calls |

### 8.1. Apache HttpClient 5 Transport

When Apache HttpClient 5 is on the classpath and Spring Cloud OpenFeign is configured to use it, Feign can reuse connections through a connection pool. To disable this HTTP client mechanism in OpenFeign configuration, you can set:

~~~yaml
spring:
  cloud:
    openfeign:
      httpclient:
        hc5:
          enabled: false
~~~

This is an **HTTP transport** setting; it does not mean LoadBalancer is disabled. Likewise, pool limits, socket timeouts, and per-route connections are not settings of the round-robin algorithm.

Since Spring Cloud OpenFeign 4, Apache HttpClient 4 is no longer a supported option in this integration; you must use a compatible transport such as HttpClient 5.

### 8.2. Circuit Breaker Is a Separate Mechanism

To enable Spring Cloud CircuitBreaker wrapping for Feign, you need the appropriate circuit breaker dependency and property:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Adding `spring-cloud-starter-loadbalancer` alone does not automatically enable a circuit breaker. A circuit breaker decides whether to continue executing calls after repeated failures; LoadBalancer decides which instance is chosen when a call is executed.

### 8.3. Retries and Timeouts Also Have Separate Configurations

Spring Cloud OpenFeign provides `Retryer.NEVER_RETRY` by default to disable Feign-level retries, unlike core Feign's default behavior. LoadBalancer retries or another resilience layer, if configured and applied, are separate concerns: do not assume every request is retried simply because LoadBalancer is present.

An illustrative timeout configuration for a Feign client:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            connectTimeout: 2000
            readTimeout: 5000
            loggerLevel: basic
~~~

`connectTimeout` and `readTimeout` here use milliseconds according to OpenFeign configuration. They belong to Feign's HTTP execution, not discovery client timeouts or instance cache TTLs. Example values should be tested in the real system, especially when multi-layer retries exist.

## 9. Named Client Configuration and Risk of Bean Overlap

Spring Cloud OpenFeign creates a **per-named-client configuration context** (via `FeignClientsConfiguration`), containing components such as:

- `Decoder` and `Encoder` to convert response/request bodies.
- `SpringMvcContract` to interpret annotations like `@GetMapping`, `@PostMapping`.
- `Feign.Builder` to create the proxy.
- `feign.Client` to execute requests; can be wrapped by `FeignBlockingLoadBalancerClient` when conditions are met.

This lets each service ID have its own timeouts, encoder/decoder, and customizations. However, if a developer defines an unsuitable custom `feign.Client` bean or misconfigures scope, it can alter the default load-balanced path.

### Using contextId When Multiple Clients Target the Same Service

When two Feign interfaces both point to `catalog-service` with different policies, use `contextId` to avoid configuration bean name conflicts:

~~~java
@FeignClient(
        contextId = "catalogReadClient",
        name = "catalog-service",
        configuration = CatalogReadFeignConfiguration.class
)
interface CatalogReadClient {
    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}

@FeignClient(
        contextId = "catalogAdminClient",
        name = "catalog-service",
        configuration = CatalogAdminFeignConfiguration.class
)
interface CatalogAdminClient {
    @GetMapping("/admin/health")
    String health();
}
~~~

Both interfaces still use the same **service ID `catalog-service`** for discovery, while having isolated Feign configuration contexts. The two configuration classes in the example are application classes you must define yourself if using this snippet.

If a custom configuration class is placed within `@ComponentScan` of the main application context, custom encoder/decoder/interceptor beans can accidentally become shared configuration across multiple Feign clients. Place them outside the main scan area or explicitly restrict their scope.

### Scope of the Feign HTTP Client

Current OpenFeign documentation emphasizes that a custom `feign.Client` bean should have **singleton** scope. Creating a new HTTP `Client` every time a Feign client initializes can create unnecessary connection pools, leading to socket exhaustion or resource leaks.

This **does not mean there can only be one Feign interface in the entire application**. Multiple Feign proxies can share or use transports/pools whose lifecycles are managed appropriately.

## 10. Common Integration Mistakes

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Cannot inject `CatalogFeignClient` | Missing `@EnableFeignClients` or scanning the wrong package/interface | Check annotations, `clients`/`basePackages`, and the module containing the interface |
| Feign resolves hostname `catalog-service` via DNS instead of discovery | Missing LoadBalancer on classpath, or using a `Client` without LB integration | Check dependency tree and the `feign.Client` bean type in use |
| Feign always calls a single IP despite multiple instances | `url` in annotation/properties, or supplier returns only one instance | Check URL precedence, discovery list, and policy |
| Client reports no instance for service ID | Wrong service ID, empty registry, or supplier filters everything out | Compare `@FeignClient(name)` with `DiscoveryClient`'s list |
| Instances exist but connection fails | Instance host/port unreachable or server not ready | Check networking from where the client runs, health, and cache |
| Enabled OkHttp/HC5 yet traffic still isn't balanced | Replaced HTTP transport without fixing instance selection | Check `FeignBlockingLoadBalancerClient` and supplier |
| Two clients with the same `name` suffer configuration conflicts | Duplicate configuration context/bean names | Use unique `contextId` when multiple configurations are needed |
| Circuit breaker/fallback does not work | Missing dependency or corresponding property not enabled | Check Spring Cloud CircuitBreaker configuration |
| Retries do not happen | Default `Retryer.NEVER_RETRY` or policy disallows retry | Inspect retry settings across Feign, LoadBalancer, and application layers |
| HTTP 503 | Possibly no instances available, or backend/proxy returned 503 | Inspect exceptions, instance selection logs, and upstream response |

**Do not diagnose solely from the HTTP status.** If no instance is available to select, the failure happens before any HTTP call is sent to a backend. If an instance was selected and the backend returns HTTP 500, the error occurs after selection; LoadBalancer cannot fix business errors by itself.

## 11. Testing Whether It Actually Load Balances

A correct configuration on paper is not enough. A short hands-on test clearly distinguishes the Feign proxy, discovery, and LoadBalancer.

### Setup

1. Start two `catalog-service` replicas on ports `8081` and `8082`; both serve `GET /whoami` returning their instance ID.
2. Declare both URIs in `SimpleDiscoveryClient` as in Section 5.
3. Add both the OpenFeign and LoadBalancer starters to the calling application.
4. Register a Feign interface **with only `name = "catalog-service"`**, and no `url` in the annotation or properties.
5. Call `/whoami` multiple times and record the returned instance ID, along with bean/transport names if needed.

An interface for the test:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogProbeClient {
    @GetMapping("/whoami")
    String whoAmI();
}
~~~

With round-robin and two candidates, results typically alternate between the two instances. Do not assume the order of the first two calls is always fixed, as it depends on selector state, concurrency, and filters.

### Experiments to Isolate Conditions

| Experiment | Change | What to Observe |
|---|---|---|
| A — With LoadBalancer | Keep both starters, no URL set | Client selects across instances provided by discovery |
| B — Fixed URL | Add `url = "http://127.0.0.1:8081"` to the Feign client | Only calls port 8081, does not select 8082 via LoadBalancer |
| C — Without LB starter | Remove LoadBalancer dependency for a separate run | Feign does not select instances via Spring Cloud LB; service name may be treated as a DNS hostname |
| D — Wrong service ID | Change `name` to `catalog-unknown` | Fails to retrieve the right instance list; observe target-selection error |
| E — Dead instance still in static config | Stop server 8081 without updating the list | LoadBalancer may still select the unreachable URI; connection error |
| F — Wrong Feign scan | Remove `@EnableFeignClients` or exclude interface from scan scope | Feign proxy is not registered as a bean |

Do not run experiments that break dependencies or stop services in production. With `SimpleDiscoveryClient`, editing YAML usually requires a restart or an appropriate refresh mechanism; a static list does not automatically deregister when a backend shuts down.

## 12. Checklist Before Concluding Feign Is Integrated with LoadBalancer

1. **Build:** Do you have `spring-cloud-starter-openfeign` **and** `spring-cloud-starter-loadbalancer`, plus a Spring Cloud BOM compatible with Spring Boot?
2. **Registration:** Is `@EnableFeignClients` present and scanning the right interfaces?
3. **Naming:** Does `@FeignClient(name = "...")` match the service ID in the registry or `SimpleDiscoveryClient`?
4. **URL:** Did you accidentally set `url` in the annotation or `spring.cloud.openfeign.client.config.<client>.url`, causing Feign to skip LoadBalancer?
5. **Instances:** Does the supplier return at least one instance, and are its host/port reachable?
6. **Client bean:** Does `FeignBlockingLoadBalancerClient` participate in the default execution path, or did a custom `feign.Client` replace it?
7. **Transport:** If using Apache HC5/OkHttp, are timeouts and pools configured properly without confusing them with the target-selection algorithm?
8. **Recovery:** Are retries, circuit breakers, and health checks enabled/configured as required, rather than assumed to exist?
9. **Observability:** Can you correlate the service ID, selected instance, HTTP status/exception, and request duration?
10. **Validation:** Have you tested with at least two instances and distinguished a load-balanced call from a fixed-URL call?

**Conclusion:** OpenFeign provides a declarative HTTP client model; Spring Cloud LoadBalancer provides **`ServiceInstance` selection by service ID** when properly included and integrated; discovery provides the **list of replicas**. With `@FeignClient(name = "catalog-service")`, no fixed URL, and all of these pieces in place, requests flow through `FeignBlockingLoadBalancerClient` before the HTTP transport connects to the selected instance. Missing the LoadBalancer starter, missing an instance list, or accidentally setting a fixed URL produces completely different behavior even though the Feign interface looks nearly identical.

**Official References:**

- [Spring Cloud OpenFeign – Features, Dependencies, and LoadBalancer](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Spring Cloud OpenFeign – Configuration Properties](https://docs.spring.io/spring-cloud-openfeign/reference/configprops.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
