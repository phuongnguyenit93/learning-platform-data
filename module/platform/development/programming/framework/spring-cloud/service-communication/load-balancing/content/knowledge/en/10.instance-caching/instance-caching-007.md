# Stopped Replicas Still Remaining in the Cache

When calling a service through **Spring Cloud LoadBalancer**, the client does not necessarily re-query the service registry on every request. The `ServiceInstance` list can be cached to lower latency and reduce discovery lookups. In exchange, for a period of time, the cache may continue to hold **a replica that has stopped, lost connectivity, or is no longer ready to serve requests**.

This is a key scenario in the **Instance Caching** chapter: the registry may already reflect that an instance is down, yet the client's LoadBalancer keeps picking the old endpoint. The typical result is `Connection refused`, a connect timeout, or an HTTP error depending on where the failure happens. The right approach is to identify **where the stale list sits**, which mechanism refreshes it, and what safeguards protect requests during the unsynchronized window.

## 1. Symptom: A Dead Instance Is Still Selected

Suppose `order-service` calls `catalog-service` via its logical URL:

~~~http
GET http://catalog-service/products/42
~~~

Two replicas of `catalog-service` are registered:

| Instance | URI | Initial Status |
|---|---|---|
| `catalog-1` | `http://10.0.1.11:8080` | Serving |
| `catalog-2` | `http://10.0.1.12:8080` | Serving |

The client caches `[catalog-1, catalog-2]`. Later, the `catalog-2` process stops abruptly. The registry removes `catalog-2`, but the client's cache has not expired yet:

~~~text
Current service registry:
  catalog-service -> [catalog-1]

LoadBalancer client cache:
  catalog-service -> [catalog-1, catalog-2]   (stale)

Target selected by LoadBalancer:
  catalog-2 -> 10.0.1.12:8080                (no longer serving)
~~~

LoadBalancer can complete **instance selection** even though **executing the HTTP request** to that endpoint fails. Round-robin selection simply operates on the supplied list; it does not test every network socket before each selection.

~~~mermaid
flowchart TD
    A["HTTP client calls catalog-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["CachingServiceInstanceListSupplier"]
    C --> D["Cache still holds catalog-1 and catalog-2"]
    D --> E["RoundRobin picks catalog-2"]
    E --> F["HTTP transport connects to 10.0.1.12:8080"]
    F --> G["Connection refused / timeout"]
    H["Registry now only has catalog-1"] -.->|"not yet refreshed into cache"| C
~~~

This does not mean the service registry is malfunctioning: an instance may already have vanished from the registry while remaining in another stale data layer.

## 2. Data Layers and Where Stale Information Can Appear

A system using service discovery typically involves several layers tied to the instance list:

| Layer | Data / Activity | Why Can Updates Lag? |
|---|---|---|
| Server process | Actually listens and handles requests | Can crash or lose network instantly |
| Service registry | Registration info and instance status | Heartbeats, disconnect detection timeouts, cluster sync |
| Discovery client | Returns `getInstances(serviceId)` | Some implementations keep a local cache or separate refresh cycle |
| `CachingServiceInstanceListSupplier` | Caches the `ServiceInstance` list for LoadBalancer | TTL has not expired; no lookup has triggered a refresh yet |
| Filtering/preference suppliers | Health checks, zone, hints, or other policies | May rely on stale source data or stale probe results |
| LoadBalancer algorithm | Picks one instance from the list | Selects from supplied candidates; does not execute HTTP |
| HTTP client/transport | Connects to the instance URI | Fails when the endpoint stops serving |

`DiscoveryClient.getInstances("catalog-service")` and the final list emitted by `ServiceInstanceListSupplier` **are not guaranteed to match**. If discovery has updated while the LoadBalancer cache has not expired, the two results can differ. If the discovery client itself caches stale data, shortening the LoadBalancer TTL alone will not yield an accurate list.

### Do Not Confuse This with Connection Pools or DNS Caches

A request can fail due to a **stale instance list**, a **stale DNS address**, or a **reused HTTP connection that was closed**. These are separate mechanisms:

- Stale instance: the client still sees and picks an invalid endpoint.
- Stale DNS: the chosen endpoint's hostname still resolves to an old IP address.
- Stale connection: the transport reuses a socket already closed by the server or an intermediary.

Changing `spring.cloud.loadbalancer.cache.ttl` directly affects only **LoadBalancer's instance list cache**; it does not alter DNS TTLs, connection pools, or registry failure-detection policies.

## 3. Timeline: Why Do Requests Still Hit a Dead Instance?

Consider an illustrative scenario. The cache writes an entry at `t = 0s` with a 35-second TTL; the registry removes the instance after detecting it has stopped:

| Time | Event | List the Client May See |
|---|---|---|
| `t = 0s` | Cache writes `[catalog-1, catalog-2]` | Two instances |
| `t = 5s` | `catalog-2` stops abruptly | Cache still has two instances |
| `t = 10s` | Registry detects and removes `catalog-2` | Registry has only `catalog-1`; cache still has two |
| `t = 15s` | Client sends request and picks `catalog-2` | Request may fail to connect |
| After cache entry TTL expires | A fresh list fetch runs | May contain only `catalog-1`, if discovery has updated |

~~~mermaid
sequenceDiagram
    participant S as catalog-2
    participant R as Service Registry
    participant C as LB Cache
    participant L as LoadBalancer
    participant H as HTTP client
    C->>R: Initial instance fetch
    R-->>C: [catalog-1, catalog-2]
    Note over S: Process stops
    R->>R: Detects / removes catalog-2
    H->>L: Calls catalog-service
    L->>C: Requests candidate list
    C-->>L: [catalog-1, catalog-2] (within TTL)
    L-->>H: Picks catalog-2
    H--xS: Connection fails
    Note over C,R: After cache expires and re-fetches list
    C->>R: Re-queries
    R-->>C: [catalog-1]
~~~

**35 seconds here is the default LoadBalancer cache TTL per current Spring Cloud Commons documentation, not a guaranteed maximum time to evict a dead instance.** TTL runs from when the entry was written to the cache. Refresh timing also depends on how the cache is accessed; if the discovery client or registry still holds stale data when the cache reloads, the dead instance can reappear.

In practice, the window during which stale instances are visible reflects the combined effect of failure detection, registry sync, discovery caching, LoadBalancer caching, and health check schedules. Phases can overlap; never treat summing TTLs as an exact timing guarantee.

## 4. What Does Spring Cloud LoadBalancer Cache?

`CachingServiceInstanceListSupplier` is the supplier used to **cache the instance list** returned by the underlying supplier. It serves LoadBalancer from stored data when appropriate, cutting down repeated discovery queries.

In Spring Cloud Commons, there are two common cache implementation options:

- **Caffeine-backed cache:** used when the `com.github.ben-manes.caffeine:caffeine` dependency is on the classpath.
- **`DefaultLoadBalancerCache`:** provided when Caffeine is absent, along with support from `spring-cloud-starter-loadbalancer`.

General configuration properties:

| Property | Current Documented Default | Effect |
|---|---|---|
| `spring.cloud.loadbalancer.cache.enabled` | `true` | Enables/disables the LoadBalancer caching mechanism |
| `spring.cloud.loadbalancer.cache.ttl` | `35s` | Cache entry lifetime measured from write time |
| `spring.cloud.loadbalancer.cache.capacity` | `256` | Initial cache capacity, not maximum instances in a service |
| `spring.cloud.loadbalancer.cache.caffeine.spec` | Unset | Optional Caffeine configuration when Caffeine is present |

Default values depend on the library version. When targeting a specific Spring Cloud release train, check that version's configuration metadata and documentation.

An illustrative configuration to shorten data retention:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 10s
        capacity: 256
~~~

`ttl: 10s` means LoadBalancer cache entries expire sooner than default. It does not force the registry to remove instances immediately, nor does it cause the HTTP client to resend failed requests.

### Caffeine Spec Can Override General Properties

If using Caffeine and explicitly configuring `spring.cloud.loadbalancer.cache.caffeine.spec`, this spec takes precedence over general LoadBalancer cache properties such as `ttl` and `capacity`. Therefore, do not write a spec with `expireAfterWrite=30s` and expect `cache.ttl: 10s` to win.

Example **replacement** configuration, not an addition to the TTL configuration above:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        caffeine:
          spec: expireAfterWrite=10s,initialCapacity=256,maximumSize=1024
~~~

This configuration is meaningful only when Caffeine is in use. Check valid `CaffeineSpec` tokens for your project's Caffeine version.

## 5. Supplier Chain and Cache Placement

`ServiceInstanceListSupplier` can be composed into a chain: discovery source, cache, health checks, zone preference, hints, or custom policies. For a standard cached chain, Spring Cloud recommends placing `CachingServiceInstanceListSupplier` **immediately after the supplier that fetches instances over the network, and before other filtering suppliers**.

~~~text
Discovery source
   ↓
CachingServiceInstanceListSupplier
   ↓
Zone / hint / other filters (if configured)
   ↓
LoadBalancer picks a ServiceInstance
   ↓
HTTP client calls host:port
~~~

That placement caches the shared list for the service ID. Placing the cache after a request-data filter (such as hints) can store results tied to one specific request, skewing subsequent requests when the cache key does not distinguish those conditions.

### Supplier Chain Configuration Example

In an application with a compatible `DiscoveryClient` and a Spring Cloud version providing the corresponding builder:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogLoadBalancerConfiguration.class
)
class CatalogLoadBalancerRegistration {}

// Keep this dedicated configuration class outside the main component scan scope,
// or omit @Configuration so it is only loaded inside the child context.
class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

This example shows where caching plugs into the supplier. It does **not** supply a complete registry; the application must have the LoadBalancer dependency and an appropriate `ServiceInstance` source. To avoid creating unnecessary cache layers, do not manually add `.withCaching()` if another configuration or integration already manages caching as needed.

## 6. Double Caching: Registry Is Accurate Yet Clients See Stale Replicas

Some discovery clients, such as `EurekaDiscoveryClient`, maintain their own cache or sync mechanism from the registry. If LoadBalancer also caches on top of that output, the system can have **two data-retention layers**:

~~~mermaid
flowchart TD
    A["Service registry<br/>catalog-1"]
    B["Discovery client cache<br/>catalog-1, catalog-2 (stale)"]
    C["LoadBalancer cache<br/>catalog-1, catalog-2 (stale)"]
    D["LoadBalancer picks catalog-2"]
    E["HTTP connection fails"]
    A -->|"refreshes with lag"| B
    B -->|"refreshes on its own TTL"| C
    C --> D --> E
~~~

Even if you drop LoadBalancer's TTL to 5 seconds, the refreshed cache may pull `[catalog-1, catalog-2]` again from the discovery client because that layer has not updated yet. Conversely, tuning registry refresh intervals while leaving an overly long LoadBalancer TTL still delays seeing the updated list.

Spring Cloud documentation recommends **disabling the LoadBalancer cache when the discovery client already performs caching** to avoid unnecessary double caching:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

This configuration disables only the LoadBalancer cache. It **does not disable internal caching in Eureka or other discovery clients**. In production, measure actual query counts and latency before removing a cache layer to avoid putting unnecessary load on the registry.

## 7. Can Health Checks Eliminate Stale Instances Immediately?

`HealthCheckServiceInstanceListSupplier` can periodically probe endpoints of the `ServiceInstance` entries provided by the underlying supplier. If an endpoint fails to report healthy under the configured check criteria, the supplier can filter it out of candidates before LoadBalancer chooses.

However, understand three limitations:

1. **Health checks run periodically.** An instance that just crashed can still be selected before the next probe detects the failure.
2. **Health checks need a sufficiently fresh instance source.** If the underlying supplier does not emit updated lists, configure refetching for that case.
3. **The default behavior when no healthy instances remain is falling back to the entire fetched list.** Per Spring Cloud documentation, `HealthCheckServiceInstanceListSupplier` returns healthy instances, **yet if no instance is healthy it returns the full supplied list**. Thus, it is not a fail-closed filter by default when every endpoint fails.

The third point is easily misunderstood: when both `catalog-1` and `catalog-2` fail health checks, the system may still pick an instance from the source list. If business rules strictly forbid routing to unhealthy endpoints, you need a custom policy and handling for having no valid candidates.

### Illustrative Health Check Configuration

In an application configured to use `HealthCheckServiceInstanceListSupplier`, these properties tune probing and refreshing:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        interval: 10s
        path:
          default: /actuator/health
        refetch-instances: true
        refetch-instances-interval: 15s
~~~

`refetch-instances: true` helps when the delegate does not proactively emit updated lists while the instance source can change. This property does not replace configuring the health-check supplier; some setups require declaring a custom chain via `.withHealthChecks()` (reactive) or `.withBlockingHealthChecks()` (blocking).

Builder example using a discovery client:

~~~java
@Bean
ServiceInstanceListSupplier healthCheckedSupplier(
        ConfigurableApplicationContext context) {
    return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withHealthChecks()
            .build(context);
}
~~~

This snippet is an **alternative** to the cached chain in the previous section, not a second bean to register alongside it. `HealthCheckServiceInstanceListSupplier` retains data via Reactor's `Flux.replay()`, so consider **not wrapping it with `CachingServiceInstanceListSupplier`** when using this mechanism. If the health endpoint is `/actuator/health`, the server must expose it, for example via Spring Boot Actuator.

## 8. Why Do Retries and Timeouts Not Automatically Purge the Cache?

Only after LoadBalancer selects `catalog-2` does the HTTP client open a connection. If connecting fails, cache entries are not automatically updated simply because an exception occurred.

Clearly separate responsibilities:

| Mechanism | Problem It Handles | What It Does Not Guarantee by Itself |
|---|---|---|
| Cache TTL | Bounds how long an instance list is kept | Old instances vanish the instant they stop |
| Service discovery | Supplies lists from the registry | Every request gets instantaneous data |
| Health check | Evaluates endpoints periodically | Dead endpoints are never selected |
| Retry | Re-attempts a call on policy-matching errors | Evicts instances from all caches/discovery |
| Connect/response timeout | Caps HTTP wait time | Picks a healthier instance on its own |
| Circuit breaker | Throttles repeated calls experiencing high failure rates | Directly updates the registry's instance list |

A properly configured retry can re-attempt a request after `Connection refused` or certain timeouts, sometimes choosing a different instance. Yet if the cache still contains both instances and the retry policy does not avoid `catalog-2`, the next attempt can pick the exact same broken endpoint.

For requests with side effects—such as payments or creating orders—retries should only be used after addressing idempotency and failure conditions. On a timeout, the first request may have reached the server and been processed even though the client received no response.

### "No Instances" vs. "Dead Instance" Errors

- **No instances:** the supplier returns an empty list; LoadBalancer has no endpoint to select. The adapter may throw a client-side error before executing HTTP.
- **Stale instance present:** the supplier returns an inactive endpoint; selection succeeds, yet the HTTP connection fails.
- **Backend returns HTTP 5xx:** the request reached a server or proxy and received an error response; inspect logs/traces to distinguish backend failures from intermediary failures.

An HTTP status code alone is insufficient to blame the cache. For example, a 503 error can arise when no instances exist, or be returned directly by a proxy or backend server.

## 9. Tuning TTL: Balancing Freshness Against Lookup Load

A short TTL re-fetches the instance list more often when requests arrive, which can raise discovery query counts. A long TTL relieves registry load, yet stretches how long a stale list remains in use.

| Criterion | Short TTL | Long TTL |
|---|---|---|
| Visibility of changes after fresh cache reads | Usually sooner | Usually slower |
| List re-fetch frequency | Potentially higher | Potentially lower |
| Risk of picking stopped instances before cache refreshes | Usually lower | Potentially higher |
| Source lookup cost | Higher if source has no cache | Lower |
| Impact if discovery source is still stale | Can still re-fetch stale data | Can still re-fetch stale data |

No single TTL is optimal for every system. Consider deployment/scaling cadence, registry failure-detection speed, client count, and request rate.

**Example:** if deployments replace instances frequently, a 10-second TTL can be a reasonable test starting point. This is only a value to benchmark, not a default production recommendation. If the registry already caches and refreshes on a longer cycle, shrinking LoadBalancer's TTL below that cycle yields little benefit.

Do not interpret `capacity: 256` as an instance limit for `catalog-service`; it is a cache capacity parameter, not a policy limiting selection to 256 servers.

## 10. Observing Incidents to Pinpoint the Exact Stale Layer

A diagnostic path should work from ground truth toward the list used by the client:

1. Verify whether `catalog-2` actually stopped or merely failed to answer health checks briefly.
2. Check whether the registry still holds `catalog-2`; record update timestamps.
3. From the client, inspect `DiscoveryClient.getInstances("catalog-service")` at the time of the incident.
4. Inspect the `ServiceInstance` list fed by the supplier to LoadBalancer, especially cache and health check layers.
5. Record instance ID, selected URI, HTTP exception, and request timestamp.
6. Check TTL, Caffeine config (if any), whether the discovery source caches internally, and refresh intervals.
7. Only after pinpointing the layer causing staleness should you adjust TTL, enable health checks, or tune retries.

Example reading `DiscoveryClient` in a Spring application:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class DiscoveryInspector {

    private final DiscoveryClient discoveryClient;

    DiscoveryInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    void logCatalogInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        System.out.println("Discovery count=" + instances.size());
        instances.forEach(instance ->
                System.out.println(instance.getInstanceId() +
                        " => " + instance.getUri()));
    }
}
~~~

This snippet reads from `DiscoveryClient`, **not directly from `CachingServiceInstanceListSupplier`'s internal cache**. For deeper diagnostics, add logging/observation in the supplier chain or run controlled tests comparing lists before and after caching.

### Signals to Monitor

| Signal | Purpose |
|---|---|
| Service ID and selected instance ID | Identify which endpoint was actually called |
| Discovery list vs. supplier list | Pinpoint which layer diverges |
| Instance stop time vs. registry update time | Measure detection lag |
| Cache entry age or refresh timestamp | Evaluate whether TTL is appropriate |
| `Connection refused`, connect timeouts, response timeouts | Classify transport failures |
| Retry rate and instance chosen per attempt | Verify whether retries avoid failed endpoints |
| LoadBalancer/HTTP metrics per service | Track error trends before and after changes |

When metrics for load-balanced calls are needed, Spring Cloud supports Micrometer integration via `spring.cloud.loadbalancer.stats.micrometer.enabled` when a `MeterRegistry` is present. Exact details and metric tags depend on the version and framework integration. Logs should carry trace/correlation IDs while avoiding tokens, cookies, or sensitive payloads.

## 11. Hands-On: Reproducing and Verifying Fixes

Tests can use a dynamic registry like Eureka/Consul or a mock supplier that lets the list change. With a static list in `SimpleDiscoveryClient`, stopping a server does not remove the instance from configuration, so that setup mostly illustrates an **unhealthy instance** rather than reproducing registry removal followed by stale caching.

### Hands-On Scenario

1. Run `catalog-service` with two instances `catalog-1` and `catalog-2`; each exposes `GET /whoami` returning its instance ID.
2. Start `order-service` with a LoadBalancer-integrated HTTP client (`RestClient`, `WebClient`, or OpenFeign) calling service ID `catalog-service`.
3. Wait until both registry and cache see both instances; send multiple requests and record which instance is chosen.
4. Abruptly stop `catalog-2`, tracking when the registry detects and removes the instance.
5. Keep sending requests while the cache has not updated; record selections of the old endpoint and exceptions.
6. Wait for refresh and confirm the final supplier retains only `catalog-1` among candidates.
7. Vary `spring.cloud.loadbalancer.cache.ttl` in an independent run; compare stale window duration and lookup frequency.
8. If using Eureka or an already-caching discovery client, try disabling just the LoadBalancer cache and observe whether errors still stem from discovery caching.
9. Add health checks or retries if needed, then evaluate handling of failed requests while the registry is still converging.

Avoid rigid expectations like "errors will vanish after exactly 10 seconds." Outcomes depend on heartbeats, cache update timing, when entries were written, and HTTP transport conditions.

### Expected Results Verification Table

| Scenario | Outcome to Observe |
|---|---|
| Registry still holds dead instance | Discovery and cache may both keep supplying that instance |
| Registry removed it, LoadBalancer cache still within TTL | Fresh discovery and supplier list can diverge |
| Cache expired, discovery updated | Supplier fetches updated list without dead instance |
| LoadBalancer TTL reduced, discovery cache unrefreshed | Client may still see the old endpoint |
| Health check spots one dead instance while another is healthy | Health-check supplier can prioritize the healthy list |
| Every instance fails health check | Under default fallback, health-check supplier may return full source list |
| Supplier returns empty list | LoadBalancer has no valid instance to pick |

## 12. Operational Practices for Real Systems

To reduce request rates to stopped instances, address multiple layers:

- **Controlled service shutdown:** transition to unready or deregister before stopping the process; leave time for transport and discovery updates while draining in-flight requests.
- **Monitor registry and discovery:** verify heartbeats, failure-detection windows, refreshes, and actual list freshness.
- **Optimize caching:** pick TTL from measurements, avoid redundant two-layer caching, and place the caching supplier properly in the chain.
- **Purposeful health checks:** use them when endpoints must be caught before registry removal; understand probe-interval limits and fallback behavior when no healthy instances remain.
- **Appropriate timeouts/retries:** bound stuck requests and retry conditionally while protecting non-idempotent operations.
- **Observe both phases:** record both the selected `ServiceInstance` and the HTTP outcome to separate list-data errors from connection errors.

Increasing retry counts alone without improving list freshness can keep picking the dead instance. Shrinking TTL alone while the registry still advertises the old instance may yield no meaningful improvement either. Find the true source of stale data before tuning.

**Key takeaway:** Spring Cloud LoadBalancer caching optimizes delivering the `ServiceInstance` list; it is not a real-time health ledger. A stopped instance can still be chosen during the unsynchronized data window. Stability comes from coordinating discovery, caching, health filtering, timeouts/retries, and observability across every layer.

**Official references:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer Caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#spring-cloud-loadbalancer-caching)
- [Spring Cloud Commons – Instance Health-Check for LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#instance-health-check-for-loadbalancer)
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
