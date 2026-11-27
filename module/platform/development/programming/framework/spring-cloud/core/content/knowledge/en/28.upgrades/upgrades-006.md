# Removing Legacy Assumptions About Required Annotations and Self-Created Clients

## 1. Why Review How Discovery Is Enabled and Clients Are Created?

In older Spring Cloud applications, many projects placed `@EnableDiscoveryClient` on the main configuration class and instantiated HTTP clients directly inside each service. That approach easily coupled code to annotations, concrete implementations, or manual instantiation.

Modern Spring Cloud Commons relies much more on auto-configuration and dependency injection:

- Putting the appropriate discovery implementation on the classpath is usually enough for Spring Boot to configure `DiscoveryClient`; `@EnableDiscoveryClient` is no longer a mandatory requirement.
- The application must still declare an HTTP client as a Spring bean when that client is needed. `RestTemplate` does not automatically appear as a bean just by adding Spring Web.
- When calling by service ID, the client must be configured with Spring Cloud LoadBalancer, typically through a bean annotated with `@LoadBalanced`.
- Services should receive abstractions or client beans via constructor injection instead of calling `new` on implementations everywhere.

The goal of this lesson is to help upgraders drop activation steps that have become redundant while keeping the bean declarations that are genuinely required. Not every `@Enable...` annotation is obsolete, and not every HTTP client is automatically load-balanced.

After this lesson, readers can:

- Explain why `@EnableDiscoveryClient` is no longer mandatory in typical cases.
- Identify which dependencies supply the discovery implementation and which supply LoadBalancer.
- Inject `DiscoveryClient`, `ServiceRegistry`, and HTTP clients via the Spring container.
- Distinguish standard HTTP clients from clients capable of resolving service IDs.
- Choose `RestClient`, `RestTemplate`, or `WebClient` according to the synchronous/reactive stack.
- Upgrade legacy code while preserving necessary auto-registration and security settings.

## 2. Discovery Is Auto-Configured from Dependencies

Spring Cloud Commons provides the `DiscoveryClient` and `ReactiveDiscoveryClient` abstractions. Integrations such as Eureka, Consul, or Zookeeper provide the concrete implementations. When an implementation dependency is on the classpath, Spring Boot can auto-configure the discovery client.

Maven dependency example for an application using Eureka:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

Or if using Consul:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
```

Choose the integration corresponding to the service registry your system uses. Normally you should not add multiple registry clients simultaneously just to "turn on discovery"; if multiple implementations are present, understand the order and role of each client.

### 2.1. @EnableDiscoveryClient Is No Longer Mandatory

Legacy code often has:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@SpringBootApplication
@EnableDiscoveryClient
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
```

With modern Spring Cloud Commons, `@EnableDiscoveryClient` can be removed:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
```

If the Eureka or Consul Discovery dependency is on the classpath and not disabled by properties, auto-configuration provides the corresponding discovery beans.

`@EnableDiscoveryClient` still exists in Spring Cloud Commons. What changed is that applications no longer need this annotation merely to tell Spring to look for an implementation. It should not be described as a removed annotation or something that broke every legacy application.

### 2.2. Dependencies and Properties Are the Conditions to Check

If discovery does not appear, check:

1. Is the registry implementation starter on the runtime classpath?
2. Does any property set `spring.cloud.discovery.enabled=false`?
3. Was blocking or reactive discovery disabled individually?
4. Was auto-configuration excluded or a bean condition disabled?
5. Are the registry endpoint, credentials, and network ready?

Common control properties:

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

`spring.cloud.discovery.enabled=false` disables service discovery in general. The two properties `blocking.enabled` and `reactive.enabled` allow disabling each client type individually. Do not use `@EnableDiscoveryClient` to try to override a configuration that intentionally disabled discovery.

The full names of the two individual properties are `spring.cloud.discovery.blocking.enabled` and `spring.cloud.discovery.reactive.enabled`.

### 2.3. SimpleDiscoveryClient When No Registry Implementation Is Present

If no service-registry-backed discovery client is on the classpath, Spring Cloud Commons can use `SimpleDiscoveryClient`. It reads instance lists from configuration instead of querying Eureka, Consul, or Zookeeper.

Its configuration prefix is `spring.cloud.discovery.client.simple.instances`; the subsequent segments are the service ID and instance index.

Example:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
            pricing-service:
              - uri: http://localhost:8082
```

This is useful for local environments, tests, or systems with a static list of endpoints. It does not register the instance into an external registry.

## 3. Remaining Annotations Serve Dedicated Purposes

Do not bulk-delete `@Enable`-prefixed annotations just because `@EnableDiscoveryClient` is no longer mandatory.

| Annotation | Role | Can it be removed just for discovery auto-config? |
| --- | --- | --- |
| `@EnableDiscoveryClient` | Legacy discovery activation mechanism; no longer mandatory when an implementation is on the classpath | Can be removed if used solely to enable discovery |
| `@EnableFeignClients` | Scans and registers `@FeignClient` interfaces | No |
| `@EnableScheduling` | Enables scheduled tasks | No |
| `@EnableAsync` | Enables asynchronous processing via Spring | No |
| `@EnableMethodSecurity` | Enables method-level authorization | No |
| `@EnableConfigurationProperties` | Registers specified configuration classes | No, unless another registration mechanism replaces it |

Each annotation has its own conditions and purpose. During an upgrade, remove `@EnableDiscoveryClient` if it was only used to turn on discovery; keep annotations that enable independent capabilities.

## 4. Controlling Auto-Registration Without Annotations

Discovery and auto-registration are related but distinct tasks:

- Discovery lets the application find service instances.
- Auto-registration registers the application's current instance with the service registry.

By default, many discovery implementations automatically register the local service. To disable that behavior, configure it via property:

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

Legacy code sometimes used:

```java
@EnableDiscoveryClient(autoRegister = false)
```

When removing the annotation, do not accidentally drop the intent to disable auto-registration. Transfer that intent to `spring.cloud.service-registry.auto-registration.enabled=false`.

If controlled registration operations are needed, inject the `ServiceRegistry` and `Registration` abstractions matching the implementation. `ServiceRegistry` is generic over the specific registration type; for example, Eureka and Consul have their own registration types. Therefore, declare the field/constructor with the exact type provided by the integration and let Spring inject the bean. Do not construct registry implementations manually with `new`.

If you only want to disable auto-registration, the property is sufficient; there is no need to inject `ServiceRegistry` and replace the entire registry lifecycle manually.

## 5. Injecting DiscoveryClient Instead of Creating Implementations Manually

`DiscoveryClient` is the abstraction for querying service instances. Applications should inject this interface:

```java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class ServiceCatalog {

    private final DiscoveryClient discoveryClient;

    public ServiceCatalog(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }

    public List<String> listServices() {
        return discoveryClient.getServices();
    }
}
```

Benefits of constructor injection:

- Spring supplies the right implementation according to current dependencies and configuration.
- Business code does not depend directly on Eureka, Consul, or Zookeeper.
- Tests can replace the `DiscoveryClient` bean with a mock or fake.
- Required dependencies are stated explicitly in the constructor.

Do not write:

```java
// Do not instantiate concrete implementations in business code.
DiscoveryClient client = new EurekaDiscoveryClient(...);
```

Concrete implementations may require many internal dependencies, lifecycles, and configurations. Creating objects manually skips auto-configuration steps and can produce a client that does not share state with the `ApplicationContext`.

### 5.1. When Choosing an Instance for a Request

`DiscoveryClient.getInstances(serviceId)` returns a list of instances. If you only need to display or inspect metadata, this is appropriate. However, if the goal is to send an HTTP request to an instance, do not manually pick the first element and assemble the URL yourself.

Use Spring Cloud LoadBalancer to select an instance and resolve service-ID URIs. This ensures selection policies, suppliers, caching, and LoadBalancer customizations are applied.

## 6. Do Not Create New HTTP Clients Inside Every Service

A common mistake is instantiating a client directly at the call site:

```java
public class InventoryGateway {

    public Inventory get(String id) {
        RestTemplate restTemplate = new RestTemplate();
        return restTemplate.getForObject(
                "http://inventory-service/api/items/" + id,
                Inventory.class
        );
    }
}
```

This client is not a Spring bean. It receives none of the interceptors, customizers, observability configuration, or LoadBalancer integration that the application configured on client beans. If the URI uses a service ID like `inventory-service`, a plain `RestTemplate` also does not know how to resolve that name via discovery.

Instead, define the client bean once and inject it into the services that need it. When calling by service ID is required, mark the client with `@LoadBalanced`.

## 7. RestTemplate: The Application Must Declare the Bean

Spring Cloud Commons explicitly notes that a `RestTemplate` bean is not created via auto-configuration. The application must declare the bean itself if it wants to inject `RestTemplate`.

Load-balanced example:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
```

Then inject via constructor:

```java
@Service
public class InventoryGateway {

    private final RestTemplate restTemplate;

    public InventoryGateway(@LoadBalanced RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public Inventory get(String id) {
        return restTemplate.getForObject(
                "http://inventory-service/api/items/{id}",
                Inventory.class,
                id
        );
    }
}
```

`@LoadBalanced` is a qualifier marking beans that need LoadBalancer integration. It does not replace the discovery implementation and does not automatically add a service registry to the classpath.

To use `@LoadBalanced RestTemplate`, a Spring Cloud LoadBalancer implementation must be on the classpath, usually via the starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

The URI must use the service ID as the host, such as `http://inventory-service/...`. LoadBalancer obtains physical instances from discovery and builds the target address.

## 8. RestClient: Synchronous Choice for New Code

With Spring Framework providing `RestClient`, Spring Cloud LoadBalancer supports a `RestClient.Builder` marked with `@LoadBalanced`.

Declare the builder bean:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Inject the builder into a client wrapper:

```java
@Component
public class PricingClient {

    private final RestClient restClient;

    public PricingClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public Price getPrice(String sku) {
        return restClient.get()
                .uri("http://pricing-service/api/prices/{sku}", sku)
                .retrieve()
                .body(Price.class);
    }
}
```

If you want to preserve customizations Spring Boot applies to `RestClient.Builder` such as observability, configure the builder using `RestClientBuilderConfigurer` according to your Boot version. Do not replace a Boot-managed builder with a raw self-created instance if the application relies on those customizers.

`RestClient` requires a Spring Framework baseline that supports this API. On older baselines, continue using `RestTemplate` or `WebClient` per the existing stack.

## 9. WebClient: Reactive Client with LoadBalancer

Reactive applications can use `WebClient.Builder` with `@LoadBalanced`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ReactiveClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Inject the builder and create the client:

```java
@Component
public class ReactiveInventoryClient {

    private final WebClient webClient;

    public ReactiveInventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<Inventory> get(String id) {
        return webClient.get()
                .uri("http://inventory-service/api/items/{id}", id)
                .retrieve()
                .bodyToMono(Inventory.class);
    }
}
```

`@LoadBalanced WebClient.Builder` requires Spring Cloud LoadBalancer on the classpath. With WebFlux, LoadBalancer uses the reactive integration; do not create a new `WebClient` inside every method if you need to retain the application's shared filters, connectors, and customizers.

## 10. Distinguishing Standard Clients from Load-Balanced Clients

An application often needs both types of clients:

- A standard client calling physical URLs or external endpoints such as `https://api.partner.example`.
- A load-balanced client calling internal service IDs such as `http://inventory-service`.

Two builders can be declared:

```java
@Configuration(proxyBeanMethods = false)
public class ClientBuildersConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    @Primary
    RestClient.Builder directBuilder() {
        return RestClient.builder();
    }
}
```

When injecting, specify the qualifier clearly:

```java
@Component
public class PartnerApiClient {

    private final RestClient restClient;

    public PartnerApiClient(RestClient.Builder directBuilder) {
        this.restClient = directBuilder.build();
    }
}

@Component
public class InternalInventoryClient {

    private final RestClient restClient;

    public InternalInventoryClient(
            @LoadBalanced RestClient.Builder loadBalancedBuilder) {
        this.restClient = loadBalancedBuilder.build();
    }
}
```

`@Primary` lets Spring pick the standard builder when injection has no qualifier. The key point is that internal clients using service IDs must explicitly receive the load-balanced builder; clients calling the public internet do not need to go through discovery.

## 11. Dependency Injection Does Not Mean Everything Is Created Automatically

During an upgrade, distinguish three things:

| Component | Who provides it? | What must the application do? |
| --- | --- | --- |
| `DiscoveryClient` | Discovery starter and auto-configuration | Add the right registry implementation, inject the interface |
| `ServiceRegistry` | Discovery integration | Inject if manual registration operations are needed |
| `RestTemplate` | Application declares the bean | Create a `@Bean`; add `@LoadBalanced` if service IDs are needed |
| Load-balanced `RestClient.Builder` | Application declares the builder with `@LoadBalanced` | Inject the builder and build a shared client |
| Load-balanced `WebClient.Builder` | Application declares the builder with `@LoadBalanced` | Inject the builder in reactive clients |
| `LoadBalancerClient` | Spring Cloud LoadBalancer | Inject when direct instance-selection API is needed |

Discovery auto-configuring itself does not mean all HTTP clients are created automatically. Conversely, the application having to declare HTTP client beans does not mean it should instantiate discovery implementations manually.

## 12. Upgrade Path from Legacy Code

When migrating an existing application, you can follow these steps:

1. Check the current registry dependency and verify it is compatible with the Spring Boot/Spring Cloud release train in use.
2. Remove `@EnableDiscoveryClient` if the annotation was used only to enable discovery.
3. If the annotation set `autoRegister=false`, move that intent to `spring.cloud.service-registry.auto-registration.enabled=false`.
4. Search for `new EurekaDiscoveryClient`, `new ConsulClient`, `new RestTemplate()`, or `new WebClient...` in business code.
5. Switch dependencies to constructor injection and centralize bean definitions in configuration classes.
6. Add the Spring Cloud LoadBalancer starter if HTTP clients need to call by service ID.
7. Apply `@LoadBalanced` to the appropriate builder/client beans and qualifiers at injection points.
8. Keep standard clients for physical URLs or external APIs.
9. Check `@EnableFeignClients` and other `@Enable` annotations; do not remove them by blanket assumption.
10. Write integration tests proving discovery beans and client beans are created by the `ApplicationContext`.
11. Verify actual requests route to instances provided by discovery.

Do not upgrade every service simultaneously without verifying behavior. Start with a service that has few downstream dependencies, confirm registration, discovery, and load balancing, and then apply the same pattern to other services.

## 13. Post-Upgrade Testing

### 13.1. Verify DiscoveryClient Is Provided Without the Annotation

This test does not declare `@EnableDiscoveryClient`. It assumes the test runtime includes a discovery implementation starter:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class DiscoveryAutoConfigurationTests {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void discoveryClientIsProvidedByClasspathIntegration() {
        assertThat(applicationContext.getBeansOfType(DiscoveryClient.class))
                .isNotEmpty();
    }
}
```

This test verifies the bean is created in the `ApplicationContext`. If an application has multiple discovery implementations, there may be a composite bean or multiple beans depending on configuration; do not assert a specific implementation class name unless testing a specific integration.
This test belongs in a project that already has the application's `@SpringBootConfiguration` and discovery dependency on the test runtime classpath. If running as a standalone test, specify `classes` pointing to the test application configuration.

### 13.2. Verify the Load-Balanced Client Is Injected

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class LoadBalancedClientConfigurationTests {

    @Autowired
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder;

    @Test
    void loadBalancedBuilderIsAvailable() {
        assertThat(loadBalancedBuilder).isNotNull();
    }
}
```

This test assumes `RestClient` is in the Spring Framework baseline and the application declared the builder bean as shown earlier. For applications using `RestTemplate` or `WebClient`, verify the bean with the corresponding qualifier.

### 13.3. Verify Service IDs Are Not Called with Standard Clients

An integration test should start two mock instances of `inventory-service`, register them with a test discovery source, send multiple requests through the load-balanced client, and confirm URIs resolve to valid instances.

Do not check only that the client bean exists. A bean qualified with `@LoadBalanced` that lacks the Spring Cloud LoadBalancer starter will not have the integration needed to resolve service IDs.

### 13.4. Verify Auto-Registration

If an environment requires disabling auto-registration:

1. Set `spring.cloud.service-registry.auto-registration.enabled=false`.
2. Start the context with the registry integration.
3. Confirm `ServiceRegistry` does not automatically receive the application's registration via the default lifecycle.
4. If the application has a manual registration flow, confirm only that flow performs registration.

Test against a suitable registry test container or mock server; do not use a production registry to test this behavior.

## 14. Common Upgrade Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Registry disappears after removing `@EnableDiscoveryClient` | Discovery starter is missing or disabled | Check runtime classpath and `spring.cloud.discovery.enabled` |
| `DiscoveryClient` exists, but no instances are found | Registry has no registrations or service ID is wrong | Check registration, namespace, and service ID |
| Calling `http://inventory-service` yields a DNS error | Standard client used instead of a load-balanced client | Declare `@LoadBalanced` bean and add LoadBalancer starter |
| Injecting `RestTemplate` reports missing bean | Application has not declared a `RestTemplate` bean | Create a `@Bean` in configuration |
| Injecting builder reports multiple beans of the same type | Both standard and load-balanced builders exist without qualifier/primary | Use `@LoadBalanced` or `@Primary` |
| Client lacks interceptors/observability | Client created with `new` outside `ApplicationContext` | Use the builder bean and Boot customizers/configurers |
| Auto-registration still happens after removing annotation | Annotation previously set `autoRegister=false`, not yet moved to property | Set `spring.cloud.service-registry.auto-registration.enabled=false` |
| `@EnableFeignClients` deleted alongside discovery annotation | Confused two annotations with different functions | Restore the Feign client scanning annotation if using OpenFeign |
| LoadBalancer has no instances | LoadBalancer starter present without an instance source | Add a discovery implementation or configure `SimpleDiscoveryClient` |
| Calling a physical URL via a load-balanced client | Client is marked `@LoadBalanced` even though URL is not a service ID | Use a standard client for physical endpoints |

## 15. Upgrade Completion Checklist

1. Identified a compatible registry implementation and dependency set.
2. Removed `@EnableDiscoveryClient` when used solely to enable discovery.
3. Kept independent enable annotations such as `@EnableFeignClients`.
4. Migrated `autoRegister=false` to properties if needed.
5. Injected `DiscoveryClient` or `ServiceRegistry` via Spring.
6. Removed manual instantiation of discovery implementations in business code.
7. Declared beans for required HTTP clients.
8. Distinguished standard clients from load-balanced clients.
9. Added the LoadBalancer starter if calling by service ID.
10. Placed `@LoadBalanced` and qualifiers properly.
11. Tested auto-configuration without `@EnableDiscoveryClient`.
12. Tested routing to service instances and auto-registration requirements.

## 16. References

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `@EnableDiscoveryClient`, auto-registration, `DiscoveryClient`, `ServiceRegistry`, `RestTemplate`, `RestClient`, and `WebClient`.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): LoadBalancer integration with discovery clients, `RestTemplate`, `RestClient`, and `WebClient`.
- [Spring Cloud Netflix](https://docs.spring.io/spring-cloud-netflix/reference/): Eureka Discovery Client configuration.
- [Spring Cloud Consul](https://docs.spring.io/spring-cloud-consul/reference/): Consul Discovery configuration.

When upgrading, drop the assumption that discovery needs a dedicated enable annotation, but do not drop the HTTP client beans your application actually needs. Dependencies supply the discovery implementation; the Spring container manages the clients; `@LoadBalanced` connects HTTP clients with service discovery and LoadBalancer. When these three responsibilities are clearly separated, business code depends less on concrete implementations and becomes easier to test.
