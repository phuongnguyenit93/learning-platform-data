# Enabling or Disabling Blocking and Reactive Discovery

Spring Cloud provides two ways to query service discovery on the application side: a **blocking** API through `DiscoveryClient` and a **reactive** API through `ReactiveDiscoveryClient`. Both APIs serve the same goal of finding a list of service instances, but they have different programming models and resource usage patterns. Spring MVC applications typically fit blocking flows; Spring WebFlux applications can use reactive flows to avoid blocking the event loop while handling requests.

Spring Cloud Commons provides configuration properties to enable or disable each discovery style. The choice should be based on the running stack, whether the discovery provider supports the corresponding API, and which beans the application actually uses. Enabling a property does not automatically create an implementation if the dependency or provider does not supply that capability.

## 1. Two discovery APIs in Spring Cloud

### 1.1. Blocking DiscoveryClient

`org.springframework.cloud.client.discovery.DiscoveryClient` is the synchronous API. Commonly used methods include:

- `getServices()`: returns a list of known service IDs.
- `getInstances(serviceId)`: returns a list of `ServiceInstance` objects belonging to the requested service ID.

When calling a method, the current thread waits for the result to return. This is straightforward to use in Spring MVC applications, command-line jobs, or synchronous processing flows.

Example:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class BlockingPaymentLookup {

    private final DiscoveryClient discoveryClient;

    public BlockingPaymentLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
```

The `getInstances` method returns the list directly on the calling thread. If the implementation has to access a remote registry or wait on a synchronous operation, the current thread may be held during that time. Therefore, do not call the blocking API directly on the WebFlux event loop.

### 1.2. ReactiveDiscoveryClient

`org.springframework.cloud.client.discovery.ReactiveDiscoveryClient` provides a reactive API, typically returning `Flux<ServiceInstance>` for the instance list and `Flux<String>` for the service list. Results are represented as a Reactor Publisher so they can be composed with reactive operators and asynchronous processing chains.

Example:

```java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.ReactiveDiscoveryClient;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class ReactivePaymentLookup {

    private final ReactiveDiscoveryClient discoveryClient;

    public ReactivePaymentLookup(ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public Flux<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
```

`Flux` is a publisher that can emit zero, one, or many instances. If there are no matching instances, the publisher can complete without emitting any elements. Consumers need to handle the empty list case using `switchIfEmpty`, `hasElements`, or equivalent logic depending on the goal.

The reactive API lets applications combine discovery with WebFlux, `WebClient`, and other reactive operations without waiting synchronously at the call site. However, the reactive API name does not by itself guarantee that all internal I/O operations in the provider are non-blocking. Actual behavior depends on the discovery implementation and library version.

## 2. Enable/disable properties

Spring Cloud Commons has the following primary configuration properties:

| Property | Meaning | Typical default when unspecified |
|---|---|---|
| `spring.cloud.discovery.enabled` | Enable/disable discovery globally. | `true` |
| `spring.cloud.discovery.blocking.enabled` | Enable/disable blocking discovery client configuration. | `true` |
| `spring.cloud.discovery.reactive.enabled` | Enable/disable reactive discovery client configuration. | `true` |

The defaults above are the common defaults of Spring Cloud Commons. Specific beans still depend on the Spring Cloud version, the starter/provider on the classpath, and other auto-configuration conditions.

Both APIs can be enabled:

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

In that case, the application can use both `DiscoveryClient` and `ReactiveDiscoveryClient` if the active provider supplies the corresponding implementations and configuration conditions are met.

### 2.1. Enabling only blocking

For a Spring MVC application that only needs the synchronous API, you can disable the reactive part:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
```

The application continues using `DiscoveryClient`. Components requiring `ReactiveDiscoveryClient` will not have the corresponding reactive configuration from the disabled auto-configuration; if code still injects that bean, the application may fail to start.

### 2.2. Enabling only reactive

For a WebFlux application with a provider that supports reactive discovery, you can disable the blocking part:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: false
      reactive:
        enabled: true
```

The application should inject `ReactiveDiscoveryClient` and keep processing flows reactive. Components directly depending on the blocking `DiscoveryClient` must be checked before disabling this API.

### 2.3. Disabling discovery globally

If the application does not need to look up services through Spring Cloud Discovery, you can disable discovery globally:

```yaml
spring:
  cloud:
    discovery:
      enabled: false
```

When the global flag is disabled, enabling `blocking.enabled` or `reactive.enabled` individually does not automatically make discovery work again. Check the auto-configuration conditions of the version in use to know exactly which beans are not created.

Do not use the global flag just to disable one API style. If the application still needs the remaining blocking or reactive discovery, keep `spring.cloud.discovery.enabled: true` and adjust the corresponding flag.

## 3. Distinguishing discovery lookup and automatic service registration

Service lookup and service registration are two different activities:

- **Discovery lookup:** the consumer asks the registry for service IDs or instance lists. `DiscoveryClient` and `ReactiveDiscoveryClient` serve this functional group.
- **Service registration:** the provider sends instance information so the registry knows where the service is running. `ServiceRegistry` and the auto-registration mechanism participate in this functional group.

Therefore, disabling a discovery API does not necessarily mean the provider has stopped registering. If the goal is to disable Spring Cloud auto-registration, you can configure it separately:

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

This property controls Spring Cloud's auto-registration mechanism. How a specific provider initializes its client or registers instances still depends on its implementation and dedicated configuration. Verify registration status on the registry after changing configuration.

## 4. Choosing the discovery style per application

### 4.1. Spring MVC applications

Spring MVC processes requests using the servlet model and typically uses synchronous APIs. `DiscoveryClient` is the natural choice when a controller or service needs to retrieve the instance list and then perform synchronous processing.

For example, an internal service needing instance addresses to record operational metrics can use `DiscoveryClient`. If the application already uses `RestTemplate` or `RestClient` with Spring Cloud LoadBalancer, verify the corresponding blocking integration.

### 4.2. Spring WebFlux applications

WebFlux uses Reactor and an event loop. When handling reactive requests, use `ReactiveDiscoveryClient` or a reactive service-calling mechanism supported by Spring Cloud. Avoid calling blocking methods directly in a `Mono`/`Flux` chain, because a synchronous wait can hold the event loop and reduce concurrency.

Example combining lookup with WebFlux:

```java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.ReactiveDiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class DiscoveryController {

    private final ReactiveDiscoveryClient discoveryClient;

    public DiscoveryController(ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/discovery/payment-instances")
    public Flux<String> paymentInstances() {
        return discoveryClient.getInstances("payment-service")
                .map(ServiceInstance::getUri)
                .map(Object::toString);
    }
}
```

This endpoint illustrates returning discovery data reactively. In real applications, carefully weigh exposing internal hostnames and ports via an API; registry information should generally only be provided to authenticated administrative tools.

### 4.3. Applications with both blocking and reactive

An application may contain both MVC and reactive flows, or have a module integrating a synchronous library inside a WebFlux system. In this case, both APIs may be needed. Enabling both does not mean the application should mix them arbitrarily; each flow should use the appropriate API and avoid blocking calls on the event loop.

If a provider only offers one discovery style, enabling the flag for the other does not automatically create an implementation. In that situation, choose a supporting provider, use an abstraction provided by the Spring Cloud version, or build an adapter tailored to requirements while understanding the adapter's limits.

## 5. Integration with Spring Cloud LoadBalancer

The discovery client returns an instance list; the load balancer is responsible for selecting an instance to send the request to. Spring Cloud LoadBalancer has blocking and reactive integration paths corresponding to how the application makes calls.

Typical examples:

| Calling approach | Processing model | Typical API/load balancer |
|---|---|---|
| `RestTemplate` with `@LoadBalanced` | Blocking | Blocking load-balancing client and blocking discovery path. |
| `RestClient` with `@LoadBalanced` in supported versions | Blocking | Blocking load-balancing client. |
| `WebClient` with `@LoadBalanced` | Reactive | Reactive load-balancing client and reactive discovery path. |

Example configuring a load-balanced `WebClient`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

When calling a URI such as `http://payment-service/...`, Spring Cloud LoadBalancer can resolve the service ID to an appropriate instance. This requires the Spring Cloud LoadBalancer dependency and the corresponding discovery provider. Disabling reactive discovery configuration can break the reactive integration path if the active version/provider requires `ReactiveDiscoveryClient`.

Load balancing is not an automatic feature of `DiscoveryClient` alone. An instance list can be looked up successfully, yet requests still need timeouts, retries, and connection error handling.

## 6. Profile-based configuration

You can use Spring profiles to enable the discovery style suited to the environment or application:

```yaml
spring:
  config:
    activate:
      on-profile: mvc
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
```

In the `webflux` profile, you can use the corresponding configuration:

```yaml
spring:
  config:
    activate:
      on-profile: webflux
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: false
      reactive:
        enabled: true
```

Place the documents in the same `application.yml` (inserting the YAML separator `---` between the two documents) or split them into `application-mvc.yml` and `application-webflux.yml`. Only activate the profile matching the type of application being run. If a service needs both APIs, keep both flags at `true` and verify provider support.

Do not copy profile configurations without checking dependent libraries. For example, an internal library might inject `DiscoveryClient` even though the main application uses WebFlux; disabling blocking discovery will cause the context startup to fail if that bean is no longer provided.

## 7. When should you enable or disable?

| Situation | Suggested configuration | Reason |
|---|---|---|
| MVC application using only synchronous APIs | Blocking `true`, reactive `false` if certain no dependency needs reactive discovery. | Reduces unused configurations/beans. |
| WebFlux application using reactive discovery | Blocking `false` if no blocking component depends on it; reactive `true`. | Keeps processing flows reactive and avoids synchronous calls on the event loop. |
| Application with both MVC and WebFlux or both client types | Both `true`. | Lets each component use the appropriate API. |
| Application not using service discovery | Global `enabled: false`. | Disables discovery auto-configuration globally. |
| Provider only supports blocking | Blocking `true`; do not rely on the reactive flag to create a reactive API. | You need an implementation that truly supports reactive to use reactive discovery. |
| Only want to stop provider auto-registration | Control `service-registry.auto-registration.enabled` and provider configuration. | That is the registration flow, separate from consumer lookup. |

Do not disable an API style merely because the application is called MVC or WebFlux. Check the beans injected across the entire context, integrated libraries, and LoadBalancer call paths before making changes.

## 8. Checking beans and diagnosing configuration

After changing properties, verify whether the application has the expected API. You can test by injecting the required API into a small bean or checking auto-configuration conditions in the startup logs.

If Actuator is enabled and the conditions endpoint is permitted in an appropriate administrative environment, the `/actuator/conditions` endpoint can help inspect which auto-configurations were applied or excluded. Do not expose this endpoint unprotected to external environments.

Common situations:

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Cannot inject `DiscoveryClient` | Blocking discovery is disabled, global discovery is disabled, or provider is missing from the classpath. | Check the three discovery flags, provider dependencies, and auto-configuration conditions. |
| Cannot inject `ReactiveDiscoveryClient` | Reactive discovery is disabled or the provider does not supply a reactive implementation. | Enable the reactive flag and verify that the provider/version actually supports it. |
| WebFlux is slow or the event loop stalls | Calling a blocking API in a reactive flow or the reactive provider performs synchronous I/O internally. | Use a reactive implementation; if forced to wrap a blocking API, offload the task to a scheduler meant for blocking work and evaluate limits. |
| Disabling blocking breaks `@LoadBalanced RestTemplate` | The RestTemplate call path needs the blocking discovery/load-balancing path. | Re-enable blocking or switch the client to an appropriate reactive path. |
| `WebClient` cannot resolve service IDs | Reactive load-balancer/discovery path is missing or dependency configuration is incorrect. | Check Spring Cloud LoadBalancer, reactive discovery, and provider. |
| Provider still appears in the registry after disabling lookup | Registration is a separate flow and is still performed by the provider. | Check `ServiceRegistry` and the auto-registration flag, then verify on the registry. |
| Discovery API returns an empty list | Service has not registered yet, status is ineligible, or registry/cache has not updated. | Check provider, registry, health, and refresh timing. |

### 8.1. Wrapping a blocking API in a reactive application when unavoidable

If a provider only has a blocking `DiscoveryClient` yet the application needs temporary integration with a reactive chain, you can offload the blocking call to `boundedElastic`:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class BlockingDiscoveryAdapter {

    private final DiscoveryClient discoveryClient;

    public BlockingDiscoveryAdapter(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public Mono<List<ServiceInstance>> findInstances(String serviceId) {
        return Mono.fromCallable(() -> discoveryClient.getInstances(serviceId))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
```

This is a way to isolate the blocking operation from the event loop, not to turn blocking I/O into non-blocking I/O. Limit concurrency, set timeouts, and monitor the thread pool; do not use an adapter as an excuse to skip a proper reactive provider under high load.

## 9. Version and security notes

- The `spring.cloud.discovery.*` properties belong to Spring Cloud Commons; check the documentation for the exact release train in use because auto-configuration conditions and property names may change across versions.
- Align Spring Boot, Spring Cloud release train, and discovery starter versions according to your project's compatibility matrix.
- Do not assume every registry provides both blocking and reactive implementations.
- Do not call blocking APIs on the WebFlux event loop; blocking operations must be isolated on an appropriate scheduler if they cannot be replaced with a reactive API.
- The registry may contain internal hostnames, IPs, ports, and metadata. Protect registry APIs, Actuator, and the conditions endpoint with appropriate network policies, authentication, and authorization.
- Disabling discovery lookup does not replace security configuration, deregistration, or instance shutdown procedures.
- When changing flags in production, check whether health indicators, gateways, load balancers, and internal libraries depend on the disabled beans.

## Conclusion

`DiscoveryClient` is the blocking API returning synchronous results; `ReactiveDiscoveryClient` is the reactive API returning data through a Reactor Publisher. Spring Cloud Commons lets you enable/disable discovery globally and per API style with `spring.cloud.discovery.enabled`, `spring.cloud.discovery.blocking.enabled`, and `spring.cloud.discovery.reactive.enabled`.

Choose the API that matches your application's processing model, verify that the provider actually supports it, and check dependent components before disabling beans. In particular, distinguish discovery lookup from service auto-registration to avoid accidentally changing provider registration behavior when your goal is only to adjust how the consumer looks up instances.
