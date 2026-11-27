# Toggling Discovery, Blocking Clients, and Reactive Clients

This lesson belongs to the **DiscoveryClient** chapter of the **SPRING_CLOUD_CORE** module. Spring Cloud Commons provides abstractions so applications can locate service instances without depending directly on Eureka, Consul, Zookeeper, or a specific registry. Applications can use the blocking `DiscoveryClient` API or the reactive `ReactiveDiscoveryClient` API. Spring Cloud allows enabling or disabling each client type individually, or disabling discovery entirely, using dedicated properties.

When configuring, distinguish four commonly confused capabilities:

- **Discovery:** querying the list of services and existing instances.
- **Blocking/reactive clients:** two API styles for querying discovery according to the application's programming model.
- **Auto-registration:** registering the application's own instance into the service registry.
- **Load balancing and health indicator:** components that consume discovery data or observe discovery status, each with its own configuration switches.

Disabling one capability does not automatically disable the others. This lesson focuses on picking the right switch, verifying created beans, and assessing the impact on the application.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain the role of DiscoveryClient in Spring Cloud Commons.
2. Distinguish `DiscoveryClient` and `ReactiveDiscoveryClient` by API signatures and usage.
3. Enable or disable the blocking discovery client via `spring.cloud.discovery.blocking.enabled`.
4. Enable or disable the reactive discovery client via `spring.cloud.discovery.reactive.enabled`.
5. Disable all service discovery via `spring.cloud.discovery.enabled`.
6. Distinguish disabling discovery from disabling application auto-registration.
7. Distinguish discovery switches from Spring Cloud LoadBalancer switches.
8. Understand the effect of switches on auto-configuration beans and dependent components.
9. Verify discovery clients, service instances, health indicators, and load-balancing behavior.
10. Design tests for blocking/reactive combinations and registry-absent scenarios.

## 2. What Does DiscoveryClient Do?

In a distributed system, a service can run multiple instances. Each instance's physical address changes during deploys, scaling, restarts, or container replacements. If an application calls a fixed IP/port, it must manage the endpoint list itself and update whenever topology changes.

Service discovery provides a way to locate instances by service ID:

~~~text
service ID: inventory-service
    ├── instance A: http://10.10.1.21:8080
    ├── instance B: http://10.10.1.22:8080
    └── instance C: http://10.10.1.23:8080
~~~

Spring Cloud Commons defines abstractions for applications to query this information. Specific providers such as Eureka, Consul, or Zookeeper handle communication with the registry and translate results into the common `ServiceInstance` type.

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> API["DiscoveryClient abstraction"]
    APP --> RAPI["ReactiveDiscoveryClient abstraction"]
    API --> PROVIDER["Discovery provider"]
    RAPI --> PROVIDER
    PROVIDER --> REG["Service registry"]
    REG --> INST["Service instances"]
    INST --> PROVIDER
    PROVIDER --> API
    PROVIDER --> RAPI
~~~

The application uses the shared abstraction rather than depending directly on a registry-specific API. Consequently, most service-calling logic can stay unchanged when switching providers, even though configuration and detailed behavior still depend on the implementation.

### 2.1. Core Operations

Blocking `DiscoveryClient` provides the primary read operations:

- `getServices()`: returns the list of known service IDs.
- `getInstances(serviceId)`: returns the list of instances belonging to a service ID.
- `description()`: describes the implementation.
- `probe()`: checks whether the client can perform discovery queries; defaults to calling `getServices()`, though implementations may provide a lighter check.

Example:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiscoveryService {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscoveryService(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

The result is the instance list at query time. If the service is not found, implementations typically return an empty list. The application still must handle both empty-instance cases and registry query failures.

### 2.2. What Does ServiceInstance Contain?

A `ServiceInstance` typically provides:

- Service ID.
- Instance ID.
- Host and port.
- URI to call the instance.
- Secure/HTTPS status.
- Metadata supplied by the provider.

Metadata can include zone, region, namespace, version, or provider-specific attributes. Do not assume every provider exposes the same metadata set or follows the same instance selection rules.

## 3. Blocking DiscoveryClient and ReactiveDiscoveryClient

Spring Cloud Commons offers two discovery APIs to match different programming models.

### 3.1. Blocking API

`DiscoveryClient` returns standard Java collections:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

Example:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

if (instances.isEmpty()) {
    throw new IllegalStateException(
        "No inventory-service instance is available"
    );
}

URI target = instances.get(0).getUri();
~~~

The call returns results directly. If the implementation must make an HTTP call to the registry or wait on synchronous I/O, the calling thread blocks until the query completes or times out.

The blocking API fits MVC applications or code using an imperative synchronous model. Never invoke a long blocking operation directly on a reactive application's event-loop thread.

### 3.2. Reactive API

`ReactiveDiscoveryClient` returns data as Reactor Publishers:

~~~java
Flux<String> getServices();

Flux<ServiceInstance> getInstances(String serviceId);
~~~

Example:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.ReactiveDiscoveryClient;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class ReactiveInventoryDiscoveryService {

    private final ReactiveDiscoveryClient discoveryClient;

    public ReactiveInventoryDiscoveryService(
            ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public Flux<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

The reactive API emits results as a stream. Applications can compose Reactor operators like `map`, `filter`, `next`, and `collectList`, or handle errors with `onErrorResume`.

The reactive API fits WebFlux and reactive processing flows. However, a `Flux` return type alone does not prove the underlying provider is completely non-blocking. Inspect the implementation and how it performs I/O; avoid calling a synchronous library on the event loop without switching to an appropriate scheduler.

### 3.3. Comparison

| Criterion | DiscoveryClient | ReactiveDiscoveryClient |
| --- | --- | --- |
| Return type | `List` | `Flux` |
| Invocation model | Synchronous; caller receives collection on completion. | Reactive; results emitted via Publisher. |
| Suitable for | Spring MVC, imperative code. | Spring WebFlux, Reactor pipelines. |
| Result processing | Loops, Stream API, collection operations. | Reactor operators and reactive composition. |
| Impact of slow I/O | Calling thread may have to wait. | Can keep pipeline non-blocking if provider also does non-blocking I/O. |
| What to check | Timeouts, thread usage, and query errors. | Whether provider blocks internally, proper schedulers, and backpressure. |

Do not pick reactive solely because the API returns `Flux`. Choose according to your application stack and the actual capabilities of your discovery provider.

### 3.4. Can One Provider Support Both APIs?

Spring Cloud Commons allows implementations to supply blocking and/or reactive clients. Documentation notes that both types are provided by default in Spring Cloud; however, whether a specific bean exists depends on the provider, dependencies, and active auto-configurations.

If an application only has a blocking provider without a corresponding reactive implementation, enabling reactive discovery does not magically turn every synchronous provider API into a truly reactive implementation. Inspect actual beans and the documentation of the provider in use.

## 4. Discovery Enable/Disable Properties

Spring Cloud Commons provides three primary switches:

| Property | Meaning | Scope |
| --- | --- | --- |
| `spring.cloud.discovery.blocking.enabled` | Enables/disables the blocking discovery client. | `DiscoveryClient` API and auto-configurations depending on blocking discovery. |
| `spring.cloud.discovery.reactive.enabled` | Enables/disables the reactive discovery client. | `ReactiveDiscoveryClient` API and auto-configurations depending on reactive discovery. |
| `spring.cloud.discovery.enabled` | Enables/disables all service discovery. | Global switch for discovery. |

Spring Cloud provides both blocking and reactive discovery clients by default. You can disable either type independently without disabling the other. To disable service discovery completely, use the global switch `spring.cloud.discovery.enabled=false`.

### 4.1. Keeping Both Client Types

If an application contains both MVC and reactive code, or libraries depending on both APIs, keeping the defaults may be appropriate:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: true
~~~

Explicit `true` values make the policy clear to readers. In ordinary applications, these properties can be omitted to use the release train defaults.

### 4.2. Enabling Only the Blocking Client

If the application only uses synchronous APIs:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
~~~

Auto-configurations requiring reactive discovery are then excluded by their corresponding conditions. Blocking beans can still be created if the provider supplies an implementation and other conditions are satisfied.

### 4.3. Enabling Only the Reactive Client

If the application uses WebFlux and the provider supports reactive discovery:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: false
      reactive:
        enabled: true
~~~

This restricts auto-configurations that depend on blocking discovery. Check whether other libraries in the application inject `DiscoveryClient`; if so, they may lose their required bean.

### 4.4. Disabling All Discovery

If a local/test profile does not need service discovery:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: false
~~~

The global switch is appropriate when the application does not need discovery queries. Dependent components, such as Spring Cloud LoadBalancer's service instance supplier, may also not be configured along the corresponding discovery path.

Do not use the global switch if your goal is merely to disable a health indicator or prevent the application from registering itself with the registry. Choose the property matching your actual goal.

## 5. Discovery vs. Auto-Registration

A common misconception is thinking that disabling auto-registration also disables DiscoveryClient. The two are independent.

- **Discovery:** the application queries the registry to find instances of other services.
- **Auto-registration:** the application registers its own instance into the registry at startup.

For example, an application may need to call `inventory-service` while not wanting to register itself in the registry. In that case, keep discovery enabled and disable auto-registration.

### 5.1. Disabling Auto-Registration via Property

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

This property disables Spring Cloud ServiceRegistry's automatic service registration behavior. DiscoveryClient can still query other services if discovery remains enabled and the provider supports it.

### 5.2. Disabling Auto-Registration via Annotation

`@EnableDiscoveryClient` has an `autoRegister` attribute:

~~~java
@Configuration
@EnableDiscoveryClient(autoRegister = false)
public class DiscoveryConfiguration {
}
~~~

However, in modern Spring Cloud, `@EnableDiscoveryClient` is no longer required just to activate discovery when an implementation is already on the classpath. The `spring.cloud.service-registry.auto-registration.enabled=false` property is usually more convenient when managing settings per profile or deployment configuration.

### 5.3. Comparison Table

| Goal | Property / Approach |
| --- | --- |
| Disable blocking client | `spring.cloud.discovery.blocking.enabled=false` |
| Disable reactive client | `spring.cloud.discovery.reactive.enabled=false` |
| Disable all discovery | `spring.cloud.discovery.enabled=false` |
| Only prevent app instance from self-registering | `spring.cloud.service-registry.auto-registration.enabled=false` |
| Only disable discovery health indicator | `spring.cloud.discovery.client.health-indicator.enabled=false` |
| Disable composite discovery health indicator | `spring.cloud.discovery.client.composite-indicator.enabled=false` |

Review your operational goal before choosing a property. A misconfiguration can stop the application from finding dependent services even when the registry is working normally.

## 6. Discovery vs. LoadBalancer

Discovery returns the list of service instances. LoadBalancer selects one instance from that list to send a request.

~~~mermaid
flowchart LR
    CALLER["Service caller"] --> LB["Spring Cloud LoadBalancer"]
    LB --> SUP["ServiceInstanceListSupplier"]
    SUP --> DISC["DiscoveryClient or ReactiveDiscoveryClient"]
    DISC --> REG["Service registry"]
    REG --> INST["ServiceInstance list"]
    INST --> SUP
    SUP --> LB
    LB --> TARGET["One selected instance"]
~~~

The two switches have different meanings:

- `spring.cloud.discovery.enabled=false` disables service discovery.
- `spring.cloud.loadbalancer.enabled=false` disables Spring Cloud LoadBalancer auto-configuration.

If you disable LoadBalancer while keeping discovery enabled, code calling DiscoveryClient directly can still query instances. If you disable discovery while LoadBalancer remains enabled, discovery-backed suppliers will not be able to fetch instances from DiscoveryClient; the application needs another instance source or will fail to resolve service IDs.

Blocking/reactive discovery flags also affect corresponding LoadBalancer configurations. For instance, a blocking LoadBalancer supplier may depend on `DiscoveryClient`; a reactive supplier may depend on `ReactiveDiscoveryClient`.

Do not confuse these three switches as a single toggle:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
    loadbalancer:
      enabled: true
~~~

This configuration keeps overall discovery enabled, keeps blocking discovery enabled, disables reactive discovery, and keeps LoadBalancer enabled. It is a common setup in imperative applications, though you should inspect the dependency graph to confirm no component requires the reactive client.

## 7. Health Indicator Is a Separate Observability Layer

Spring Cloud Commons can create a health indicator backed by the discovery client. The health indicator tests discovery query capability and may display the service list in health details.

Related properties:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          include-description: false
          use-services-query: true
        composite-indicator:
          enabled: true
~~~

Meaning:

- `health-indicator.enabled=false`: disables DiscoveryClientHealthIndicator.
- `health-indicator.include-description=false`: omits the implementation description from health results.
- `health-indicator.use-services-query=false`: uses `probe()` instead of fetching the full service list; can reduce overhead on large registries.
- `composite-indicator.enabled=false`: disables the composite indicator aggregating discovery health indicators.

If you only want to stop health checks from calling `getServices()` on a registry with thousands of services, consider `use-services-query=false`. There is no need to disable discovery just to reduce health-endpoint overhead.

A disabled health indicator does not mean the discovery client is disabled. Likewise, a discovery client can operate even when no health indicator is registered.

## 8. Is `@EnableDiscoveryClient` Still Necessary?

In modern Spring Cloud versions, `@EnableDiscoveryClient` is no longer required when a DiscoveryClient implementation is on the classpath and provider auto-configuration is active.

Example of an application with a suitable discovery starter:

~~~java
@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

You do not need to add `@EnableDiscoveryClient` solely to inject DiscoveryClient when auto-configuration already supplies the bean.

Even so, the annotation can still be useful in certain setups, especially when setting `autoRegister=false` directly on the annotation or working with older versions/integrations. Check documentation for your exact release train and provider.

## 9. SimpleDiscoveryClient When Not Using a Registry-Backed Client

Spring Cloud Commons provides `SimpleDiscoveryClient`. When no service-registry-connected DiscoveryClient is on the classpath, this simple implementation can read instance lists from property configuration.

Example:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
            pricing-service:
              - uri: http://localhost:8091
~~~

An equivalent indexed-properties configuration:

~~~properties
spring.cloud.discovery.client.simple.instances.inventory-service[0].uri=http://localhost:8081
spring.cloud.discovery.client.simple.instances.inventory-service[1].uri=http://localhost:8082
spring.cloud.discovery.client.simple.instances.pricing-service[0].uri=http://localhost:8091
~~~

SimpleDiscoveryClient is useful in local development, tests, or small apps with static endpoint lists. It does not self-register, track, or synchronize topology with an external registry.

Do not confuse SimpleDiscoveryClient with disabling discovery. It is still an implementation of the discovery abstraction, merely using a different data source.

## 10. Choosing Configuration Combinations by Goal

| Scenario | Global Discovery | Blocking | Reactive | Auto-registration |
| --- | --- | --- | --- | --- |
| MVC service using a registry and self-registering | Enabled | Enabled | Can disable | Enabled |
| WebFlux service with a reactive provider | Enabled | Can disable | Enabled | As required |
| App only queries services, no self-registration | Enabled | Per API used | Per API used | Disabled |
| Local test using SimpleDiscoveryClient | Enabled | Enabled if testing imperative code | Enabled if testing reactive code | No external registry applies |
| App does not use service discovery | Disabled | Irrelevant | Irrelevant | Configure per provider if needed |
| Only disable discovery health checks | Enabled | As needed | As needed | Unchanged |

### 10.1. MVC Service

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
    service-registry:
      auto-registration:
        enabled: true
~~~

The application can inject `DiscoveryClient` and use collection APIs. If other reactive components exist that do not use discovery, disabling reactive discovery cuts unnecessary auto-configurations.

### 10.2. WebFlux Service

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: false
      reactive:
        enabled: true
    service-registry:
      auto-registration:
        enabled: true
~~~

Use this configuration only when the provider supplies an appropriate reactive DiscoveryClient and application dependencies do not require a blocking client. If the provider only supplies a blocking API, evaluate supported adapters or integrations rather than assuming a reactive client appears automatically.

### 10.3. Local Application Without a Registry

~~~yaml
spring:
  cloud:
    discovery:
      enabled: false
~~~

If you still need to call other services in a local profile, keep discovery enabled and use SimpleDiscoveryClient with a static URI list. If the application does not call services by ID and needs no registry, disabling discovery entirely makes the configuration clearer.

## 11. Verifying Beans and Startup Behavior

When changing properties, do not just inspect the YAML file. Verify that the ApplicationContext actually applied the properties and check which beans were created.

### 11.1. Verifying Beans via ApplicationContext

Example verification in an integration test:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void blockingClientIsAvailableWhenEnabled() {
    assertThat(applicationContext.getBeansOfType(DiscoveryClient.class))
        .isNotEmpty();
}
~~~

This test assumes a test provider is on the classpath with appropriate registry configuration. If the test has no provider, do not expect registry-backed beans to appear.

### 11.2. Verifying the Reactive Client

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void reactiveClientIsAvailableWhenEnabled() {
    assertThat(
        applicationContext.getBeansOfType(ReactiveDiscoveryClient.class)
    ).isNotEmpty();
}
~~~

In a test with reactive discovery disabled, expect reactive beans managed by auto-configuration not to be created. If the application defines custom beans itself, distinguish custom beans from beans supplied by Spring Cloud auto-configuration.

### 11.3. Verifying Service and Instance Lists

Blocking:

~~~java
List<String> services = discoveryClient.getServices();

List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");
~~~

Reactive:

~~~java
Mono<List<ServiceInstance>> instances =
        reactiveDiscoveryClient.getInstances("inventory-service")
            .collectList();
~~~

Results depend on the registry and query timing. Tests should check service IDs/instances registered by test fixtures rather than relying on shared environment data.

### 11.4. Inspecting the Features and Health Endpoints

Spring Cloud Commons provides the `/features` endpoint to inspect features detected on the classpath and the health endpoint to observe discovery indicators when exposed. In test/diagnostic environments, these endpoints help confirm the provider is detected and health indicators are active.

Do not expose actuator endpoints broadly in production solely to debug discovery. Protect them with authentication, authorization, and network policies.

## 12. Testing Enable/Disable Combinations

A useful test matrix:

| ID | discovery.enabled | blocking.enabled | reactive.enabled | What to Verify |
| --- | --- | --- | --- | --- |
| D1 | true | true | true | Provider-supported APIs can be registered. |
| D2 | true | true | false | Blocking client remains active; reactive auto-configuration is disabled. |
| D3 | true | false | true | Reactive client remains active; blocking auto-configuration is disabled. |
| D4 | false | true | true | Global switch disables discovery; sub-flags do not re-enable discovery. |
| D5 | true | true | true | Health indicator disabled independently, yet discovery client still works. |
| D6 | true | true | true | Auto-registration disabled, yet discovery queries still work. |
| D7 | true | true | false | SimpleDiscoveryClient reads static instances from properties. |
| D8 | true | true | true | LoadBalancer enabled and able to fetch instances via the right API. |
| D9 | true | true | true | LoadBalancer disabled, yet direct code can still call DiscoveryClient. |

Include both context-startup tests and query-behavior tests. Bean existence does not prove the registry connected successfully; similarly, a disabled health indicator does not prove the provider was excluded from the context.

## 13. Common Errors and Remedies

| Symptom | Possible Cause | Remedy |
| --- | --- | --- |
| Cannot inject DiscoveryClient | Blocking client disabled, provider missing from classpath, or auto-configuration not running. | Check properties, dependencies, and condition report. |
| Cannot inject ReactiveDiscoveryClient | Reactive discovery disabled or provider lacks reactive implementation. | Check `spring.cloud.discovery.reactive.enabled` and provider support. |
| Disabled blocking and LoadBalancer finds no instances | Blocking supplier depends on DiscoveryClient. | Enable blocking client or switch to a compatible reactive supplier. |
| WebFlux blocks when querying registry | Code uses blocking DiscoveryClient on the event loop. | Use a truly non-blocking reactive API or offload blocking work to an appropriate scheduler. |
| Service not found despite client bean existing | Service not in registry yet, wrong service ID, or query failed. | Check registry, service ID, namespace, network, and permissions. |
| App does not register yet still queries services | Auto-registration is disabled; these are two independent mechanisms. | Check `spring.cloud.service-registry.auto-registration.enabled`. |
| Disabled health indicator yet discovery still works | Only the health indicator was disabled. | This is expected behavior; use discovery switches to disable queries. |
| Disabled LoadBalancer yet DiscoveryClient bean still exists | LoadBalancer and discovery have separate switches. | Pick the switch for the exact component to disable. |
| SimpleDiscoveryClient returns empty list | Wrong prefix, service ID, or index/URI in properties. | Check `spring.cloud.discovery.client.simple.instances`. |
| Both blocking and reactive clients exist despite using one API | The other flag is still enabled or provider defines a custom bean. | Check bound properties and bean creation sources. |
| Disabled discovery globally yet custom bean still exists | Application defines custom bean outside auto-configuration. | Inspect custom bean definitions and registration conditions. |
| Discovery health turns DOWN | Registry unreachable or probe/query failed. | Check registry endpoint, timeouts, DNS, credentials, and network. |

## 14. Deployment Principles

1. **Choose the API matching the app model.** MVC typically uses blocking; WebFlux should prefer a reactive provider that genuinely supports non-blocking I/O.
2. **Disable at the right scope.** Use blocking/reactive flags to exclude one API; use the global flag when the app does not use discovery.
3. **Separate querying from registration.** If you only want to skip registering the current instance, disable auto-registration while keeping discovery.
4. **Separate discovery from LoadBalancer.** Check both direct callers and instance-selection components.
5. **Separate health from discovery.** Disabling the health indicator only changes observability, not query capability.
6. **Verify the provider.** A registry starter can supply blocking, reactive, or both implementations; do not infer from the dependency name.
7. **Inspect startup conditions.** Use the condition report, bean inspection, and diagnostic endpoints in protected environments.
8. **Set timeouts and handle errors.** Slow or unavailable registries must be handled gracefully.
9. **Never assume instance lists are static.** Instances can change between two queries; handle empty lists and connection errors.
10. **Cross-check your release train.** Auto-configurations and property conditions must be verified against the Spring Cloud version in use.

## 15. Completion Checklist

- [ ] Can explain DiscoveryClient in Spring Cloud Commons.
- [ ] Can distinguish blocking DiscoveryClient and ReactiveDiscoveryClient.
- [ ] Can state the List and Flux return types of the two APIs.
- [ ] Know that blocking and reactive discovery can be toggled independently.
- [ ] Can configure `spring.cloud.discovery.blocking.enabled`.
- [ ] Can configure `spring.cloud.discovery.reactive.enabled`.
- [ ] Can configure `spring.cloud.discovery.enabled` to disable discovery globally.
- [ ] Can distinguish discovery from auto-registration.
- [ ] Know `spring.cloud.service-registry.auto-registration.enabled`.
- [ ] Know `@EnableDiscoveryClient` is no longer required in modern Spring Cloud when a provider is auto-configured.
- [ ] Can distinguish discovery from Spring Cloud LoadBalancer.
- [ ] Can distinguish discovery clients from health indicators.
- [ ] Understand the role and limitations of SimpleDiscoveryClient.
- [ ] Verify beans and query behavior after changing properties.
- [ ] Have tests for blocking/reactive/global combinations and registry-without-service cases.
- [ ] Cross-check properties and providers against the project's Spring Cloud release train.

**Official documentation to verify against your project version:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): blocking/reactive DiscoveryClient, enable/disable switches, auto-registration, health indicators, and SimpleDiscoveryClient.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): list of discovery properties and related settings.
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): how LoadBalancer retrieves service instances via discovery.
- [Spring Cloud Commons – DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java): blocking API signatures.
- [Spring Cloud Commons – EnableDiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/EnableDiscoveryClient.java): `autoRegister` attribute.

Always verify your project's Spring Cloud BOM and specific discovery provider. Property conditions control auto-configuration, while actual query capability depends on the provider, registry, network, and instance data at call time.
