# DiscoveryClient Has No Instances or Selects the Wrong Implementation

When `DiscoveryClient#getInstances(serviceId)` returns an empty list, it is often mistaken for a lost connection to the service registry. In reality, an empty result simply indicates that the invoked implementation found no instances for that exact `serviceId` at query time. The cause may lie in runtime dependencies, profile-specific configuration, the service ID, the registry, ordering among multiple discovery clients, or the application calling a blocking API while only a reactive client is enabled.

This lesson guides you along the path from the Spring context to the registry, identifying the actual implementation selected and inspecting the instance list before adjusting configuration.

## 1. Understanding What DiscoveryClient Returns

`org.springframework.cloud.client.discovery.DiscoveryClient` is Spring Cloud Commons' blocking abstraction. Two key operations are:

- `getServices()` returns the service IDs known to the current client.
- `getInstances(serviceId)` returns the `ServiceInstance` objects belonging to the requested service ID.

A `ServiceInstance` describes an instance's address, typically including service ID, host, port, URI, secure flag, and metadata. If `getInstances("inventory")` returns an empty list, check `getServices()` first to see whether the client sees the `inventory` service ID at all. If the service list is also empty, investigate the discovery source and connection settings. If the list contains the service yet has no instances, check registration status, filters, and exact service name.

Distinguishing these three layers helps narrow down the scope quickly:

| Layer | Responsibility | Signals to Check |
| --- | --- | --- |
| Service registry | Stores registered service and instance metadata | Whether the service appears in the registry, matches namespace/region/tenant, and is in a traffic-eligible state |
| `DiscoveryClient` | Reads instances from a registry or static configuration | Which bean is created, and what `getServices()` and `getInstances()` return |
| Spring Cloud LoadBalancer | Picks an instance from the list to send requests | `ServiceInstanceListSupplier`, filters, caching, and per-service-ID client config |

Therefore, if calling `DiscoveryClient` directly returns an empty list, investigate discovery first. If `DiscoveryClient` returns instances yet load-balanced requests still fail, move on to checking LoadBalancer and HTTP client configuration.

Spring Cloud also provides `ReactiveDiscoveryClient`, which uses reactive return types. This is a separate abstraction. An application can enable or disable blocking and reactive discovery independently; one client type existing does not guarantee the other exists.

## 2. Checking Runtime Dependencies and Auto-Configuration

Concrete implementations are supplied by their respective integrations, such as Eureka, Consul, or ZooKeeper. Adding only `spring-cloud-commons`, which provides the abstraction, is not enough to connect to a specific registry. Inspect dependencies for the exact module running the application, especially `runtimeClasspath`; dependencies present only in tests or another module will not create the integration in the failing process.

Examples of common starters:

| Registry | Commonly Used Starter |
| --- | --- |
| Eureka | `org.springframework.cloud:spring-cloud-starter-netflix-eureka-client` |
| Consul Discovery | `org.springframework.cloud:spring-cloud-starter-consul-discovery` |
| ZooKeeper Discovery | `org.springframework.cloud:spring-cloud-starter-zookeeper-discovery` |

With Gradle, you can inspect the application module's dependency tree:

```bash
./gradlew :<application-module>:dependencies --configuration runtimeClasspath
```

Look for the expected registry starter, the matching Spring Cloud Commons version, and any unintended integrations. If the application intends to use Eureka yet the runtime lacks the Eureka client, Spring Cloud cannot infer which registry to connect to. If multiple discovery starters coexist, verify whether that is intentional or leftover dependencies.

Check discovery flags in the loaded configuration:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: true
```

The values above illustrate having both client types enabled. If `spring.cloud.discovery.enabled=false`, discovery is disabled. If `spring.cloud.discovery.blocking.enabled=false`, do not expect the blocking `DiscoveryClient` to be enabled; similarly, `spring.cloud.discovery.reactive.enabled=false` affects reactive discovery. Property names and auto-configuration conditions can change across release trains, so consult the documentation for your application's exact version.

In current Spring Cloud versions, `@EnableDiscoveryClient` is no longer mandatory: placing the appropriate implementation on the classpath triggers the integration's auto-configuration. Adding this annotation cannot substitute for a missing starter, fix a dependency scope, or re-enable a property disabling discovery. For older release trains, check the specific guide for the version in use.

## 3. Confirming Which Implementation Is Actually Created

Do not look solely at declared dependencies. Inspect the beans in the Spring ApplicationContext once the application has started. You can temporarily add an `ApplicationRunner` to log bean names, implementation classes, ordering, and query results. The example below uses `inventory` as an illustrative service ID:

```java
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
class DiscoveryClientDiagnostics implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoveryClientDiagnostics.class);

    private final ApplicationContext applicationContext;

    DiscoveryClientDiagnostics(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    @Override
    public void run(ApplicationArguments args) {
        String serviceId = "inventory";
        Map<String, DiscoveryClient> clients =
                applicationContext.getBeansOfType(DiscoveryClient.class);

        if (clients.isEmpty()) {
            log.warn("No blocking DiscoveryClient bean found");
            return;
        }

        clients.forEach((beanName, client) -> {
            try {
                List<String> services = client.getServices();
                List<ServiceInstance> instances = client.getInstances(serviceId);

                log.info(
                        "bean={} type={} order={} description={} services={} target={} instanceCount={}",
                        beanName,
                        client.getClass().getName(),
                        client.getOrder(),
                        client.description(),
                        services,
                        serviceId,
                        instances == null ? 0 : instances.size());

                if (instances != null) {
                    instances.forEach(instance -> log.info(
                            "bean={} serviceId={} host={} port={} secure={}",
                            beanName,
                            instance.getServiceId(),
                            instance.getHost(),
                            instance.getPort(),
                            instance.isSecure()));
                }
            }
            catch (RuntimeException ex) {
                log.warn("Failed to query DiscoveryClient bean {}", beanName, ex);
            }
        });
    }
}
```

Run diagnostics in a controlled environment, then remove or restrict logging once the cause is found. Service lists, instance addresses, and registry names can be internal operational data; never expose diagnostic endpoints or logs publicly.

Interpret the output using these signals:

1. No `DiscoveryClient` bean: check whether the starter is on the runtime classpath, `spring.cloud.discovery.*` flags, auto-configuration exclusions, and context initialization failures.
2. Implementation is `SimpleDiscoveryClient` when Eureka/Consul was expected: typically indicates checking whether the registry starter is missing, in the wrong module, or running under the wrong profile.
3. Implementation is `CompositeDiscoveryClient`: multiple blocking clients are registered. Inspect each child bean, its `order`, and each backend's result.
4. Provider bean throws an exception: inspect the integration's logs to distinguish DNS, connectivity, authentication, TLS, timeout, or protocol errors.
5. `getServices()` includes the service ID yet `getInstances(serviceId)` is empty: cross-check the exact ID, instance status, and registry filtering rules.

## 4. Understanding SimpleDiscoveryClient and Service ID Configuration

`SimpleDiscoveryClient` is a property-based implementation. Spring Cloud Commons documentation notes it is used when the classpath has no `DiscoveryClient` implementation backed by a service registry. Thus, seeing `SimpleDiscoveryClient` when expecting a real registry usually signals checking runtime dependencies and startup configuration.

Example configuring two static instances for service `inventory`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Equivalent property for the first instance:

```properties
spring.cloud.discovery.client.simple.instances.inventory[0].uri=http://localhost:8081
```

`inventory` in the configuration is the service ID that the caller must pass to `getInstances("inventory")`. If configuration uses `inventory-api` while the caller queries `inventory`, `SimpleDiscoveryClient` returns an empty list. Instance list indices start at `0`.

Do not confuse `spring.application.name` with the target's service ID. `spring.application.name` normally identifies the application itself when registering; the `serviceId` parameter in `getInstances(serviceId)` is the name of the service the caller wants to look up. The two values may match in some setups, but there is no requirement that they match.

Check active profiles and actual configuration sources. An `application-local.yml` file may contain the right instance list while the container runs the `prod` profile; environment variables or command-line arguments can also override YAML files. Verify the final effective values of the relevant properties, not just configuration files in the repository.

## 5. When Multiple Implementations Exist: Ordering and CompositeDiscoveryClient

`DiscoveryClient` extends `Ordered`. Default implementations have an `order` of `0`; custom implementations can override `getOrder()`. Spring Cloud Commons allows setting order for Spring Cloud-provided clients via integration-specific properties, such as `spring.cloud.consul.discovery.order` or `eureka.client.order`. `SimpleDiscoveryClient` has `spring.cloud.discovery.client.simple.order`.

For blocking discovery, `CompositeDiscoveryClient` sorts clients by order and invokes `getInstances(serviceId)` sequentially. It returns the first non-empty list and stops; it does not merge instances from all registries. Therefore, if multiple backends share a service ID, the earlier backend decides which addresses the application sees. Only if the first backend returns empty does the composite try the next backend.

For example, when intentionally prioritizing Eureka ahead of Consul, configure order according to both integrations' documentation and verify the outcome with diagnostic logs. Smaller `order` values are processed first per `Ordered` rules. Use multiple backends only when you have clearly defined the primary source and desired fallback behavior; if the application needs only one registry, removing leftover dependencies makes configuration far easier to reason about.

Reactive discovery must be examined separately. `ReactiveCompositeDiscoveryClient` has different default behavior: querying in parallel and returning the fastest non-empty response. The implementation also has a constructor supporting sequential ordering. Hence, do not apply conclusions about blocking `CompositeDiscoveryClient` ordering to reactive clients without verifying the version and how the composite is constructed.

If the application uses WebFlux, check the exact bean type and `spring.cloud.discovery.reactive.enabled`. If code requires blocking `DiscoveryClient`, check `spring.cloud.discovery.blocking.enabled` and dependencies providing the blocking implementation. Arbitrarily changing the injected type can mask that the application has enabled the wrong client kind.

## 6. Distinguishing Registry Errors from Service ID and LoadBalancer Errors

When the instance list is empty, check in this order:

1. **Service ID:** Call `getServices()` and compare the exact ID with the argument passed to `getInstances`. Do not guess names from URLs, display names, or module names.
2. **Registration:** Open the registry UI or API and confirm instances are registered under the right application, namespace, datacenter/region, and in a state eligible to receive traffic.
3. **Caller configuration:** Check active profiles, registry addresses, credentials, TLS, namespaces, and overriding properties. Inspect startup logs of the provider integration.
4. **Network from the application process:** Check DNS, routes, firewalls, network policies, and registry ports from the actual container or host running the application. Reaching the registry from your laptop does not prove a pod shares the same network path.
5. **Timing:** Confirm the instance registered before the caller queried. Registries can propagate status with delay; do not use a fixed `Thread.sleep` for synchronization. If business logic must wait for service readiness, use bounded retries with explicit backoff and timeouts.
6. **LoadBalancer:** If `DiscoveryClient` already returns instances yet requests by service name still fail to pick a server, inspect `ServiceInstanceListSupplier`, caches, health-check suppliers, zone preferences, filters, and per-service-ID client settings.

Actuator can assist observability. `DiscoveryClientHealthIndicator` relies on the registered implementation; `spring.cloud.discovery.client.health-indicator.enabled` controls this health indicator. By default, the health indicator may call `getServices()`. In systems with many services, `spring.cloud.discovery.client.health-indicator.use-services-query=false` switches to `probe()` instead of querying the entire service list. An `UP` health status means the indicator's check succeeded; it does not prove a specific service ID has instances. Inspect `getInstances(serviceId)` directly when verifying a target service.

Spring Cloud Commons' `features` Actuator endpoint can also show which discovery features are on the classpath and enabled. Expose Actuator or configuration details only on an authenticated, authorized management network; never expose `/actuator/env`, `/actuator/configprops`, or sensitive registry data publicly.

## 7. Testing Discovery Configuration

You should have tests confirming that service IDs the application depends on resolve in the corresponding test environment. If using a real registry, integration tests must start the registry or use a test environment with pre-registered instances. If using `SimpleDiscoveryClient`, explicitly configure mock instances for the test profile.

Example testing the blocking contract at the Spring context level:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest
class DiscoveryConfigurationTest {

    @Autowired
    private DiscoveryClient discoveryClient;

    @Test
    void inventoryServiceHasAtLeastOneInstance() {
        assertThat(discoveryClient.getServices()).contains("inventory");
        assertThat(discoveryClient.getInstances("inventory")).isNotEmpty();
    }
}
```

This test requires registry configuration or `SimpleDiscoveryClient` matching the test profile; otherwise, a failure reflects an unconfigured test environment. In multi-registry setups, add tests verifying the expected implementation and priority order so a newly added dependency cannot silently change which backend supplies instances.

## 8. Version Compatibility Notes

Spring Cloud is released in release trains, each supporting a specific Spring Boot version range. Use the Spring Cloud BOM matching your application's Boot version rather than upgrading an individual starter or `spring-cloud-commons` alone to the latest version. The compatibility verifier can catch incompatible Boot/Cloud combinations at startup; do not disable the verifier just to hide version configuration errors.

Property names, auto-configuration conditions, and blocking/reactive details may change across release trains. When troubleshooting, consult `Spring Cloud Commons` documentation and the integration documentation (Eureka, Consul, ZooKeeper, or Kubernetes) for the exact running version. Do not take an example from `current` docs and assume that property exists in an application running an older release train.

## 9. Quick Checklist

- [ ] Confirm whether the application calls blocking `DiscoveryClient` or `ReactiveDiscoveryClient`.
- [ ] Verify the registry starter is in `runtimeClasspath` of the right module.
- [ ] Verify `spring.cloud.discovery.enabled` and the flag enabling the corresponding client type.
- [ ] Record bean name, implementation class, `order`, `getServices()`, and `getInstances(serviceId)` output.
- [ ] If `SimpleDiscoveryClient`, check registry dependencies and `spring.cloud.discovery.client.simple.instances`.
- [ ] If `CompositeDiscoveryClient`, check each delegate and priority order; remember blocking composite takes the first non-empty list.
- [ ] Compare the service ID against the name published by the registry; verify instances are registered and healthy.
- [ ] If discovery returns instances, move on to checking Spring Cloud LoadBalancer.
- [ ] Align Spring Cloud release train with Spring Boot and consult version-matched documentation.

## Official References

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `DiscoveryClient`, discovery enable/disable flags, implementation ordering, `SimpleDiscoveryClient`, health indicators, and LoadBalancer.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): configuration properties published by Spring Cloud Commons.
- [DiscoveryClient.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java): blocking contract and `Ordered`.
- [CompositeDiscoveryClient.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/composite/CompositeDiscoveryClient.java): how blocking composite sorts and selects instance lists.
- [ReactiveCompositeDiscoveryClient.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/composite/reactive/ReactiveCompositeDiscoveryClient.java): reactive query behavior and sequential ordering option.
- [Spring Cloud Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/index.html): release train versions and Spring Boot compatibility relationships.
