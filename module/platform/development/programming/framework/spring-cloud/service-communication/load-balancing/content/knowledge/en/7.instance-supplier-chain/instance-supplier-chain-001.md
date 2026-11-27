# Designing ServiceInstanceListSupplier with Builders and Decorators

When a client calls `http://inventory-service`, Spring Cloud LoadBalancer needs a list of `ServiceInstance` objects before selecting a target address. This list is provided by `ServiceInstanceListSupplier`. The supplier design determines where the data comes from and which replicas can become candidates after applying caching, health checks, zones, or routing policies.

This lesson belongs to the **Instance Supplier Chain** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. The goal of the module is to understand client-side load balancing mechanisms: selecting a `ServiceInstance` by service ID, discovery, health checks, and routing policies; and practicing resilient communication with `RestClient`, `WebClient`, OpenFeign, retry/timeout, and error observability. Here, we focus on two tools for designing the candidate supplier chain: the Spring Cloud LoadBalancer **builder** and **decorators** for adding or customizing behavior.

After this lesson, you will be able to build a supplier chain per service ID, understand the order of each layer, write a decorator that filters instances by metadata, inspect the list before and after filtering, and avoid common pitfalls when combining caching with request-dependent policies.

## 1. Responsibility Boundaries: Supplier Provides, LoadBalancer Selects

A typical call flow:

~~~mermaid
flowchart LR
    C["RestClient / WebClient / OpenFeign"] --> L["LoadBalancer for inventory-service"]
    L --> S["ServiceInstanceListSupplier"]
    S --> D["DiscoveryClient or static source"]
    D --> S
    S --> F["Filtered candidate list"]
    F --> L
    L --> I["Select one ServiceInstance"]
    I --> H["HTTP to host:port"]
~~~

For the same service ID, discovery might return three replicas:

~~~text
inventory-service
  ├─ inv-a | localhost:8081 | trafficTier=stable
  ├─ inv-b | localhost:8082 | trafficTier=canary
  └─ inv-c | localhost:8083 | trafficTier=stable
~~~

If the caller's policy only allows `trafficTier=stable`, the supplier should provide `inv-a` and `inv-c`. `RoundRobinLoadBalancer` then selects one of the two. **The instance selection algorithm is not responsible for performing traffic tier filtering itself**; the input list must reflect the agreed-upon policy.

`ServiceInstanceListSupplier` operates at the candidate list layer. It does not send HTTP requests, execute target service business logic, replace service discovery, or guarantee that a request will succeed. Timeouts, retries, and error handling belong to other coordinating layers.

## 2. API and Structure of a Supplier Chain

The interface provides methods to get the service ID, get the instance list, and a variant with a request context:

~~~java
String getServiceId();
Flux<List<ServiceInstance>> get();
Flux<List<ServiceInstance>> get(Request request);
~~~

In current Spring Cloud LoadBalancer APIs, `Request` is an abstraction carrying selection context; the `Flux<List<ServiceInstance>>` type allows returning the list in a reactive stream. If an implementation only needs a regular list, `get()` is sufficient; if a policy depends on a specific request, you must pay attention to `get(Request request)`.

A supplier chain typically consists of two groups of components:

| Group | Responsibility | Examples |
|---|---|---|
| **Source** | Creates the initial list from a registry or configuration | Discovery client, static source |
| **Decorator** | Receives the list from a delegate and caches, filters, or prioritizes it | Caching, health check, zone preference, hint, custom decorator |

A chain might look like this:

~~~mermaid
flowchart TD
    A["DiscoveryClient supplier"] --> B["Caching supplier"]
    B --> C["Health-check supplier"]
    C --> D["Traffic-tier decorator"]
    D --> E["List sent to LoadBalancer"]
~~~

This diagram illustrates the order in which **data is processed**. In code, each decorator holds a reference to an inner supplier. When LoadBalancer calls the outermost decorator, the call propagates inward first, and then the returned list flows through each processing step in reverse order. Therefore, the order when constructing the chain must be checked carefully.

## 3. Designing with ServiceInstanceListSupplier.builder()

Spring Cloud LoadBalancer provides a builder to compose a source and decorators without manually instantiating every class. For example, if a caller wants to fetch the list from discovery, cache the source list, and prefer instances in the same zone:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .withZonePreference()
            .build(context);
    }
}
~~~

Meaning of each step:

1. `withDiscoveryClient()` chooses the source that retrieves `ServiceInstance` objects provided by the discovery mechanism.
2. `withCaching()` adds caching to avoid repeatedly querying the source on every selection.
3. `withZonePreference()` applies zone preference when the caller's zone is configured and matching zone metadata exists on the instances.
4. `build(context)` builds the supplier chain attached to the application context used by LoadBalancer.

The snippet above is a **configuration template for a single service**. The actual behavior of each step still depends on the Spring Cloud version, the installed discovery client, and the available metadata. The builder does not create a registry by itself, does not assign zones to instances automatically, and does not make an instance healthy on its own.

If the problem only requires discovery and caching, keep the chain minimal:

~~~java
return ServiceInstanceListSupplier.builder()
    .withDiscoveryClient()
    .withCaching()
    .build(context);
~~~

When client-side health checks are needed, you can use the corresponding chain:

~~~java
return ServiceInstanceListSupplier.builder()
    .withDiscoveryClient()
    .withHealthChecks()
    .build(context);
~~~

A health-check supplier requires a reachable health endpoint, the corresponding HTTP client mechanism, and appropriate check settings. Builder method names in example documentation should be verified against the Spring Cloud version your project uses; do not blindly attach all decorators into one chain without an identified need.

## 4. Registering Per-Service ID Configuration

`@LoadBalancerClient` binds a configuration to a specific service ID. For example, in an application calling `inventory-service`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryLoadBalancerConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

Spring Cloud LoadBalancer creates an isolated context per service ID to look up beans used for instance selection. The `InventoryLoadBalancerConfiguration` class must be placed **outside the general component scan scope** of the application, or excluded from component scanning. If that class is scanned as a global configuration, a supplier bean meant exclusively for `inventory-service` could unintentionally affect other services.

Illustrative package organization:

~~~text
com.example.caller
  └─ CallerApplication.java
com.example.loadbalancer.inventory
  └─ InventoryLoadBalancerConfiguration.java
~~~

The main application in `com.example.caller` can reference the configuration by class, while the dedicated configuration package is not picked up by automatic component scanning of the application package into the parent context. If your project uses custom component scan rules, double-check their scope.

**Do not create multiple competing `ServiceInstanceListSupplier` beans in a single LoadBalancer context.** One complete chain should be built and registered for that service. When adding a custom decorator, modify the existing chain instead of creating an additional standalone bean of the same type.

## 5. Decorators: Adding Behavior Without Replacing the Discovery Source

The builder handles features already supported by Spring Cloud well. When you have an internal policy—such as sending traffic only to instances carrying `trafficTier=stable` metadata—you can write a decorator that takes another supplier as its `delegate`.

Design principles:

- A decorator does not query the registry itself; it obtains the list from its delegate.
- A decorator must not mutate the list held by a cache directly.
- The filtered result can be a new list, including an empty list if required.
- Methods accepting a request context must forward that context to the delegate.
- Fallback rules must be chosen deliberately and documented.

Example `TrafficTierSupplier` class filtering by metadata:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.Request;
import org.springframework.cloud.loadbalancer.core.DelegatingServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import reactor.core.publisher.Flux;

public final class TrafficTierSupplier
        extends DelegatingServiceInstanceListSupplier {

    private final String requiredTier;

    public TrafficTierSupplier(
            ServiceInstanceListSupplier delegate,
            String requiredTier) {
        super(delegate);
        this.requiredTier = requiredTier;
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return delegate.get().map(this::filterByTier);
    }

    @Override
    public Flux<List<ServiceInstance>> get(Request request) {
        return delegate.get(request).map(this::filterByTier);
    }

    private List<ServiceInstance> filterByTier(
            List<ServiceInstance> instances) {
        return instances.stream()
            .filter(instance -> requiredTier.equals(
                instance.getMetadata().get("trafficTier")))
            .toList();
    }
}
~~~

How it works: each time the delegate emits a list, `map(this::filterByTier)` transforms that list into the instances with matching metadata. `List.toList()` creates a new result list without modifying the source data.

Here, **there is no fallback to another tier**. If no `stable` instance exists, the supplier returns an empty list and LoadBalancer has no candidate to choose. This is intentional behavior when a tier represents a routing boundary that must be strictly enforced. If the tier is only a performance or affinity preference where fallback is allowed, write an explicit fallback policy rather than automatically dropping the filter condition in every case.

This decorator uses a fixed `requiredTier` for all requests of the service ID. If requirements vary per request, design how to read the context and pass data through `get(Request request)`; this example is not yet request-aware routing.

## 6. Combining the Builder with a Custom Decorator

You can let the builder create the discovery source and cache, and then wrap it with a decorator:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        ServiceInstanceListSupplier sourceAndCache =
            ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);

        return new TrafficTierSupplier(sourceAndCache, "stable");
    }
}
~~~

This is an **alternative configuration** replacing the builder-only bean from the previous section, not a second bean added alongside it. The resulting chain has the following processing order:

~~~text
LoadBalancer
    -> TrafficTierSupplier
        -> CachingServiceInstanceListSupplier
            -> DiscoveryClient-backed supplier
~~~

When a request arrives, the call travels from outside to inside; the returned list flows back from the discovery source through the cache and is then filtered by tier. Thus, the cache only stores the baseline list, while the tier policy result is computed after the cache.

For a filter that evaluates each request individually, this arrangement also avoids the risk of reusing a previous request's filtered result for a subsequent request. Never place a shared cache on the outermost layer if the cache key does not distinguish the request attributes that change the candidate list.

## 7. Why Does Decorator Order Matter?

Consider the following two structures.

**Option A: cache the discovery list, then filter.**

~~~text
Discovery -> Cache -> TrafficTierFilter -> LoadBalancer
~~~

The cache holds the discovery list. The filter layer decides the outcome whenever LoadBalancer needs candidates. Tier information can change policy at the outer layer without polluting the baseline list cache.

**Option B: filter first, then cache the filtered result.**

~~~text
Discovery -> TrafficTierFilter -> Cache -> LoadBalancer
~~~

If the filter relies on request context and the cache does not differentiate those contexts, the list from the first request can be wrongly reused for another request. For example, request A asks for `stable` and request B asks for `canary`, yet B receives the list already filtered for A.

Guideline table:

| Concern | How to handle |
|---|---|
| Caching discovery data | Prefer placing the cache near the discovery source, before request-dependent filters. |
| Health checks | Place near the list source and ensure the health endpoint is correct; consider its interaction with caching. |
| Zone preference | Apply after obtaining the list and valid zone metadata. |
| Per-request filtering | Preserve request context throughout the chain; avoid caching results without an appropriate cache key. |
| Filter producing an empty list | Explicitly choose fail-closed or fallback based on business semantics. |
| Multiple decorators | Document the order and verify the list at each step. |

In Spring Cloud LoadBalancer, documentation generally recommends placing caching or health-checking suppliers close to the network-based instance source, before other filtering suppliers. When combining both caching and health checks, verify refresh behavior, TTL, and the library version in use to avoid stale lists or duplicate health checks.

## 8. Preparing a Test Source with Metadata

To test a decorator without needing a real registry yet, you can use `SimpleDiscoveryClient` with a static list of instances in the caller application:

~~~yaml
spring:
  application:
    name: caller-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
                metadata:
                  trafficTier: stable
              - uri: http://localhost:8082
                metadata:
                  trafficTier: canary
              - uri: http://localhost:8083
                metadata:
                  trafficTier: stable
~~~

In this setup, three `inventory-service` processes must actually be running on their respective ports. `SimpleDiscoveryClient` only supplies the declared list; it does not prove that the processes are alive and does not replace health checks.

When calling through a supplier that only permits `stable`, the expected candidate set is:

~~~text
localhost:8081
localhost:8083
~~~

`localhost:8082` is excluded because of `trafficTier=canary` metadata. If both `stable` instances are available, LoadBalancer can choose either one according to the configured algorithm. Actual distribution ratios depend on the algorithm, configuration, and instance state.

Do not use `trafficTier` as a security mechanism. Metadata and filters are routing tools; access control between service groups still requires proper network policies and authentication.

## 9. Testing Calls via RestClient with LoadBalancer

In the caller, configure a builder annotated with `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class CallerHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Then create the client:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryProbeClient {

    private final RestClient restClient;

    public InventoryProbeClient(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public String readInstanceIdentity() {
        return restClient.get()
            .uri("http://inventory-service/internal/instance")
            .retrieve()
            .body(String.class);
    }
}
~~~

The `/internal/instance` endpoint on each replica can return JSON containing `instanceId` or the port so you can observe which replica actually handles the request. When configured for the `stable` tier, we expect zero responses from the `canary` replica.

The same supplier chain can also serve requests made by `WebClient` or OpenFeign when that client is integrated with Spring Cloud LoadBalancer and uses the same service ID. The difference between HTTP clients lies in how requests are constructed and sent; the candidate list is still provided by the service's LoadBalancer context.

## 10. Designing a Decorator Based on Request Context

The decorator above uses a fixed `requiredTier`. When each request requires a different tier, `get(Request request)` becomes a key extension point.

A sound design workflow:

1. Define the context field carrying the tier and who is allowed to set that value.
2. Determine how the HTTP client or LoadBalancer component passes the tier into the `Request` of the instance selection process.
3. Inside the decorator, extract the context from the request using the API types appropriate for your version; do not cast arbitrarily.
4. Call `delegate.get(request)`, then filter the list based on the extracted context.
5. Define the policy when the tier is missing, the tier value is invalid, or no candidates remain.

Pseudo-code illustrating the idea:

~~~text
get(request):
    candidates = delegate.get(request)
    tier = readValidatedTierFromContext(request)

    if tier is absent:
        return applyDocumentedDefaultPolicy(candidates)

    return candidates with metadata.trafficTier == tier
~~~

Do not assume an HTTP request's `X-Traffic-Tier` header automatically appears inside LoadBalancer's `Request`. An explicit integration mechanism is required to bridge data from the HTTP request into the load-balancing request context. For clients that already support hints or sticky sessions out of the box, consider Spring Cloud's built-in suppliers rather than reimplementing everything from scratch.

If the tier represents tenant isolation or a sensitive environment boundary, never trust a value self-declared by an external client. The caller must verify permissions and determine the permitted tier before passing it into the pipeline.

## 11. Layered Testing and Integration Testing

Do not check only that the application starts. A chain can start up cleanly yet return the wrong list because of incorrect metadata or a configuration bean placed in the wrong context.

With the three-instance example, test the following scenarios:

| Scenario | Expected result |
|---|---|
| Discovery returns three instances | The baseline supplier includes 8081, 8082, and 8083. |
| `stable` filter | Final list contains only 8081 and 8083. |
| `canary` filter | Final list contains only 8082. |
| Filter with no matching instances | Empty list under a fail-closed policy. |
| Metadata missing `trafficTier` | Instance is excluded from the list when a specific tier is requested. |
| One `stable` instance stops | Caller may encounter connection errors if the static source hasn't removed it; health checks/discovery are needed to update candidates. |
| Same service ID but wrong scope configuration | Detect and fix supplier configuration affecting unintended services. |
| Repeated requests through LoadBalancer | Every response comes from the allowed instance set; the algorithm selects within that set. |

For unit testing a decorator, you can use a fake supplier returning a fixed list of `ServiceInstance` objects and test both `get()` and `get(request)`. For integration testing, run multiple replicas returning distinct identifiers, invoke via the service ID, and verify the identifiers in the responses.

When caching is enabled, also test behavior after adding or removing instances: changes in the registry may not appear immediately in the list served by the cache. When adding health checks, verify the health path, check timeout, and the policy for an empty list.

Do not conclude that round robin is broken just because instances are not chosen in a strict fixed order across a few requests. Verify the candidate set first, and only then evaluate the instance selection algorithm.

## 12. Error Observability and Operations

When encountering `No servers available` or a response indicating no available instances, inspect the pipeline in order:

~~~mermaid
flowchart TD
    A["Client calls service ID"] --> B{"Does discovery have instances?"}
    B -- No --> C["Check service ID, registry, source configuration"]
    B -- Yes --> D{"Does cache have matching data?"}
    D -- No --> E["Check TTL and cache"]
    D -- Yes --> F{"Any candidates left after health / zone / metadata filter?"}
    F -- No --> G["Check filter conditions, metadata, fallback"]
    F -- Yes --> H["Check selection algorithm and HTTP transport"]
~~~

Common design mistakes:

- Placing a request-dependent filter inside a shared cache and caching the filtered result.
- Calling `get()` in a request-aware decorator, preventing the delegate from receiving the request context.
- Mutating a shared list returned by another supplier or cache directly.
- Declaring multiple beans of the same type in the LoadBalancer context without knowing which bean is used.
- Placing `@LoadBalancerClient` configuration inside global component scanning.
- Enabling health checks while the health endpoint is blocked or uses the wrong path.
- Assuming zone/traffic tier metadata exists automatically in the registry.
- Falling back to all instances when the filter is meant to isolate a traffic group.

In production environments, controlled logging should capture the service ID, supplier chain type, input/output candidate counts, and the selected instance identifier. When investigating specific cases, a correlation ID helps correlate requests between caller and callee. Avoid turning continuously changing request IDs, instance IDs, or high-cardinality metadata into unbounded metric labels.

## 13. Key Principles to Remember

- `ServiceInstanceListSupplier.builder()` composes a discovery source and built-in decorators; `DelegatingServiceInstanceListSupplier` lets you add custom logic without rewriting the data source.
- A chain should have a clear source, a clear decorator order, and a single final bean per service ID.
- Cache the baseline list near the discovery source to avoid reusing request-dependent filtered results.
- `get(Request request)` preserves the context required for per-request policies.
- A filter returning an empty list must be handled as an explicit routing decision.
- `@LoadBalancerClient` enables per-service configuration; place configuration classes outside general component scanning to prevent unintended side effects.
- Tests should verify the generated candidate set before evaluating round-robin behavior, retries, timeouts, or HTTP communication quality.

When the supplier chain is designed properly, Spring Cloud LoadBalancer selects from a `ServiceInstance` set aligned with discovery, health status, and routing policies. This forms the foundation for using `RestClient`, `WebClient`, or OpenFeign reliably when a service has multiple replicas.
