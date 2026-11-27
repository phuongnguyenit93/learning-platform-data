# Scope of spring.cloud.loadbalancer Properties

In the **Spring Cloud Service Communication Load Balancing** module, a calling application may contact multiple target services by service ID such as `inventory-service`, `payment-service`, or `catalog-service`. Spring Cloud LoadBalancer uses the `ServiceInstance` list from discovery, filters candidates according to enabled policies, and selects an instance for `RestClient`, `WebClient`, or OpenFeign to send the request. Each target service may need different cache durations, retries, health checks, and routing policies.

To configure this accurately, you must understand property scoping under the `spring.cloud.loadbalancer` prefix: shared defaults, per-LoadBalancer-client overrides, and a few special switches that only operate at the application-wide level. Placing a property under the right prefix does not automatically enable the corresponding feature; for example, configuring a health-check path does not automatically create a `HealthCheckServiceInstanceListSupplier`.

## 1. Three Scopes to Distinguish

In Spring Cloud, the following three names can look identical on paper yet represent three different things:

| Object | Example | Role |
|---|---|---|
| Caller application name | `spring.application.name: order-service` | Identifies the Spring Boot process sending the request |
| LoadBalancer client ID / target service ID | `inventory-service` | Key used to select configuration and look up target instances |
| A specific ServiceInstance | `inventory-1:8081` | Host, port, instance ID, and metadata of a replica provided by discovery |

Example in an `order-service` application:

~~~text
order-service (caller)
  |
  +-- RestClient -> http://inventory-service/api/items/42
  |                 LoadBalancer client ID: inventory-service
  |                 -> inventory-1 or inventory-2
  |
  +-- WebClient  -> http://catalog-service/api/products/42
  |                 LoadBalancer client ID: catalog-service
  |                 -> catalog-a or catalog-b
  |
  +-- OpenFeign  -> @FeignClient(name = "payment-service")
                    LoadBalancer client ID: payment-service
                    -> payment-1 or payment-2
~~~

The caller's `spring.application.name` is not the client ID used to look up per-target-service configurations. For `@LoadBalanced`-integrated `RestClient`/`WebClient`, the service ID usually comes from the logical host in the URI; for load-balanced OpenFeign, the service ID corresponds to the service name declared in `@FeignClient(name = "...")`. Feign's `contextId` primarily identifies the Feign context/bean and should not be confused with the actual target service ID being called.

Spring Cloud LoadBalancer creates a child context for each service ID, typically initialized when that service is called for the first time. These contexts can have their own `ReactorLoadBalancer` or `ServiceInstanceListSupplier` configurations.

## 2. Property Naming Structure

There are two main ways to place configuration:

~~~text
spring.cloud.loadbalancer.<property>
spring.cloud.loadbalancer.clients.<clientId>.<property>
~~~

The first line sets shared default values; the second sets configuration per LoadBalancer client ID. For most properties supported in both places, Spring Cloud builds the effective configuration by merging both levels, giving precedence to the per-client value.

Example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 1s
        interval: 25s

      clients:
        inventory-service:
          health-check:
            interval: 8s

        catalog-service:
          health-check:
            initial-delay: 3s
~~~

Assuming each service has been configured to use the health-check supplier, the effective values are:

| Client | Initial delay | Interval | Value Source |
|---|---:|---:|---|
| `inventory-service` | 1 second | 8 seconds | Inherits shared delay, overrides interval |
| `catalog-service` | 3 seconds | 25 seconds | Overrides delay, inherits shared interval |
| `payment-service` | 1 second | 25 seconds | No per-client config, uses both shared values |

Per-client configuration does not require duplicating the entire property tree. Declare only the fields you want to change. However, detailed merging behavior can differ for complex map/list values; when dealing with keys such as `health-check.path`, check how the map is supported in your version and test the effective configuration.

`<clientId>` is the logical name of the LoadBalancer client; in this lesson, it is the service ID. If you mistakenly write `inventory` while requests use `inventory-service`, that per-client branch will not govern the intended service.

## 3. Which Property Groups Typically Live in This Namespace?

Commonly used groups:

| Group | Representative Properties | Purpose |
|---|---|---|
| Core toggle | `enabled` | Enables/disables Spring Cloud LoadBalancer application-wide |
| Instance caching | `cache.enabled`, `cache.ttl`, `cache.capacity` | Reduces how often the instance list is fetched from discovery |
| Retry | `retry.enabled`, `retry.max-retries-on-same-service-instance`, `retry.max-retries-on-next-service-instance` | Controls retry behavior for load-balanced calls |
| Health check | `health-check.initial-delay`, `health-check.interval`, `health-check.path` | Timing and URL for checking instances |
| Conditional routing | `zone`, `hint`, `hint-header-name` | Provides zone/hint values for configured instance filters |
| Preset configurations | `configurations` | Selects a pre-packaged LoadBalancer supplier/configuration set |
| Context initialization | `eager-load.clients` | Pre-initializes contexts for the listed service IDs |
| Observability | `stats.micrometer.enabled`, `stats.include-path` | Metrics for load-balanced calls |
| Discovery lookup | `service-discovery.timeout` | Timeout for querying service discovery |
| Sticky/subset | `sticky-session.*`, `subset.*` | Fine-tunes the corresponding policy when enabled |

Properties are bound by Spring Boot into configuration and related load-balancing components. Not every property group corresponds to a feature enabled by default. For example, `zone` does not create `ZonePreferenceServiceInstanceListSupplier` on its own, and `hint` does not create `HintBasedServiceInstanceListSupplier` on its own; the corresponding supplier must exist in the pipeline.

Property names, default values, and support depend on the Spring Cloud Commons/LoadBalancer version. When copying configuration into a real project, verify against the `Configuration Properties` reference of the exact release train instead of guessing key names.

## 4. Four Switches with Global Scope

The Spring Cloud Commons documentation highlights four properties with special scope. Do not treat them like ordinary per-client options.

| Property | Actual Scope | Note |
|---|---|---|
| `spring.cloud.loadbalancer.enabled` | Application-wide | Disabling globally turns off Spring Cloud LoadBalancer; `clients.<id>.enabled` cannot re-enable it independently |
| `spring.cloud.loadbalancer.retry.enabled` | Global retry permission | When enabled globally and the corresponding retry mechanism is present, retries can be disabled for a single client; when disabled globally, a client cannot turn them back on |
| `spring.cloud.loadbalancer.cache.enabled` | Global cache permission | When disabled globally, a client cannot turn it back on; when enabled globally, excluding caching for one client requires configuring a supplier without `CachingServiceInstanceListSupplier` |
| `spring.cloud.loadbalancer.stats.micrometer.enabled` | Application-wide | Enables/disables lifecycle metrics generation; not an independent per-service metrics switch |

Example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      enabled: true

      retry:
        enabled: true

      cache:
        enabled: true

      stats:
        micrometer:
          enabled: true

      clients:
        payment-service:
          retry:
            enabled: false
~~~

Here LoadBalancer remains active for service IDs. Retries are allowed globally, while `payment-service` is configured to disable LoadBalancer retries. Other clients can use retries if the appropriate integration/library is present and the request qualifies.

If you change `spring.cloud.loadbalancer.retry.enabled` to `false`, setting `clients.inventory-service.retry.enabled: true` will not re-enable retries for inventory alone. Similarly, `clients.inventory-service.cache.enabled: false` is not a guaranteed way to remove the caching supplier for inventory alone. Use a per-service supplier configuration when you need to omit a component from the chain.

Do not confuse `stats.micrometer.enabled: true` with metrics appearing immediately. The application also needs a corresponding `MeterRegistry`, such as from Spring Boot Actuator, and a registry configured to export metrics.

## 5. Example Combining Shared and Per-Service Configuration

Suppose `order-service` calls two services: inventory has multiple replicas and occasionally hits transient network errors; payment is sensitive to duplicate execution and the caller does not want LoadBalancer to retry automatically.

~~~yaml
spring:
  application:
    name: order-service

  cloud:
    loadbalancer:
      enabled: true

      cache:
        enabled: true
        ttl: 35s
        capacity: 256

      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retry-on-all-operations: false

      health-check:
        initial-delay: 1s
        interval: 25s
        path:
          default: /actuator/health
          inventory-service: /internal/ready

      clients:
        inventory-service:
          cache:
            ttl: 10s
          retry:
            max-retries-on-next-service-instance: 2
          health-check:
            interval: 10s

        payment-service:
          retry:
            enabled: false

      stats:
        micrometer:
          enabled: true
        include-path: false
~~~

Reading the configuration by group:

- **Cache:** `inventory-service` requests a 10-second TTL if using a caching supplier; clients without an override inherit 35 seconds. A custom Caffeine spec, if configured, can override cache TTL/capacity settings; do not declare both styles expecting both to take effect simultaneously.
- **Retry:** `inventory-service` allows up to two retries on a next instance under Spring Cloud LoadBalancer configuration; other clients inherit one, while `payment-service` disables retries at this layer. This is the retry count, not the total HTTP request count; include the initial attempt.
- **Health check:** `inventory-service` uses a 1-second initial delay and a 10-second interval if the health-check supplier is enabled. The `/internal/ready` path applies to inventory; the default for other clients is `/actuator/health`.
- **Metrics:** Micrometer lifecycle metrics are allowed globally; `include-path: false` reduces the risk of `uri` tag cardinality explosion when request paths contain dynamic IDs.

This is a configuration model illustrating scope. It does not construct `HealthCheckServiceInstanceListSupplier` or add the libraries required for retries/metrics by itself; those components must be configured in the application.

## 6. Distinguishing Property Configuration from Strategy Configuration

A common mistake is assuming you can write:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          strategy: random
~~~

`strategy: random` is not a standard property documented by Spring Cloud LoadBalancer for switching algorithms. By default, `RoundRobinLoadBalancer` is typically used. If you want `inventory-service` to use Random while `payment-service` keeps Round Robin, configure a dedicated LoadBalancer client.

Example of registering per service:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Define `InventoryLoadBalancerConfiguration` in a package that is not scanned by the main application as a global configuration, or use a dedicated configuration class without `@Configuration` and import it only via `@LoadBalancerClient`:

~~~java
public class InventoryLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> randomLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME
        );

        return new RandomLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class
                ),
                serviceId
        );
    }
}
~~~

This example illustrates selecting an algorithm by service ID. The corresponding Spring Cloud LoadBalancer imports and discovery configuration providing instances for inventory are required. `@LoadBalancerClient` sets up beans in the child context for `inventory-service`; this differs from declaring numeric/duration values under `clients.inventory-service`.

When multiple services need custom configuration, `@LoadBalancerClients` can hold multiple `@LoadBalancerClient` declarations. Do not allow those configuration classes to be component-scanned as global configurations, because doing so can cause custom beans to apply more broadly than intended.

The `spring.cloud.loadbalancer.configurations` property provides several built-in configurations, such as `weighted` or `zone-preference`, but that does not mean every custom strategy can be enabled via an arbitrary string. Check the supported values for the version you are using.

## 7. Health Checks: Scope and Activation Conditions

Health-check paths are a special case that already supports per-service-ID mapping directly under the global branch:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 1s
        interval: 20s
        path:
          default: /actuator/health
          inventory-service: /internal/ready
          catalog-service: /internal/health
~~~

`health-check.path.default` is the shared path. Keys under `path` can override the path per service ID. This is a map syntax retained for backward compatibility; it is not an indication that every property can be written in the form `spring.cloud.loadbalancer.<serviceId>.<property>`.

If using `/actuator/health`, the target service needs Spring Boot Actuator or a matching endpoint. If the service exposes a separate management port, `health-check.port` may need to be configured for health-check requests, noting the difference between the probe port and the business port.

To create a health-check supplier, it can be registered specifically for one LoadBalancer client:

~~~java
public class InventoryHealthLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryInstances(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
~~~

And bind that configuration to `inventory-service` using `@LoadBalancerClient(name = "inventory-service", configuration = InventoryHealthLoadBalancerConfiguration.class)`.

If the system uses a service registry that already filters out unhealthy instances, re-checking each instance from the caller can generate unnecessary network traffic. If a health-check supplier is used, place it close to the discovery source in the supplier chain per Spring Cloud's guidance; this supplier maintains its own cached results and should not be arbitrarily wrapped with duplicate caching.

Configuring `health-check.interval` only controls the supplier's polling interval when that supplier actually exists. Without adding the supplier, changing the interval value will not make the caller check instance health automatically.

## 8. Instance Caching: A Different Scope from HTTP Client TTLs

LoadBalancer caching stores the `ServiceInstance` list for target selection. It is not an HTTP response cache or a business object cache.

~~~text
Request
  -> Service ID
     -> ServiceInstanceListSupplier
        -> cached instance list
           -> select instance
              -> RestClient/WebClient/OpenFeign
                 -> HTTP request to instance
~~~

A typical configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
      clients:
        inventory-service:
          cache:
            ttl: 5s
~~~

When a caching supplier is configured and supported in the version in use, a dedicated TTL for inventory can refresh the instance list more frequently. However, setting `ttl: 5s` alone does not guarantee every request sees instant updates: `DiscoveryClient` itself, the registry, or other caching layers also have refresh intervals.

If Caffeine is on the classpath, `spring.cloud.loadbalancer.cache.caffeine.spec` allows configuring the cache using Caffeine spec syntax. When this spec is set, general cache settings such as `ttl` and `capacity` may be overridden by the spec. Therefore, choose one consistent configuration mechanism and verify the behavior.

If discovery already caches instance data on its own, such as with certain registry integrations, consider disabling LoadBalancer caching to avoid multi-layer caching delaying instance state updates. This is an application- and supplier-pipeline-level decision; do not infer it from a single TTL value alone.

## 9. Retry: Global Gate and Per-Service Policy

Commonly used properties:

| Property under `spring.cloud.loadbalancer.` | Meaning |
|---|---|
| `retry.enabled` | Application-wide switch enabling the retry mechanism |
| `retry.max-retries-on-same-service-instance` | Number of retries on the same instance |
| `retry.max-retries-on-next-service-instance` | Number of retries on a newly selected instance |
| `retry.retry-on-all-operations` | Whether to retry operations other than GET |
| `retry.retryable-status-codes` | Set of HTTP status codes considered eligible for retry |
| `retry.retryable-exceptions` | Exception types configured for retry |
| `retry.avoid-previous-instance` | Helps avoid the previously failed instance when choosing a new one |
| `retry.backoff.*` | Backoff settings for reactive retries |

Place fields for attempt counts or error types under `clients.inventory-service.retry.*` to customize inventory. Retries can be disabled specifically for `payment-service` with `clients.payment-service.retry.enabled: false` when enabled globally.

Distinguish the configuration switch from the actual retry mechanism available. For blocking clients, retry behavior depends on integration and the Spring Retry library; for reactive `WebClient`, it depends on reactive integration. Thus, `retry.enabled: true` does not mean every HTTP client automatically retries every request.

Retrying a non-idempotent write operation can cause duplicate order creation or double charging. Disabling retries at the LoadBalancer layer for sensitive services is one option, but you still need to check retries in `RestClient`, Feign, the gateway, and the application layer. Retries across multiple layers can multiply execution counts beyond expectations.

`spring.cloud.loadbalancer.retry.backoff.min-backoff` and similar fields are not TCP connection timeouts; they control the delay between reactive retry attempts when backoff is enabled. HTTP connect/read/response timeouts belong to transport or individual HTTP client configuration.

## 10. Zone, Hint, and Instance Selection Policies

`spring.cloud.loadbalancer.zone` can be configured to indicate the caller's preferred zone. Instances intended for zone filtering need matching metadata, and the pipeline must include `ZonePreferenceServiceInstanceListSupplier`. If no instance exists in the desired zone, the supplier may return the full list according to its fallback strategy.

Hints are commonly used for metadata-based routing:

~~~yaml
spring:
  cloud:
    loadbalancer:
      hint:
        default: stable
        inventory-service: canary
      hint-header-name: X-SC-LB-Hint
~~~

`hint` supports a `default` key and service ID keys; Spring Cloud versions have retained this per-service declaration style for compatibility. To actually filter instances, `HintBasedServiceInstanceListSupplier` or an equivalent component must be configured. The `X-SC-LB-Hint` header can supply a hint per request; the instance list needs matching `hint` metadata. If no instances match, the default supplier may fall back to the original list.

Do not drop values like `zone`, `hint`, or `weight` into an arbitrary YAML file assuming LoadBalancer will automatically switch algorithms. Policies require a supplier or configuration preset that actually reads that data.

## 11. Properties Outside spring.cloud.loadbalancer

This namespace only manages LoadBalancer mechanics and related configurations. It does not replace configuration for every part along the HTTP request path.

| Need | Actual Configuration to Look For |
|---|---|
| Caller application identifier | `spring.application.name` |
| Static instance list | `spring.cloud.discovery.client.simple.instances.<serviceId>` |
| Eureka/Consul registration & discovery | Corresponding Eureka/Consul DiscoveryClient properties |
| RestClient URL, timeouts, and connection pool | `RestClient.Builder` and HTTP request factory/transport |
| WebClient timeouts and pool | `WebClient.Builder`, Reactor Netty, or active connector |
| OpenFeign timeouts | `spring.cloud.openfeign.client.config.<name>.connectTimeout`, `readTimeout`, and version-appropriate client settings |
| Circuit breaker, rate limit, bulkhead | Resilience4j/Spring Cloud CircuitBreaker or equivalent component |
| Target service health endpoint | Spring Boot Actuator and `management.*` |
| Tracing and metrics export | Spring Boot Actuator, Micrometer, tracing backend |

In particular, `spring.cloud.loadbalancer.service-discovery.timeout` relates to the time spent querying discovery. Do not treat it as the timeout for the entire HTTP request to the selected instance.

In addition, `clients.<clientId>` is a per-client configuration branch; it is not where you list a service's `host`, `port`, or `instances`. The instance list must come from `ServiceInstanceListSupplier`, `DiscoveryClient`, a registry, or another properly supplied data source.

## 12. How to Verify Per-Service Configuration

Suppose the caller invokes both inventory and payment simultaneously.

**Step 1: verify the actual service ID.** Use logs or a breakpoint to inspect the service ID URI passed to the load-balanced client. For example, with RestClient/WebClient:

~~~java
// The Builder bean must be configured with @LoadBalanced.
RestClient inventoryClient = loadBalancedBuilder
        .baseUrl("http://inventory-service")
        .build();

RestClient paymentClient = loadBalancedBuilder
        .baseUrl("http://payment-service")
        .build();
~~~

If a client directly calls `http://localhost:8081`, policies under `clients.inventory-service` will not automatically participate in that request.

**Step 2: verify the instance list.** Check that discovery returns the right `ServiceInstance` objects for each service ID, including zone/hint metadata if metadata-based routing is used.

**Step 3: check effective values.** Compare shared and per-service properties. In the example where inventory has a 10-second interval and payment inherits 25 seconds, confirm whether the health-check supplier is registered for the clients that need checking.

**Step 4: verify the feature is actually active.** To observe retries, induce controlled failures on a target instance for an idempotent HTTP GET and trace where retries occur. To observe caching, change the instance list in discovery and measure how long it takes the caller to pick up the update.

**Step 5: check metrics.** Enable an appropriate registry, call endpoints via the load-balanced client, and inspect Spring Cloud LoadBalancer metrics. Metrics may appear only after requests occur. When paths contain dynamic values, consider `stats.include-path: false` to limit cardinality.

**Step 6: compare two clients.** Confirm that changing inventory's override does not inadvertently change payment's behavior. If changing the algorithm or supplier in code, ensure configuration intended for inventory is not component-scanned application-wide.

## 13. Common Configuration Mistakes

**Confusing client ID with caller application name.** Putting properties under `clients.order-service` when the caller invokes `inventory-service` prevents overrides from applying to inventory requests. Key by the target service ID.

**Putting a global property under a client expecting to re-enable it.** `clients.inventory-service.enabled: true` does not override `spring.cloud.loadbalancer.enabled: false`. The four special switches must be understood according to their actual scope.

**Declaring only health-check interval without creating a health-check supplier.** An interval does not add a health checker on its own. Use a supported preset or configure the appropriate `ServiceInstanceListSupplier`.

**Using non-existent properties such as strategy.** `clients.inventory-service.strategy: random` is not standard syntax to switch algorithms. Use `@LoadBalancerClient` and a dedicated `ReactorLoadBalancer` bean.

**Mistaking instance caching for HTTP response caching.** `cache.ttl` governs the instance list, not how long a `GET /products` response is cached.

**Confusing discovery timeout with HTTP timeout.** Configuring a discovery timeout does not enforce connection/read timeouts for `RestClient`, `WebClient`, or Feign.

**Assuming retry.enabled always performs retries.** Ensure the required dependencies/integrations are present; furthermore, requests ineligible for retry will still not be retried.

**Treating health-check.path as a single string property for all services.** It is a map with a default path and per-service-ID entries. Verify proper YAML structure and endpoint availability.

## 14. Pre-Deployment Checklist

- [ ] Confirm the client ID matches the request's service ID, not `spring.application.name`.
- [ ] Use `spring.cloud.loadbalancer.*` for defaults and `spring.cloud.loadbalancer.clients.<clientId>.*` for supported per-service values.
- [ ] Know the four global switches: `enabled`, `retry.enabled`, `cache.enabled`, and `stats.micrometer.enabled`.
- [ ] Do not expect per-client overrides to re-enable a globally disabled feature.
- [ ] Understand that cache TTL is the TTL of the `ServiceInstance` list.
- [ ] Enable the appropriate supplier when health checks, zone preference, or hint filtering are needed.
- [ ] Use `@LoadBalancerClient` when a specialized instance-selection bean or supplier chain is required.
- [ ] Configure HTTP timeouts on the HTTP client; do not confuse them with service-discovery timeout.
- [ ] Retry only safe operations, and verify that dependencies/transport actually support retries.
- [ ] Observe two service IDs side by side to confirm overrides take effect within the right scope.
- [ ] Cross-check the property list against the exact Spring Cloud Commons version in use.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): per-client configuration, custom LoadBalancer, caching, health checks, hints, zones, and Micrometer.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): property names and default values.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): retrying load-balanced calls.

The `spring.cloud.loadbalancer` scope lets you define consistent defaults and tune individual service IDs as needed. Yet not all properties have the same level of override capability: some are global switches, some merge with per-service configuration, and others only take effect if the corresponding supplier/strategy or integration is enabled. Distinguishing these three cases helps you design stable load-balancing policies without unintentionally altering other services.
