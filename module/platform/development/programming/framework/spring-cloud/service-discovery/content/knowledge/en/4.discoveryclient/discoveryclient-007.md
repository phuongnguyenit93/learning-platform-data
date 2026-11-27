# Multiple DiscoveryClients: Precedence Order and Composite Behavior

A Spring Cloud application can have multiple `DiscoveryClient` implementations at the same time, such as Eureka and Consul. Spring Cloud Commons provides a shared abstraction so application code queries services without depending directly on each registry. When multiple implementations exist, Spring creates a composite client to coordinate queries. The order of the clients and the type of composite used determine which instances are returned.

A key point to understand is that a composite does not automatically synchronize data between registries. For the blocking API, instance queries follow the precedence order and use the first non-empty result. For the reactive API, by default the client returning a non-empty result fastest wins; configuration can enforce ordering or combine results. These two approaches produce different behaviors when a service is registered in multiple places.

## 1. Why does an application have multiple DiscoveryClients?

`DiscoveryClient` is the abstraction for reading service discovery data. Each implementation connects to a specific source, for example:

- `EurekaDiscoveryClient`: reads instance lists from Eureka.
- `ConsulDiscoveryClient`: reads services and health state from Consul.
- `ZookeeperDiscoveryClient`: reads discovery data from ZooKeeper.
- `SimpleDiscoveryClient`: reads a static instance list from application configuration.
- Custom implementation: reads from an internal registry or another data source.

An application may need multiple clients in several scenarios:

1. Phased registry migration, for example migrating services from Eureka to Consul.
2. Some services still reside in the old registry while newer services have registered in the new registry.
3. Teams or deployment zones use different registries while consumers need a shared abstraction.
4. Needing a static instance source for development or testing environments.

When the corresponding starters are on the classpath and auto-configuration is enabled, Spring Cloud can create multiple discovery client beans. Spring Cloud Commons provides `CompositeDiscoveryClient` for the blocking API and `ReactiveCompositeDiscoveryClient` for the reactive API. The blocking composite is the `@Primary` bean by default, so standard injection of `DiscoveryClient` gives the application the composite without having to manually pick a single registry.

In modern Spring Cloud, `@EnableDiscoveryClient` is no longer strictly required just to activate discovery. Having the corresponding implementation on the classpath along with auto-configuration is usually enough. Blocking discovery, reactive discovery, or discovery as a whole can be disabled individually via configuration properties.

## 2. Precedence order of DiscoveryClient

`DiscoveryClient` extends Spring's `Ordered`. Each client has an order value so the composite sorts them before querying:

- **Smaller** numeric values have higher priority and are evaluated first.
- `DiscoveryClient.DEFAULT_ORDER` defaults to `0`.
- If multiple clients share the same `order`, do not rely on bean initialization order to determine which registry wins. Set distinct values for clients that need clear precedence.

For example, to query Eureka before Consul:

```yaml
eureka:
  client:
    order: -10

spring:
  cloud:
    consul:
      discovery:
        order: 0
```

The general configuration property for Spring Cloud-provided clients follows the pattern `spring.cloud.{clientIdentifier}.discovery.order`. Eureka uses its own property `eureka.client.order`. Other examples:

| Discovery client | Order property |
|---|---|
| Eureka | `eureka.client.order` |
| Consul | `spring.cloud.consul.discovery.order` |
| ZooKeeper | `spring.cloud.zookeeper.discovery.order` |
| Simple | `spring.cloud.discovery.client.simple.order` |

For custom implementations, override `getOrder()`:

```java
public final class InternalDiscoveryClient implements DiscoveryClient {

    @Override
    public int getOrder() {
        // Smaller numbers are evaluated first by the composite.
        return -20;
    }

    // description(), getInstances(), and getServices()
    // are implemented against the internal data source.
}
```

Setting `order` only determines the coordination order across clients. It does not sort instances inside a list and does not determine Spring Cloud LoadBalancer's instance selection algorithm.

## 3. How does the blocking CompositeDiscoveryClient work?

The blocking API `org.springframework.cloud.client.discovery.DiscoveryClient` returns `List<ServiceInstance>`. The composite uses the list of clients sorted by order to perform queries.

For `getInstances(serviceId)`, the composite queries each client in turn:

1. Call `getInstances(serviceId)` on the highest-priority client.
2. If the result contains instances, return that list and stop querying remaining clients.
3. If the result is empty, continue querying the next client.
4. If all return empty, the final result is an empty list.

Example:

| Order | Source | Result for `payment-service` |
|---:|---|---|
| `-10` | Eureka | Empty |
| `0` | Consul | `payment-1`, `payment-2` |
| `20` | Internal registry | `payment-3` |

The composite's result contains only `payment-1` and `payment-2`. Once Consul returns a non-empty list, the client with order `20` is not queried. Lists from Eureka and Consul are not concatenated either.

For `getServices()`, the composite aggregates the service IDs known by its constituent clients. Therefore, service enumeration may show that a service exists across multiple registries, while `getInstances(serviceId)` returns only the list from the first source that has instances.

### 3.1. Ordering is not a fallback mechanism for all error types

Order-based fallback happens when a higher-priority client returns an empty list. Do not assume a registry connection failure is equivalent to an empty list. If an implementation throws an exception during lookup, the exception can escape the composite call and halt the query flow before the next client is asked.

This is especially important when running Eureka and Consul side by side. If Eureka is prioritized but Eureka loses connectivity, placing Consul at a lower priority does not by itself create a failover mechanism when an exception occurs. Clarify whether the adapter returns empty, throws an error, or uses a cache when the registry is unreachable; if fault tolerance is needed, design a controlled timeout, cache, or wrapper policy and test that behavior.

Do not blindly turn errors into empty lists. An empty list can mean the service is genuinely unregistered; masking exceptions as empty can hide a registry outage.

## 4. ReactiveCompositeDiscoveryClient has different default behavior

The reactive API `ReactiveDiscoveryClient` returns `Flux<ServiceInstance>` and `Flux<String>`. With multiple reactive discovery clients, the composite by default favors the client that returns a non-empty result fastest. Therefore, `Ordered` ordering does not mean the composite always waits for the client with the smallest order value.

Spring Cloud Commons provides two properties to change this behavior:

| Property | Default | Behavior |
|---|---|---|
| `spring.cloud.discovery.reactive.order-enforced` | `false` | When enabled, only subscribes to query lower-priority clients after higher-priority clients return no instances |
| `spring.cloud.discovery.reactive.combine-instances` | `false` | When enabled, combines instances from all reactive discovery clients instead of using only one client's result |

### 4.1. Enforcing reactive lookup order

```yaml
spring:
  cloud:
    discovery:
      reactive:
        order-enforced: true
        combine-instances: false
```

With `order-enforced: true`, a lower-priority client is only subscribed to when all higher-priority clients return no instances. This is ordered fallback behavior close to the blocking composite.

In return, a higher-priority client that responds very slowly or never completes can delay results from subsequent clients. According to the Spring Cloud Commons documentation, an error from the currently queried client is propagated; the composite does not automatically treat that error as a signal to move on to the next client.

### 4.2. Combining instances from multiple reactive clients

```yaml
spring:
  cloud:
    discovery:
      reactive:
        order-enforced: false
        combine-instances: true
```

With `combine-instances: true`, results from the clients are combined. An error in one client is logged and does not prevent results from other clients from being returned. If `order-enforced: true` is also enabled, clients are queried in the configured order while results are still combined.

`getServices()` on the reactive composite continues to aggregate service lists from the clients; `order-enforced` only affects instance queries. Therefore, do not use the service enumeration result alone to infer which registry supplied instances for a request.

Combining multiple registries can create logically duplicate instances if the same endpoint is registered in multiple places. Do not assume the composite automatically deduplicates two records just because their host and port match. If combining, define instance identification rules, source metadata, and deduplication logic before passing the list to the load balancer.

## 5. Comparing blocking and reactive behavior

| Scenario | Blocking `CompositeDiscoveryClient` | Default Reactive `ReactiveCompositeDiscoveryClient` |
|---|---|---|
| Instance query order | By `Ordered` | Competitive; fastest client returning non-empty wins |
| High-priority client returns empty list | Queries the next client | Empty result does not win; waits for other clients if results remain |
| Can enforce order-based fallback | Already ordered | Yes, enable `order-enforced` |
| Can combine instances across all registries | Not default `getInstances` behavior | Yes, enable `combine-instances` |
| Service ID enumeration | Aggregated from constituent clients | Aggregated from constituent clients |
| Client throws an error | Do not assume error equals empty list; inspect implementation and handle | When order is enforced, error is propagated; when combined, per-client errors are logged and other sources can still return results |

Choose the API according to the application model and clearly understand the aggregation policy. Do not configure `order-enforced` or `combine-instances` and assume they also change the behavior of the blocking `DiscoveryClient`.

## 6. SimpleDiscoveryClient: static instance source

`SimpleDiscoveryClient` reads instances from configuration instead of querying a remote registry. Spring Cloud uses it when no service-registry-based `DiscoveryClient` is on the classpath. This mechanism is useful for local environments, demos, or simple integration tests.

Example declaring two instances for `catalog-service`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

In properties format, the same configuration is represented as:

```properties
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://localhost:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://localhost:8082
```

`SimpleDiscoveryClient` does not automatically check whether endpoints are actually healthy and does not update automatically when instances change. If using it as a discovery source, manage instance configuration and lifecycle via deployment processes. Do not mistake `SimpleDiscoveryClient` for a registry with heartbeats or health checks.

The `spring.cloud.discovery.client.simple.order` property determines the order of the Simple client when this implementation participates in a composite list. However, the Simple client is primarily a fallback option when no registry-backed client is present; do not rely on it as an automatic backup registry alongside Eureka/Consul without verifying the actual beans in the application context.

## 7. CompositeDiscoveryClient is not the Composite Health Indicator

There are two similarly named concepts serving different purposes:

- `CompositeDiscoveryClient` coordinates reading services and instances from multiple `DiscoveryClient` beans.
- `DiscoveryCompositeHealthContributor` aggregates `DiscoveryHealthIndicator` beans to report the health status of discovery components.

The composite health contributor is enabled by default when matching health indicators are present. It can be disabled with:

```yaml
spring:
  cloud:
    discovery:
      client:
        composite-indicator:
          enabled: false
```

`DiscoveryClientHealthIndicator` calls `getServices()` by default to check the client and puts the service list into health details. In environments with very many services, this operation can be expensive; you can switch to the lighter `probe()`:

```yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
```

Adjusting the health indicator does not change the ordering or instance aggregation policy of `CompositeDiscoveryClient`. Likewise, a health indicator reporting `UP` does not guarantee that a specific service called by the consumer has healthy instances.

## 8. Discovery and service registration are two separate directions

`DiscoveryClient` reads instances. `ServiceRegistry` registers or deregisters instances. When an application has multiple discovery integrations, check both directions:

- Consumers can query multiple registries through the composite.
- Producers can be auto-registered with one or more `ServiceRegistry` beans depending on active starters and configurations.

Having two `DiscoveryClient` beans does not automatically ensure a service is registered in both registries. Conversely, if multiple auto-registration mechanisms are active at once, the service may be registered in multiple places. This is a separate deployment decision that must be confirmed via registration logs and each registry's catalog.

Spring Cloud Commons lets you disable general auto-registration with:

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

You can also configure `@EnableDiscoveryClient(autoRegister = false)` in cases where that annotation is still used. Disabling auto-registration does not disable the ability to read instances with `DiscoveryClient`; the two features are independent.

## 9. Integration with Spring Cloud LoadBalancer

Discovery returns a list of `ServiceInstance` objects; LoadBalancer chooses one instance from the list to send a request to. These two steps are distinct:

1. Composite discovery decides which source the instance list comes from or how lists are combined.
2. Spring Cloud LoadBalancer applies the instance selection algorithm over the list supplied by `ServiceInstanceListSupplier`.

For example, if the blocking composite chooses Consul because Eureka returned empty, LoadBalancer selects an instance from the Consul list. Changing `eureka.client.order` does not change a round-robin algorithm into another algorithm, nor does it make LoadBalancer automatically merge instances across registries.

If you want to balance across instances from multiple registries, explicitly define the aggregation before LoadBalancer receives the list. For the reactive composite, `combine-instances` is a built-in merge option. For the blocking API, a custom composite implementation may be needed if the use case requires a union; in that case, resolve duplicates, metadata, zones, health, and instance origin.

## 10. Inspecting order and results in the application

Before enabling multiple discovery starters in production, inspect the actual beans in the application context. For example, you can list the bean name and order of each client:

```java
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@Configuration
class DiscoveryDiagnostics {

    @Bean
    ApplicationRunner logDiscoveryClients(
            Map<String, DiscoveryClient> clients) {
        return args -> clients.forEach((name, client) ->
            System.out.printf("%s -> %s, order=%d%n",
                name, client.description(), client.getOrder()));
    }
}
```

In a composite configuration, the bean map may include both the composite and the constituent clients. When inspecting order, distinguish the composite bean from the actual implementations that call registries. Do not call `getInstances()` on every client and sum the results in production code without a deduplication and error-handling policy.

You can test queries through the injected abstraction:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class CatalogLookup {

    private final DiscoveryClient discoveryClient;

    CatalogLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }
}
```

In an application using default auto-configuration, injection by type usually receives the `@Primary` composite. If you need to call a specific registry for diagnostics, inject the bean by qualifier or look up the bean map by explicit name; avoid changing `@Primary` globally just for a diagnostic check.

## 11. Safe multi-registry rollout process

1. Define the objective: ordered fallback, picking one preferred source, or merging instances across multiple registries.
2. Choose the blocking or reactive API according to the application stack; read the corresponding composite behavior carefully.
3. Set distinct order values for clients requiring clear precedence and verify the property prefix matches the starter.
4. Decide which registry producers will register with; verify auto-registration independently of lookup.
5. Standardize service IDs, instance IDs, metadata, zones, and deduplication policies during migration.
6. Set timeouts and error policies per registry; determine when to return an empty list versus throwing an exception.
7. Check registry caches, discovery caches, and LoadBalancer caches to understand update latency.
8. Test when the prioritized registry returns empty, responds slowly, loses connectivity, or throws exceptions.
9. Test when a service exists only in the secondary registry and when the same service appears in both registries.
10. Monitor the selected instance source, per-registry error rates, query latency, and fallback counts.

## 12. Common configuration issues

| Symptom | Common cause | How to check/resolve |
|---|---|---|
| Clients do not run in expected order | Wrong property prefix or clients have the same order | Check config properties and log `getOrder()` for each bean; set distinct orders |
| Eureka has instances but composite returns instances from Consul | Consul has higher precedence by order or Eureka returned empty | Check `eureka.client.order`, `spring.cloud.consul.discovery.order`, and results from each registry |
| Prioritized registry error prevents querying the next source | Client throws an exception instead of returning an empty list; blocking composite is not a circuit breaker | Check adapter exceptions, timeouts, and failure policies; add controlled fallback |
| Same service appears in `getServices()` but instances come from only one registry | Service enumeration aggregates; blocking instance lookup stops at the first client with results | Check each registry and remember the two methods have different semantics |
| Reactive lookup returns results from the faster-responding registry | Default reactive composite picks fastest non-empty | Enable `spring.cloud.discovery.reactive.order-enforced=true` if ordering must be enforced |
| Reactive lookup is slow or errors without fallback | `order-enforced` waits for the higher-priority client; errors are propagated | Check latency/timeouts and error policy; consider `combine-instances` if aggregation is desired |
| Duplicate instances when merging registries | Same endpoint registered in multiple places or inconsistent instance IDs | Design identification and deduplication rules before LoadBalancer receives the list |
| Service registered in multiple registries unexpectedly | Multiple auto-registration integrations active at once | Check `ServiceRegistry`, registration events, and enable/disable configuration of each integration |

## 13. Checklist

- [ ] Identified all `DiscoveryClient` beans created in the application context.
- [ ] Set distinct orders for registries that need explicit precedence.
- [ ] Identified whether blocking or reactive composite is in use.
- [ ] Understood that blocking lookup returns the first non-empty list, whereas reactive by default selects the fastest non-empty result.
- [ ] If using reactive, explicitly configured `order-enforced` and `combine-instances` according to goals.
- [ ] Checked how each client surfaces registry errors: empty, exception, or cache.
- [ ] Distinguished `getServices()` from `getInstances(serviceId)`.
- [ ] Decided which registry producers register into and verified auto-registration.
- [ ] Handled duplicates, metadata, zones, and instance IDs if merging sources.
- [ ] Verified the actual instance list received by LoadBalancer.

## References

- [Spring Cloud Commons — Common Abstractions, DiscoveryClient ordering, and reactive composite](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons — DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java)
- [Spring Cloud Commons — CompositeDiscoveryClient auto-configuration](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/composite/CompositeDiscoveryClientAutoConfiguration.java)
